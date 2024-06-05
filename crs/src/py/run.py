import time

from api.submit import healthcheck, submit_vulnerability, submit_patch
from api.cp_fs import get_projects, read_project_yaml, write_file_to_scratch, move_projects_to_scratch, run_cp_run_sh

move_projects_to_scratch()
projects = get_projects()
project = projects[0]  # for project in projects:
project_config = read_project_yaml(project)

# Assuming this is "Mock CP" for now and using hardcoded inputs and patches
# print(f"Building {project_config['cp_name']}")
# run_cp_run_sh(project, "build")

input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

blob_file = write_file_to_scratch("input.blob", input_data)

# run_cp_run_sh(project, "run_pov", blob_file, "stdin_harness.sh")  # project_config["harnesses"]["id_1"]["binary"]

while not healthcheck():
    time.sleep(5)
else:
    print("healthcheck passed")
status, cpv_uuid = submit_vulnerability(
    cp_name="Mock CP",  # project_config['cp_name']
    commit_sha1="9d38fc63bb9ffbc65f976cbca45e096bad3b30e1",
    sanitizer_id="id_1",
    harness_id="id_1",
    data=input_data,
)
print("Vulnerability:", status, cpv_uuid)

if status != 'rejected':
    patch = r"""diff --git a/mock_vp.c b/mock_vp.c
index 56cf8fd..abb73cd 100644
--- a/mock_vp.c
+++ b/mock_vp.c
@@ -11,7 +11,8 @@ int main()
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
    patch_path = write_file_to_scratch("patch.diff", patch)
#
    # print("Re-building CP with patch")
    # run_cp_run_sh(project, "build", patch_path.absolute(), "samples")
    # run_cp_run_sh(project, "run_pov", blob_file, "stdin_harness.sh")  # project_config["harnesses"]["id_1"]["binary"]
    # run_cp_run_sh(project, "run_tests")

    print("Submitting patch")
    status, gp_uuid = submit_patch(cpv_uuid, patch)
    print("Patch:", status, gp_uuid)
