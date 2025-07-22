from pathlib import Path

from inspect_ai.dataset import Sample, json_dataset
from pydantic import BaseModel


class PairedVulnMetadata(BaseModel, frozen=True):
    correct: str
    predict: str
    files: list[str]
    code: str
    language: str
    vulnerable: bool


def record_to_sample(record) -> Sample:
    metadata = record["metadata"]
    return Sample(
        input=record["input"],
        id=record["id"],
        choices=["Vulnerable", "Not vulnerable"],
        target="A" if metadata["vulnerable"] else "B",
        metadata={
            "correct": f"pair_correct_{metadata["cpv"]}",
            "predict": f"pair_prediction_{metadata["cpv"]}",
            "files": metadata["files"],
            "code": metadata["code"],
            "language": metadata["language"],
            "vulnerable": metadata["vulnerable"],
        },
    )


def read_dataset(challenge_project: str):
    path = (Path(__file__).parent / "output" / f"{challenge_project.replace("-", "_")}.json").absolute()
    dataset = json_dataset(str(path), record_to_sample)
    return dataset
