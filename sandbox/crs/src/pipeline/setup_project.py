from git import Repo

from api.cp import ChallengeProjectReadOnly
from config import OUTPUT_PATH


async def setup_project(project_path) -> ChallengeProjectReadOnly:
    with Repo(path=project_path).config_writer(config_level="global") as config_writer:
        config_writer.add_value("safe", "directory", "*")
    path_common = OUTPUT_PATH / project_path.name
    input_path = path_common / "harness_input"
    input_path.mkdir(parents=True, exist_ok=True)

    return ChallengeProjectReadOnly(project_path, input_path=input_path)
