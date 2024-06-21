import os

AIXCC_API_HOSTNAME = os.environ.get("AIXCC_API_HOSTNAME", "http://iapi:8080")
AIXCC_CP_ROOT = os.environ.get("AIXCC_CP_ROOT", "/cp_root")
AIXCC_CRS_SCRATCH_SPACE = os.environ.get("AIXCC_CRS_SCRATCH_SPACE", "/crs_scratch")
AIXCC_LITELLM_HOSTNAME = os.environ.get("AIXCC_LITELLM_HOSTNAME", "http://litellm")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-1234")

LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", False)
LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
