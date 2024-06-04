import time
from typing import TypedDict
import requests
from config import AIXCC_API_HOSTNAME


class ProofOfVulnerability(TypedDict):
    harness: str
    data: str


class ProofOfUnderstanding(TypedDict):
    commit_sha1: str
    sanitizer: str


class VDSSubmission(TypedDict):
    cp_name: str
    pou: ProofOfUnderstanding
    pov: ProofOfVulnerability


AUTH = ("00000000-0000-0000-0000-000000000000", "secret")


def healthcheck():
    response = requests.get(
        f"{AIXCC_API_HOSTNAME}/health/",
        auth=AUTH,
    )
    return response.json().get("status") == "ok"


def submit_vds(vds: VDSSubmission):
    response = requests.post(
        f"{AIXCC_API_HOSTNAME}/submission/vds",
        auth=AUTH,
        headers={"Content-Type": "application/json"},
        data=vds,
    )
    vd_uuid = response.json().get("vd_uuid")
    status = response.json().get("status")

    return vd_uuid, status


def check_vds_status(vd_uuid):
    response = requests.get(
        f"{AIXCC_API_HOSTNAME}/submission/vds/{vd_uuid}",
        auth=AUTH,
    )
    return response.json().get("status")


def wait_until_vds_checked(vd_uuid):
    status = "pending"
    while status == "pending":
        time.sleep(10)
        status = check_vds_status(vd_uuid)
    return status
