import time

from api.fs import empty_scratch, get_projects, move_projects_to_scratch
from api.submit import healthcheck, submit_patch, submit_vulnerability
from logger import logger
from pipeline.patch_gen import patch_generation
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import vuln_discovery


def run():
    empty_scratch()
    move_projects_to_scratch()
    projects = get_projects()
    for project_path in projects:
        if not project_path.name == "mock-cp":
            # Assuming this is "Mock CP" for now as it's using hardcoded inputs and patches
            logger.warning(f"Skipping {project_path.name}")
            continue
        project = setup_project(project_path)

        for cp_source in project.sources:
            vulnerabilities = vuln_discovery.run(project, cp_source)
            for vulnerability in vulnerabilities:
                while not healthcheck():
                    time.sleep(5)
                else:
                    logger.info("healthcheck passed")

                # todo: save input to persistent storage and check it to avoid double submissions
                status, cpv_uuid = submit_vulnerability(cp_name=project.name, vulnerability=vulnerability)
                # todo: update input in persistent storage and mark as accepted
                logger.info(f"Vulnerability: {status} {cpv_uuid}")

                if status != "rejected":
                    patch = patch_generation.run(project, cp_source, cpv_uuid, vulnerability)
                    if patch:
                        # todo: save patch to persistent storage and check it to avoid double submissions
                        logger.info("Submitting patch")
                        status, gp_uuid = submit_patch(cpv_uuid, patch)
                        logger.info(f"Patch: {status} {gp_uuid}")
                        # todo: update patch in persistent storage and mark as accepted


if __name__ == "__main__":
    try:
        run()
    except Exception as err:
        logger.exception(err)
        raise
