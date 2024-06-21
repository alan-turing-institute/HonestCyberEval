from typing import TypeAlias, Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field, SecretStr
from langchain_openai import ChatOpenAI

from config import LITELLM_KEY, AIXCC_LITELLM_HOSTNAME

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
    "text-embedding-3-large",
    "text-embedding-3-small",
    # Google
    "textembedding-gecko",
]


class HarnessInput(BaseModel):
    """Input to test harness that triggers vulnerability"""
    harness_input: str = Field(
        description="Lines of input terminating with newline, including empty lines"
    )


def llm_prompt_harness_input(
    model_name: str = "claude-3-sonnet",  # LLMmodel https://github.com/python/mypy/issues/9230
    harness_text: str = "",
    code_snippet: str = "",
    sanitizer: str = "",
    error_code: str = "",
):
    system_message = """You should generate the input to a program.
    The input will be piped into the program.
    """
    user_message = """Generate an input txt file for the following test harness:
    {harness_text}
    . The harness should exercise the code:
    {code_snippet}
    . The harness should cause the code to trigger a {sanitizer}: {error_code} error.
    """

    harness_input_template = ChatPromptTemplate.from_messages(
        [("system", system_message), ("user", user_message)]
    )

    model = ChatOpenAI(
        model=model_name,
        api_key=SecretStr(LITELLM_KEY),
        base_url=AIXCC_LITELLM_HOSTNAME,
    ).with_structured_output(HarnessInput)

    chain = harness_input_template | model

    response = chain.invoke({
        "harness_text": harness_text,
        "code_snippet": code_snippet,
        "sanitizer": sanitizer,
        "error_code": error_code,
    })

    assert isinstance(response, HarnessInput)
    return response.harness_input
