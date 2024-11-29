import functools
from operator import itemgetter
from typing import Literal, Optional, Type, TypeAlias, TypeVar

from langchain.output_parsers import OutputFixingParser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.output_parsers.openai_tools import PydanticToolsParser
from langchain_core.prompts import BasePromptTemplate, PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, SecretStr
from langchain_core.runnables import RunnableLambda, RunnableMap, RunnablePassthrough
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai import ChatOpenAI

from config import AIXCC_LITELLM_HOSTNAME, LITELLM_KEY
from params import MAX_BACKUP_LLM_RETRIES, MAX_CHAT_CLIENT_RETRIES

from .error_handler import ErrorHandler as ErrorHandler

input_fixing_prompt = PromptTemplate.from_template(
    """Instructions:
--------------
{instructions}
--------------
Completion:
--------------
{completion}
--------------

Above, the Completion did not satisfy the constraints given in the Instructions.
Error:
--------------
{error}
--------------

Please try again. Please only respond with an answer that satisfies the constraints laid out in the Instructions:"""
)

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
        api_key=SecretStr(LITELLM_KEY),
        base_url=AIXCC_LITELLM_HOSTNAME,
        max_retries=MAX_CHAT_CLIENT_RETRIES,
    )
    return model


OutputType = TypeVar("OutputType", bound=BaseModel)

T = TypeVar("T")


# the langchain one is actually broken...
class CustomOutputFixingParser(OutputFixingParser[T]):
    @classmethod
    def from_llm_with_structured_output(
        cls,
        llm: ChatOpenAI,
        schema,
        parser: PydanticOutputParser,
        prompt: BasePromptTemplate = input_fixing_prompt,
        max_retries: int = MAX_BACKUP_LLM_RETRIES,
    ) -> OutputFixingParser[T]:
        chain = prompt | add_structured_output(llm, schema)
        return cls(parser=parser, retry_chain=chain, max_retries=max_retries)

    def parse(self, completion):  # type: ignore
        retries = 0

        try:
            return self.parser.parse(completion)
        except OutputParserException as e:
            error = e
            while retries <= self.max_retries:
                retries += 1
                result = self.retry_chain.invoke({
                    "instructions": self.parser.get_format_instructions(),
                    "completion": completion,
                    "error": repr(error),
                })

                error = result["parsing_error"]
                if not result["parsing_error"]:
                    return result["parsed"]
            else:
                raise error

    async def aparse(self, completion):  # type: ignore
        retries = 0

        try:
            return await self.parser.aparse(completion)
        except OutputParserException as e:
            error = e
            while retries <= self.max_retries:
                retries += 1
                result = await self.retry_chain.ainvoke({
                    "instructions": self.parser.get_format_instructions(),
                    "completion": completion,
                    "error": repr(error),
                })

                error = result["parsing_error"]
                if not result["parsing_error"]:
                    return result["parsed"]
            else:
                raise error


class PydanticToolsParser2(PydanticToolsParser):
    def parse_result(self, parse_result, *, partial: bool = True):
        return super().parse_result(parse_result, partial=True)


def add_structured_output(
    model: ChatOpenAI,
    schema: Type[OutputType],
    backup_model_gemini: Optional[ChatOpenAI | LLMmodel] = None,
):
    if is_o1(model):

        def parse_output(output):
            output = output.split("```")
            if len(output) > 1:
                output = output[1]
            else:
                output = output[0]
            output = output.lstrip("plaintext").encode().decode("unicode_escape")
            return schema(input=output)

        model_with_tools = model
        output_parser = (
            StrOutputParser()
            # | RunnableLambda(lambda x : schema(**{field: x}))
            | RunnableLambda(parse_output)
            # lambda x: schema(input=(text if (text := x.split('```')[1]) else 1).lstrip("plaintext").encode().decode("unicode_escape")))
        )
    elif is_gemini(model):
        model_with_tools = model.bind(response_format={"type": "json_object"})
        output_parser = PydanticOutputParser(pydantic_object=schema)

        if backup_model_gemini:
            if not isinstance(backup_model_gemini, ChatOpenAI):
                backup_model_gemini = create_chat_client(backup_model_gemini)
            output_parser = CustomOutputFixingParser.from_llm_with_structured_output(
                parser=output_parser,
                llm=backup_model_gemini,
                schema=schema,
                prompt=input_fixing_prompt,
            )
    else:
        if is_anthropic(model):
            model_with_tools = model.bind_tools([schema], tool_choice=True)
        else:
            tool_name = convert_to_openai_tool(schema)["function"]["name"]
            model_with_tools = model.bind_tools([schema], tool_choice=tool_name, parallel_tool_calls=False)
        output_parser = PydanticToolsParser2(tools=[schema], first_tool_only=True)
    parser_assign = RunnablePassthrough.assign(
        parsed=itemgetter("raw") | output_parser,
        parsing_error=lambda _: None,
    )
    parser_assign = parser_assign.assign(
        ai_message=(itemgetter("raw") if is_gemini(model) else lambda x: AIMessage(content=str(x["parsed"]))),
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


def fix_anthropic_weirdness(
    model: ChatOpenAI | LLMmodel,
) -> dict[str, list[tuple[str, str]]]:
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
