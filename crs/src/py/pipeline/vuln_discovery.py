import asyncio
import pprint
import random
from dataclasses import asdict
from itertools import product
from pathlib import Path
from typing import Optional

from params import (
    VD_CHOSEN_DETAIL_LEVEL,
    VD_MAX_LLM_TRIALS,
    # VD_MODEL_LIST,
    VD_TOP_RAG_DOCS,
    VDDetailLevel,
)

from api.cp import ChallengeProjectReadOnly
from api.data_types import Vulnerability, VulnerabilityWithSha
from api.fs import write_harness_input_to_disk
from api.llm import (
    LLMmodel,
    add_docs_to_vectorstore,
    create_rag_docs,
    create_vector_store,
    format_chat_history,
)
from logger import logger

from .langgraph_vuln import run_vuln_langraph
from .preprocess_commits import ProcessedCommits

mock_input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

mock_input_data_segv = """ab
b

501
"""


def remove_duplicate_vulns(
    vulnerabilities: list[VulnerabilityWithSha],
) -> list[VulnerabilityWithSha]:
    # create vulnerability bucket for each commit
    commit_buckets = {vuln.commit: [] for vuln in vulnerabilities}
    for vuln in vulnerabilities:
        commit_buckets[vuln.commit].append(vuln)

    # deduplicate each bucket
    deduped_commit_buckets = {}
    for commit, commit_vuln_list in commit_buckets.items():
        accepted_vulns = [vuln for vuln in commit_vuln_list if vuln.status == "accepted"]
        if accepted_vulns:
            # if vulnerability already submitted for commit and accepted
            accepted_vuln = accepted_vulns[0]
            deduped_commit_buckets[commit] = [accepted_vuln]
        else:
            deduped_dict = {
                (vuln.harness_id, vuln.sanitizer_id): vuln
                for vuln in commit_vuln_list
                # if vulnerability already submitted for commit and rejected, filter it out, submit something else
                if vuln.status != "rejected"
            }
            deduped_list = list(deduped_dict.values())
            deduped_commit_buckets[commit] = deduped_list

    # choose vulnerabilities that maximizes coverage
    vuln_combinations = product(*[commit_vuln_list for commit_vuln_list in deduped_commit_buckets.values()])
    best_coverage = 0
    deduped_vuln_list = []
    for vuln_list in vuln_combinations:
        num_unique_sanitizers = len(set([vuln.sanitizer_id for vuln in vuln_list]))
        if num_unique_sanitizers > best_coverage:
            deduped_vuln_list = list(vuln_list)
            best_coverage = num_unique_sanitizers

    logger.info(f"Compressed {len(vulnerabilities)} vulnerabilities into {len(deduped_vuln_list)} unique ones")
    return deduped_vuln_list


