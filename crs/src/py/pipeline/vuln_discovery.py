import subprocess
from collections import namedtuple
from typing import List, Optional

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from api.cp import ChallengeProject
from api.fs import write_file_to_scratch
from api.llm import createChatClient

from logger import logger

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

mock_input_data_segv = """ab
b

501
"""

Vulnerability = namedtuple('Vulnerability', ['harness_id', 'sanitizer_id', 'input_data', 'blob_file'])
VulnerabilityWithSha = namedtuple('VulnerabilityWithSha', ['commit', 'harness_id', 'sanitizer_id', 'input_data', 'blob_file'])


class HarnessInput(BaseModel):
    """Input to test harness that triggers vulnerability"""
    harness_input: str = Field(
        description="Lines of input terminating with newline, including empty lines"
    )


system_message = """You should generate the input to a program.
The input will be piped into the program.
"""

user_message = """Generate an input txt file for the following test harness:
{harness_text}
. The harness should exercise the code:
{code_snippet}
. The harness should cause the code to trigger a {sanitizer}: {error_code} error.
"""

harness_input_template = ChatPromptTemplate.from_messages([
    ("system", system_message),
    ("user", user_message)
])


class VulnDiscovery:
    project: ChallengeProject
    cp_source: str

    @staticmethod
    def write_harness_input_to_disk(harness_input, i, harness_id, sanitizer_id, model_name):
        return write_file_to_scratch(
            f"input_harness_{harness_id}_sanitizer_{sanitizer_id}_{model_name}_{i}.blob",
            harness_input,
        )

    def detect_vulns_in_file(self, bad_file: str) -> List[Vulnerability]:
        code_snippet = self.project.open_project_source_file(self.cp_source, bad_file).replace('\n', '')
        vulnerabilities = []
        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                vuln = self.llm_harness_input(
                    harness_id,
                    sanitizer_id,
                    code_snippet,
                    max_trials=2,
                )
                if vuln:
                    vulnerabilities.append(vuln)
        return vulnerabilities

    def llm_harness_input(self, harness_id, sanitizer_id, code_snippet, max_trials=2) -> Optional[Vulnerability]:
        """
        This function:
        1. Reads the harness file
        2. Asks LLM for an input to the harness
        3. Runs harness with above input
        4. Repeat 2-3 until success or max. attempts
        """
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]
        # step 1: Read the harness file
        harness_path = self.project.harnesses[harness_id].file_path
        harness_text = harness_path.read_text().replace('\n', '')

        models = ["oai-gpt-4o", "claude-3.5-sonnet"]

        for model_name in models:
            for i in range(max_trials):
                # step 2: Ask LLM for an input to the harness
                logger.info(f"Attempting to trigger sanitizer {sanitizer_id} through the harness {harness_id} using model {model_name}")
                model = createChatClient(model_name)
                chain = (
                        harness_input_template
                        | model.with_structured_output(HarnessInput)
                        | (lambda response: response.harness_input)
                )
                harness_input = chain.invoke({
                    "harness_text": harness_text,
                    "code_snippet": code_snippet,
                    "sanitizer": sanitizer,
                    "error_code": error_code,
                })

                #  step 3: Run harness with above input
                harness_input_file = self.write_harness_input_to_disk(harness_input, i, harness_id, sanitizer_id, model_name)
                try:
                    has_sanitizer_triggered, stderr = self.project.run_harness_and_check_sanitizer(
                            harness_input_file,
                            harness_id,
                            sanitizer_id,
                    )
                    if has_sanitizer_triggered:
                        logger.info(f"Found vulnerability using harness {harness_id}: {sanitizer}: {error_code}")
                        return Vulnerability(harness_id, sanitizer_id, harness_input, harness_input_file)
                    else:
                        # TODO: give feedback to LLM using stderr?
                        ...

                except subprocess.TimeoutExpired:
                    # malformed input
                    # TODO: ask again?
                    ...

        # reached max. attempts
        logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
        return None

    def identify_bad_commits(self, vulnerabilities: List[Vulnerability]) -> List[VulnerabilityWithSha]:
        """
        Given a list of Vulnerabilities, this function:
        1. Gets list of commits and loops over them (latest to earliest)
        2. Reverts the Git repo to a commit i
        3. Tests the harness on commit i for each Vulnerability
        4. Assigns the vulnerability a commit when the previous commit does not trigger the sanitizer
        """

        # step 1: Get list of commits and loop over them (latest to earliest)
        git_repo, ref = self.project.repos.get(self.cp_source)
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
                    vuln.blob_file,
                    vuln.harness_id,
                    vuln.sanitizer_id,
                )

                if harness_triggered:
                    logger.debug(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
                    vulnerabilities_next.append(vuln)
                # step 4: When sanitizer is not triggered the previous commit introduced the vulnerability, assign previous commit as bug introducing
                else:
                    logger.info(f"Found bad commit: {previous_commit.hexsha} that introduced vulnerability {sanitizer}: {error_code}  ")
                    vulnerabilities_with_sha.append(VulnerabilityWithSha(previous_commit.hexsha, *vuln))
            previous_commit = inspected_commit

        # cleaning up:
        # reset repo back to head
        self.project.reset_source_repo(self.cp_source)
        # rebuild project at head
        self.project.build_project()

        return vulnerabilities_with_sha

    def run(self, project: ChallengeProject, cp_source: str) -> List[VulnerabilityWithSha]:
        self.project = project
        self.cp_source = cp_source

        # Detect vulnerabilities using LLMs
        vulnerabilities = self.detect_vulns_in_file("mock_vp.c")

        # Hardcoding values to test patch generation
        if self.project.name == "Mock CP" and len(vulnerabilities) < 2:
            logger.warning("Not all Mock CP vulnerabilities discovered")
            both = len(vulnerabilities) == 0
            if both or vulnerabilities[0].sanitizer_id == "id_2":
                mock_input_file = self.write_harness_input_to_disk(mock_input_data, 0, "id_1", "id_1", "mock")
                vulnerabilities.append(Vulnerability("id_1", "id_1", mock_input_data, mock_input_file))
            if both or vulnerabilities[0].sanitizer_id == "id_1":
                mock_input_file = self.write_harness_input_to_disk(mock_input_data_segv, 0, "id_1", "id_2", "mock")
                vulnerabilities.append(Vulnerability("id_1", "id_2", mock_input_data_segv, mock_input_file))

        vulnerabilities_with_sha = self.identify_bad_commits(vulnerabilities)

        return vulnerabilities_with_sha


vuln_discovery = VulnDiscovery()
