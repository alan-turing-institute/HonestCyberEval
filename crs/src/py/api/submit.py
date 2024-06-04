import time
from typing import TypedDict, Literal, TypeAlias
import requests
from requests import Session
from requests.auth import HTTPBasicAuth
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


VDuuid: TypeAlias = str
CAPIStatus: TypeAlias = Literal["accepted", "pending", "rejected"]

AUTH = HTTPBasicAuth("00000000-0000-0000-0000-000000000000", "secret")

session = Session()
session.auth = AUTH
session.headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
}


def healthcheck() -> bool:
    response = session.get(
        f"{AIXCC_API_HOSTNAME}/health/",
    )
    try:
        return response.json().get("status") == "ok"
    except ValueError:
        return False


def submit_vds(vds: VDSSubmission) -> tuple[VDuuid, CAPIStatus]:
    response = session.post(
        f"{AIXCC_API_HOSTNAME}/submission/vds/",
        json=vds,
    )
    if not response.ok:
        raise Exception(response.reason, response.status_code)
    vd_uuid = response.json().get("vd_uuid")
    status = response.json().get("status")

    return vd_uuid, status


def check_vds_status(vd_uuid: VDuuid) -> CAPIStatus:
    response = session.get(
        f"{AIXCC_API_HOSTNAME}/submission/vds/{vd_uuid}",
    )
    return response.json().get("status")


def wait_until_vds_checked(vd_uuid: VDuuid, status: CAPIStatus = "pending", max_retries=15) -> CAPIStatus:
    retries = 0
    while status == "pending" and retries < max_retries:
        time.sleep(10)  # sleep(10) from run.sh
        status = check_vds_status(vd_uuid)
        retries += 1
    return status
