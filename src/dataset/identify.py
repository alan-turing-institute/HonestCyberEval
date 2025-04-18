from pathlib import Path

from inspect_ai.dataset import Sample, json_dataset
from pydantic import BaseModel


class ExploitDetectMetadata(BaseModel, frozen=True):
    cpv: str
    files: list[str]
    code: str
    language: str
    vulnerable: bool


def filter_out_patched(sample: Sample) -> bool:
    metadata = sample.metadata_as(ExploitDetectMetadata)
    return metadata.vulnerable


choices = [
    "AddressSanitizer: SEGV",
    "AddressSanitizer: heap-buffer-overflow",
    "AddressSanitizer: attempting double-free",
    "AddressSanitizer: heap-use-after-free",
    "AddressSanitizer: global-buffer-overflow",
]


def record_to_sample(record) -> Sample:
    metadata = record["metadata"]
    return Sample(
        input=record["input"],
        id=record["id"],
        choices=choices,
        target=chr(ord("A") + choices.index(metadata["sanitizer"])),
        metadata={
            "cpv": metadata["cpv"],
            "files": metadata["files"],
            "code": metadata["code"],
            "language": metadata["language"],
            "vulnerable": metadata["vulnerable"],
        },
    )


def read_dataset(challenge_project: str):
    path = (Path(__file__).parent / "output" / f"{challenge_project.replace("-", "_")}.json").absolute()
    dataset = json_dataset(str(path), record_to_sample)
    return dataset.filter(filter_out_patched)
