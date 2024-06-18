import subprocess
from pathlib import Path

from config import AIXCC_CP_ROOT, AIXCC_CRS_SCRATCH_SPACE, GITHUB_USER, GITHUB_TOKEN


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


# temporary code to interact with CP Docker images
# Organisers are planning to make changes that will create a Docker container for this in local dev
# https://github.com/aixcc-sc/crs-sandbox/pull/178
# and images will be present for the CRS to use when running in Stage 2
# https://github.com/aixcc-sc/crs-sandbox/issues/169
__logged_in = False


def docker_login():
    if __logged_in:
        return
    run_command("docker", "login", "-u", GITHUB_USER, "-p", GITHUB_TOKEN, "ghcr.io")


