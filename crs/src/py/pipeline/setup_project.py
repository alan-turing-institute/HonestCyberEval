from git import Repo

from api.cp import ChallengeProjectReadOnly
from config import OUTPUT_PATH


async def setup_project(project_path):
    with Repo(path=project_path).config_writer(config_level="global") as config_writer:
        config_writer.add_value("safe", "directory", "*")
    path_common = OUTPUT_PATH / project_path.name
    input_path = path_common / "harness_input"
    patch_path = path_common / "patches"
    for p in [input_path, patch_path]:
        p.mkdir(parents=True, exist_ok=True)

    project = ChallengeProjectReadOnly(project_path, input_path=input_path, patch_path=patch_path)

    return project
