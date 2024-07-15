from pathlib import Path
from typing import Literal, NamedTuple, Optional, TypeAlias

from pydantic.dataclasses import dataclass

CAPIStatus: TypeAlias = Literal["accepted", "pending", "rejected"]

VDuuid: TypeAlias = str
CPVuuid: TypeAlias = str
GPuuid: TypeAlias = str


@dataclass(order=True)
class Vulnerability:
    harness_id: str
    sanitizer_id: str
    input_data: str
    input_file: Path
    cp_source: str


@dataclass(order=True)
class VulnerabilityWithSha(Vulnerability):
    commit: str
    status: CAPIStatus = "pending"
    vd_uuid: Optional[VDuuid] = None
    cpv_uuid: Optional[CPVuuid] = None
    patch: Optional["Patch"] = None


@dataclass
class Patch:
    diff: str
    diff_file: Path
    vulnerability: VulnerabilityWithSha
    status: CAPIStatus = "pending"
    gp_uuid: Optional[GPuuid] = None
