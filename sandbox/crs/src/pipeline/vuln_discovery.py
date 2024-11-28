from pathlib import Path
from typing import Optional

from api.cp import ChallengeProject
from api.data_types import Vulnerability
from api.fs import write_harness_input_to_disk
from api.llm import format_chat_history
from logger import logger
from params import VD_MAX_LLM_TRIALS

from .langgraph_vuln import run_vuln_langraph


class VulnDiscovery:
    project: ChallengeProject
    cp_source: str

    async def harness_input_langgraph(
        self, model_name, harness_id, sanitizer_id, code_snippet, max_trials, diff=""
    ) -> Optional[Vulnerability]:
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]

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

                return Vulnerability(harness_id, sanitizer_id, harness_input, harness_input_file, self.cp_source)

            logger.info(f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id}")
            logger.debug(
                f"{model_name} failed to trigger sanitizer {sanitizer_id} using {harness_id} with error: \n"
                f" {output['error']}"
            )

        return

    async def run(
        self,
        project:ChallengeProject,
        cp_source: str,
        cpv: str,
        llms: list[str],
        harness_id: str,
        sanitizer_id: str,
        files: list[Path],
    ):
        self.project = project
        self.cp_source = cp_source

        vulnerabilities=[]

        code = "\n".join([
            self.project.open_project_source_file(cp_source, file_path)
            for file_path in files
        ])
        for model_name in llms:
            logger.info(f"attempting {cpv} using {model_name}")
            logger.info(f"==========================================")
            vuln = await self.harness_input_langgraph(
                model_name=model_name,
                harness_id=harness_id,
                sanitizer_id=sanitizer_id,
                code_snippet=code,
                max_trials=VD_MAX_LLM_TRIALS,
            )

            if not vuln:
                logger.warning(f"Failed to trigger sanitizer {sanitizer_id} using {harness_id}!")
            else:
                vulnerabilities.append(vuln)

        logger.info(f"Found {len(vulnerabilities)} vulnerabilities")
        for vuln in vulnerabilities:
            logger.info(f"{vuln.harness_id}, {vuln.sanitizer_id},{vuln.input_file}\n{vuln.input_data}")


vuln_discovery = VulnDiscovery()
