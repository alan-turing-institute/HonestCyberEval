import subprocess
from pathlib import Path
import yaml
from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE


def move_projects_to_scratch():
    subprocess.run(["cp", "--recursive", AIXCC_CP_ROOT + "/.", AIXCC_CRS_SCRATCH_SPACE])


def get_projects():
    return [item for item in Path(AIXCC_CRS_SCRATCH_SPACE).iterdir() if item.is_dir()]


def read_project_yaml(project_path):
    with open(project_path / "project.yaml", "r") as stream:
        return yaml.safe_load(stream)


def run_cp_run_sh(project_path, *command):
    """
    Copied from run.sh:
    A helper script for CP interactions.

    Usage: build|run_pov|run_test|custom

    Subcommands:
        build [<patch_file> <source>]       Build the CP (an optional patch file for a given source repo can be supplied)
        run_pov <blob_file> <harness_name>  Run the binary data blob against specified harness
        run_tests                           Run functionality tests
        custom <arbitrary cmd ...>          Run an arbitrary command in the docker container
    """
    subprocess.run([project_path / "run.sh", *command])


def run_cp_make(project_path, *command):
    subprocess.run(["make", "-C", project_path, *command])

def run_cp_git(project_path, *command):
    subprocess.run(["git", "-C", project_path, *command])


def write_file_to_scratch(filename, content):
    file_path = Path(AIXCC_CRS_SCRATCH_SPACE) / filename
    with open(Path(AIXCC_CRS_SCRATCH_SPACE) / filename, "w") as output_file:
        output_file.write(content)
        output_file.close()
    return file_path
