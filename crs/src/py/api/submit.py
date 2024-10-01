import asyncio
import base64
from typing import TypedDict

from aiohttp import BasicAuth, ClientSession
from params import RETRY_SUBMISSIONS
from pprint import pprint

from config import AIXCC_GP_URL, AIXCC_HEALTHCHECK_URL, AIXCC_VDS_URL
from logger import logger

from .data_types import CAPIStatus, CPVuuid, Patch, VulnerabilityWithSha


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


AUTH = BasicAuth("00000000-0000-0000-0000-000000000000", "secret")

headers = {
    "accept": "application/json",
    "Content-Type": "application/json",
}

__capi_up = True
__lock = asyncio.Lock()


async def healthcheck():
    global __capi_up

    # only one healthcheck needs to poll the healthcheck, the rest should just wait until that's done
    async with __lock:
        if __capi_up:
            return
        async with ClientSession(auth=AUTH, headers=headers) as session:
            while True:
                response = await session.get(
                    AIXCC_HEALTHCHECK_URL,
                )
                try:
                    content = await response.json()
                    __capi_up = content.get("status") == "ok"
                except ValueError:
                    pass
                if __capi_up:
                    return
                await asyncio.sleep(5)


async def submit_vulnerability(cp_name: str, vulnerability: VulnerabilityWithSha) -> None:
    if vulnerability.vd_uuid is not None or vulnerability.cpv_uuid is not None:
        logger.warn(f"Attempted re-submission of vulnerability {vulnerability}")
        return
    vulnerability.status = "accepted"
    vulnerability.vd_uuid = "foo"
    return

    # vds: VDSubmission = {
    #     "cp_name": cp_name,
    #     "pou": {
    #         "commit_sha1": vulnerability.commit,
    #         "sanitizer": vulnerability.sanitizer_id,
    #     },
    #     "pov": {
    #         "harness": vulnerability.harness_id,
    #         "data": base64.b64encode(vulnerability.input_data.encode()).decode("ascii"),
    #     },
    # }
    # await healthcheck()
    # async with ClientSession(auth=AUTH, headers=headers) as session:
    #     for _ in range(RETRY_SUBMISSIONS):
    #         response = await session.post(
    #             AIXCC_VDS_URL,
    #             json=vds,
    #         )
    #         if not response.ok:
    #             logger.warn(response.reason, response.status, cp_name, vulnerability)
    #             await asyncio.sleep(2)
    #         else:
    #             content = await response.json()
    #             vulnerability.status = content.get("status")
    #             vulnerability.vd_uuid = content.get("vd_uuid")
    #
    #             while True:  # do-while loop; need to hit endpoint at least once to get cpv_uuid (or rejection)
    #                 if vulnerability.status == "pending":
    #                     await asyncio.sleep(5)
    #                 response = await session.get(
    #                     f"{AIXCC_VDS_URL}{vulnerability.vd_uuid}",
    #                 )
    #                 if not response.ok:
    #                     logger.warn(response.reason, response.status, cp_name, vulnerability)
    #                 else:
    #                     content = await response.json()
    #                     vulnerability.status = content.get("status")
    #                     vulnerability.cpv_uuid = content.get("cpv_uuid")
    #                     if not vulnerability.status == "pending":
    #                         return


def _encode_patch(patch: Patch) -> GPSubmission:
    encoded_patch = base64.b64encode(patch.diff.encode()).decode("ascii")
    cpv_uuid: str = patch.vulnerability.cpv_uuid  # type:ignore
    return {
        "cpv_uuid": cpv_uuid,
        "data": encoded_patch,
    }


async def submit_patch(patch: Patch) -> None:
    if patch.gp_uuid is not None:
        logger.warn(f"Attempted re-submission of patch {patch}")
        return
    patch.status = "accepted"
    patch.gp_uuid = "foo"
    return
    #
    # gp = _encode_patch(patch)
    # await healthcheck()
    # async with ClientSession(auth=AUTH, headers=headers) as session:
    #     for _ in range(RETRY_SUBMISSIONS):
    #         response = await session.post(
    #             AIXCC_GP_URL,
    #             json=gp,
    #         )
    #         if not response.ok:
    #             logger.warn(response.reason, response.status)
    #             await asyncio.sleep(2)
    #         else:
    #             content = await response.json()
    #             patch.status = content.get("status")
    #             patch.gp_uuid = content.get("gp_uuid")
    #             while patch.status == "pending":
    #                 await asyncio.sleep(5)  # sleep(10) from run.sh
    #                 response = await session.get(
    #                     f"{AIXCC_GP_URL}{patch.gp_uuid}",
    #                 )
    #                 if not response.ok:
    #                     logger.warn(response.reason, response.status)
    #                 else:
    #                     content = await response.json()
    #                     patch.status = content.get("status")
    #                     patch.gp_uuid = content.get("gp_uuid")
    #             return
