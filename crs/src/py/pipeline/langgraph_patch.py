import difflib
from enum import auto

from langchain_core.runnables import Runnable
from strenum import StrEnum
from typing import TypedDict, Literal, Optional

from api.cp import ChallengeProject
from api.data_types import Patch, VulnerabilityWithSha
from api.fs import PatchException, write_file_to_scratch
from api.llm import create_chat_client, LLMmodel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langgraph.graph import END, StateGraph

from api.submit import CPVuuid
from logger import add_prefix_to_logger, logger

logger = add_prefix_to_logger(logger, "Patching Graph")


class HarnessTriggeredAfterPatchException(PatchException):
    message = "The patch does not solve the error"

    def __init__(self, stderr, patch, vuln):
        super().__init__(stderr, patch=patch)
        self.vuln = vuln

    def __str__(self):
        return "\n".join(
            [
                super().__str__(),
                f"Harness {self.vuln.harness_id} with input:",
                str(self.vuln.input_file.absolute()),
                self.vuln.input_data,
                f"still triggers sanitizer {self.vuln.sanitizer_id}",
            ]
        )


class TestFailedException(PatchException):
    message = "Test failed; the patch removed functionality"


def patched_to_diff(vuln_code, patched_file, bad_file_name):
    diff_obj = difflib.unified_diff(
        vuln_code.splitlines(True),
        patched_file.splitlines(True),
        fromfile=bad_file_name,
        tofile=bad_file_name,
        lineterm='\n',
        n=3,
    )
    patch_text = "".join(diff_obj) + "\n"
    return patch_text


patch_gen_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a coding assistant with expertise in fixing bugs and vulnerabilities in {language} program code. 
    The code provided by the user has a {sanitizer} vulnerability.
    Your task is to write a patched version of the code provided by the user. 
    The patched file should fix the vulnerability and maintain the code functionality.
    The first line of the code should not be 'c'. 
    Here is the vulnerable code:""",
        ),
        ("placeholder", "{messages}"),
    ]
)


class PatchedFile(BaseModel):
    """Input to test harness that triggers vulnerability"""
    file: str = Field(
        description="A program file that does not include a vulnerability"
    )


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        error : Last exception to occur
        messages : With user question, error messages, reasoning
        patched_file : Harness input solution
        iterations : Number of tries
    """
    model_name: LLMmodel
    project: ChallengeProject
    cp_source: str
    cpv_uuid: CPVuuid
    vulnerability: VulnerabilityWithSha
    vuln_code: str
    bad_file: str
    sanitizer_str: str
    patch_gen_chain: Runnable
    should_reflect: bool
    error: Optional[Exception]
    messages: list
    patched_file: str
    iterations: int
    max_iterations: int


class Nodes(StrEnum):
    GENERATE = auto()
    CHECK_CODE = auto()
    END = auto()
    REFLECT = auto()


def run_patch_langraph(
        *,
        model_name: LLMmodel,
        project: ChallengeProject,
        cp_source: str,
        cpv_uuid: CPVuuid,
        vulnerability: VulnerabilityWithSha,
        vuln_code: str,
        bad_file: str,
        max_iterations: int,
        should_reflect: bool = True
):

    sanitizer, error_code = project.sanitizers[vulnerability.sanitizer_id]
    sanitizer_str = f"{sanitizer}: {error_code}"

    patch_gen_chain = (
            patch_gen_prompt | create_chat_client(model_name).with_structured_output(PatchedFile)
    )

    workflow = StateGraph(GraphState)

    # Define the nodes
    workflow.add_node(Nodes.GENERATE, generate)
    workflow.add_node(Nodes.CHECK_CODE, patch_check)
    workflow.add_node(Nodes.REFLECT, reflect)

    # Build graph
    workflow.set_entry_point(Nodes.GENERATE)
    workflow.add_edge(Nodes.GENERATE, Nodes.CHECK_CODE)
    workflow.add_conditional_edges(
        Nodes.CHECK_CODE,
        decide_to_finish,
        {
            Nodes.END: END,
            Nodes.REFLECT: Nodes.REFLECT,
            Nodes.GENERATE: Nodes.GENERATE,
        },
    )
    workflow.add_edge(Nodes.REFLECT, Nodes.GENERATE)
    vuln_app = workflow.compile()

    return vuln_app.invoke({
        "model_name": model_name,
        "project": project,
        "cp_source": cp_source,
        "cpv_uuid": cpv_uuid,
        "vulnerability": vulnerability,
        "vuln_code": vuln_code,
        "bad_file": bad_file,
        "sanitizer_str": sanitizer_str,
        "patch_gen_chain": patch_gen_chain,
        "messages": [("user", vuln_code)],
        "iterations": 0,
        "max_iterations": max_iterations,
        "should_reflect": should_reflect,
    })

