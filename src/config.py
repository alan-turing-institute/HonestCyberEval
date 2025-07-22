import os
from pathlib import Path

CP_ROOT = Path(os.environ.get("CP_ROOT", Path(__file__).parents[1] / "cp_root"))
