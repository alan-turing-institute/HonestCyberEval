from pathlib import Path
from typing import NamedTuple

Vulnerability = NamedTuple(
    "Vulnerability", (("harness_id", str), ("sanitizer_id", str), ("input_data", str), ("input_file", Path))
)
VulnerabilityWithSha = NamedTuple(
    "VulnerabilityWithSha",
    (("harness_id", str), ("sanitizer_id", str), ("input_data", str), ("input_file", Path), ("commit", str)),
)
# TODO: ConfirmedVulnerability

Patch = NamedTuple("Patch", (("diff", str), ("diff_file", Path)))
# TODO: ConfirmedPatch
