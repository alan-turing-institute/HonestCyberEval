import os
from pathlib import Path

_project_root = Path(__file__).parent.parent

CP_ROOT = _project_root / os.environ.get("CP_ROOT", "./cp_root")
CRS_SCRATCH_SPACE = _project_root / os.environ.get("CRS_SCRATCH_SPACE", "./crs_scratch")
PROJECT_PATH = CRS_SCRATCH_SPACE / CP_ROOT.name
OUTPUT_PATH = Path(CRS_SCRATCH_SPACE) / "crs_output"
