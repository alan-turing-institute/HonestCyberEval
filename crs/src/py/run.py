import asyncio

from api.fs import empty_scratch, get_projects, move_projects_to_scratch
from api.submit import submit_patch, submit_vulnerability
from logger import logger
from pipeline.patch_gen import patch_generation
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import vuln_discovery


async def run():
    empty_scratch()
    move_projects_to_scratch()
    projects = get_projects()
    for project_path in projects:
        project = setup_project(project_path)

        for cp_source in project.sources:
            vulnerabilities = await vuln_discovery.run(project, cp_source)
            for vulnerability in vulnerabilities:
                # todo: we can now submit vulnerabilities async, make use of that?
                # todo: save input to persistent storage and check it to avoid double submissions
                status, cpv_uuid = await submit_vulnerability(cp_name=project.name, vulnerability=vulnerability)
                # todo: update input in persistent storage and mark as accepted
                logger.info(f"Vulnerability: {status} {cpv_uuid}")
                # todo: if vulnerability is rejected and we haven't triggered all sanitisers, look some more?
                if status != "rejected":
                    patch = await patch_generation.run(project, cp_source, cpv_uuid, vulnerability)
                    if patch:
                        # todo: save patch to persistent storage and check it to avoid double submissions
                        logger.info("Submitting patch")
                        status, gp_uuid = await submit_patch(cpv_uuid, patch)
                        logger.info(f"Patch: {status} {gp_uuid}")
                        # todo: update patch in persistent storage and mark as accepted


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as err:
        logger.exception(err)
        raise
