import os
from pathlib import Path

CP_ROOT = Path(os.environ.get("CP_ROOT", "/cp_root"))
CRS_SCRATCH_SPACE = Path(os.environ.get("CRS_SCRATCH_SPACE", "/crs_scratch"))
PROJECT_PATH = CRS_SCRATCH_SPACE / CP_ROOT.name
OUTPUT_PATH = Path(CRS_SCRATCH_SPACE) / "crs_output"

LITELLM_HOSTNAME = os.environ.get("LITELLM_HOSTNAME", "http://litellm")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-1234")

LANGCHAIN_TRACING_V2 = os.environ.get("LANGCHAIN_TRACING_V2", False)
LANGCHAIN_API_KEY = os.environ.get("LANGCHAIN_API_KEY", "")
