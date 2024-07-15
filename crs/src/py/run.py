import asyncio

from api.fs import empty_scratch, get_projects
from api.submit import submit_patch, submit_vulnerability
from logger import logger
from pipeline.patch_gen import patch_generation
from pipeline.preprocess_commits import find_functional_changes
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import vuln_discovery, remove_duplicate_vulns

vulnerabilities = []


async def run():
    logger.info("Starting CRS")
    empty_scratch()
    projects = get_projects()
    for project_path in projects:
        project_read_only = await setup_project(project_path)

        preprocessed_commits = {}
        for cp_source in project_read_only.sources:
            preprocessed_commits[cp_source] = find_functional_changes(
                project_read_only=project_read_only, cp_source=cp_source
            )
            # logger.debug(f"Preprocessed Commits:\n {pprint.pformat(preprocessed_commits)}\n")
            vulnerabilities.extend(
                await vuln_discovery.run(
                    project_read_only=project_read_only,
                    cp_source=cp_source,
                    preprocessed_commits=preprocessed_commits[cp_source],
                )
            )

        deduped_vulnerabilities = remove_duplicate_vulns(vulnerabilities)
        project_writeable = await project_read_only.writeable_copy_async
        for vulnerability in deduped_vulnerabilities:
            # todo: we can now submit vulnerabilities async, make use of that?
            if vulnerability.status == "pending":
                await submit_vulnerability(
                    cp_name=project_read_only.name,
                    vulnerability=vulnerability,
                )
            logger.info(f"Vulnerability: {vulnerability.status} {vulnerability.cpv_uuid}")
            # todo: if vulnerability is rejected and we haven't triggered all sanitisers, look some more?
            if vulnerability.status != "rejected":
                if vulnerability.patch is None or vulnerability.patch.status == "rejected":
                    await patch_generation.run(
                        project=project_writeable,
                        preprocessed_commits=preprocessed_commits[vulnerability.cp_source],
                        vulnerability=vulnerability,
                    )
                if vulnerability.patch and vulnerability.patch.status == "pending":
                    logger.info("Submitting patch")
                    await submit_patch(vulnerability.patch)
                    logger.info(f"Patch: {vulnerability.patch.status} {vulnerability.patch.gp_uuid}")


if __name__ == "__main__":
    retry = True
    while retry:
        try:
            asyncio.run(run())
        except Exception as err:
            logger.exception(err)
        else:
            retry = False
