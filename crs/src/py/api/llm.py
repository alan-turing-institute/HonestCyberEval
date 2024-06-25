from typing import TypeAlias, Literal

from langchain_core.pydantic_v1 import SecretStr
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
    "text-embedding-3-large",
    "text-embedding-3-small",
    # Google
    "textembedding-gecko",
]


def createChatClient(model_name):
    model = ChatOpenAI(
        model=model_name,
        api_key=SecretStr(LITELLM_KEY),
        base_url=AIXCC_LITELLM_HOSTNAME,
    )
    return model