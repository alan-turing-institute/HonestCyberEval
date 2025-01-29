from operator import itemgetter
from typing import Any, TypeVar

from inspect_ai.model import ChatMessage, ChatMessageUser
from inspect_ai.solver import Generate, TaskState, bridge, solver
from langchain_core.messages import AIMessage, BaseMessage, convert_to_messages
from langchain_core.output_parsers import PydanticOutputParser, PydanticToolsParser
from langchain_core.runnables import RunnableMap, RunnablePassthrough
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

OutputType = TypeVar("OutputType", bound=BaseModel)

T = TypeVar("T")


def as_langchain_chat_history(messages: list[ChatMessage]) -> list[BaseMessage]:
    return convert_to_messages([dict(role=message.role, content=message.text) for message in messages])


@solver
def model_with_structured_output(
    schema: type[OutputType],
):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        from inspect_ai.solver._bridge.patch import openai_request_to_inspect_model

        model = ChatOpenAI(
            model="inspect",
        )
        model_name = state.model
        if model_name == "o1" or model_name == "llama" or model_name == "mockllm":
            llm = model.bind(response_format={"type": "json_object"})
            output_parser = PydanticOutputParser(pydantic_object=schema)
            instructions = output_parser.get_format_instructions()
            state.messages.append(ChatMessageUser(content=instructions))
        else:
            tool_name = convert_to_openai_tool(schema)["function"]["name"]
            llm = model.bind_tools([schema], tool_choice=tool_name, parallel_tool_calls=False)
            output_parser = PydanticToolsParser(
                tools=[schema],
                first_tool_only=True,
                strict=False,
            ).bind(partial=True)
        parser_assign = RunnablePassthrough.assign(
            parsed=itemgetter("raw") | output_parser,
            parsing_error=lambda _: None,
        )
        parser_assign = parser_assign.assign(ai_message=lambda x: AIMessage(content=x["parsed"].model_dump_json()))
        parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
        parser_with_fallback = parser_assign.with_fallbacks([parser_none], exception_key="parsing_error")
        llm = RunnableMap(raw=llm) | parser_with_fallback
        async with openai_request_to_inspect_model():
            result = await llm.ainvoke(as_langchain_chat_history(state.messages))
            state.store.set("result", result)
        return state

    return solve
