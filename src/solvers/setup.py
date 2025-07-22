from inspect_ai.model import ChatMessageUser
from inspect_ai.solver import Generate, Solver, TaskState, solver

from api.sandbox import apply_patches, build
from logger import logger


@solver
def patch_and_build_project() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        sources = state.metadata["sources"]
        logger.info("Applying patches")
        for source in sources:
            await apply_patches(source)
        logger.info("Building project")
        await build()
        logger.info("Project built")
        return state

    return solve


@solver
def add_code_message() -> Solver:
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        code = state.metadata["code"]
        state.messages = [ChatMessageUser(content=code)]
        return state

    return solve
