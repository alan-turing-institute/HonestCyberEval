import base64
import time
from typing import TypedDict, Literal, TypeAlias
from requests import Session
from requests.auth import HTTPBasicAuth
from config import AIXCC_API_HOSTNAME

CPVuuid: TypeAlias = str
GPuuid: TypeAlias = str
CAPIStatus: TypeAlias = Literal["accepted", "pending", "rejected"]


class ProofOfVulnerability(TypedDict):
    harness: str  # harness id from project.yaml e.g. id_1
    data: str  # input for harness to trigger vulnerability


class ProofOfUnderstanding(TypedDict):
    commit_sha1: str  # git commit hash that introduced vulnerability
    sanitizer: str  # sanitizer id from project.yaml e.g. id_1


class VDSubmission(TypedDict):
    cp_name: str  # directory name of the challenge project NOT the name from project.yaml
    pou: ProofOfUnderstanding
    pov: ProofOfVulnerability


class GPSubmission(TypedDict):
    cpv_uuid: CPVuuid
    data: str  # patch in unified diff format (www.gnu.org/software/diffutils/manual/html_node/Unified-Format.html)


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


def submit_vulnerability(vds: VDSubmission) -> tuple[CAPIStatus, CPVuuid]:
    vds_url = f"{AIXCC_API_HOSTNAME}/submission/vds/"
    response = session.post(
        vds_url,
        json=vds,
    )
    if not response.ok:
        raise Exception(response.reason, response.status_code)
    content = response.json()
    vd_uuid = content.get("vd_uuid")
    while True:
        response = session.get(
            f"{vds_url}{vd_uuid}",
        )
        if not response.ok:
            raise Exception(response.reason, response.status_code)
        content = response.json()
        status, cpv_uuid = content.get("status"), content.get("cpv_uuid")
        if not status == "pending":
            return status, cpv_uuid
        time.sleep(10)  # sleep(10) from run.sh


def _encode_patch(cpv_uuid: CPVuuid, patch: str) -> GPSubmission:
    encoded_patch = base64.b64encode(patch.encode()).decode('ascii')
    return {
        "cpv_uuid": cpv_uuid,
        "data": encoded_patch,
    }


def submit_patch(cpv_uuid: CPVuuid, patch: str) -> tuple[CAPIStatus, GPuuid]:
    gp_url = f"{AIXCC_API_HOSTNAME}/submission/gp/"
    gp = _encode_patch(cpv_uuid, patch)
    response = session.post(
        gp_url,
        json=gp,
    )
    if not response.ok:
        raise Exception(response.reason, response.status_code)
    content = response.json()
    status, gp_uuid = content.get("status"), content.get("gp_uuid")
    while status == "pending":
        time.sleep(10)  # sleep(10) from run.sh
        response = session.get(
            f"{gp_url}{gp_uuid}",
        )
        if not response.ok:
            raise Exception(response.reason, response.status_code)
        content = response.json()
        status, gp_uuid = content.get("status"), content.get("gp_uuid")
    return status, gp_uuid
