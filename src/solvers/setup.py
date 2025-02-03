from git import Repo
from inspect_ai.solver import Generate, Solver, TaskState, solver

from api.cp import ChallengeProjectReadOnly
from config import OUTPUT_PATH


def setup_project(project_path) -> ChallengeProjectReadOnly:
    with Repo(path=project_path).config_writer(config_level="global") as config_writer:
        config_writer.add_value("safe", "directory", "*")
    input_path = OUTPUT_PATH / project_path.name / "harness_input"
    input_path.mkdir(parents=True, exist_ok=True)

    return ChallengeProjectReadOnly(project_path, input_path=input_path)


@solver
def copy_and_build_if_needed(project_read_only) -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        cpv = state.metadata["cpv"]
        project = await project_read_only.make_writeable_copy(
            name_extra=cpv, other_patches=state.metadata["other_patches"]
        )
        state.store.set("project", project)
        return state

    return solve
