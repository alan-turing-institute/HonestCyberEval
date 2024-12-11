from enum import StrEnum, auto
from logging import Logger
from typing import Literal, Optional, TypedDict

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from langgraph import graph
from pydantic import AliasChoices, BaseModel, Field

from api.cp import ChallengeProject
from api.fs import write_harness_input_to_disk
from api.llm import ErrorHandler, LLMmodel, add_structured_output, create_chat_client
from params import MAX_ALLOWED_HISTORY_CHARS, NUM_MESSAGES_PER_ROUND

__all__ = [
    "run_vuln_graph",
]

harness_input_gen_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a coding assistant with expertise in finding bugs and vulnerabilities in {language} program code.
    Your task is to help the user find vulnerabilities in the code provided by the user. 
    Your output will help the user in patching those vulnerabilities. 
    Here is the harness: \n ------- \n {harness_code} \n ------- \n
    Provide the user with an input to the above harness that would trigger the sanitizer {sanitizer}.
    Ensure any harness input you generate is not too long and that it will result in a valid run. \n
    Structure your answer so that it only includes the harness input. \n
    Here is the potentially vulnerable code:""",
    ),
    ("placeholder", "{messages}"),
    ("user", "{question}"),
])


class HarnessInput(BaseModel):
    """Input to test harness that triggers vulnerability"""

    input: str = Field(
        description="Lines of input terminating with newline, including empty lines",
        validation_alias=AliasChoices("harness_input", "input"),
    )

    def __str__(self):
        return self.input


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        error : Most recent exception
        chat_history : With user question, error messages, reasoning
        solution : Harness input solution
        iterations : Number of tries
        max_iterations : Max number of tries
    """

    model: ChatOpenAI
    project: ChallengeProject
    chat_history: ChatMessageHistory
    solution: str
    error: Optional[Exception]
    iterations: int
    max_iterations: int
    harness_id: str
    harness_code: str
    sanitizer_id: str
    sanitizer_str: str
    code_snippet: str
    model: ChatOpenAI
    logger: Logger


class Nodes(StrEnum):
    GENERATE = auto()
    RUN_HARNESS = auto()
    REFLECT = auto()
    END = graph.END
    START = graph.START


# Nodes


async def generate(state: GraphState) -> GraphState:
    state["logger"].info("Generating harness solution")

    error = state["error"]
    question = state["code_snippet"]
    model = state["model"]

    # We have been routed back to generation with an error
    if error:
        question = """Try again using the information from your messages and your previous inputs.
         Generate another harness input that triggers the sanitizer in the code.
         Do NOT offer an explanation, only provide the input.
         """

    # prune chat history
    state["logger"].debug(f"Chat history length [chars]: {len(state['chat_history'].__str__())}")
    if state["iterations"] > 1 and len(state["chat_history"].__str__()) > MAX_ALLOWED_HISTORY_CHARS:
        state["logger"].debug("Had to unfortunately prune chat history!")
        old_messages = state["chat_history"].messages
        state["chat_history"].clear()
        state["chat_history"].add_messages([old_messages[0]] + old_messages[-NUM_MESSAGES_PER_ROUND:])

    harness_input_gen_chain = RunnableWithMessageHistory(
        harness_input_gen_prompt
        | add_structured_output(  # type: ignore  # types around with_structured_output are a mess
            model,
            HarnessInput,
        ),
        lambda _: state["chat_history"],
        output_messages_key="ai_message",
        input_messages_key="question",
        history_messages_key="messages",
    )

    e_handler = ErrorHandler()
    while e_handler.ok_to_retry():
        try:
            output = await harness_input_gen_chain.ainvoke(
                {
                    "harness_code": state["harness_code"],
                    "language": state["project"].language,
                    "sanitizer": state["sanitizer_str"],
                    "question": question,
                },
                {"configurable": {"session_id": "unused"}},
            )
        except Exception as e:
            await e_handler.exception_caught(e)
        else:
            harness_input_solution = output["parsed"]
            try:
                assert type(harness_input_solution) is HarnessInput
            except AssertionError:
                error = output["parsing_error"]
                ai_message = output["raw"]
                raise Exception(f"Output not present\n{error}\n{repr(ai_message)}")
            else:
                solution = harness_input_solution.input
                state["logger"].warning("solution:\n" + solution)
                return GraphState(**{
                    **state,
                    "solution": solution,
                    "iterations": state["iterations"] + 1,
                    "error": None,
                })
    else:
        e_handler.raise_exception()


