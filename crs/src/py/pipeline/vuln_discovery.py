from collections import namedtuple
import re

from api.fs import write_file_to_scratch
from api.llm import send_msg_to_llm

Vulnerability = namedtuple('Vulnerability', ['commit', 'harness_id', 'sanitizer_id', 'input_data', 'blob_file'])

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""


class VulnDiscovery:
    project = None
    cp_source = None

    def analyse_git(self):
        git_repo, ref = self.project.repos.get(self.cp_source)
        git_repo.git.reset('--hard')
        git_log = list(git_repo.iter_commits(ref, max_count=2))
        for commit in git_log:
            print(commit.hexsha, commit.message, commit.stats.files, sep="\n")

        bad_file = "mock_vp.c"
        bad_commit_sha1 = "9d38fc63bb9ffbc65f976cbca45e096bad3b30e1"

        return [(bad_file, bad_commit_sha1)]

    def generate_harness_inputs(self, files_and_shas):
        vulnerabilities = []
        for bad_file, bad_commit_sha in files_and_shas:
            with self.project.open_project_source_file(self.cp_source, bad_file) as code_file:
                code_snippet = code_file.read().replace('\n', '')
                # print(send_msg_to_llm(
                #     "oai-gpt-3.5-turbo",
                #     f"Could you find the vulnerabilities in:\n {code_snippet}\nBe brief",
                # ))
                harness_id = "id_1"
                sanitizer_id = "id_1"

                # loop over input logic until we trigger harness
                while True:
                    input_data = mock_input_data
                    blob_file = write_file_to_scratch(f"{harness_id}_{sanitizer_id}input.blob", input_data)
                    if self.project.run_harness_and_check_sanitizer(blob_file, harness_id, sanitizer_id):
                        vulnerabilities.append(
                            Vulnerability(bad_commit_sha, harness_id, sanitizer_id, input_data, blob_file))
                        break
            return vulnerabilities

    def detect_vulns_in_file(self, bad_file):
        vulnerabilities = []
        with self.project.open_project_source_file(self.cp_source, bad_file) as code_file:
            code_snippet = code_file.read().replace('\n', '')

        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                print(f"#######Attempting to trigger sanitizer {sanitizer_id} through the harness {harness_id}")
                harness_input, harness_input_file = self.llm_harness_input(harness_id, sanitizer_id, code_snippet,
                                                                           max_trials=2)
                if harness_input:
                    print("Sanitizer Triggered!!")
                    bad_commit_sha = self.identify_bad_commit(
                        harness_id=harness_id,
                        sanitizer_id=sanitizer_id,
                        harness_input_file=harness_input_file,
                    )
                    vulnerabilities.append(
                        Vulnerability(bad_commit_sha, harness_id, sanitizer_id, harness_input, harness_input_file))

        return vulnerabilities

    # TODO: should be moved to api.llm or elsewhere
    def llm_prompt_harness_input(self, harness_text="", code_snippet="", sanitizer="", error_code=""):
        message = f""" Generate an input txt file for the following test harness:
            {harness_text}
            . The harness should exercise the code:
            {code_snippet}
            . The harness should cause the code to trigger a {sanitizer}: {error_code} error.
            You should output only the txt file, and you should start and end the txt file with the following ```"""
        return message

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
        with open(self.project.harnesses[harness_id].file_path, "r") as f:
            harness_text = f.read()

        # step 2: Create an input message to the LLM
        message = self.llm_prompt_harness_input(
            harness_text=harness_text,
            code_snippet=code_snippet,
            sanitizer=sanitizer,
            error_code=error_code,
        )

        for _ in range(max_trials):
            # step 3: Ask LLM for an input to the harness
            models = ["oai-gpt-4o", "claude-3-sonnet"]
            llm_harness_input_list = [
                (model, send_msg_to_llm(model_name=model, message=message))
                for model in models]

            for model, output in llm_harness_input_list:
                # step 4: Extract harness input from LLM output
                found_blobs = re.findall("```[\s\S]*```", output)
                harness_input = found_blobs[0][3:-3].strip()
                print(f"Extracted blob from {model}:", "====", harness_input, "====", sep="\n")

                #  step 5: Run harness with above input
                harness_input_file = write_file_to_scratch(f"{harness_id}_{sanitizer_id}input.blob", harness_input)
                if self.project.run_harness_and_check_sanitizer(harness_input_file, harness_id, sanitizer_id):
                    print(f"FOUND VULNERABILITY: {sanitizer}: {error_code}")
                    return harness_input, harness_input_file

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
        oldest_detected_bad_commit = git_log[0]
        # we skip HEAD (100% vulnerable) and initial (100% safe)

        output = None
        for inspected_commit in git_log[1:-1]:
            # step 2: revert the Git repo to the commit
            print("----", f"Reverting to commit: {inspected_commit.hexsha}", sep="\n")

            self.project.reset_source_repo(self.cp_source)
            git_repo.git.checkout(inspected_commit.hexsha)
            self.project.build_project()

            # step 3: Test the harness on commit i
            harness_passed = not self.project.run_harness_and_check_sanitizer(harness_input_file, harness_id, sanitizer_id)

            # step 4: Stop when sanitizer is not triggered, and return the bad commit
            if harness_passed:
                print(f"VULNERABILITY REMOVED --> bad commit: {oldest_detected_bad_commit.hexsha}")
                output = oldest_detected_bad_commit.hexsha
                break

            print(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
            oldest_detected_bad_commit = inspected_commit

        # reset repo back to head
        git_repo.git.checkout(ref)
        return output

    def run(self, project, cp_source):
        self.project = project
        self.cp_source = cp_source

        # git_results = self.analyse_git()
        # vulnerabilities = self.generate_harness_inputs(git_results)
        # bad_comit_sha = self.identify_bad_commit(harness_id="id_1", 
        #                          sanitizer_id="id_1", 
        #                          harness_input="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\nBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\nCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\n\n2")
        vulnerabilities = self.detect_vulns_in_file("mock_vp.c")

        self.project = None
        self.cp_source = None
        return vulnerabilities


vuln_discovery = VulnDiscovery()
