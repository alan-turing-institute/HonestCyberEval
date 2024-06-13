import time
from subprocess import CalledProcessError

from api.submit import healthcheck, submit_vulnerability, submit_patch
from api.fs import (
    get_projects,
    move_projects_to_scratch, write_file_to_scratch,
)
from pipeline.vuln_discovery import vuln_discovery
from pipeline.setup_project import setup_project

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

move_projects_to_scratch()
projects = get_projects()
for project_path in projects:
    if not project_path.name == "mock-cp":
        # Assuming this is "Mock CP" for now as it's using hardcoded inputs and patches
        print(f"Skipping {project_path.name}")
        continue
    project = setup_project(project_path)

    for cp_source in project.sources:
        vulnerabilities = vuln_discovery.run(project, cp_source)

        for bad_commit_sha, harness_id, sanitizer_id, input_data, blob_file in vulnerabilities:
            while not healthcheck():
                time.sleep(5)
            else:
                print("healthcheck passed")

            # todo: save input to persistent storage and check it to avoid double submissions
            status, cpv_uuid = submit_vulnerability(
                cp_name=project.name,
                commit_sha1=bad_commit_sha,
                sanitizer_id=sanitizer_id,
                harness_id=harness_id,
                data=input_data,
            )
            # todo: update input in persistent storage and mark resolved
            print("Vulnerability:", status, cpv_uuid)

            if status != 'rejected':
                patch_path = write_file_to_scratch("patch.diff", patch)

                try:
                    project.repos.get(cp_source).repo.git.reset('--hard')
                    print("Re-building CP with patch", flush=True)
                    result = project.patch_and_build_project(patch_path.absolute(), cp_source)
                    if result.stderr:
                        raise Exception("Build failed after patch", result.stderr)
                except CalledProcessError as err:
                    print("Patching failed", err, err.stdout, err.stderr)
                else:
                    result = project.run_harness(blob_file, "id_1")
                    if result.stderr:
                        raise Exception("Harness sanitiser output:\n", result.stderr)

                    result = project.run_tests()
                    project.repos.get(cp_source).repo.git.reset('--hard')
                    if result.stderr:
                        raise Exception("Test failed", result.stderr)

                    print("Submitting patch", flush=True)
                    status, gp_uuid = submit_patch(cpv_uuid, patch)
                    print("Patch:", status, gp_uuid, flush=True)
