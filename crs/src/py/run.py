from submit import healthcheck, submit_vds, wait_until_vds_checked

print(healthcheck())

vds_submission = {"cp_name": "mock-cp",
                  "pou": {"commit_sha1": "451dfb089f10ae0b5afd091a428e8c501c8b9b45", "sanitizer": "id_1"},
                  "pov": {"harness": "id_1", "data": "YWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmCmIKCjEK"}}

vd_uuid, status = submit_vds(vds_submission)
print(status)
status = wait_until_vds_checked(vd_uuid)
print(status)
