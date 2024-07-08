import functools
from operator import itemgetter
from typing import Literal, Optional, Type, TypeAlias, TypeVar

from langchain.output_parsers import OutputFixingParser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.pydantic_v1 import BaseModel, SecretStr
from langchain_core.runnables import RunnableMap, RunnablePassthrough
from langchain_openai import ChatOpenAI

from config import AIXCC_LITELLM_HOSTNAME, LITELLM_KEY

LLMmodel: TypeAlias = Literal[
    # OpenAI
    "oai-gpt-3.5-turbo",
    "oai-gpt-3.5-turbo-16k",
    "oai-gpt-4",
    "oai-gpt-4-turbo",
    "oai-gpt-4o",
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

EmbeddingModel: TypeAlias = Literal[
    # OpenAI
    "oai-text-embedding-3-large",
    "oai-text-embedding-3-small",
    # Google
    "textembedding-gecko",
]


def create_chat_client(model_name: LLMmodel) -> ChatOpenAI:
    model = ChatOpenAI(
        model=model_name,
        api_key=SecretStr(LITELLM_KEY),
        base_url=AIXCC_LITELLM_HOSTNAME,
        max_retries=1,
    )
    return model


OutputType = TypeVar("OutputType", bound=BaseModel)


def add_structured_output(
    model: ChatOpenAI, schema: Type[OutputType], backup_model_gemini: Optional[ChatOpenAI | LLMmodel] = None
):
    if is_gemini(model):
        model_with_tools = model.bind(response_format={"type": "json_object"})
        output_parser = PydanticOutputParser(pydantic_object=schema)

        if backup_model_gemini:
            if not isinstance(backup_model_gemini, ChatOpenAI):
                backup_model_gemini = create_chat_client(backup_model_gemini)
            output_parser = OutputFixingParser.from_llm(parser=output_parser, llm=backup_model_gemini)
    else:
        model_with_tools = model.bind_tools([schema], tool_choice=True)
        output_parser = PydanticToolsParser(tools=[schema], first_tool_only=True)
    parser_assign = RunnablePassthrough.assign(
        parsed=itemgetter("raw") | output_parser,
        parsing_error=lambda _: None,
    )
    parser_assign = parser_assign.assign(
        ai_message=itemgetter("raw") if is_gemini(model) else lambda x: AIMessage(content=str(x["parsed"])),
    )
    parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
    parser_with_fallback = parser_assign.with_fallbacks([parser_none], exception_key="parsing_error")
    return RunnableMap(raw=model_with_tools) | parser_with_fallback


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

is_anthropic = functools.partial(
    is_kind,
    [
        "claude-3-opus",
        "claude-3-sonnet",
        "claude-3-haiku",
        "claude-3.5-sonnet",
    ],
)


def fix_anthropic_weirdness(model: ChatOpenAI | LLMmodel) -> dict[str, list[tuple[str, str]]]:
    """
    To be used with placeholder_anthropic_weirdness.
    Place placeholder_fix_anthropic_weirdness in the prompt template like:

        ChatPromptTemplate.from_messages([
            placeholder_fix_anthropic_weirdness,
            ...,
        ])

    Then, when invoking the chain, pass **fix_anthropic_weirdness(model) in the invoke call:

        await chain.ainvoke({
            ...,
            **fix_anthropic_weirdness(model),
        })

    """
    return {"anthropic_weirdness": [("user", ".")] if is_anthropic(model) else []}


placeholder_fix_anthropic_weirdness = ("placeholder", "{anthropic_weirdness}")
