"""The correction loop API: detection reviews, manual adjustments, and the
verification path. Every mutation recomputes the cost report so the budget
always reflects what the human accepted, and broadcasts the change."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from klave_engine.common.config import Settings
from klave_engine.common.errors import ReportGenerationError
from klave_engine.common.ids import short_uuid
from klave_engine.costing.models import CostingOverrides, CostReport
from klave_engine.costing.recompute import load_overrides, recompute_and_persist
from klave_engine.costing.reviews import (
    DetectionReview,
    ManualAdjustment,
    ProjectReviews,
    load_reviews,
    save_reviews,
)
from klave_engine.costing.revision import build_revision_table
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from pydantic import BaseModel, Field

from apps.api.dependencies import (
    ProjectStore,
    get_settings,
    get_store,
    project_recompute_lock,
)
from apps.api.events import BUS, clean_actor, clean_client_id
from apps.api.jobs import JOB_STORE, JobQueueFullError

router = APIRouter(prefix="/projects")


class ReviewInput(BaseModel):
    status: Literal["confirmed", "excluded", "none"]
    note: str = Field(default="", max_length=300)


class AdjustmentInput(BaseModel):
    concept_code: str = Field(min_length=2, max_length=40)
    quantity_delta: float = 0.0
    # Editing in place: the quantity the engineer asserts, replacing the
    # engine's figure. A set needs a reason — the number changes silently
    # otherwise, and silence is what costs trust.
    quantity_set: float | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=300)


class BulkReviewInput(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=2000)
    status: Literal["confirmed", "excluded", "none"]
    note: str = Field(default="", max_length=300)
    # Batched clients send several calls and recompute once, on the last.
    recompute: bool = True


class VerificationInput(BaseModel):
    step: Literal["units", "detections", "assumptions"]
    confirmed: bool
    # Step "units" only: the unit the engineer asserts (m, cm, mm, ft, in).
    unit: Literal["m", "cm", "mm", "ft", "in"] | None = None


def _summary(reviews: ProjectReviews) -> dict:
    confirmed = sum(1 for r in reviews.detections.values() if r.status == "confirmed")
    excluded = sum(1 for r in reviews.detections.values() if r.status == "excluded")
    return {
        "confirmed": confirmed,
        "excluded": excluded,
        "adjustments": len(reviews.adjustments),
    }


def _reviews_payload(reviews: ProjectReviews) -> dict:
    payload = reviews.model_dump(mode="json")
    payload["summary"] = _summary(reviews)
    return payload


def _recompute_after_review(
    store: ProjectStore,
    settings: Settings,
    project_id: str,
    actor: str,
    client_id: str | None,
    action: str,
    detail: str,
) -> None:
    """Recompute with current overrides (version unchanged: reviews live
    outside the parametros form) and broadcast both the review change and the
    resulting cost movement."""
    root = store.get_root(project_id)
    control_dir = root / settings.processed_dir_name
    try:
        prev_grand_total = store.read_artifact(project_id, "cost_report.json")[
            "integration"
        ]["grand_total"]
    except (HTTPException, KeyError, TypeError):
        prev_grand_total = None
    overrides = load_overrides(control_dir) or CostingOverrides()
    try:
        report = recompute_and_persist(
            store.artifact_root(project_id),
            control_dir,
            root / "reports",
            project_id,
            overrides,
        )
    except ReportGenerationError:
        return  # Not processed yet: the review is saved and applies later.
    BUS.publish(
        "review_updated",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": client_id,
            "action": action,
            "detail": detail,
            "summary": _summary(load_reviews(control_dir)),
        },
    )
    BUS.publish(
        "costing_updated",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": client_id,
            "version": overrides.version,
            "direct_cost": report.boq.direct_cost_total,
            "grand_total": report.integration.grand_total,
            "prev_grand_total": prev_grand_total,
            "review_action": action,
        },
    )


@router.get("/{project_id}/reviews")
def get_reviews(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    return _reviews_payload(load_reviews(control_dir))


@router.put("/{project_id}/reviews/detections/{key}")
def set_detection_review(
    project_id: str,
    key: str,
    body: ReviewInput,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        reviews = load_reviews(control_dir)
        if body.status == "none":
            reviews.detections.pop(key, None)
        else:
            reviews.detections[key] = DetectionReview(
                status=body.status, note=body.note.strip(), actor=actor
            )
        save_reviews(control_dir, reviews)
        _recompute_after_review(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            f"detection_{body.status}", key,
        )
    return _reviews_payload(reviews)


@router.put("/{project_id}/reviews/detections")
def set_detection_reviews(
    project_id: str,
    body: BulkReviewInput,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Many elements, one verdict, one recompute: review at scale."""
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    keys = [k.strip() for k in body.keys if k.strip()][:2000]
    with project_recompute_lock(project_id):
        reviews = load_reviews(control_dir)
        for key in keys:
            if body.status == "none":
                reviews.detections.pop(key, None)
            else:
                reviews.detections[key] = DetectionReview(
                    status=body.status, note=body.note.strip(), actor=actor
                )
        save_reviews(control_dir, reviews)
        if body.recompute:
            _recompute_after_review(
                store, settings, project_id, actor, clean_client_id(x_client_id),
                f"detections_{body.status}", f"{len(keys)} elementos",
            )
    return _reviews_payload(reviews)


