import subprocess
from pathlib import Path

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE


def run_command(*args):
    result = subprocess.run(args, capture_output=True, text=True)
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
