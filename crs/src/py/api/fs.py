import subprocess
from pathlib import Path

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE


class RunException(Exception):
    def __init__(self, message, stderr):
        super().__init__(message)
        self.stderr = stderr

    def __str__(self):
        return f"{super().__str__()}\n{self.stderr}"


def run_command(*args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    result.check_returncode()
    return result


def move_projects_to_scratch():
    run_command("cp", "--recursive", AIXCC_CP_ROOT + "/.", AIXCC_CRS_SCRATCH_SPACE)


def get_projects():
    return [item for item in Path(AIXCC_CRS_SCRATCH_SPACE).iterdir() if item.is_dir()]


def write_file_to_scratch(filename, content):
    file_path = Path(AIXCC_CRS_SCRATCH_SPACE) / filename
    with open(file_path, "w") as output_file:
        output_file.write(content)
        output_file.close()
    return file_path
