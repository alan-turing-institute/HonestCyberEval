import argparse
import asyncio

from api.fs import empty_scratch, get_project
from logger import logger
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import vuln_discovery


async def run(challenge_project: str, cpv: str, llms: list[str]):
    if not challenge_project == "nginx-cp-full":
        raise Exception("Only nginx-cp-full is supported currently")
    logger.info("Starting CRS")
    empty_scratch()
    project_path = get_project(challenge_project)
    project_read_only = await setup_project(project_path)

    cp_source, harness_id, sanitizer_id, files, other_patches = project_read_only.get_cpv_info(cpv)
    project = await project_read_only.writeable_copy_async
    project.apply_patches(other_patches)
    await project.build_project()
    await vuln_discovery.run(
        project=project,
        cp_source=cp_source,
        cpv=cpv,
        llms=llms,
        harness_id=harness_id,
        sanitizer_id=sanitizer_id,
        files=files,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Benchmark")
    parser.add_argument(
        "challenge_project",
        help="One of the AIxCC projects defined in config/cp_config.yaml",
        type=str,
        default="nginx-cp-full",
    )
    parser.add_argument(
        "cpv", help="A vulnerability that was introduced in the challenge project", type=str, default="cpv1"
    )
    parser.add_argument("LLM", help="An LLM defined in the LiteLLM config", nargs="+", default=["o1-mini"])

    args = parser.parse_args()

    try:
        asyncio.run(run(args.challenge_project, args.cpv, args.LLM))
    except Exception as err:
        logger.exception(err)