class VulnDiscovery:
    project_read_only: ChallengeProjectReadOnly
    cp_source: str

    async def harness_input_langgraph(
        self, model_name, harness_id, sanitizer_id, code_snippet, max_trials, diff=""
    ) -> Optional[Vulnerability]:
        sanitizer, error_code = self.project_read_only.sanitizers[sanitizer_id]

        try:
            project = await self.project_read_only.writeable_copy_async
            output = await run_vuln_langraph(
                model_name=model_name,
                project=project,
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
                    project, harness_input, "work", harness_id, sanitizer_id, model_name
                )

                return Vulnerability(harness_id, sanitizer_id, harness_input, harness_input_file, self.cp_source)

            logger.info(f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id}")
            logger.debug(
                f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id} with error: \n"
                f" {output['error']}"
            )

        return

    # async def identify_bad_commits(self, vulnerabilities: list[Vulnerability]) -> list[VulnerabilityWithSha]:
    #     """
    #     Given a list of Vulnerabilities, this function:
    #     1. Gets list of commits and loops over them (latest to earliest)
    #     2. Reverts the Git repo to a commit i
    #     3. Tests the harness on commit i for each Vulnerability
    #     4. Assigns the vulnerability a commit when the previous commit does not trigger the sanitizer
    #     """
    #
    #     # step 1: Get list of commits and loop over them (latest to earliest)
    #     project = await self.project_read_only.writeable_copy_async
    #     git_repo, ref = project.repos[self.cp_source]
    #     git_log = list(git_repo.iter_commits(ref))
    #     # Start at HEAD and go down the commit log
    #     previous_commit = git_log[0]
    #
    #     vulnerabilities_with_sha = []
    #
    #     # check vulnerabilities for oldest commit they're found in
    #     vulnerabilities_next = vulnerabilities
    #
    #     for inspected_commit in git_log[1:]:
    #         if not vulnerabilities_next:
    #             # no vulnerabilities left without commit that introduced them, stop searching
    #             break
    #
    #         vulnerabilities_left = vulnerabilities_next
    #         vulnerabilities_next = []
    #
    #         # step 2: revert the Git repo to the commit
    #         logger.debug(f"Reverting to commit: {inspected_commit.hexsha}")
    #
    #         async with project.build_lock:
    #             git_repo.git.switch("--detach", inspected_commit.hexsha)
    #             await project.build_project()
    #
    #             for vuln in vulnerabilities_left:
    #                 sanitizer, error_code = project.sanitizers[vuln.sanitizer_id]
    #
    #                 # step 3: Test the harness on commit i
    #                 harness_triggered, _ = await project.run_harness_and_check_sanitizer(
    #                     vuln.input_file,
    #                     vuln.harness_id,
    #                     vuln.sanitizer_id,
    #                 )
    #
    #                 if harness_triggered:
    #                     logger.info(f"VULNERABILITY STILL EXISTS: {sanitizer}: {error_code}")
    #                     vulnerabilities_next.append(vuln)
    #
    #                 # step 4: When sanitizer is not triggered the previous commit introduced the vulnerability,
    #                 # assign previous commit as bug introducing
    #                 else:
    #                     logger.info(
    #                         f"Found bad commit: {previous_commit.hexsha} that introduced vulnerability {sanitizer}:"
    #                         f" {error_code}  "
    #                     )
    #
    #                     vulnerabilities_with_sha.append(
    #                         VulnerabilityWithSha(**(asdict(vuln)), commit=previous_commit.hexsha)
    #                     )
    #
    #             previous_commit = inspected_commit
    #
    #     # cleaning up:
    #     # reset repo back to head
    #     project.reset_source_repo(self.cp_source)
    #     # rebuild project at head
    #     await project.build_project()
    #
    #     return vulnerabilities_with_sha

    # async def detect_vulns_norag(self, docs, max_trials: int = VD_MAX_LLM_TRIALS) -> list[Vulnerability]:
    #     vulnerabilities = []
    #     for harness_id in self.project_read_only.harnesses.keys():
    #         for sanitizer_id in self.project_read_only.sanitizers.keys():
    #             for doc in docs:
    #                 logger.debug(f"Using document:\n{pprint.pformat(doc)}")
    #                 logger.info(f"Using document: {doc.metadata}")
    #
    #                 vulns = await asyncio.gather(*[
    #                     self.harness_input_langgraph(
    #                         model_name=model_name,
    #                         harness_id=harness_id,
    #                         sanitizer_id=sanitizer_id,
    #                         code_snippet=doc.page_content,
    #                         max_trials=max_trials,
    #                     )
    #                     for model_name in VD_MODEL_LIST
    #                 ])
    #                 vulns = [vuln for vuln in vulns if vuln]
    #                 if not vulns:
    #                     logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
    #                 for vuln in vulns:
    #                     vulnerabilities.append(vuln)
    #     return vulnerabilities

    # async def detect_vulns_rag(self, retriever, max_trials: int = VD_MAX_LLM_TRIALS) -> list[Vulnerability]:
    #     vulnerabilities = []
    #     for harness_id in self.project_read_only.harnesses.keys():
    #         for sanitizer_id in self.project_read_only.sanitizers.keys():
    #             sanitizer_str = self.project_read_only.sanitizer_str[sanitizer_id]
    #
    #             retrieved_docs = retriever.invoke(f"""{sanitizer_str} memory error bug vulnerability""")
    #             logger.debug(f"Retrieved docs:\n{pprint.pformat(retrieved_docs)}")
    #
    #             for doc in retrieved_docs:
    #                 logger.debug(f"Using document:\n{pprint.pformat(doc)}")
    #                 logger.info(f"Using document: {doc.metadata}")
    #
    #                 vulns = await asyncio.gather(*[
    #                     self.harness_input_langgraph(
    #                         model_name=model_name,
    #                         harness_id=harness_id,
    #                         sanitizer_id=sanitizer_id,
    #                         code_snippet=doc.page_content,
    #                         max_trials=max_trials,
    #                     )
    #                     for model_name in VD_MODEL_LIST
    #                 ])
    #                 vulns = [vuln for vuln in vulns if vuln]
    #                 if not vulns:
    #                     logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
    #                 for vuln in vulns:
    #                     vulnerabilities.append(vuln)
    #     return vulnerabilities

    # async def detect_with_unified_vectorstore(
    #     self,
    #     preprocessed_commits: ProcessedCommits,
    #     top_docs: int = 1,
    #     detail_level: VDDetailLevel = VDDetailLevel.LATEST_FILES,
    # ) -> list[Vulnerability]:
    #
    #     files_latest, files, file_diffs, funcs, func_diffs = [], [], [], [], []
    #     file_paths, func_paths, func_names, file_commits, func_commits = [], [], [], [], []
    #     vectorstore = create_vector_store()
    #
    #     for commit_sha, commit in preprocessed_commits.items():
    #
    #         for filename in commit:
    #             file_diff = commit[filename]
    #             file_path = file_diff.filepath
    #
    #             try:
    #                 file_latest = self.project_read_only.open_project_source_file(
    #                     self.cp_source, file_path=Path(file_path)
    #                 )
    #             except FileNotFoundError:
    #                 logger.warning(f"The file {file_path} was not found")
    #             else:
    #                 # populate lists of strings
    #                 files.append(file_diff.after_str())
    #                 file_diffs.append(file_diff.diff_str())
    #                 files_latest.append(file_latest)
    #                 file_commits.append(commit_sha)
    #                 file_paths.append(file_path)
    #
    #                 for function_diff_name in file_diff.diff_functions:
    #                     function_diff = file_diff.diff_functions[function_diff_name]
    #
    #                     # populate list of strings
    #                     funcs.append(function_diff.after_str())
    #                     func_diffs.append(function_diff.diff_str())
    #                     func_commits.append(commit_sha)
    #                     func_paths.append(file_path)
    #                     func_names.append(function_diff_name)
    #
    #     metadatas = []
    #     match detail_level:
    #         case VDDetailLevel.LATEST_FILES:
    #             unique_paths, text_list = [], []
    #             for text, path in zip(files_latest, file_paths):
    #                 if path not in unique_paths:
    #                     unique_paths.append(path)
    #                     text_list.append(text)
    #             metadatas = [{"file": filename} for filename in unique_paths]
    #         case VDDetailLevel.COMMIT_FILES:
    #             text_list = files
    #             metadatas = [
    #                 {"commit": commit_sha, "file": filename} for commit_sha, filename in zip(file_commits, file_paths)
    #             ]
    #         case VDDetailLevel.COMMIT_FUNCS:
    #             text_list = funcs
    #             metadatas = [
    #                 {"commit": commit_sha, "file": filename, "function": funcname}
    #                 for commit_sha, filename, funcname in zip(func_commits, func_paths, func_names)
    #             ]
    #         case VDDetailLevel.FILE_DIFFS:
    #             text_list = file_diffs
    #             metadatas = [
    #                 {"commit": commit_sha, "file": filename} for commit_sha, filename in zip(file_commits, file_paths)
    #             ]
    #         case VDDetailLevel.FUNC_DIFFS:
    #             text_list = func_diffs
    #             metadatas = [
    #                 {"commit": commit_sha, "file": filename, "function": funcname}
    #                 for commit_sha, filename, funcname in zip(func_commits, func_paths, func_names)
    #             ]
    #
    #     rag_docs = create_rag_docs(text_list, self.project_read_only.language, metadatas=metadatas)
    #
    #     try:
    #         vectorstore = await add_docs_to_vectorstore(rag_docs, vectorstore)
    #     except Exception as error:
    #         logger.info(f"RAG Failed: {error}")
    #         logger.info("Proceeding with randomly chosen documents")
    #         return await self.detect_vulns_norag(random.sample(rag_docs, k=min(top_docs, len(rag_docs))))
    #
    #     logger.info(f"Total number of RAG docs in vector store: {len(vectorstore. get()['documents'])}")
    #     retriever = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": top_docs})
    #
    #     return await self.detect_vulns_rag(retriever)

    async def run(
        self,
        project_read_only: ChallengeProjectReadOnly,
        cp_source: str,
        preprocessed_commits: ProcessedCommits,
    ) -> list[VulnerabilityWithSha]:
        self.project_read_only = project_read_only
        self.cp_source = cp_source
        vulnerabilities = []
        # model_name = "oai-gpt-4o"
        model_name = "o1-preview"
        # model_name = "o1-mini"

        if project_read_only.name == "Mock CP":
            answers = [
                ('cpv1', "id_1", "id_1", "mock_vp.c"),
                ('cpv2', "id_1", "id_2", "mock_vp.c"),
            ]
        elif project_read_only.name == "nginx":
            answers = [
                # cpv, harness_id, sanitizer_id
                # ('cpv1', 'id_2', 'id_2', 'src/http/ngx_http_request.c'), # cpv1 pov_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv2', 'id_2', 'id_2', 'src/http/ngx_http_core_module.c'), # cpv2 pov_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv3', 'id_2', 'id_2', 'src/http/ngx_http_request.c'), # cpv3 pov_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv4', 'id_2', 'id_2', 'src/http/ngx_http_core_module.c'), # cpv4 pov_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv5', 'id_2', 'id_1', 'src/core/ngx_cycle.c'), # cpv5 pov_harness, AddressSanitizer: SEGV
                # # cpv6, cpv7 missing
                # ('cpv8', 'id_1', 'id_2', 'src/mail/ngx_mail_pop3_handler.c'), # cpv8 mail_request_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv9', 'id_2', 'id_4', 'src/core/ngx_cycle.c'), # cpv9 pov_harness, AddressSanitizer: heap-use-after-free
                # ('cpv10', 'id_2', 'id_3', 'src/http/ngx_http_request.c'), # cpv10 pov_harness, AddressSanitizer: attempting double-free
                # ('cpv11', 'id_2', 'id_4', 'src/core/ngx_cycle.c'), # cpv11 pov_harness, AddressSanitizer: heap-use-after-free
                # ('cpv12', 'id_2', 'id_2', 'src/os/unix/ngx_linux_sendfile_chain.c'), # cpv12 pov_harness, AddressSanitizer: heap-buffer-overflow
                # ('cpv13', 'id_1', 'id_1', 'src/mail/ngx_mail_pop3_handler.c'), # cpv13 mail_request_harness, AddressSanitizer: SEGV
                ('cpv14', 'id_2', 'id_5', 'src/http/ngx_http_script.c'), # cpv14 pov_harness, AddressSanitizer: global-buffer-overflow
                # ('cpv15', 'id_2', 'id_1', 'src/http/modules/ngx_http_userid_filter_module.c'), # cpv15 pov_harness, AddressSanitizer: SEGV
                # # cpv16 missing
                # ('cpv17', "id_3", "id_4", "src/mail/ngx_mail_smtp_handler.c"),  # cpv17 smtp_harness, AddressSanitizer: heap-use-after-free
            ]
        else:
            answers = []
        for cpv, harness_id, sanitizer_id, file_path in answers:
            logger.info(f"attempting {cpv}")
            logger.info(f"==========================================")
            vuln = await self.harness_input_langgraph(
                model_name=model_name,
                harness_id=harness_id,
                sanitizer_id=sanitizer_id,
                code_snippet=self.project_read_only.open_project_source_file(
                    self.cp_source, file_path=Path(file_path)
                ),
                max_trials=VD_MAX_LLM_TRIALS,
            )

            if not vuln:
                logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
            else:
                vulnerabilities.append(vuln)

        logger.info(f"Found {len(vulnerabilities)} vulnerabilities")
        for vuln in vulnerabilities:
            logger.info(f"{vuln.harness_id}, {vuln.sanitizer_id},{vuln.input_file}\n{vuln.input_data}")
        return vulnerabilities
        # return await self.identify_bad_commits(vulnerabilities)


vuln_discovery = VulnDiscovery()
