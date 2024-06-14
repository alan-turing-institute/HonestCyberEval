from collections import namedtuple

from api.fs import write_file_to_scratch

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

    def run(self, project, cp_source):
        self.project = project
        self.cp_source = cp_source

        git_results = self.analyse_git()
        vulnerabilities = self.generate_harness_inputs(git_results)

        self.project = None
        self.cp_source = None
        return vulnerabilities


vuln_discovery = VulnDiscovery()
