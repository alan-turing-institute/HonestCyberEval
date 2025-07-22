from pathlib import Path

from inspect_ai.dataset import Sample, json_dataset
from pydantic import BaseModel


class PairedVulnMetadata(BaseModel, frozen=True):
    code_files: list[str]
    code: str
    fixed_code: str
    language: str
    sanitizer: str


def record_to_sample(record) -> Sample:
    metadata = record["metadata"]
    return Sample(
        input=record["input"],
        id=record["id"],
        choices=["Vulnerable", "Not vulnerable"],
        metadata={
            "code_files": metadata["code_files"],
            "code": metadata["code"],
            "fixed_code": metadata["fixed_code"],
            "language": metadata["language"],
            "sanitizer": metadata["sanitizer"],
        },
    )


def read_dataset(challenge_project: str):
    path = (
        Path(__file__).parent / "output" / f"{challenge_project.replace('-', '_')}.json"
    ).absolute()
    dataset = json_dataset(str(path), record_to_sample)
    return dataset
