import asyncio

from api.fs import empty_scratch, get_projects
from api.submit import submit_patch, submit_vulnerability
from logger import logger
from pipeline.patch_gen import patch_generation
from pipeline.preprocess_commits import find_functional_changes
from pipeline.setup_project import setup_project
from pipeline.vuln_discovery import remove_duplicate_vulns, vuln_discovery

vulnerabilities = []


async def submit_vuln_and_patch(vulnerability, project_writeable, preprocessed_commits):
    if vulnerability.status == "pending":
        await submit_vulnerability(
            cp_name=project_writeable.name,
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
            solved_commits = [
                vuln.commit for vuln in vulnerabilities if vuln.cp_source == cp_source and vuln.status == "accepted"
            ]

            commits_to_investigate = {
                commit: diff for commit, diff in preprocessed_commits[cp_source].items() if commit not in solved_commits
            }

            vulnerabilities.extend(
                await vuln_discovery.run(
                    project_read_only=project_read_only,
                    cp_source=cp_source,
                    preprocessed_commits=commits_to_investigate,
                )
            )

        deduped_vulnerabilities = remove_duplicate_vulns(vulnerabilities)
        project_writeable = await project_read_only.writeable_copy_async
        await asyncio.gather(*[
            submit_vuln_and_patch(
                vulnerability,
                project_writeable,
                preprocessed_commits,
            )
            for vulnerability in deduped_vulnerabilities
        ])


if __name__ == "__main__":
    retry = True
    while retry:
        try:
            asyncio.run(run())
        except Exception as err:
            logger.exception(err)
        else:
            # todo: when else should we try to re-run?
            retry = False
