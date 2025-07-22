from inspect_ai.scorer import Metric, SampleScore, Value, metric

from dataset.paired import PairedVulnMetadata


@metric
def pair_correct() -> Metric:
    def metric(scores: list[SampleScore]) -> Value:
        if len(scores) != 2:
            return 0

        metadata = scores[0].sample_metadata_as(PairedVulnMetadata)
        if metadata is None:
            raise ValueError("No sample metadata available on score")

        vulnerable_score, patched_score = scores if metadata.vulnerable else reversed(scores)
        match vulnerable_score.score.value, patched_score.score.value:
            case (1, 1):
                return 1
            case (0, 1) | (1, 0) | (0, 0):
                return 0
            case _:
                raise ValueError(f"Unexpected MCQ results \n{vulnerable_score}\n{patched_score}")

    return metric
