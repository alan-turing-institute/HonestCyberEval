from datetime import datetime
from subprocess import CalledProcessError

from inspect_ai.util import ExecResult, sandbox


async def _run_sandbox_and_raise(
    command: list[str],
    stdin: str | bytes | None = None,
):
    result = await sandbox().exec(command, input=stdin, env={"LOCAL_USER": "0:0"})
    if not result.success:
        raise CalledProcessError(
            returncode=result.returncode,
            stderr=result.stderr,
            output=result.stdout,
            cmd=" ".join(command),
        )
    return result


async def apply_patches(source: str):
    patches_folder = f"patches/{source}/"
    result = await _run_sandbox_and_raise(["find", patches_folder, "-name", "*.diff"])
    result = await _run_sandbox_and_raise(
        ["xargs", "-0", "-d", "\\n", "realpath"], stdin=result.stdout
    )
    return await _run_sandbox_and_raise(
        ["xargs", "-0", "-d", "\\n", "git", "-C", f"/src/{source}", "apply"],
        stdin=result.stdout,
    )


async def _run_command(command: str | list[str]):
    if type(command) is str:
        command = [command]
    return await _run_sandbox_and_raise(["cmd_harness.sh", *command])


async def build():
    return await _run_command("build")


async def run_tests(self):
    """Runs a specified project test suite and returns the output of the process.
    Check stderr for failed test output if it exists.
    """
    return await _run_command("run_tests")


async def write_harness_input(
    harness_input: str | bytes,
    i: int,
    cpv: int | str,
    model_name: str,
):
    model_name = model_name.replace("/", "_")
    filename = f"/work/input_{datetime.today().isoformat()}_{cpv}_{model_name}_{i}_hash{str(hash(harness_input))[:6]}.blob"
    await sandbox().write_file(filename, harness_input)
    return filename


async def run_harness(harness_input_file, harness_name) -> ExecResult[str]:
    """Runs a specified project test harness and returns the output of the process.
    Check result.stderr for sanitizer output if it exists.
    """
    return await _run_command(
        [
            "pov",
            harness_input_file,
            harness_name,
        ],
    )


async def run_harness_and_check_sanitizer(
    harness_input_file, harness_name, sanitizer, timeout=False
) -> tuple[bool, str]:
    """Runs a specified project test harness and returns whether sanitizer is triggered."""
    result = await run_harness(harness_input_file, harness_name)
    stderr = result.stderr
    return sanitizer in stderr, stderr
