import functools
from operator import itemgetter
from typing import Literal, Type, TypeAlias, TypeVar

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnableMap, RunnablePassthrough
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from config import AIXCC_LITELLM_HOSTNAME, LITELLM_KEY
from params import MAX_CHAT_CLIENT_RETRIES

from .error_handler import ErrorHandler as ErrorHandler

LLMmodel: TypeAlias = Literal[
    # OpenAI
    "oai-gpt-3.5-turbo",
    "oai-gpt-3.5-turbo-16k",
    "oai-gpt-4",
    "oai-gpt-4-turbo",
    "oai-gpt-4o",
    "o1-preview",
    "o1-mini",
    # Anthropic
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "claude-3.5-sonnet",
    # Google
    "gemini-1.0-pro",
    "gemini-1.5-pro",
    # Azure OpenAI
    "azure-gpt-3.5-turbo",
    "azure-gpt-3.5-turbo-16k",
    "azure-gpt-4o",
]


def create_chat_client(model_name: LLMmodel) -> ChatOpenAI:
    model = ChatOpenAI(
        model=model_name,
        api_key=LITELLM_KEY,
        base_url=AIXCC_LITELLM_HOSTNAME,
        max_retries=MAX_CHAT_CLIENT_RETRIES,
    )
    return model


OutputType = TypeVar("OutputType", bound=BaseModel)

T = TypeVar("T")


def add_structured_output(
    model: ChatOpenAI,
    schema: Type[OutputType],
):
    if is_o1(model):

        def parse_output(output):
            output = output.split("```")
            if len(output) > 1:
                output = output[1]
            else:
                output = output[0]
            output = output.lstrip("plaintext").encode().decode("unicode_escape")
            return schema(harness_input=output)

        model_with_tools = model
        output_parser = StrOutputParser() | RunnableLambda(parse_output)
        parser_assign = RunnablePassthrough.assign(
            parsed=itemgetter("raw") | output_parser,
            parsing_error=lambda _: None,
        )
        parser_assign = parser_assign.assign(
            ai_message=itemgetter("raw"),
        )
        parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
        parser_with_fallback = parser_assign.with_fallbacks([parser_none], exception_key="parsing_error")
        return RunnableMap(raw=model_with_tools) | parser_with_fallback
    elif is_gemini(model):
        return model.with_structured_output(schema=schema, method="json_mode", include_raw=True)
    return model.with_structured_output(schema=schema, include_raw=True)


def format_chat_history(chat_history: ChatMessageHistory) -> str:
    return "\n".join(map(lambda x: x.pretty_repr(), chat_history.messages))


def is_kind(models: list[LLMmodel], model: ChatOpenAI | LLMmodel) -> bool:
    if type(model) is ChatOpenAI:
        return model.model_name in models
    return model in models


is_gemini = functools.partial(
    is_kind,
    [
        "gemini-1.0-pro",
        "gemini-1.5-pro",
    ],
)

is_o1 = functools.partial(
    is_kind,
    [
        "o1-preview",
        "o1-mini",
    ],
)

is_anthropic = functools.partial(
    is_kind,
    [
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
        "claude-3.5-sonnet",
    ],
)
