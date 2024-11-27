from pathlib import Path

from pydantic.dataclasses import dataclass


@dataclass(order=True)
class Vulnerability:
    harness_id: str
    sanitizer_id: str
    input_data: str
    input_file: Path
    cp_source: str
