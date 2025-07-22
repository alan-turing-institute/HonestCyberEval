from enum import IntEnum

from inspect_ai.scorer import Metric, SampleScore, Value, metric

from dataset.paired import PairedVulnMetadata


class PairWisePrediction(IntEnum):
    # https://arxiv.org/pdf/2403.18624
    Correct = 0b11
    Vulnerable = 0b10  # The model incorrectly predicts both elements of the pair as vulnerable.
    Benign = 0b01  # The model incorrectly predicts both elements of the pair as benign.
    Reversed = 0b00  # The model incorrectly inverts the labels
    NotAvailable = -1


@metric
def pair_prediction() -> Metric:
    def metric(scores: list[SampleScore]) -> Value:
        if len(scores) != 2:
            return PairWisePrediction.NotAvailable

        metadata = scores[0].sample_metadata_as(PairedVulnMetadata)
        if metadata is None:
            raise ValueError("No sample metadata available on score")

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
                raise ValueError(f"Unexpected MCQ results \n{vulnerable_score}\n{patched_score}")

    return metric
