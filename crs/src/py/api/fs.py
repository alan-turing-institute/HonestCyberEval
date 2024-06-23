import subprocess
from pathlib import Path
from shutil import rmtree

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE


class RunException(Exception):
    message = ""

    def __init__(self, stderr):
        super().__init__(self.message)
        self.stderr = stderr

    def __str__(self):
        return f"{super().__str__()}\n{self.stderr}"


def run_command(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    result.check_returncode()
    return result


PROJECT_PATH = AIXCC_CRS_SCRATCH_SPACE / AIXCC_CP_ROOT.name


def move_projects_to_scratch():
    run_command("cp", "--recursive", AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE)


def get_projects():
    return [item for item in PROJECT_PATH.iterdir() if item.is_dir()]


OUTPUT_PATH = Path(AIXCC_CRS_SCRATCH_SPACE) / "crs_output"


def empty_scratch():
    if PROJECT_PATH.exists():
        rmtree(PROJECT_PATH)

    if OUTPUT_PATH.exists():
        rmtree(OUTPUT_PATH)


def write_file_to_scratch(filename, content):
    OUTPUT_PATH.mkdir(exist_ok=True)
    file_path = OUTPUT_PATH / filename
    file_path.write_text(content)
    return file_path
