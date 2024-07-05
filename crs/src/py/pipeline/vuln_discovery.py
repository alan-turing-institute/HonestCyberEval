from typing import Optional

from api.cp import ChallengeProject
from api.data_types import Vulnerability, VulnerabilityWithSha
from api.fs import write_harness_input_to_disk
from api.llm import LLMmodel, format_chat_history

from logger import logger
from .langgraph_vuln import run_vuln_langraph
from .preprocess_commits import find_diff_between_commits

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

mock_input_data_segv = """ab
b

501
"""


class VulnDiscovery:
    project: ChallengeProject
    cp_source: str

    def detect_vulns_in_file(self, bad_file: str) -> list[Vulnerability]:
        code_snippet = self.project.open_project_source_file(self.cp_source, bad_file)
        vulnerabilities = []
        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                vuln = self.harness_input_langgraph(
                    harness_id,
                    sanitizer_id,
                    code_snippet,
                    max_trials=6,
                )
                if vuln:
                    vulnerabilities.append(vuln)
        return vulnerabilities

    def harness_input_langgraph(self, harness_id, sanitizer_id, code_snippet, max_trials=2) -> Optional[Vulnerability]:
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]
        models: list[LLMmodel] = ["gemini-1.5-pro", "oai-gpt-4o", "claude-3.5-sonnet"]
        for model_name in models:
            try:
                output = run_vuln_langraph(
                    model_name=model_name,
                    project=self.project,
                    harness_id=harness_id,
                    sanitizer_id=sanitizer_id,
                    code_snippet=code_snippet,
                    max_iterations=max_trials,
                )

                logger.debug(f"LangGraph Message History\n\n{format_chat_history(output['chat_history'])}\n\n")
                if not output["error"]:
                    logger.info(f"Found vulnerability using harness {harness_id}: {sanitizer}: {error_code}")
                    harness_input = output["solution"]
                    harness_input_file = write_harness_input_to_disk(self.project, harness_input, "work", harness_id, sanitizer_id, model_name)
                    return Vulnerability(harness_id, sanitizer_id, harness_input, harness_input_file)
                logger.info(f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id}")
                logger.debug(f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id} with error: \n {output['error']}")
            except Exception as error:
                logger.error(f"LangGraph vulnerability detection failed for {model_name} with\n{error}")
        logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
        return None

    def identify_bad_commits(self, vulnerabilities: list[Vulnerability]) -> list[VulnerabilityWithSha]:
        """
        Given a list of Vulnerabilities, this function:
        1. Gets list of commits and loops over them (latest to earliest)
        2. Reverts the Git repo to a commit i
        3. Tests the harness on commit i for each Vulnerability
        4. Assigns the vulnerability a commit when the previous commit does not trigger the sanitizer
        """

        # step 1: Get list of commits and loop over them (latest to earliest)
        git_repo, ref = self.project.repos[self.cp_source]
        git_log = list(git_repo.iter_commits(ref))
        # Start at HEAD and go down the commit log
        previous_commit = git_log[0]

        vulnerabilities_with_sha = []

        # check vulnerabilities for oldest commit they're found in
        vulnerabilities_next = vulnerabilities
        for inspected_commit in git_log[1:]:
            if not vulnerabilities_next:
                # no vulnerabilities left without commit that introduced them, stop searching
                break
            vulnerabilities_left = vulnerabilities_next
            vulnerabilities_next = []

            # step 2: revert the Git repo to the commit
            logger.debug(f"Reverting to commit: {inspected_commit.hexsha}")

            git_repo.git.switch('--detach', inspected_commit.hexsha)
            self.project.build_project()

            for vuln in vulnerabilities_left:
                sanitizer, error_code = self.project.sanitizers[vuln.sanitizer_id]

                # step 3: Test the harness on commit i
                harness_triggered, _ = self.project.run_harness_and_check_sanitizer(
                    vuln.input_file,
                    vuln.harness_id,
                    vuln.sanitizer_id,
                )

                if harness_triggered:
                    logger.debug(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
                    vulnerabilities_next.append(vuln)
                # step 4: When sanitizer is not triggered the previous commit introduced the vulnerability, assign previous commit as bug introducing
                else:
                    logger.info(f"Found bad commit: {previous_commit.hexsha} that introduced vulnerability {sanitizer}: {error_code}  ")
                    vulnerabilities_with_sha.append(VulnerabilityWithSha(*vuln, commit=previous_commit.hexsha))
            previous_commit = inspected_commit

        # cleaning up:
        # reset repo back to head
        self.project.reset_source_repo(self.cp_source)
        # rebuild project at head
        self.project.build_project()

        return vulnerabilities_with_sha

    def find_functional_changes(self):

        # get relevant repo
        repo, ref = self.project.repos[self.cp_source]

        # firstly get all the commits needed:
        # Iterate over all branches to get all commits
        all_commits_set = set()

        # Get commits from all branches
        for commit in repo.iter_commits(ref):
            all_commits_set.add(commit)

        # Sort commits by date
        all_commits = sorted(all_commits_set, key=lambda c: c.committed_datetime)

        # then for each commit and compare with it's parent to find the relevant files changed and the functional changes within each file
        preprocessed_commits = {}

        for commit in all_commits:
            # print(f"\nCommit Hash: {commit.hexsha}")

            if commit.parents:
                parent_commit = commit.parents[0]
                diffs = find_diff_between_commits(parent_commit, commit)

                if diffs:
                    preprocessed_commits[commit.hexsha] = diffs
                    # TODO: do we want the commit objects in here too?

        return preprocessed_commits

    def run(self, project: ChallengeProject, cp_source: str) -> list[VulnerabilityWithSha]:
        self.project = project
        self.cp_source = cp_source

        # Find functional changes in diffs
        preprocessed_commits = self.find_functional_changes()
        logger.debug(f"Preprocessed Commits:\n {preprocessed_commits}\n")

        # Detect vulnerabilities using LLMs
        vulnerabilities = self.detect_vulns_in_file("mock_vp.c")

        # Hardcoding values to test patch generation
        if self.project.name == "Mock CP" and len(vulnerabilities) < 2:
            logger.warning("Not all Mock CP vulnerabilities discovered")
            both = len(vulnerabilities) == 0
            if both or vulnerabilities[0].sanitizer_id == "id_2":
                mock_input_file = write_harness_input_to_disk(self.project, mock_input_data, 0, "id_1", "id_1", "mock")
                vulnerabilities.append(Vulnerability("id_1", "id_1", mock_input_data, mock_input_file))
            if both or vulnerabilities[0].sanitizer_id == "id_1":
                mock_input_file = write_harness_input_to_disk(self.project, mock_input_data_segv, 0, "id_1", "id_2", "mock")
                vulnerabilities.append(Vulnerability("id_1", "id_2", mock_input_data_segv, mock_input_file))

        vulnerabilities_with_sha = self.identify_bad_commits(vulnerabilities)

        return vulnerabilities_with_sha


vuln_discovery = VulnDiscovery()
