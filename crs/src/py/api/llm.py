from typing import TypeAlias, Literal

import openai
from config import LITELLM_KEY, AIXCC_LITELLM_HOSTNAME

LLMmodel: TypeAlias = Literal[
    "oai-gpt-3.5-turbo",
    "oai-gpt-3.5-turbo-16k",
    "oai-gpt-4"
    "oai-gpt-4-turbo",
    "oai-gpt-4o",
    "text-embedding-3-large",
    "text-embedding-3-small",
    "claude-3-opus",
    "claude-3-sonnet",
    "claude-3-haiku",
    "gemini-1.0-pro",
    "gemini-1.5-pro",
    "textembedding-gecko",
    "azure-gpt-3.5-turbo",
    "azure-gpt-3.5-turbo-16k",
    "azure-gpt-4o",
]

client = openai.OpenAI(
    api_key=LITELLM_KEY,
    base_url=AIXCC_LITELLM_HOSTNAME
)


def send_msg_to_llm(model_name, message):
    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "user",
                "content": message
            }
        ],
    )
    return completion.choices[0].message.content
