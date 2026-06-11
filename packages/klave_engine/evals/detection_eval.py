"""Detection evaluation: predicted detections vs gold labels (per type)."""

from collections import Counter

from pydantic import BaseModel

from klave_engine.detection.results import Detection


class DetectionEvalResult(BaseModel):
    detection_type: str
    expected_count: int
    predicted_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def evaluate_detections(
    detections: list[Detection], gold: dict[str, list[str]]
) -> list[DetectionEvalResult]:
    """Match predicted labels against gold labels as multisets, per detection type."""
    predicted_by_type: dict[str, Counter] = {}
    for detection in detections:
        predicted_by_type.setdefault(detection.detection_type.value, Counter())[
            detection.label
        ] += 1

    results = []
    for detection_type in sorted(set(gold) | set(predicted_by_type)):
        expected = Counter(gold.get(detection_type, []))
        predicted = predicted_by_type.get(detection_type, Counter())
        true_positives = sum((expected & predicted).values())
        false_positives = sum((predicted - expected).values())
        false_negatives = sum((expected - predicted).values())
        precision = _safe_div(true_positives, true_positives + false_positives)
        recall = _safe_div(true_positives, true_positives + false_negatives)
        results.append(
            DetectionEvalResult(
                detection_type=detection_type,
                expected_count=sum(expected.values()),
                predicted_count=sum(predicted.values()),
                true_positives=true_positives,
                false_positives=false_positives,
                false_negatives=false_negatives,
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1=round(_safe_div(2 * precision * recall, precision + recall), 4),
            )
        )
    return results
