import argparse
import asyncio

from api.fs import empty_scratch, get_project
from logger import logger
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import vuln_discovery

vulnerabilities = []


async def run(challenge_project: str, cpv: str, llm: list[str]):
    logger.info("Starting CRS")
    empty_scratch()
    project_path = get_project(challenge_project)
    project_read_only = await setup_project(project_path)

    print(project_path)
    quit()

    # does project have exemplar_only or .internal_only folder?
    # - .internal_only
    #     is cpv folder there? no=>error
    #     read pov_pou_info -- map back to config_id
    #     apply all patches but the current

    for cp_source in project_read_only.sources:
        vulnerabilities.extend(
            await vuln_discovery.run(
                project_read_only=project_read_only,
                cp_source=cp_source,
                preprocessed_commits=[],
            )
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
