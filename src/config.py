import os
from pathlib import Path

CP_ROOT = Path(os.environ.get("CP_ROOT", Path(__file__).parents[1] / "cp_root"))
CRS_SCRATCH_SPACE = Path(os.environ.get("CRS_SCRATCH_SPACE", Path(__file__).parents[1] / "crs_scratch"))
PROJECT_PATH = CRS_SCRATCH_SPACE / CP_ROOT.name
OUTPUT_PATH = Path(CRS_SCRATCH_SPACE) / "crs_output"
