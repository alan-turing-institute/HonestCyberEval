import os
from pathlib import Path

CP_ROOT = Path(os.environ.get("CP_ROOT", "./cp_root"))
CRS_SCRATCH_SPACE = Path(os.environ.get("CRS_SCRATCH_SPACE", "./crs_scratch"))
PROJECT_PATH = CRS_SCRATCH_SPACE / CP_ROOT.name
OUTPUT_PATH = Path(CRS_SCRATCH_SPACE) / "crs_output"
