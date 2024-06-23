from api.cp import ProjectPatchException, ProjectBuildException
from api.fs import write_file_to_scratch, RunException


class HarnessTriggeredAfterPatchException(RunException):
    message = "The patch does not solve the error"

    def __init__(self, stderr, patch_file, harness_input_file, harness_id, sanitizer_id):
        super().__init__(stderr)
        self.patch_file = patch_file
        self.harness_input_file = harness_input_file
        self.harness_id = harness_id
        self.sanitizer_id = sanitizer_id

    def __str__(self):
        return "\n".join([
            super().__str__(),
            f"Harness {self.harness_id} with input:",
            str(self.harness_input_file.absolute()),
            self.harness_input_file.read_text(),
            f"still triggers sanitizer {self.sanitizer_id}",
            "after applying patch:",
            str(self.patch_file),
            self.patch_file.read_text(),
        ])


class TestFailedException(RunException):
    message = "Test failed; the patch removed functionality"

    def __init__(self, stderr, patch_file):
        super().__init__(stderr)
        self.patch_file = patch_file

    def __str__(self):
        return "\n".join([
            super().__str__(),
            f"Patch removed functionality:",
            str(self.patch_file.absolute()),
            self.patch_file.read_text(),
        ])


mock_patch = {
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


class PatchGen:
    project = None
    cp_source = None

    def gen_patch(self, i=None):
        if i is None:
            return "\n".join([mock_patch[f"id_1"], mock_patch[f"id_2"]])
        return mock_patch[f"id_{i}"]

    def write_patch_to_disk(self, cpv_uuid, potential_patch):
        return write_file_to_scratch(
            f"{self.project.name}_{self.cp_source}_{cpv_uuid}_patch.diff",
            potential_patch,
        )

    def validate_patch(self, patch_path, harness_id, harness_input_file, sanitizer_id):
        print("Re-building CP with patch", flush=True)
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
                patch_file=patch_path,
                harness_input_file=harness_input_file,
                harness_id=harness_id,
                sanitizer_id=sanitizer_id,
            )

        result = self.project.run_tests()
        if result.stderr:
            raise TestFailedException(
                stderr=result.stderr,
                patch_file=patch_path,
            )

    def run(self, project, cp_source, cpv_uuid, harness_id, harness_input, sanitizer_id):
        self.project = project
        self.cp_source = cp_source

        potential_patch = self.gen_patch(1)
        patch_path = self.write_patch_to_disk(cpv_uuid, potential_patch)

        # TODO: if validation fails, do something
        try:
            self.validate_patch(patch_path, harness_id, harness_input, sanitizer_id)
        except ProjectPatchException as err:
            # todo: patch was not a valid patch, try again?
            raise
        except ProjectBuildException as err:
            # todo: patch did not produce valid code, try again?
            raise
        except HarnessTriggeredAfterPatchException as err:
            # todo: patch did not resolve the issue, the sanitiser still gets triggered, tell LLM and to try again?
            potential_patch = self.gen_patch()  # some inputs require both example patches to be applied to be fixed
            patch_path = self.write_patch_to_disk(cpv_uuid, potential_patch)
            self.validate_patch(patch_path, harness_id, harness_input, sanitizer_id)
        except TestFailedException as err:
            # todo: the patch broke functionality, tell LLM and to try again?
            raise

        self.project = None
        self.cp_source = None
        return potential_patch


patch_generation = PatchGen()
