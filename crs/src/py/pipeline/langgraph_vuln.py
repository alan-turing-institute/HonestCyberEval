from enum import auto
from strenum import StrEnum
from typing import Literal, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.runnables import Runnable
from langgraph.graph import END, StateGraph

from api.cp import ChallengeProject
from api.fs import write_file_to_scratch
from api.llm import LLMmodel, create_chat_client
from logger import add_prefix_to_logger, logger

logger = add_prefix_to_logger(logger, "Vulnerability Graph")

harness_input_gen_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a coding assistant with expertise in finding bugs and vulnerabilities in {language} program code. 
    Your task is to help the user find vulnerabilities in the code provided by the user.  
    Here is the harness: \n ------- \n {harness_code} \n ------- \n 
    Provide the user with an input to the above harness that would trigger the sanitizer {sanitizer}.
    Ensure any harness input you generate is not too long and that it will result in a valid run. \n 
    Structure your answer so that it only includes the harness input. \n
    Here is the potentially vulnerable code:""",
        ),
        ("placeholder", "{messages}"),
    ]
)


class HarnessInput(BaseModel):
    """Input to test harness that triggers vulnerability"""
    harness_input: str = Field(
        description="Lines of input terminating with newline, including empty lines"
    )


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        error : Most recent exception
        messages : With user question, error messages, reasoning
        solution : Harness input solution
        iterations : Number of tries
        max_iterations : Max number of tries
    """

    model_name: LLMmodel
    project: ChallengeProject
    messages: list
    solution: str
    error: Optional[Exception]
    iterations: int
    max_iterations: int
    harness_id: str
    harness_code: str
    sanitizer_id: str
    sanitizer_str: str
    code_snippet: str
    should_reflect: bool
    harness_input_gen_chain: Runnable


class Nodes(StrEnum):
    GENERATE = auto()
    CHECK_CODE = auto()
    END = auto()
    REFLECT = auto()


def run_vuln_langraph(
        *,
        project: ChallengeProject,
        max_iterations: int,
        model_name: LLMmodel,
        should_reflect: bool = True,
        harness_id: str,
        sanitizer_id: str,
        code_snippet: str,
):
    harness_input_gen_chain = (
            harness_input_gen_prompt | create_chat_client(model_name).with_structured_output(HarnessInput)
    )
    harness_path = project.harnesses[harness_id].file_path
    harness_code = harness_path.read_text().replace('\n', '')

    sanitizer, error_code = project.sanitizers[sanitizer_id]
    sanitizer_str = f"{sanitizer}: {error_code}"

    workflow = StateGraph(GraphState)

    # Define the nodes
    workflow.add_node(Nodes.GENERATE, generate)
    workflow.add_node(Nodes.CHECK_CODE, harness_check)
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
        "project": project,
        "model_name": model_name,
        "messages": [("user", code_snippet)],
        "iterations": 0,
        "error": None,
        "max_iterations": max_iterations,
        "should_reflect": should_reflect,
        "harness_id": harness_id,
        "harness_code": harness_code,
        "sanitizer_id": sanitizer_id,
        "sanitizer_str": sanitizer_str,
        "code_snippet": code_snippet,
        "harness_input_gen_chain": harness_input_gen_chain,
    })


def generate(state: GraphState) -> GraphState:
    logger.debug("Generating harness solution")

    messages = state["messages"]
    iterations = state["iterations"]
    error = state["error"]

    # We have been routed back to generation with an error
    if error:
        messages += [
            (
                "user",
                "Now, try again based on your reflections. Generate another harness input that triggers the sanitizer:",
            )
        ]
    harness_input_solution = state["harness_input_gen_chain"].invoke({
        "harness_code": state["harness_code"],
        "language": state["project"].language,
        "sanitizer": state["sanitizer_str"],
        "messages": [("user", state["code_snippet"])],
    })
    assert type(harness_input_solution) is HarnessInput
    solution = harness_input_solution.harness_input
    messages += [
        (
            "assistant",
            f"{solution}",
        )
    ]

    return GraphState({
        **state,
        "solution": solution,
        "messages": messages,
        "iterations": iterations + 1,
        "error": None,
    })


def harness_check(state: GraphState) -> GraphState:
    logger.debug("Checking Harness Input")

    project = state["project"]
    harness_id = state["harness_id"]
    sanitizer_id = state["sanitizer_id"]

    # Check harness input
    try:
        harness_input_file = write_harness_input_to_disk(project, state["solution"], state["iterations"], harness_id, sanitizer_id, state["model_name"])
        has_sanitizer_triggered, stderr = project.run_harness_and_check_sanitizer(
            harness_input_file,
            harness_id,
            sanitizer_id,
        )
        if not has_sanitizer_triggered:
            raise Exception(f"The sanitizer was not triggered. Instead, this was the sanitizer output: {stderr}")
    except Exception as error:
        logger.debug("Harness input check: Failed")
        return GraphState({
            **state,
            "messages": state["messages"] + [("user", f"Your solution failed: {error}")],
            "error": error,
        })

    logger.debug("Harness input check: Passed")
    return state


def reflect(state: GraphState) -> GraphState:
    logger.debug("Generating harness input reflection")

    messages = state["messages"]

    # Add reflection
    reflections = state["harness_input_gen_chain"].invoke({
        "harness_code": state["harness_code"],
        "language": state["project"].language,
        "sanitizer": state["sanitizer_str"],
        "messages": messages,
    })
    messages += [("assistant", f"Here are reflections on the error: {reflections}")]
    return GraphState({
        **state,
        "messages": messages,
        "error": None,
    })


def decide_to_finish(state: GraphState) -> Literal[Nodes.END, Nodes.REFLECT, Nodes.GENERATE]:
    if (not state["error"]) or state["iterations"] == state["max_iterations"]:
        logger.debug("Decision: Finish")
        return Nodes.END
    else:
        logger.debug("Decision: re-try solution")
        if state["should_reflect"]:
            return Nodes.REFLECT
        else:
            return Nodes.GENERATE


def write_harness_input_to_disk(
        project: ChallengeProject,
        harness_input: str,
        i: int | str,
        harness_id: str,
        sanitizer_id: str,
        model_name: LLMmodel | Literal['mock']
):
    return write_file_to_scratch(
        project.input_path / f"harness_{harness_id}_sanitizer_{sanitizer_id}_{model_name}_{i}.blob",
        harness_input,
    )
