import pprint
from pathlib import Path
from typing import Optional

from params import PATCH_MAX_LLM_TRIALS, PATCH_MODEL_LIST

from api.cp import ChallengeProject
from api.data_types import Patch, VulnerabilityWithSha
from api.fs import write_patch_to_disk
from api.llm import LLMmodel, create_rag_docs, format_chat_history, get_retriever
from logger import logger
from pipeline.langgraph_patch import (
    HarnessTriggeredAfterPatchException,
    apply_patch_and_check,
    patched_file_to_diff,
    run_patch_langraph,
)

from .langgraph_patch import TestFailedException
from .preprocess_commits import ProcessedCommits

mock_patches = {
    "id_1": r"""diff --git a/mock_vp.c b/mock_vp.c
index 9dc6bf0..72678be 100644
--- a/mock_vp.c
+++ b/mock_vp.c
@@ -10,7 +10,8 @@ func_a(){
         printf("input item:");
         buff = &items[i][0];
         i++;
-        fgets(buff, 40, stdin);
+        fgets(buff, 9, stdin);
+        if (i==3){buff[0]= 0;}
         buff[strcspn(buff, "\n")] = 0;
     }while(strlen(buff)!=0);
     i--;
""",
    "id_2": r"""diff --git a/mock_vp.c b/mock_vp.c
index 9dc6bf0..ca80ed1 100644
--- a/mock_vp.c
+++ b/mock_vp.c
@@ -22,8 +22,10 @@ func_b(){
     int j;
     printf("display item #:");
     scanf("%d", &j);
-    buff = &items[j][0];
-    printf("item %d: %s\n", j, buff);
+    if (j < 0 || j>2){;}else{
+        buff = &items[j][0];
+        printf("item %d: %s\n", j, buff);
+    }
 }

 #ifndef ___TEST___
""",
}


class PatchGen:
    project: ChallengeProject

    @staticmethod
    def gen_mock_patch(i=None):
        if i is None:
            return "\n".join([mock_patches["id_1"], mock_patches["id_2"]])
        return mock_patches[f"id_{i}"]

    async def gen_patch_langgraph(
        self,
        cpv_uuid,
        vulnerability: VulnerabilityWithSha,
        vuln_code: str,
        bad_file: str,
        max_trials: int = PATCH_MAX_LLM_TRIALS,
    ) -> Optional[Patch]:
        models: list[LLMmodel] = PATCH_MODEL_LIST
        for model_name in models:
            try:
                output = await run_patch_langraph(
                    model_name=model_name,
                    project=self.project,
                    cpv_uuid=cpv_uuid,
                    vulnerability=vulnerability,
                    bad_file=bad_file,
                    vuln_code=vuln_code,
                    max_iterations=max_trials,
                )
            except Exception as error:
                logger.error(f"LangGraph patch generation failed for {model_name} with \n {repr(error)}")
            else:
                logger.debug(f"LangGraph Message History\n\n{format_chat_history(output['chat_history'])}\n\n")
                if not output["error"]:
                    logger.info(f"Patching succeeded using {model_name}")
                    patched_file = output["patched_file"]
                    patch_text = patched_file_to_diff(vuln_code, patched_file, bad_file)
                    patch_path = write_patch_to_disk(
                        self.project, cpv_uuid, patch_text, "work", vulnerability, model_name
                    )
                    patch = Patch(diff=patch_text, diff_file=patch_path)
                    return patch
                logger.info(f"{model_name} failed to find good patch")
                logger.debug(f"{model_name} failed to find good patch with error: \n {output['error']}")
        logger.warning("Failed to find good patch!")
        return None

    async def run(
        self,
        project: ChallengeProject,
        preprocessed_commits: ProcessedCommits,
        cpv_uuid,
        vulnerability: VulnerabilityWithSha,
        use_funcdiffs: bool = False,
    ) -> Optional[Patch]:
        self.project = project

        if vulnerability.commit in preprocessed_commits:
            logger.info(f"Patching Functional Commit")
            commit = preprocessed_commits[vulnerability.commit]

            for filename, file_diff in commit.items():
                file_path = file_diff.filepath

                # file_text = file_diff.after_str()

                try:
                    file_text = self.project.open_project_source_file(vulnerability.cp_source, Path(file_path))

                except FileNotFoundError:
                    logger.warning(f"The file {file_path} was not found")

                else:
                    funcs = []
                    for function_diff in file_diff.diff_functions.values():
                        funcs.append(function_diff.after_str())

                    vuln_code = "".join(f + "\n" for f in funcs) if use_funcdiffs else file_text

                    patch = await self.gen_patch_langgraph(
                        cpv_uuid=cpv_uuid, vulnerability=vulnerability, vuln_code=vuln_code, bad_file=file_path
                    )

                    if patch:
                        return patch

        else:
            logger.warning(f"NO FUNCTIONAL COMMIT MATCHES VULN COMMIT")
            return None


patch_generation = PatchGen()
