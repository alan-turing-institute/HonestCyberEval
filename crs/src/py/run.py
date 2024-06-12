import time
from subprocess import CalledProcessError

from api.submit import healthcheck, submit_vulnerability, submit_patch
from api.cp import ChallengeProject
from api.fs import (
    get_projects,
    write_file_to_scratch,
    move_projects_to_scratch,
)
from api.llm import send_msg_to_llm

input_data = r"""abcdefabcdefabcdefabcdefabcdefabcdef
b

1"""

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
    project = ChallengeProject(project_path)
    if not project.name == "Mock CP":
        # Assuming this is "Mock CP" for now as it's using hardcoded inputs and patches
        print(f"Skipping {project.name}")
        continue
    project.repo.git.reset('--hard')
    project.pull_docker_image()

    for cp_source in project.sources:
        git_repo, ref = project.repos.get(cp_source)
        git_log = list(git_repo.iter_commits(ref, max_count=2))
        for commit in git_log:
            print(commit.hexsha, commit.message, commit.stats.files, sep="\n")

        print(f"Building {project.config['cp_name']}", flush=True)
        result = project.build_project()
        if result.stderr:
            raise Exception("Build failed", result.stderr)

        with project.open_project_source_file(cp_source, "mock_vp.c") as code_file:
            code_snippet = code_file.read().replace('\n', '')

        # print(send_msg_to_llm(
        #     "oai-gpt-3.5-turbo",
        #     f"Could you find the vulnerabilities and write a diff patch for the following code:\n {code_snippet}\nBe brief",
        # ))

        blob_file = write_file_to_scratch("input.blob", input_data)
        result = project.run_harness(blob_file, "id_1")
        print("Harness sanitiser output:\n", result.stderr)

        while not healthcheck():
            time.sleep(5)
        else:
            print("healthcheck passed")
        status, cpv_uuid = submit_vulnerability(
            cp_name=project.name,
            commit_sha1="9d38fc63bb9ffbc65f976cbca45e096bad3b30e1",
            sanitizer_id="id_1",
            harness_id="id_1",
            data=input_data,
        )
        print("Vulnerability:", status, cpv_uuid)

        if status != 'rejected':
            patch_path = write_file_to_scratch("patch.diff", patch)

            try:
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

                if result.stderr:
                    raise Exception("Test failed", result.stderr)

                print("Submitting patch", flush=True)
                status, gp_uuid = submit_patch(cpv_uuid, patch)
                print("Patch:", status, gp_uuid, flush=True)
