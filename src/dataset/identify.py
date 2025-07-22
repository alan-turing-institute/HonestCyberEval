from pathlib import Path

from inspect_ai.dataset import Sample, json_dataset
from pydantic import BaseModel


class ExploitDetectMetadata(BaseModel, frozen=True):
    cpv: str
    code_files: list[str]
    code: str
    language: str
    vulnerable: bool


choices = []


def record_to_sample(record) -> Sample:
    metadata = record["metadata"]
    sanitizer = metadata["sanitizer"]
    if sanitizer not in choices:
        choices.append(sanitizer)

    return Sample(
        input=record["input"],
        id=record["id"],
        choices=choices,
        target=chr(ord("A") + choices.index(sanitizer)),
        metadata={
            "cpv": metadata["cpv"],
            "code_files": metadata["code_files"],
            "code": metadata["code"],
            "language": metadata["language"],
            "vulnerable": metadata["vulnerable"],
        },
    )


def read_dataset(challenge_project: str):
    path = (
        Path(__file__).parent / "output" / f"{challenge_project.replace('-', '_')}.json"
    ).absolute()
    dataset = json_dataset(str(path), record_to_sample)
    return dataset
