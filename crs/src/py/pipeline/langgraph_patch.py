import difflib
from enum import auto
from typing import Literal, Optional, TypedDict

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.graph import CompiledGraph
from params import BACKUP_MODEL_GEMINI, MAX_ALLOWED_HISTORY_CHARS, NUM_MESSAGES_PER_ROUND
from strenum import StrEnum

from api.cp import ChallengeProject
from api.data_types import Patch, VulnerabilityWithSha
from api.fs import PatchException, write_patch_to_disk
from api.llm import (
    ErrorHandler,
    LLMmodel,
    add_structured_output,
    create_chat_client,
    fix_anthropic_weirdness,
    placeholder_fix_anthropic_weirdness,
)
from api.submit import CPVuuid
from logger import add_prefix_to_logger, logger

logger = add_prefix_to_logger(logger, "Patching Graph")


class HarnessTriggeredAfterPatchException(PatchException):
    message = "The patch does not solve the error"

    def __init__(self, stderr, patch, vuln):
        super().__init__(stderr, patch=patch)
        self.vuln = vuln

    def __str__(self):
        return "\n".join([
            super().__str__(),
            f"Harness {self.vuln.harness_id} with input:",
            str(self.vuln.input_file.absolute()),
            self.vuln.input_data,
            f"still triggers sanitizer {self.vuln.sanitizer_id}",
        ])


class TestFailedException(PatchException):
    message = "Test failed; the patch removed functionality"


patch_gen_prompt = ChatPromptTemplate.from_messages([
    placeholder_fix_anthropic_weirdness,
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
    ("user", "{question}"),
])