async def run_harness(state: GraphState) -> GraphState:
    state["logger"].info("Checking harness input")

    project = state["project"]
    harness_id = state["harness_id"]
    sanitizer_id = state["sanitizer_id"]
    model_name: LLMmodel = state["model"].model_name  # type: ignore  # we know it's one of the models...

    harness_input_file = write_harness_input_to_disk(
        project,
        state["solution"],
        state["iterations"],
        harness_id,
        sanitizer_id,
        model_name,
    )

    try:
        has_sanitizer_triggered, stderr = await project.run_harness_and_check_sanitizer(
            harness_input_file,
            harness_id,
            sanitizer_id,
        )
        if not has_sanitizer_triggered:
            raise Exception(
                f"The correct sanitizer {state['sanitizer_str']} was not triggered. Instead, this was the"
                f" output: {stderr}"
            )
    except Exception as error:
        state["logger"].info("Harness input check: Failed")
        state["chat_history"].add_user_message(f"Your solution failed. Here is the output: {error}")
        return GraphState(**{
            **state,
            "error": error,
        })

    state["logger"].info("Harness input check: Passed")
    return state


async def reflect(state: GraphState) -> GraphState:
    state["logger"].info("Generating harness input reflection")

    model = state["model"]
    reflection_chain = RunnableWithMessageHistory(
        harness_input_gen_prompt | model,  # type: ignore  # types around with_structured_output are a mess
        lambda _: state["chat_history"],
        input_messages_key="question",
        history_messages_key="messages",
    )

    question = """Analyse your previous attempt, be critical.
     Provide insight that could help you produce output that does produce the error.
     Do not provide new input, only reflect on your previous input."""
    await reflection_chain.ainvoke(
        {
            "harness_code": state["harness_code"],
            "language": state["project"].language,
            "sanitizer": state["sanitizer_str"],
            "question": question,
        },
        {"configurable": {"session_id": "unused"}},
    )
    return state


# Branches
def check_if_finished(
    state: GraphState,
) -> Literal[Nodes.END, Nodes.REFLECT, Nodes.GENERATE]:
    if (not state["error"]) or state["iterations"] == state["max_iterations"]:
        state["logger"].info("Decision: Finish")
        return Nodes.END

    state["logger"].info("Decision: re-try solution")
    return Nodes.REFLECT


# Setup
def make_workflow():
    workflow = graph.StateGraph(GraphState)
    workflow.add_node(Nodes.GENERATE, generate)
    workflow.add_node(Nodes.RUN_HARNESS, run_harness)
    workflow.add_node(Nodes.REFLECT, reflect)
    workflow.add_edge(Nodes.START, Nodes.GENERATE)
    workflow.add_edge(Nodes.GENERATE, Nodes.RUN_HARNESS)
    workflow.add_conditional_edges(Nodes.RUN_HARNESS, check_if_finished)
    workflow.add_edge(Nodes.REFLECT, Nodes.GENERATE)
    return workflow.compile()


async def run_vuln_graph(
    *,
    project: ChallengeProject,
    max_iterations: int,
    model_name: LLMmodel,
    harness_id: str,
    sanitizer_id: str,
    code_snippet: str,
):
    from logger import add_prefix_to_logger, logger

    logger = add_prefix_to_logger(logger, f"Vulnerability Graph - <{model_name}>")
    harness_path = project.harnesses[harness_id].file_path
    harness_code = harness_path.read_text().replace("\n", "")

    sanitizer, error_code = project.sanitizers[sanitizer_id]
    sanitizer_str = f"{sanitizer}: {error_code}"

    model = create_chat_client(model_name)
    chat_history = ChatMessageHistory()
    workflow = make_workflow()

    return await workflow.ainvoke(
        GraphState(**{
            "model": model,
            "project": project,
            "chat_history": chat_history,
            "solution": "",
            "iterations": 0,
            "error": None,
            "max_iterations": max_iterations,
            "harness_id": harness_id,
            "harness_code": harness_code,
            "sanitizer_id": sanitizer_id,
            "sanitizer_str": sanitizer_str,
            "code_snippet": code_snippet,
            "logger": logger,
        })
    )
