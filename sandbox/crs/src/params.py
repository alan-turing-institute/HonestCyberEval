from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from api.llm import LLMmodel

# Submit
RETRY_SUBMISSIONS = 2

# LLM
MAX_ALLOWED_HISTORY_CHARS = 100_000  # divide by 4 to get approx. number of tokens tokens
MAX_CHAT_CLIENT_RETRIES = 1

# Error Handler
ERROR_HANDLER_RETRIES = 4
ERROR_HANDLER_DELAYS: list[float] = [10, 20, 30, 60]

VD_MODEL_LIST: list["LLMmodel"] = [
    "oai-gpt-4o",
    "o1-preview",
    "o1-mini",
    "gemini-1.5-pro",
    "claude-3.5-sonnet",
]
VD_MAX_LLM_TRIALS = 8

# VD LangGraph
NUM_MESSAGES_PER_ROUND = 4  # this is not an actual parameter. Change only if you changed LangGraph logic
