import os
from pathlib import Path

AIXCC_CP_ROOT = Path(os.environ.get("AIXCC_CP_ROOT", "/cp_root"))
AIXCC_CRS_SCRATCH_SPACE = Path(os.environ.get("AIXCC_CRS_SCRATCH_SPACE", "/crs_scratch"))
PROJECT_PATH = AIXCC_CRS_SCRATCH_SPACE / AIXCC_CP_ROOT.name
OUTPUT_PATH = Path(AIXCC_CRS_SCRATCH_SPACE) / "crs_output"

AIXCC_LITELLM_HOSTNAME = os.environ.get("AIXCC_LITELLM_HOSTNAME", "http://litellm")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-1234")

LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", False)
LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
