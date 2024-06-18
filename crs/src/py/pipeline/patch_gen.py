import subprocess

from api.cp import ProjectPatchException, ProjectBuildException
from api.fs import write_file_to_scratch

mock_patch = r"""diff --git a/mock_vp.c b/mock_vp.c
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
"""


class PatchGen:
    project = None
    cp_source = None

    def gen_patch(self):
        return mock_patch

    def write_patch_to_disk(self, cpv_uuid, potential_patch):
        return write_file_to_scratch(
            f"{self.project.name}_{self.cp_source}_{cpv_uuid}_patch.diff",
            potential_patch,
        )

    def validate_patch(self, patch_path, harness_id, harness_input_file, sanitizer_id):
        print("Re-building CP with patch", flush=True)
        try:
            self.project.patch_and_build_project(patch_path.absolute(), self.cp_source)
        except ProjectPatchException as err:
            # todo: patch was not a valid patch, try again?
            print(err.stderr)
            raise err
        except ProjectBuildException as err:
            # todo: patch did not produce valid code, try again?
            print(err.stderr)
            raise err
        else:  # build with patch worked, checking fix
            has_sanitizer_triggered = self.project.run_harness_and_check_sanitizer(harness_input_file, harness_id, sanitizer_id)
            if has_sanitizer_triggered:
                # todo: the patch doesn't solve the error, sanitizer still complaining
                print(self.project.run_harness(harness_input_file, harness_id).stderr)
                raise Exception("the patch doesn't solve the error")
            result = self.project.run_tests()
            if result.stderr:
                # todo: the patch broke functionality
                print(result.stderr)
                raise Exception("Test failed", result.stderr)

    def run(self, project, cp_source, cpv_uuid, harness_id, harness_input, sanitizer_id):
        self.project = project
        self.cp_source = cp_source

        potential_patch = self.gen_patch()
        patch_path = self.write_patch_to_disk(cpv_uuid, potential_patch)

        # TODO: if validation fails, do something
        self.project.reset_source_repo(self.cp_source)
        self.validate_patch(patch_path, harness_id, harness_input, sanitizer_id)
        self.project.reset_source_repo(self.cp_source)

        self.project = None
        self.cp_source = None
        return potential_patch


patch_generation = PatchGen()