@router.get("/{project_id}/revision")
def get_revision_table(
    project_id: str,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Every element behind the presupuesto as a reviewable row."""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    report = CostReport.model_validate(store.read_artifact(project_id, "cost_report.json"))
    detections = [
        Detection.model_validate(d) for d in store.read_artifact(project_id, "detections.json")
    ]
    try:
        segmentation: SheetSegmentation | None = SheetSegmentation.model_validate(
            store.read_artifact(project_id, "views.json")
        )
    except HTTPException:
        segmentation = None
    table = build_revision_table(report, detections, segmentation, load_reviews(control_dir))
    return table.model_dump(mode="json")


@router.post("/{project_id}/reviews/adjustments", status_code=201)
def add_adjustment(
    project_id: str,
    body: AdjustmentInput,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    if body.quantity_set is None and body.quantity_delta == 0:
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "invalid_adjustment",
                "message": "El ajuste debe ser distinto de cero.",
            },
        )
    if not body.note.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "error_type": "reason_required",
                "message": (
                    "Fijar una cantidad requiere decir por qué."
                    if body.quantity_set is not None
                    else "Agregar una cantidad a mano requiere decir por qué."
                ),
            },
        )
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        reviews = load_reviews(control_dir)
        reviews.adjustments.append(
            ManualAdjustment(
                adjustment_id=short_uuid("adj"),
                concept_code=body.concept_code.strip().upper(),
                quantity_delta=body.quantity_delta if body.quantity_set is None else 0.0,
                quantity_set=body.quantity_set,
                note=body.note.strip(),
                actor=actor,
            )
        )
        save_reviews(control_dir, reviews)
        _recompute_after_review(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            "quantity_set" if body.quantity_set is not None else "adjustment_added",
            body.concept_code,
        )
    return _reviews_payload(reviews)


@router.delete("/{project_id}/reviews/adjustments/{adjustment_id}")
def delete_adjustment(
    project_id: str,
    adjustment_id: str,
    x_actor: Annotated[str | None, Header()] = None,
    x_client_id: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    actor = clean_actor(x_actor) or ""
    control_dir = store.get_root(project_id) / settings.processed_dir_name
    with project_recompute_lock(project_id):
        reviews = load_reviews(control_dir)
        before = len(reviews.adjustments)
        reviews.adjustments = [
            a for a in reviews.adjustments if a.adjustment_id != adjustment_id
        ]
        if len(reviews.adjustments) == before:
            raise HTTPException(
                status_code=404,
                detail={"error_type": "adjustment_not_found", "id": adjustment_id},
            )
        save_reviews(control_dir, reviews)
        _recompute_after_review(
            store, settings, project_id, actor, clean_client_id(x_client_id),
            "adjustment_removed", adjustment_id,
        )
    return _reviews_payload(reviews)


@router.put("/{project_id}/reviews/verification")
def set_verification(
    project_id: str,
    body: VerificationInput,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Verification sign-offs change no numbers; no recompute needed."""
    actor = clean_actor(x_actor) or ""
    root = store.get_root(project_id)
    control_dir = root / settings.processed_dir_name
    now = datetime.now(UTC)
    reprocessing = False
    with project_recompute_lock(project_id):
        reviews = load_reviews(control_dir)
        verification = reviews.verification
        if body.step == "units":
            verification.units_confirmed_at = now if body.confirmed else None
            verification.units_confirmed_by = actor if body.confirmed else ""
            if body.confirmed and body.unit:
                try:
                    current = store.read_artifact(project_id, "drawing_units.json").get("unit")
                except HTTPException:
                    current = None
                verification.units_override = body.unit
                # A unit the engine did not detect changes every threshold
                # downstream: the only honest response is to read again.
                reprocessing = body.unit != current
            elif not body.confirmed:
                verification.units_override = None
        elif body.step == "detections":
            verification.detections_confirmed_at = now if body.confirmed else None
            verification.detections_confirmed_by = actor if body.confirmed else ""
        else:
            verification.assumptions_confirmed_at = now if body.confirmed else None
            verification.assumptions_confirmed_by = actor if body.confirmed else ""
        save_reviews(control_dir, reviews)
    if reprocessing:
        try:
            JOB_STORE.enqueue(project_id, root, settings)
        except JobQueueFullError:
            reprocessing = False
    BUS.publish(
        "review_updated",
        project_id=project_id,
        actor=actor,
        data={
            "action": f"verification_{body.step}",
            "confirmed": body.confirmed,
            "unit": body.unit,
            "reprocessing": reprocessing,
        },
    )
    return {**_reviews_payload(reviews), "reprocessing": reprocessing}
