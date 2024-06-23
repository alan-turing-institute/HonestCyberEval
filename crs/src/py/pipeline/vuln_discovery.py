import subprocess
from collections import namedtuple

from api.fs import write_file_to_scratch
from api.llm import llm_prompt_harness_input

Vulnerability = namedtuple('Vulnerability', ['commit', 'harness_id', 'sanitizer_id', 'input_data', 'blob_file'])

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""


class VulnDiscovery:
    project = None
    cp_source = None

    def detect_vulns_in_file(self, bad_file):
        vulnerabilities = []
        code_snippet = self.project.open_project_source_file(self.cp_source, bad_file).replace('\n', '')

        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                print(f"#######Attempting to trigger sanitizer {sanitizer_id} through the harness {harness_id}", flush=True)
                harness_input, harness_input_file = self.llm_harness_input(harness_id, sanitizer_id, code_snippet,
                                                                           max_trials=2)
                if harness_input:
                    print("Sanitizer Triggered!!")
                    bad_commit_sha = self.identify_bad_commit(
                        harness_id=harness_id,
                        sanitizer_id=sanitizer_id,
                        harness_input_file=harness_input_file,
                    )
                    if bad_commit_sha:
                        vulnerabilities.append(
                            Vulnerability(bad_commit_sha, harness_id, sanitizer_id, harness_input, harness_input_file))

        return vulnerabilities

    def llm_harness_input(self, harness_id, sanitizer_id, code_snippet, max_trials=2):
        """
        This function:
        1. Reads the harness file
        2. Creates an input message to the LLM
        3. Asks LLM for an input to the harness
        4. Extracts harness input from LLM output
        5. Runs harness with above input
        6. Repeat 3-5 until success or max. attempts
        """
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]
        # step 1: Read the harness file
        harness_path = self.project.harnesses[harness_id].file_path
        harness_text = harness_path.read_text().replace('\n', '')

        models = ["oai-gpt-4o", "claude-3-sonnet"]

        for i in range(max_trials):
            # step 2: Ask LLM for an input to the harness
            inputs = [
                (
                    model,
                    llm_prompt_harness_input(
                        model_name=model,
                        harness_text=harness_text,
                        code_snippet=code_snippet,
                        sanitizer=sanitizer,
                        error_code=error_code,
                    )
                ) for model in models
            ]
            for model, harness_input in inputs:
                #  step 3: Run harness with above input
                try:
                    harness_input_file = write_file_to_scratch(
                        f"input_{i}_harness_{harness_id}_sanitizer_{sanitizer_id}_{model}.blob",
                        harness_input,
                    )
                    if self.project.run_harness_and_check_sanitizer(
                            harness_input_file,
                            harness_id,
                            sanitizer_id,
                    )[0]:
                        print(f"FOUND VULNERABILITY: {sanitizer}: {error_code}")
                        return harness_input, harness_input_file
                except subprocess.TimeoutExpired:
                    # malformed input
                    # TODO: ask again?
                    pass

        # reached max. attempts
        print("FAILED TO TRIGGER THE SANITIZER!!")
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
            print("----", f"Reverting to commit: {inspected_commit.hexsha}", sep="\n")

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
                print(f"VULNERABILITY REMOVED --> bad commit: {oldest_detected_bad_commit.hexsha}")
                output = oldest_detected_bad_commit.hexsha
                break

            print(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
            oldest_detected_bad_commit = inspected_commit

        # reset repo back to head
        self.project.reset_source_repo(self.cp_source)
        return output

    def run(self, project, cp_source):
        self.project = project
        self.cp_source = cp_source

        vulnerabilities = self.detect_vulns_in_file("mock_vp.c")

        self.project = None
        self.cp_source = None
        return vulnerabilities


vuln_discovery = VulnDiscovery()
