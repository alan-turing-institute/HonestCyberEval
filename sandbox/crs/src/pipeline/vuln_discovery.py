from pathlib import Path
from typing import Optional

from api.cp import ChallengeProjectReadOnly
from api.data_types import Vulnerability
from api.fs import write_harness_input_to_disk
from api.llm import LLMmodel, format_chat_history
from logger import logger
from params import VD_MAX_LLM_TRIALS

from .langgraph_vuln import run_vuln_langraph


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

    async def run(
        self,
        project_read_only: ChallengeProjectReadOnly,
        cp_source: str,
    ) -> list[Vulnerability]:
        self.project_read_only = project_read_only
        self.cp_source = cp_source
        vulnerabilities = []
        # model_name = "oai-gpt-4o"
        model_name = "o1-preview"
        # model_name = "o1-mini"

        if project_read_only.name == "Mock CP":
            answers = [
                ("cpv1", "id_1", "id_1", "mock_vp.c"),
                ("cpv2", "id_1", "id_2", "mock_vp.c"),
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
                (
                    "cpv14",
                    "id_2",
                    "id_5",
                    "src/http/ngx_http_script.c",
                ),  # cpv14 pov_harness, AddressSanitizer: global-buffer-overflow
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
                code_snippet=self.project_read_only.open_project_source_file(self.cp_source, file_path=Path(file_path)),
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


vuln_discovery = VulnDiscovery()
