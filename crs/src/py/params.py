from enum import auto

from strenum import StrEnum

# Submit
RETRY_SUBMISSIONS = 2

# LLM
MAX_ALLOWED_HISTORY_CHARS = 100_000  # divide by 4 to get approx. number of tokens tokens
MAX_CHAT_CLIENT_RETRIES = 1
MAX_BACKUP_LLM_RETRIES = 1

# Error Handler
ERROR_HANDLER_RETRIES = 4
ERROR_HANDLER_DELAYS: list[float] = [10, 20, 30, 60]

# RAG
RAG_CHUNK_SIZE = 1000
RAG_CHUNK_OVERLAP = 0
RAG_VECTORSTORE_STEP = 50  # number of documents to ad to vector store at once
RAG_EMBEDDING_MODEL = "oai-text-embedding-3-large"


# Vulnerability Discovery
class VDDetailLevel(StrEnum):
    LATEST_FILES = auto()
    COMMIT_FILES = auto()
    COMMIT_FUNCS = auto()
    FILE_DIFFS = auto()
    FUNC_DIFFS = auto()


VD_MODEL_LIST: list = ["oai-gpt-4o", "gemini-1.5-pro", "claude-3.5-sonnet"]
VD_MAX_LLM_TRIALS = 2
VD_TOP_RAG_DOCS = 10
VD_CHOSEN_DETAIL_LEVEL = VDDetailLevel.LATEST_FILES

# VD LangGraph
BACKUP_MODEL_GEMINI = "oai-gpt-4o"
NUM_MESSAGES_PER_ROUND = 4  # this is not an actual parameter. Change only if you changed LangGraph logic

# Patch Generation
PATCH_MODEL_LIST: list = ["oai-gpt-4o", "claude-3.5-sonnet", "gemini-1.5-pro"]
PATCH_MAX_LLM_TRIALS = 3
