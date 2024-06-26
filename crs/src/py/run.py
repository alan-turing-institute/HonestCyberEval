import time

from api.submit import healthcheck, submit_vulnerability, submit_patch
from api.fs import (
    get_projects,
    empty_scratch,
    move_projects_to_scratch,
)
from logger import logger
from pipeline.patch_gen import patch_generation
from pipeline.vuln_discovery import vuln_discovery
from pipeline.setup_project import setup_project


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

            for bad_commit_sha, harness_id, sanitizer_id, input_data, blob_file in vulnerabilities:
                while not healthcheck():
                    time.sleep(5)
                else:
                    logger.info("healthcheck passed")

                # todo: save input to persistent storage and check it to avoid double submissions
                status, cpv_uuid = submit_vulnerability(
                    cp_name=project.name,
                    commit_sha1=bad_commit_sha,
                    sanitizer_id=sanitizer_id,
                    harness_id=harness_id,
                    data=input_data,
                )
                # todo: update input in persistent storage and mark as accepted
                logger.info(f"Vulnerability: {status} {cpv_uuid}")

                if status != 'rejected':
                    patch = patch_generation.run(
                        project, cp_source, cpv_uuid, harness_id, blob_file, sanitizer_id
                    )
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
