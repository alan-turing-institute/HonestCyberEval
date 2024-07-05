import base64
import time
from typing import Literal, TypeAlias, TypedDict

from requests import Session
from requests.auth import HTTPBasicAuth

from config import AIXCC_API_HOSTNAME

from .data_types import Patch, VulnerabilityWithSha

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
    cp_name: str  # cp_name from project.yaml
    # https://github.com/aixcc-sc/capi/issues/28)
    pou: ProofOfUnderstanding
    pov: ProofOfVulnerability


class GPSubmission(TypedDict):
    cpv_uuid: CPVuuid
    data: str  # patch in unified diff format
    # (see https://www.gnu.org/software/diffutils/manual/html_node/Unified-Format.html)


AUTH = HTTPBasicAuth("00000000-0000-0000-0000-000000000000", "secret")

session = Session()
session.auth = AUTH
session.headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

__capi_up = False


def healthcheck() -> bool:
    global __capi_up
    if __capi_up:
        return True

    response = session.get(
        f"{AIXCC_API_HOSTNAME}/health/",
    )
    try:
        __capi_up = response.json().get("status") == "ok"
    except ValueError:
        pass
    return __capi_up


def submit_vulnerability(cp_name: str, vulnerability: VulnerabilityWithSha) -> tuple[CAPIStatus, CPVuuid]:

    vds_url = f"{AIXCC_API_HOSTNAME}/submission/vds/"

    vds: VDSubmission = {
        "cp_name": cp_name,
        "pou": {
            "commit_sha1": vulnerability.commit,
            "sanitizer": vulnerability.sanitizer_id,
        },
        "pov": {
            "harness": vulnerability.harness_id,
            "data": base64.b64encode(vulnerability.input_data.encode()).decode("ascii"),
        },
    }

    response = session.post(
        vds_url,
        json=vds,
    )
    if not response.ok:
        raise Exception(response.reason, response.status_code, cp_name, vulnerability)
    content = response.json()
    status, vd_uuid = content.get("status"), content.get("vd_uuid")
    status = "pending"
    while True:  # do-while loop; need to hit endpoint at least once to get cpv_uuid (or rejection)
        if status == "pending":
            time.sleep(10)
        response = session.get(
            f"{vds_url}{vd_uuid}",
        )
        if not response.ok:
            raise Exception(response.reason, response.status_code, cp_name, vulnerability)
        content = response.json()
        status, cpv_uuid = content.get("status"), content.get("cpv_uuid")
        if not status == "pending":
            return status, cpv_uuid


def _encode_patch(cpv_uuid: CPVuuid, patch: Patch) -> GPSubmission:
    encoded_patch = base64.b64encode(patch.diff.encode()).decode("ascii")
    return {
        "cpv_uuid": cpv_uuid,
        "data": encoded_patch,
    }


def submit_patch(cpv_uuid: CPVuuid, patch: Patch) -> tuple[CAPIStatus, GPuuid]:
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
