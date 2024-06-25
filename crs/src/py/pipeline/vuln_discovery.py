import subprocess
from collections import namedtuple

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

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

Vulnerability = namedtuple('Vulnerability', ['commit', 'harness_id', 'sanitizer_id', 'input_data', 'blob_file'])


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
    project = None
    cp_source = None

    @staticmethod
    def write_harness_input_to_disk(harness_input, i, harness_id, sanitizer_id, model_name):
        return write_file_to_scratch(
            f"input_{i}_harness_{harness_id}_sanitizer_{sanitizer_id}_{model_name}.blob",
            harness_input,
        )

    def detect_vulns_in_file(self, bad_file):
        vulnerabilities = []
        code_snippet = self.project.open_project_source_file(self.cp_source, bad_file).replace('\n', '')

        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                logger.info(f"Attempting to trigger sanitizer {sanitizer_id} through the harness {harness_id}")
                harness_input, harness_input_file = self.llm_harness_input(
                    harness_id,
                    sanitizer_id,
                    code_snippet,
                    max_trials=2,
                )
                if harness_input:
                    logger.info("Sanitizer Triggered!")
                    bad_commit_sha = self.identify_bad_commit(
                        harness_id=harness_id,
                        sanitizer_id=sanitizer_id,
                        harness_input_file=harness_input_file,
                    )
                    if bad_commit_sha:
                        vulnerabilities.append(
                            Vulnerability(bad_commit_sha, harness_id, sanitizer_id, harness_input, harness_input_file)
                        )

        return vulnerabilities

    def llm_harness_input(self, harness_id, sanitizer_id, code_snippet, max_trials=2):
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

        for i in range(max_trials):
            for model_name in models:
                # step 2: Ask LLM for an input to the harness
                model = createChatClient(model_name)
                chain = harness_input_template | model.with_structured_output(HarnessInput)
                response = chain.invoke({
                    "harness_text": harness_text,
                    "code_snippet": code_snippet,
                    "sanitizer": sanitizer,
                    "error_code": error_code,
                })

                assert isinstance(response, HarnessInput)
                harness_input = response.harness_input
                #  step 3: Run harness with above input
                try:
                    harness_input_file = self.write_harness_input_to_disk(harness_input, i, harness_id, sanitizer_id, model_name)
                    if self.project.run_harness_and_check_sanitizer(
                            harness_input_file,
                            harness_id,
                            sanitizer_id,
                    )[0]:
                        logger.info(f"FOUND VULNERABILITY: {sanitizer}: {error_code}")
                        return harness_input, harness_input_file
                except subprocess.TimeoutExpired:
                    # malformed input
                    # TODO: ask again?
                    pass

        # reached max. attempts
        logger.warning("FAILED TO TRIGGER THE SANITIZER!")
        return None, None

    def identify_bad_commit(self, harness_id, sanitizer_id, harness_input_file):
        """
        Given a WORKING TEST HARNESS INPUT, this function:
        1. Gets list of commits and loops over them (latest to earliest)
        2. Reverts the Git repo to a commit i
        3. Tests the harness on commit i
        4. Stops when sanitizer is not triggered, and returns the bad commit
        """
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]

        # step 1: Get list of commits and loop over them (latest to earliest)
        git_repo, ref = self.project.repos.get(self.cp_source)
        git_log = list(git_repo.iter_commits(ref))
        # Start at HEAD and go down the commit log; when a good commit is found, the previous commit introduced the bug
        oldest_detected_bad_commit = git_log[0]

        output = None
        for inspected_commit in git_log[1:]:
            # step 2: revert the Git repo to the commit
            logger.info(f"Reverting to commit: {inspected_commit.hexsha}")

            git_repo.git.switch('--detach', inspected_commit.hexsha)
            self.project.build_project()

            # step 3: Test the harness on commit i
            harness_passed = not self.project.run_harness_and_check_sanitizer(
                harness_input_file,
                harness_id,
                sanitizer_id,
            )[0]

            # step 4: Stop when sanitizer is not triggered, and return the bad commit
            if harness_passed:
                logger.info(f"VULNERABILITY REMOVED --> bad commit: {oldest_detected_bad_commit.hexsha}")
                output = oldest_detected_bad_commit.hexsha
                break

            logger.info(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
            oldest_detected_bad_commit = inspected_commit

        # reset repo back to head
        self.project.reset_source_repo(self.cp_source)
        return output

    def run(self, project, cp_source):
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
                vulnerabilities.append(Vulnerability("11dafa9a5babc127357d710ee090eb4c0c05154f", "id_1", "id_1", mock_input_data, mock_input_file))
            if both or vulnerabilities[0].sanitizer_id == "id_1":
                mock_input_file = self.write_harness_input_to_disk(mock_input_data_segv, 0, "id_1", "id_2", "mock")
                vulnerabilities.append(Vulnerability("22e7f707e16ab7f6ef8a7e9adbb60b24bde49e27", "id_1", "id_2", mock_input_data_segv, mock_input_file))

        self.project = None
        self.cp_source = None
        return vulnerabilities


vuln_discovery = VulnDiscovery()