def generate(state: GraphState) -> GraphState:
    logger.debug("Generating patch")

    messages = state["messages"]

    # We have been routed back to generation with an error
    if state["error"]:
        messages += [
            (
                "user",
                "Now, try again based on your reflections. Generate another patch that fixes the code:",
            )
        ]

    patch_solution = state["patch_gen_chain"].invoke({
        "language": state["project"].language,
        "sanitizer": state["sanitizer_str"],
        "messages": [("user", state["vuln_code"])]
    })

    assert type(patch_solution) is PatchedFile
    patched_file = patch_solution.file

    messages += [
        (
            "assistant",
            f"{patched_file}",
        )
    ]

    return GraphState({
        **state,
        "patched_file": patched_file,
        "messages": messages,
        "iterations": state["iterations"] + 1,
    })

def patch_check(state: GraphState) -> GraphState:
    logger.debug("Checking patch")

    vulnerability = state["vulnerability"]

    # convert to diff
    patch_text = patched_to_diff(state["vuln_code"], state["patched_file"], state["bad_file"])

    # Check patch
    try:
        patch_path = write_patch_to_disk(state["project"], state["cpv_uuid"], patch_text, state["iterations"], vulnerability, state["model_name"])
        patch = Patch(diff=patch_text, diff_file=patch_path)
        validate_patch(state["project"], state["cp_source"], vulnerability, patch)
    except Exception as error:
        logger.debug("Patch check: Failed")
        return GraphState({
            **state,
            "messages": state["messages"] + [("user", f"Your solution failed: {error}")],
            "error": error,
        })

    logger.debug("Patch check: Passed")
    return GraphState({
        **state,
        "error": None,
    })

def reflect(state: GraphState) -> GraphState:
    logger.debug("Generating patch reflections")

    messages = state["messages"]

    reflections = state["patch_gen_chain"].invoke({
        "language": state["project"].language,
        "sanitizer": state["sanitizer_str"],
        "messages": messages
    })

    return GraphState({
        **state,
        "messages": messages + [("assistant", f"Here are reflections on the error: {reflections}")],
        "error": None,
    })


def decide_to_finish(state: GraphState) -> Literal[Nodes.END, Nodes.REFLECT, Nodes.GENERATE]:
    if (not state["error"]) or state["iterations"] == state["max_iterations"]:
        logger.debug("Decision: Finish")
        return Nodes.END
    else:
        logger.debug("Decision: Re-try solution")
        if state["should_reflect"]:
            return Nodes.REFLECT
        return Nodes.GENERATE


def validate_patch(project: ChallengeProject, cp_source: str, vuln: VulnerabilityWithSha, patch: Patch):
    logger.info("Re-building CP with patch")
    try:
        project.patch_and_build_project(patch, cp_source)
    finally:
        project.reset_source_repo(cp_source)

    has_sanitizer_triggered, stderr = project.run_harness_and_check_sanitizer(
        vuln.input_file,
        vuln.harness_id,
        vuln.sanitizer_id,
    )
    if has_sanitizer_triggered:
        raise HarnessTriggeredAfterPatchException(
            stderr=stderr,
            vuln=vuln,
            patch=patch,
        )

    result = project.run_tests()
    if result.stderr:
        raise TestFailedException(
            stderr=result.stderr,
            patch=patch,
        )


def write_patch_to_disk(
        project: ChallengeProject,
        cpv_uuid: str,
        patch_text: str,
        i: int | str,
        vulnerability: VulnerabilityWithSha,
        model_name: LLMmodel | Literal['mock']
):
    return write_file_to_scratch(
        project.patch_path / f"{cpv_uuid}_{i}_harness_{vulnerability.harness_id}_sanitizer_{vulnerability.sanitizer_id}_{model_name}.diff",
        patch_text,
    )
