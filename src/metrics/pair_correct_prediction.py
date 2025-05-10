from enum import IntEnum, auto

from inspect_ai.dataset._dataset import metadata_as
from inspect_ai.scorer import Metric, SampleScore, metric

from dataset.paired import PairedVulnMetadata


class PairWisePrediction(IntEnum):
    # https://arxiv.org/pdf/2403.18624
    Correct = 0b11
    Vulnerable = 0b10  # The model incorrectly predicts both elements of the pair as vulnerable.
    Benign = 0b01  # The model incorrectly predicts both elements of the pair as benign.
    Reversed = 0b00  # The model incorrectly inverts the labels
    NotAvailable = -1


@metric
def pair_correct_prediction() -> Metric:
    def metric(scores: list[SampleScore]) -> PairWisePrediction:
        if len(scores) != 2:
            return PairWisePrediction.NotAvailable
        if scores[0].sample_metadata is None:
            raise ValueError("No sample metadata available on score")

        metadata = metadata_as(
            scores[0].sample_metadata,
            PairedVulnMetadata,
        )

        vulnerable_score, patched_score = scores if metadata.vulnerable else reversed(scores)
        match vulnerable_score.score.value, patched_score.score.value:
            case (1, 1):
                return PairWisePrediction.Correct
            case (0, 1):
                return PairWisePrediction.Benign
            case (1, 0):
                return PairWisePrediction.Vulnerable
            case (0, 0):
                return PairWisePrediction.Reversed
            case _:
                raise ValueError("Unexpected MCQ results")

    return metric
