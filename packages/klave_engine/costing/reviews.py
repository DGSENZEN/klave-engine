"""Human corrections over the machine takeoff: the correction loop.

Detection reviews let an estimator confirm or exclude individual detections;
manual adjustments add or remove quantity at the concept level with a note.
Both carry attribution and flow into the cost report, so the number the tool
shows is always the number the human accepted — never detection output alone.

Reviews are keyed by ``display_label`` when the detection has one (labels are
deterministic per family ordinal, so re-runs name the same element identically
and review work survives a reprocess); unlabeled detections fall back to their
run-local detection id, which a reprocess invalidates harmlessly.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.common.io import read_json, write_json
from klave_engine.detection.results import Detection

REVIEWS_FILENAME = "detection_reviews.json"


class DetectionReview(BaseModel):
    status: Literal["confirmed", "excluded"]
    note: str = ""
    actor: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ManualAdjustment(BaseModel):
    """One documented human correction to a concept's quantity.

    ``quantity_delta`` adds or removes quantity; ``quantity_set`` replaces the
    quantity outright (editing in place). Exactly one of them is meaningful —
    a set ignores the delta — and both keep the engine's figure on the line
    (``engine_quantity``) so the change is always visible, never silent.
    """

    adjustment_id: str
    concept_code: str
    quantity_delta: float = 0.0
    quantity_set: float | None = None
    note: str = ""
    actor: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_set(self) -> bool:
        return self.quantity_set is not None


class VerificationState(BaseModel):
    """The verification path: explicit human sign-off per step."""

    units_confirmed_at: datetime | None = None
    units_confirmed_by: str = ""
    # The unit the engineer confirmed the drawing is in; overrides detection
    # and triggers a reprocess, because every detector threshold scales by it.
    units_override: str | None = None
    detections_confirmed_at: datetime | None = None
    detections_confirmed_by: str = ""
    assumptions_confirmed_at: datetime | None = None
    assumptions_confirmed_by: str = ""


class ProjectReviews(BaseModel):
    detections: dict[str, DetectionReview] = Field(default_factory=dict)
    adjustments: list[ManualAdjustment] = Field(default_factory=list)
    verification: VerificationState = Field(default_factory=VerificationState)


def review_key(detection: Detection) -> str:
    label = getattr(detection, "display_label", "") or ""
    return label or detection.detection_id


def load_reviews(control_dir: Path) -> ProjectReviews:
    path = control_dir / REVIEWS_FILENAME
    if not path.exists():
        return ProjectReviews()
    return ProjectReviews.model_validate(read_json(path))


def save_reviews(control_dir: Path, reviews: ProjectReviews) -> None:
    write_json(control_dir / REVIEWS_FILENAME, reviews)


def excluded_keys(reviews: ProjectReviews) -> set[str]:
    return {
        key
        for key, review in reviews.detections.items()
        if review.status == "excluded"
    }


def filter_excluded(
    detections: list[Detection], reviews: ProjectReviews
) -> list[Detection]:
    excluded = excluded_keys(reviews)
    if not excluded:
        return detections
    return [d for d in detections if review_key(d) not in excluded]
