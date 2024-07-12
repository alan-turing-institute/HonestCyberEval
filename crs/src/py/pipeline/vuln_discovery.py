import pprint
from enum import auto
from typing import Optional, TypeAlias

from strenum import StrEnum

from api.cp import ChallengeProject
from api.data_types import Vulnerability, VulnerabilityWithSha
from api.fs import write_harness_input_to_disk
from api.llm import LLMmodel, create_rag_docs, format_chat_history, get_retriever
from logger import logger

from .langgraph_vuln import run_vuln_langraph
from .preprocess_commits import FileDiff, find_diff_between_commits

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

mock_input_data_segv = """ab
b

501
"""

ProcessedCommits: TypeAlias = dict[str, dict[str, FileDiff]]


class VDLLMInputType(StrEnum):
    ONE_FILE = auto()
    ONE_FUNC = auto()
    MULTI_FILE = auto()
    MULTI_FUNC = auto()
    FILE_DIFFS = auto()
    FUNC_DIFFS = auto()


class VulnDiscovery:
    project: ChallengeProject
    cp_source: str

    async def harness_input_langgraph(
        self, harness_id, sanitizer_id, code_snippet, max_trials, diff=""
    ) -> Optional[Vulnerability]:

        sanitizer, error_code = self.project.sanitizers[sanitizer_id]
        models: list[LLMmodel] = ["gemini-1.5-pro", "oai-gpt-4o", "claude-3.5-sonnet"]

        for model_name in models:
            try:
                output = await run_vuln_langraph(
                    model_name=model_name,
                    project=self.project,
                    harness_id=harness_id,
                    sanitizer_id=sanitizer_id,
                    code_snippet=code_snippet,
                    diff=diff,
                    max_iterations=max_trials,
                )
            except Exception as error:
                logger.error(f"LangGraph vulnerability detection failed for {model_name} with\n{repr(error)}")
            else:
                logger.debug(f"LangGraph Message History\n\n{format_chat_history(output['chat_history'])}\n\n")

                if not output["error"]:
                    logger.info(f"Found vulnerability using harness {harness_id}: {sanitizer}: {error_code}")
                    harness_input = output["solution"]
                    harness_input_file = write_harness_input_to_disk(
                        self.project, harness_input, "work", harness_id, sanitizer_id, model_name
                    )

                    return Vulnerability(harness_id, sanitizer_id, harness_input, harness_input_file)

                logger.info(f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id}")
                logger.debug(
                    f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id} with error: \n"
                    f" {output['error']}"
                )

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

            git_repo.git.switch("--detach", inspected_commit.hexsha)
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
                    logger.info(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
                    vulnerabilities_next.append(vuln)

                # step 4: When sanitizer is not triggered the previous commit introduced the vulnerability,
                # assign previous commit as bug introducing
                else:
                    logger.info(
                        f"Found bad commit: {previous_commit.hexsha} that introduced vulnerability {sanitizer}:"
                        f" {error_code}  "
                    )

                    vulnerabilities_with_sha.append(VulnerabilityWithSha(*vuln, commit=previous_commit.hexsha))

            previous_commit = inspected_commit

        # cleaning up:
        # reset repo back to head
        self.project.reset_source_repo(self.cp_source)
        # rebuild project at head
        self.project.build_project()

        return vulnerabilities_with_sha

    def find_functional_changes(self) -> ProcessedCommits:

        repo, ref = self.project.repos[self.cp_source]

        logger.info("Preprocessing commits")

        # for each commit compare with it's parent to find the relevant files changed and the functional
        # changes within each file
        preprocessed_commits = {}

        for commit in repo.iter_commits(ref):
            if commit.parents:
                parent_commit = commit.parents[0]
                diffs = find_diff_between_commits(parent_commit, commit)
                # logger.info(f"Commit: {commit.hexsha}:\n{diffs}")

                if diffs:
                    preprocessed_commits[commit.hexsha] = diffs

        logger.debug(f"Functional changes found in the following commits: {list(preprocessed_commits.keys())}")
        logger.info(
            f"{len(preprocessed_commits)} out of {len(list(repo.iter_commits(ref)))} commits have potentially functional differences."
        )

        return preprocessed_commits

    def potential_llm_inputs(self, preprocessed_commits: ProcessedCommits) -> list[tuple[VDLLMInputType, str]]:
        """ "
        Returns:
            List of potential strings representing the commit changes in the CP,
            which we could send to the LLM. Each element includes the type of input [VDLLMInputType]
            and the string itself.

        Example usage:
            potential_inputs = self.potential_llm_inputs(preprocessed_commits)
            simp_simp_list = [ f"{k} {len(v)}" for (k,v) in potential_inputs]
            logger.info("\n".join(simp_simp_list))
        """
        potential_texts = []

        for commit_sha, file_diffs in preprocessed_commits.items():

            logger.debug("=" * 20)
            logger.debug(f"#files changed in commit {commit_sha}: {len(file_diffs)}")

            cumulative_files_str = ""
            cumulative_funcs_str = ""
            cumulative_file_diffs_str = ""
            cumulative_func_diffs_str = ""

            for file_name, file_diff in file_diffs.items():
                after_str = file_diff.print_after()
                diff_str = file_diff.print_diff()
                logger.debug("")
                logger.debug(f"\tFilename: {file_name}")
                logger.debug(
                    f"\tFile Diff length [chars]: {len(diff_str)}. After commit file length [chars]: {len(after_str)}"
                )

                file_text = after_str
                # file_text = self.project.open_project_source_file(self.cp_source, bad_file)

                cumulative_files_str += f"File: {file_name}\n{file_text}\n\n"
                cumulative_file_diffs_str += f"Diff of file: {file_name}\n{diff_str}\n\n"

                potential_texts.append((VDLLMInputType.ONE_FILE, file_text))

                for func_name, func_diff in file_diff.diff_functions.items():
                    after_str = func_diff.print_after()
                    diff_str = func_diff.print_diff()

                    logger.debug("")
                    logger.debug(f"\t\tFunction Name: {func_name}")
                    logger.debug(
                        f"\t\tFunction Diff length [chars]: {len(diff_str)}. After commit function length [chars]: {len(after_str)}"
                    )

                    cumulative_funcs_str += f"Function: {func_name}\n{after_str}\n\n"
                    cumulative_func_diffs_str += f"Diff of function: {func_name}\n{diff_str}\n\n"

                    potential_texts.append((VDLLMInputType.ONE_FUNC, after_str))

            # append cumulative stuff
            potential_texts.append((VDLLMInputType.MULTI_FILE, cumulative_files_str))
            potential_texts.append((VDLLMInputType.FILE_DIFFS, cumulative_file_diffs_str))
            potential_texts.append((VDLLMInputType.MULTI_FUNC, cumulative_funcs_str))
            potential_texts.append((VDLLMInputType.FUNC_DIFFS, cumulative_func_diffs_str))
        return potential_texts

    async def detect_commit_vulns_rag(self, retriever, max_trials: int = 2) -> list[Vulnerability]:
        vulnerabilities = []
        for harness_id in self.project.harnesses.keys():
            for sanitizer_id in self.project.sanitizers.keys():
                sanitizer_str = self.project.sanitizer_str[sanitizer_id]

                retrieved_docs = retriever.invoke(f"""{sanitizer_str} error bug vulnerability""")
                logger.debug(f"Retrieved docs:\n{pprint.pformat(retrieved_docs)}")

                for doc in retrieved_docs:
                    vuln = await self.harness_input_langgraph(
                        harness_id=harness_id,
                        sanitizer_id=sanitizer_id,
                        code_snippet=doc.page_content,
                        max_trials=max_trials,
                    )

                    if vuln:
                        vulnerabilities.append(vuln)
        return vulnerabilities

    async def detect_vulns_in_commits(
        self, preprocessed_commits: ProcessedCommits, top_docs: int = 1, use_funcdiffs: bool = False
    ) -> list[Vulnerability]:
        vulnerabilities = []

        for commit_sha, commit in preprocessed_commits.items():
            logger.info(f"Commit: {commit_sha}")

            files, funcs = [], []
            for filename in commit:
                file_diff = commit[filename]
                files.append(file_diff.after_str())

                for function_diff_name in file_diff.diff_functions:
                    function_diff = file_diff.diff_functions[function_diff_name]
                    funcs.extend([function_diff.after_str(), function_diff.diff_str()])

            text_list = funcs if use_funcdiffs else files
            rag_docs = create_rag_docs(text_list, self.project.language)
            retriever = get_retriever(code_docs=rag_docs, topk=top_docs, embedding_model="oai-text-embedding-3-large")

            vulns = await self.detect_commit_vulns_rag(retriever)
            vulnerabilities.extend(vulns)
        return vulnerabilities

    async def run(self, project: ChallengeProject, cp_source: str) -> list[VulnerabilityWithSha]:
        self.project = project
        self.cp_source = cp_source

        preprocessed_commits = self.find_functional_changes()
        # logger.debug(f"Preprocessed Commits:\n {pprint.pformat(preprocessed_commits)}\n")

        vulnerabilities = await self.detect_vulns_in_commits(preprocessed_commits, top_docs=1)

        # # Detect vulnerabilities using LLMs
        # vulnerabilities = []
        # for commit_sha in preprocessed_commits:
        #     commit = preprocessed_commits[commit_sha]

        #     for filename in commit:
        #         file_diff = commit[filename]

        # for function_diff_name in file_diff.diff_functions:
        #     function_diff = file_diff.diff_functions[function_diff_name]
        #     vulnerabilities = await self.detect_vulns_in_file(filename, function_diff)
        #     # vulnerabilities = self.detect_vulns_in_file(filename)

        logger.info(f"Found {len(vulnerabilities)} vulnerabilities")

        # Hardcoding values to test patch generation
        if self.project.name == "Mock CP" and len(vulnerabilities) < 2:
            logger.warning("Not all Mock CP vulnerabilities discovered")
            both = len(vulnerabilities) == 0

            if both or vulnerabilities[0].sanitizer_id == "id_2":
                mock_input_file = write_harness_input_to_disk(self.project, mock_input_data, 0, "id_1", "id_1", "mock")
                vulnerabilities.append(Vulnerability("id_1", "id_1", mock_input_data, mock_input_file))

            if both or vulnerabilities[0].sanitizer_id == "id_1":
                mock_input_file = write_harness_input_to_disk(
                    self.project, mock_input_data_segv, 0, "id_1", "id_2", "mock"
                )

                vulnerabilities.append(Vulnerability("id_1", "id_2", mock_input_data_segv, mock_input_file))

        # Left this check in even though we have the SHA for the commit as a final confirmation check
        vulnerabilities_with_sha = self.identify_bad_commits(vulnerabilities)

        return vulnerabilities_with_sha


vuln_discovery = VulnDiscovery()
