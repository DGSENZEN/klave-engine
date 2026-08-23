"""Versions of the presupuesto: named snapshots an engineer saves on purpose.

A version freezes the cost report together with everything a human had
decided at that moment — detection reviews, manual adjustments, costing
overrides — so it can be compared line by line against the current state or
another version, and restored. Restoring reapplies the human decisions on
the *current* detection run (the drawings may have been reprocessed since);
the snapshot's figures stay in the version, untouched, for the record.

Files, under the project's control dir:
  versions/index.json        — the list, newest last
  versions/<version_id>.json — one full snapshot
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.ids import short_uuid
from klave_engine.common.io import read_json, write_json
from klave_engine.costing.models import CostingOverrides, CostReport
from klave_engine.costing.reviews import ProjectReviews, load_reviews

VERSIONS_DIRNAME = "versions"
INDEX_FILENAME = "index.json"


class VersionSummary(BaseModel):
    version_id: str
    number: int
    label: str
    note: str = ""
    actor: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str | None = None
    overrides_version: int = 0
    direct_cost: float
    grand_total: float
    line_count: int
    adjustments: int = 0
    excluded: int = 0


class PresupuestoVersion(BaseModel):
    summary: VersionSummary
    report: CostReport
    reviews: ProjectReviews
    overrides: CostingOverrides


class LineChange(BaseModel):
    concept_code: str
    description: str
    unit: str
    status: str  # added | removed | changed | same
    quantity_before: float | None = None
    quantity_after: float | None = None
    unit_price_before: float | None = None
    unit_price_after: float | None = None
    amount_before: float = 0.0
    amount_after: float = 0.0

    @property
    def amount_delta(self) -> float:
        return round(self.amount_after - self.amount_before, 2)


class VersionDiff(BaseModel):
    before_label: str
    after_label: str
    lines: list[LineChange]
    direct_cost_before: float
    direct_cost_after: float
    grand_total_before: float
    grand_total_after: float
    changed: int
    added: int
    removed: int
    notes: list[str] = Field(default_factory=list)


def _dir(control_dir: Path) -> Path:
    return control_dir / VERSIONS_DIRNAME


def list_versions(control_dir: Path) -> list[VersionSummary]:
    path = _dir(control_dir) / INDEX_FILENAME
    if not path.exists():
        return []
    return [VersionSummary.model_validate(item) for item in read_json(path)]


def _save_index(control_dir: Path, versions: list[VersionSummary]) -> None:
    write_json(_dir(control_dir) / INDEX_FILENAME, versions)


def load_version(control_dir: Path, version_id: str) -> PresupuestoVersion | None:
    path = _dir(control_dir) / f"{version_id}.json"
    if not path.exists() or not version_id.startswith("ver_"):
        return None
    return PresupuestoVersion.model_validate(read_json(path))


def save_version(
    control_dir: Path,
    report: CostReport,
    reviews: ProjectReviews,
    overrides: CostingOverrides,
    *,
    label: str,
    note: str = "",
    actor: str = "",
    run_id: str | None = None,
) -> VersionSummary:
    versions = list_versions(control_dir)
    number = (max((v.number for v in versions), default=0)) + 1
    summary = VersionSummary(
        version_id=short_uuid("ver"),
        number=number,
        label=label.strip() or f"Versión {number}",
        note=note.strip(),
        actor=actor,
        run_id=run_id,
        overrides_version=overrides.version,
        direct_cost=report.boq.direct_cost_total,
        grand_total=report.integration.grand_total,
        line_count=len(report.boq.lines),
        adjustments=len(reviews.adjustments),
        excluded=sum(1 for r in reviews.detections.values() if r.status == "excluded"),
    )
    _dir(control_dir).mkdir(parents=True, exist_ok=True)
    write_json(
        _dir(control_dir) / f"{summary.version_id}.json",
        PresupuestoVersion(summary=summary, report=report, reviews=reviews, overrides=overrides),
    )
    versions.append(summary)
    _save_index(control_dir, versions)
    return summary


AUTO_LABEL_PREFIX = "Antes de reprocesar"


def snapshot_before_reprocess(
    control_dir: Path, previous_run_id: str | None = None
) -> VersionSummary | None:
    """Keep the presupuesto as it stood before a new run replaces it, so the
    engineer can compare corrida N with N+1 line by line. Saved once per
    run (a second reprocess without changes does not pile up copies)."""
    from klave_engine.costing.recompute import load_overrides  # avoids an import cycle

    pointer = control_dir / "active_run.json"
    if not pointer.exists():
        return None
    try:
        active = read_json(pointer)
        artifact_dir = control_dir / str(active.get("artifact_dir") or "")
        override = control_dir / "cost_report_override.json"
        report_path = override if override.exists() else artifact_dir / "cost_report.json"
        if not report_path.exists():
            return None
        report = CostReport.model_validate(read_json(report_path))
    except (OSError, ValueError):
        return None
    run_id = previous_run_id or str(active.get("run_id") or "") or None
    if run_id and any(
        v.run_id == run_id and v.label.startswith(AUTO_LABEL_PREFIX)
        for v in list_versions(control_dir)
    ):
        return None
    overrides = load_overrides(control_dir) or CostingOverrides()
    return save_version(
        control_dir,
        report,
        load_reviews(control_dir),
        overrides,
        label=f"{AUTO_LABEL_PREFIX} ({datetime.now(UTC):%d/%m %H:%M})",
        note="Guardada sola al reprocesar: el presupuesto tal como estaba con la corrida anterior.",
        actor="Klave",
        run_id=run_id,
    )


def delete_version(control_dir: Path, version_id: str) -> bool:
    versions = list_versions(control_dir)
    kept = [v for v in versions if v.version_id != version_id]
    if len(kept) == len(versions):
        return False
    path = _dir(control_dir) / f"{version_id}.json"
    if path.exists():
        path.unlink()
    _save_index(control_dir, kept)
    return True


def diff_reports(
    before: CostReport, after: CostReport, *, before_label: str, after_label: str
) -> VersionDiff:
    """Line-by-line movement between two presupuestos, by concept code."""
    lines_before = {line.concept_code: line for line in before.boq.lines}
    lines_after = {line.concept_code: line for line in after.boq.lines}
    changes: list[LineChange] = []
    order = list(lines_after) + [code for code in lines_before if code not in lines_after]
    for code in order:
        b = lines_before.get(code)
        a = lines_after.get(code)
        if a is None and b is None:
            continue
        if b is None and a is not None:
            status = "added"
        elif a is None and b is not None:
            status = "removed"
        elif (
            a is not None
            and b is not None
            and (
                abs(a.quantity - b.quantity) > 1e-6
                or abs(a.unit_price - b.unit_price) > 0.005
                or abs(a.amount - b.amount) > 0.005
            )
        ):
            status = "changed"
        else:
            status = "same"
        ref = a or b
        assert ref is not None
        changes.append(
            LineChange(
                concept_code=code,
                description=ref.description,
                unit=ref.unit,
                status=status,
                quantity_before=b.quantity if b else None,
                quantity_after=a.quantity if a else None,
                unit_price_before=b.unit_price if b else None,
                unit_price_after=a.unit_price if a else None,
                amount_before=b.amount if b else 0.0,
                amount_after=a.amount if a else 0.0,
            )
        )
    notes: list[str] = []
    if before.drawing_units.unit != after.drawing_units.unit:
        notes.append(
            f"Unidades distintas: {before.drawing_units.unit} → {after.drawing_units.unit}."
        )
    return VersionDiff(
        before_label=before_label,
        after_label=after_label,
        lines=changes,
        direct_cost_before=before.boq.direct_cost_total,
        direct_cost_after=after.boq.direct_cost_total,
        grand_total_before=before.integration.grand_total,
        grand_total_after=after.integration.grand_total,
        changed=sum(1 for c in changes if c.status == "changed"),
        added=sum(1 for c in changes if c.status == "added"),
        removed=sum(1 for c in changes if c.status == "removed"),
        notes=notes,
    )