class PatchedFile(BaseModel):
    """File patched by LLM"""

    file: str = Field(description="A program file that does not include a vulnerability")

    def __str__(self):
        return self.file


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        error : Last exception to occur
        messages : With user question, error messages, reasoning
        patched_file : File after LLM patch
        iterations : Number of tries
    """

    model: ChatOpenAI
    project: ChallengeProject
    chat_history: ChatMessageHistory
    cpv_uuid: CPVuuid
    vulnerability: VulnerabilityWithSha
    vuln_code: str
    bad_file: str
    sanitizer_str: str
    should_reflect: bool
    error: Optional[Exception]
    messages: list
    patched_file: str
    iterations: int
    max_iterations: int


class Nodes(StrEnum):
    GENERATE = auto()
    CHECK_CODE = auto()
    REFLECT = auto()
    END = END


def patched_file_to_diff(vuln_code, patched_file, bad_file_name):
    diff_obj = difflib.unified_diff(
        vuln_code.splitlines(True),
        patched_file.splitlines(True),
        fromfile=bad_file_name,
        tofile=bad_file_name,
        lineterm="\n",
        n=3,
    )
    patch_text = "".join(diff_obj) + "\n"
    return patch_text


async def apply_patch_and_check(project: ChallengeProject, vuln: VulnerabilityWithSha, patch: Patch):
    # only one patch should be applied and building at any one time
    async with project.build_lock:
        logger.info("Re-building CP with patch")
        try:
            await project.patch_and_build_project(patch, vuln.cp_source)
        finally:
            project.reset_source_repo(vuln.cp_source)

        has_sanitizer_triggered, stderr = await project.run_harness_and_check_sanitizer(
            vuln.input_file,
            vuln.harness_id,
            vuln.sanitizer_id,
            timeout=True,
        )
        if has_sanitizer_triggered:
            raise HarnessTriggeredAfterPatchException(
                stderr=stderr,
                vuln=vuln,
                patch=patch,
            )

        stderr = await project.run_tests()
        if stderr:
            raise TestFailedException(
                stderr=stderr,
                patch=patch,
            )


# Nodes
async def generate(state: GraphState) -> GraphState:
    logger.info("Generating patch")

    chat_history = state["chat_history"]
    error = state["error"]

    question = state["vuln_code"]
    model = state["model"]

    # We have been routed back to generation with an error
    if error:
        if state["should_reflect"]:
            question = """Try again using the information from your messages and your previous patches.
             Generate another patch that fixes the code.
             """
        else:
            question = f"""The previous solution produced: \n {error}
                        Generate another patch that fixes the code."""

    # prune chat history
    logger.debug(f"Chat history length [chars]: {len(state['chat_history'].__str__())}")
    if state["iterations"] > 1 and len(state["chat_history"].__str__()) > MAX_ALLOWED_HISTORY_CHARS:
        logger.debug("Had to unfortunately prune chat history!")
        old_messages = state["chat_history"].messages
        state["chat_history"].clear()
        state["chat_history"].add_messages([old_messages[0]] + old_messages[-NUM_MESSAGES_PER_ROUND:])

    patch_gen_chain = RunnableWithMessageHistory(
        patch_gen_prompt
        | add_structured_output(  # type: ignore  # types around with_structured_output are a mess
            model,
            PatchedFile,
            BACKUP_MODEL_GEMINI,
        ),
        lambda _: chat_history,
        output_messages_key="ai_message",
        input_messages_key="question",
        history_messages_key="messages",
    )

    e_handler = ErrorHandler()
    while e_handler.ok_to_retry():
        try:
            output = await patch_gen_chain.ainvoke(
                {
                    "language": state["project"].language,
                    "sanitizer": state["sanitizer_str"],
                    "question": question,
                    **fix_anthropic_weirdness(model),
                },
                {"configurable": {"session_id": "unused"}},
            )
        except Exception as e:
            await e_handler.exception_caught(e)
        else:
            patch_solution = output["parsed"]
            try:
                assert type(patch_solution) is PatchedFile
            except AssertionError:
                error = output["parsing_error"]
                ai_message = output["raw"]
                raise Exception(f"Output not present\n{error}\n{repr(ai_message)}")
            else:
                patched_file = patch_solution.file

                return GraphState(**{
                    **state,
                    "patched_file": patched_file,
                    "iterations": state["iterations"] + 1,
                    "error": None,
                })
    else:
        e_handler.raise_exception()


async def check_patch(state: GraphState) -> GraphState:
    logger.info("Checking patch")

    vulnerability = state["vulnerability"]
    model_name: LLMmodel = state["model"].model_name  # type: ignore  # we know it's one of the models...

    patch_text = patched_file_to_diff(state["vuln_code"], state["patched_file"], state["bad_file"])

    patch_path = write_patch_to_disk(
        state["project"], state["cpv_uuid"], patch_text, state["iterations"], vulnerability, model_name
    )
    patch = Patch(diff=patch_text, diff_file=patch_path)

    try:
        await apply_patch_and_check(state["project"], vulnerability, patch)
    except Exception as error:
        logger.info("Patch check: Failed")
        return GraphState(**{
            **state,
            "error": error,
        })

    logger.info("Patch check: Passed")
    return GraphState(**{
        **state,
        "error": None,
    })


async def reflect(state: GraphState) -> GraphState:
    logger.info("Generating patch reflections")

    model = state["model"]
    reflection_chain = RunnableWithMessageHistory(
        patch_gen_prompt | model,  # type: ignore  # types around with_structured_output are a mess
        lambda _: state["chat_history"],
        input_messages_key="question",
        history_messages_key="messages",
    )

    question = """Analyse your previous attempt, be critical.
         Provide insight that could help you produce a fix for the vulnerability.
         Do not provide new input, only reflect on your previous input."""

    await reflection_chain.ainvoke(
        {
            "language": state["project"].language,
            "sanitizer": state["sanitizer_str"],
            "question": question,
            **fix_anthropic_weirdness(model),
        },
        {"configurable": {"session_id": "unused"}},
    )

    return state


# Branches
def check_if_finished(state: GraphState) -> Literal[Nodes.END, Nodes.REFLECT, Nodes.GENERATE]:
    if (not state["error"]) or state["iterations"] == state["max_iterations"]:
        logger.info("Decision: Finish")
        return Nodes.END
    else:
        logger.info("Decision: Re-try solution")
        if state["should_reflect"]:
            return Nodes.REFLECT
        return Nodes.GENERATE


# Setup
__workflows: dict[str, CompiledGraph] = dict()


def make_workflow(key: str = "default") -> CompiledGraph:
    try:
        return __workflows[key]
    except KeyError:
        match key:
            case "default":
                workflow = StateGraph(GraphState)
                workflow.add_node(Nodes.GENERATE, generate)
                workflow.add_node(Nodes.CHECK_CODE, check_patch)
                workflow.add_node(Nodes.REFLECT, reflect)
                workflow.add_edge(START, Nodes.GENERATE)
                workflow.add_edge(Nodes.GENERATE, Nodes.CHECK_CODE)
                workflow.add_conditional_edges(Nodes.CHECK_CODE, check_if_finished)
                workflow.add_edge(Nodes.REFLECT, Nodes.GENERATE)
                __workflows[key] = workflow.compile()
        return __workflows[key]


async def run_patch_langraph(
    *,
    model_name: LLMmodel,
    project: ChallengeProject,
    cpv_uuid: CPVuuid,
    vulnerability: VulnerabilityWithSha,
    vuln_code: str,
    bad_file: str,
    max_iterations: int,
    should_reflect: bool = True,
):
    sanitizer, error_code = project.sanitizers[vulnerability.sanitizer_id]
    sanitizer_str = f"{sanitizer}: {error_code}"

    model = create_chat_client(model_name)
    chat_history = ChatMessageHistory()
    workflow = make_workflow()

    return await workflow.ainvoke(
        GraphState(**{
            "model": model,
            "project": project,
            "chat_history": chat_history,
            "cpv_uuid": cpv_uuid,
            "vulnerability": vulnerability,
            "vuln_code": vuln_code,
            "bad_file": bad_file,
            "sanitizer_str": sanitizer_str,
            "messages": [("user", vuln_code)],
            "iterations": 0,
            "max_iterations": max_iterations,
            "should_reflect": should_reflect,
        })
    )
