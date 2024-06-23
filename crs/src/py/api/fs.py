import subprocess
from shutil import rmtree

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE, OUTPUT_PATH, PROJECT_PATH
from logger import logger


class RunException(Exception):
    message = ""

    def __init__(self, stderr):
        super().__init__(self.message)
        self.stderr = stderr

    def __str__(self):
        return f"{super().__str__()}\n{self.stderr}"


class PatchException(RunException):
    def __init__(self, stderr, patch_path):
        super().__init__(stderr)
        self.patch_path = patch_path

    def __str__(self):
        return "\n".join([
            super().__str__(),
            "Patch applied to cause exception:",
            str(self.patch_path.absolute()),
            self.patch_path.read_text(),
        ])


def run_command(*args, **kwargs):
    logger.debug(f"Running {' '.join((str(arg) for arg in args))}")
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    logger.debug("\n".join([
        f"Output of running {' '.join((str(arg) for arg in args))}:",
        result.stdout,
        result.stderr,
    ]))
    result.check_returncode()
    return result


def move_projects_to_scratch():
    run_command("cp", "--recursive", AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE)


def get_projects():
    return [item for item in PROJECT_PATH.iterdir() if item.is_dir()]


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
