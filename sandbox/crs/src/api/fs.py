import asyncio
from pathlib import Path
from shutil import rmtree
from subprocess import CalledProcessError
from typing import TYPE_CHECKING, Literal

from api.llm import LLMmodel
from config import AIXCC_CP_ROOT, OUTPUT_PATH, PROJECT_PATH
from logger import logger

if TYPE_CHECKING:
    from api.cp import ChallengeProject


class RunException(Exception):
    message = ""

    def __init__(self, stderr):
        super().__init__(self.message)
        self.stderr = stderr

    def __str__(self):
        return f"{super().__str__()}\n{self.stderr}"


async def run_command(*args, timeout=None, **kwargs):
    logger.debug(f"Running {' '.join((str(arg) for arg in args))}")
    process = await asyncio.create_subprocess_exec(
        *args,
        **kwargs,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    logger.debug(
        f"Running {' '.join((str(arg) for arg in args))} in process {process.pid} {f'with timeout{timeout}' if timeout else ''}"
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

    stdout = stdout.decode()
    stderr = stderr.decode()

    logger.debug(
        "\n".join([
            f"Output of running {' '.join((str(arg) for arg in args))}:",
            stdout,
            stderr,
        ])
    )
    returncode = process.returncode
    if returncode:
        raise CalledProcessError(returncode, args, stdout, stderr)
    return process, stdout, stderr


def get_project(challenge_project) -> Path:
    for item in AIXCC_CP_ROOT.iterdir():
        if item.is_dir() and item.name == challenge_project:
            return item
    raise Exception(f"Could not find project {challenge_project}")


def empty_scratch():
    if PROJECT_PATH.exists():
        rmtree(PROJECT_PATH)

    # if OUTPUT_PATH.exists():
    # rmtree(OUTPUT_PATH)


def write_file_to_scratch(filename, content):
    OUTPUT_PATH.mkdir(exist_ok=True)
    file_path = OUTPUT_PATH / filename
    file_path.write_text(content + "\n\n\n")
    return file_path


def write_harness_input_to_disk(
    project: "ChallengeProject",
    harness_input: str,
    i: int | str,
    harness_id: str,
    sanitizer_id: str,
    model_name: LLMmodel | Literal["mock"],
):
    return write_file_to_scratch(
        project.input_path
        / f"harness_{harness_id}_sanitizer_{sanitizer_id}_{model_name}_{i}_hash{str(hash(harness_input))[:6]}.blob",
        harness_input,
    )
