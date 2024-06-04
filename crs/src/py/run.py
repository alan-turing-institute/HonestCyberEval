import time

from api.submit import healthcheck, submit_vulnerability, submit_patch, VDSubmission

while not healthcheck():
    time.sleep(5)
else:
    print("healthcheck passed")

vds_submission: VDSubmission = {"cp_name": "Mock CP",
                                "pou": {"commit_sha1": "451dfb089f10ae0b5afd091a428e8c501c8b9b45",
                                        "sanitizer": "id_1",
                                        },
                                "pov": {"harness": "id_1",
                                        "data": "YWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmCmIKCjEK",
                                        }
                                }

status, cpv_uuid = submit_vulnerability(vds_submission)
print("Vulnerability:", status, cpv_uuid)

patch = """diff --git a/mock_vp.c b/mock_vp.c
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

status, gp_uuid = submit_patch(cpv_uuid, patch)
print("Patch:", status, gp_uuid)
