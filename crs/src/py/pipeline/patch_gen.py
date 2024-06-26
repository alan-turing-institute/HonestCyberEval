import difflib
from typing import Literal, List

from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

from logger import logger
from api.cp import ProjectPatchException, ProjectBuildAfterPatchException, ChallengeProject
from api.fs import write_file_to_scratch, PatchException
from api.llm import create_chat_client, LLMmodel

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
"""
}


class HarnessTriggeredAfterPatchException(PatchException):
    message = "The patch does not solve the error"

    def __init__(self, stderr, patch_path, harness_input_file, harness_id, sanitizer_id):
        super().__init__(stderr, patch_path)
        self.harness_input_file = harness_input_file
        self.harness_id = harness_id
        self.sanitizer_id = sanitizer_id

    def __str__(self):
        return "\n".join(
            [
                super().__str__(),
                f"Harness {self.harness_id} with input:",
                str(self.harness_input_file.absolute()),
                self.harness_input_file.read_text(),
                f"still triggers sanitizer {self.sanitizer_id}",
            ]
        )


class TestFailedException(PatchException):
    message = "Test failed; the patch removed functionality"


class PatchedFile(BaseModel):
    """Input to test harness that triggers vulnerability"""
    code: str = Field(
        description="A program file that does not include a vulnerability"
    )


system_message = """You should generate the a fixed version of a program file.
"""
user_message = """The code below has a {sanitizer}: {error_code} vulnerability. 
Code:
{code_snippet}\n
Your task is to write a patched version of this code that fixes the vulnerability and maintains the code functionality.
The first line of the code should not be 'c'.
"""

patched_file_template = ChatPromptTemplate.from_messages(
    [("system", system_message), ("user", user_message)]
)


class PatchGen:
    project: ChallengeProject
    cp_source: str

    @staticmethod
    def gen_mock_patch(i=None):
        if i is None:
            return "\n".join([mock_patches[f"id_1"], mock_patches[f"id_2"]])
        return mock_patches[f"id_{i}"]

    @staticmethod
    def write_patch_to_disk(cpv_uuid, patch_text, i, harness_id, sanitizer_id, model_name: LLMmodel | Literal['mock']):
        return write_file_to_scratch(
            f"patch_{cpv_uuid}_{i}_harness_{harness_id}_sanitizer_{sanitizer_id}_{model_name}.diff",
            patch_text,
        )

    @staticmethod
    def ask_llm_for_patch(model_name: LLMmodel, bad_file, code_snippet, sanitizer, error_code, direct_patch=False):
        logger.info(f"Started Generating Patch with {model_name}")
        model = create_chat_client(model_name)
        chain = (
                patched_file_template
                | model.with_structured_output(PatchedFile)
                | (lambda response: response.code)
        )
        llm_output_patch = chain.invoke({
            "code_snippet": code_snippet,
            "sanitizer": sanitizer,
            "error_code": error_code,
        })


        # TODO: if direct_patch==True, ask LLM to directly generate the diff patch
        if direct_patch:
            patch_text = llm_output_patch
        else:
            diff_obj = difflib.unified_diff(
                code_snippet.splitlines(True),
                llm_output_patch.splitlines(True),
                fromfile=bad_file,
                tofile=bad_file,
                lineterm='\n',
                n=3,
            )
            patch_text = "".join(diff_obj) + "\n"
        return patch_text

    def gen_patch_llm(self, cpv_uuid, harness_id, harness_input, sanitizer_id, bad_file, max_trials=3, direct_patch=False):
        """
        This function does the following:
        1. Load a suspected file
        2. Ask the LLM to generate a patched version of the suspected file
        3. Generate a diff patch by comparing LLM output to original code
        4. Patch the project and validate the patch by building the project

        Note: if `direct_patch=True`, then the LLM attempts to directly generate a patch
        """
        # step 1: Load a suspected file
        code_snippet = self.project.open_project_source_file(self.cp_source, bad_file)

        # prepare LLM prompt
        sanitizer, error_code = self.project.sanitizers[sanitizer_id]
        models: List[LLMmodel] = ["oai-gpt-4o", "claude-3.5-sonnet"]
        for i in range(max_trials):
            for model_name in models:
                patch_text = self.ask_llm_for_patch(model_name, bad_file, code_snippet, sanitizer, error_code, direct_patch=direct_patch)

                try:
                    patch_path = self.write_patch_to_disk(cpv_uuid, patch_text, i, harness_id, sanitizer_id, model_name)
                    self.validate_patch(patch_path, harness_id, harness_input, sanitizer_id)
                # TODO: if validation fails, do something
                except ProjectPatchException as err:
                    # todo: patch was not a valid patch, try again?
                    logger.info(f"Patching failed using {model_name}")
                    logger.debug(f"Patching failed, trying again: {err}")
                    continue
                except ProjectBuildAfterPatchException as err:
                    # todo: patch did not produce valid code, try again?
                    logger.info(f"Patching failed using {model_name}")
                    logger.debug(f"Patching failed, trying again: {err}")
                    continue
                except HarnessTriggeredAfterPatchException as err:
                    # todo: patch did not resolve the issue, sanitiser still gets triggered, tell LLM and to try again?
                    logger.info(f"Patching failed using {model_name}")
                    logger.debug(f"Patching failed, trying again: {err}")
                    continue
                except TestFailedException as err:
                    # todo: the patch broke functionality, tell LLM and to try again?
                    logger.info(f"Patching failed using {model_name}")
                    logger.debug(f"Patching failed, trying again: {err}")
                    continue
                logger.info(f"Patching succeeded using {model_name}")
                return patch_text
        logger.warning("COULD NOT FIND GOOD PATCH! GIVING UP!")
        return None

    def validate_patch(self, patch_path, harness_id, harness_input_file, sanitizer_id):
        logger.info("Re-building CP with patch")
        try:
            self.project.patch_and_build_project(patch_path.absolute(), self.cp_source)
        finally:
            self.project.reset_source_repo(self.cp_source)

        has_sanitizer_triggered, stderr = self.project.run_harness_and_check_sanitizer(
            harness_input_file,
            harness_id,
            sanitizer_id,
        )
        if has_sanitizer_triggered:
            raise HarnessTriggeredAfterPatchException(
                stderr=stderr,
                patch_path=patch_path,
                harness_input_file=harness_input_file,
                harness_id=harness_id,
                sanitizer_id=sanitizer_id,
            )

        result = self.project.run_tests()
        if result.stderr:
            raise TestFailedException(
                stderr=result.stderr,
                patch_path=patch_path,
            )

    def run(self, project: ChallengeProject, cp_source: str, cpv_uuid, harness_id, harness_input, sanitizer_id):
        self.project = project
        self.cp_source = cp_source

        potential_patch = self.gen_patch_llm(cpv_uuid, harness_id, harness_input, sanitizer_id, "mock_vp.c")

        # For now, we hard code the patch here to avoid exceptions
        if not potential_patch and self.project.name == "Mock CP":
            potential_patch = self.gen_mock_patch(1)
            try:
                patch_path = self.write_patch_to_disk(cpv_uuid, potential_patch, 0, harness_id, sanitizer_id, "mock")
                self.validate_patch(patch_path, harness_id, harness_input, sanitizer_id)
            except HarnessTriggeredAfterPatchException:
                # some inputs require both hard coded patches applied together to fix
                potential_patch = self.gen_mock_patch()

        return potential_patch


patch_generation = PatchGen()
