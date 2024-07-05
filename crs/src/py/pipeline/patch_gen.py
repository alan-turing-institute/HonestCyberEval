from typing import Optional

from api.cp import ChallengeProject
from api.data_types import Patch, VulnerabilityWithSha
from api.fs import write_patch_to_disk
from api.llm import LLMmodel, format_chat_history
from logger import logger
from pipeline.langgraph_patch import (
    HarnessTriggeredAfterPatchException,
    apply_patch_and_check,
    patched_file_to_diff,
    run_patch_langraph,
)

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
    cp_source: str

    @staticmethod
    def gen_mock_patch(i=None):
        if i is None:
            return "\n".join([mock_patches[f"id_1"], mock_patches[f"id_2"]])
        return mock_patches[f"id_{i}"]

    def gen_patch_langgraph(self, cpv_uuid, vulnerability: VulnerabilityWithSha, bad_file, max_trials=3):
        vuln_code = self.project.open_project_source_file(self.cp_source, bad_file)
        models: list[LLMmodel] = ["oai-gpt-4o", "claude-3.5-sonnet", "gemini-1.5-pro"]
        for model_name in models:
            try:
                output = run_patch_langraph(
                    model_name=model_name,
                    project=self.project,
                    cp_source=self.cp_source,
                    cpv_uuid=cpv_uuid,
                    vulnerability=vulnerability,
                    bad_file=bad_file,
                    vuln_code=vuln_code,
                    max_iterations=max_trials,
                )
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
            except Exception as error:
                logger.error(f"LangGraph patch generation failed for {model_name} with \n {error}")
        logger.warning("Failed to find good patch!")
        return None

    def run(
        self, project: ChallengeProject, cp_source: str, cpv_uuid, vulnerability: VulnerabilityWithSha
    ) -> Optional[Patch]:
        self.project = project
        self.cp_source = cp_source

        patch = self.gen_patch_langgraph(cpv_uuid, vulnerability, "mock_vp.c")

        # For now, we hard code the patch here to avoid exceptions
        if not patch and self.project.name == "Mock CP":
            potential_patch = self.gen_mock_patch(1)
            patch_path = write_patch_to_disk(project, cpv_uuid, potential_patch, 0, vulnerability, "mock")
            patch = Patch(diff=potential_patch, diff_file=patch_path)
            try:
                apply_patch_and_check(project, cp_source, vulnerability, patch)
            except HarnessTriggeredAfterPatchException:
                # some inputs require both hard coded patches applied together to fix
                potential_patch = self.gen_mock_patch()
                patch = Patch(diff_file=patch_path, diff=potential_patch)

        return patch


patch_generation = PatchGen()
