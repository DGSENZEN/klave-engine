"""Gold set: real drawings with known-good detections, and the runner that
keeps the engine honest against them.

An entry is captured from a processed project: its current detections are
the labels, and every human review on it is folded in — excluded detections
leave the labels, confirmed ones are pinned. The entry's ``status`` says how
much to trust it: ``baseline`` (no reviews: a regression guard, not truth),
``partial`` (some reviews), ``verified`` (the engineer signed off the
detections step). Drawings are identified by content hash, never committed.

    python -m klave_engine.evals.gold capture data/uploads/<root> --id prueba-1
    python -m klave_engine.evals.gold run            # all entries
"""

import argparse
import hashlib
import shutil
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.common.config import Settings, get_settings
from klave_engine.common.io import read_json, write_json, write_text
from klave_engine.costing.models import CostingConfig, CostReport
from klave_engine.costing.report import generate_cost_report
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.dimensions import DimensionInventory
from klave_engine.detection.results import Detection
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.units import DrawingUnits
from klave_engine.pipeline import run_full_pipeline

GOLD_DIR = Path("evals/gold")
DRAWING_SUFFIXES = (".dxf", ".dwg")


class TypeScore(BaseModel):
    detection_type: str
    expected: int
    predicted: int
    precision: float
    recall: float
    f1: float
    baseline_f1: float
    passed: bool


class QuantityExpectation(BaseModel):
    """What one concept should measure on this drawing. ``engine`` rows are
    the current engine's own figure (a regression fence); ``human`` rows are
    a takeoff someone did by hand (the truth), with its own tolerance."""

    quantity: float
    unit: str
    tolerance_pct: float = 10.0
    source: Literal["engine", "human"] = "engine"
    note: str = ""


class MoneyExpectation(BaseModel):
    """Quantities and the direct cost at the engine's reference prices, so a
    change in a rule, a matrix or a seed price shows up as money."""

    concepts: dict[str, QuantityExpectation] = Field(default_factory=dict)
    direct_cost: float | None = None
    direct_cost_tolerance_pct: float = 5.0
    unpriced: list[str] = Field(default_factory=list)


class MoneyScore(BaseModel):
    concept_code: str
    unit: str
    expected: float
    actual: float | None
    deviation_pct: float | None
    tolerance_pct: float
    source: str
    passed: bool


class GoldEntry(BaseModel):
    drawing_id: str
    source: str
    files: dict[str, str]
    status: Literal["baseline", "partial", "verified"]
    captured_at: datetime
    labels: dict[str, list[str]] = Field(default_factory=dict)
    confirmed: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    baseline_f1: dict[str, float] = Field(default_factory=dict)
    money: MoneyExpectation | None = None
    notes: str = ""


class EntryResult(BaseModel):
    drawing_id: str
    status: str
    available: bool
    fingerprint_matches: bool | None = None
    scores: list[TypeScore] = Field(default_factory=list)
    confirmed_missing: list[str] = Field(default_factory=list)
    excluded_present: list[str] = Field(default_factory=list)
    money_scores: list[MoneyScore] = Field(default_factory=list)
    direct_cost_expected: float | None = None
    direct_cost_actual: float | None = None
    direct_cost_passed: bool | None = None
    concepts_unexpected: list[str] = Field(default_factory=list)
    passed: bool
    message: str = ""


# ------------------------------------------------------------------ helpers

def _key(detection: Detection) -> str:
    return detection.display_label or detection.label


def fingerprint(project_root: Path) -> dict[str, str]:
    drawings = project_root / "drawings"
    files: dict[str, str] = {}
    for path in sorted(drawings.glob("*")):
        if path.suffix.lower() in DRAWING_SUFFIXES and path.is_file():
            files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def _active_detections(project_root: Path, settings: Settings) -> list[Detection]:
    control_dir = project_root / settings.processed_dir_name
    pointer = control_dir / "active_run.json"
    artifact_dir = control_dir
    if pointer.exists():
        try:
            candidate = (control_dir / str(read_json(pointer)["artifact_dir"])).resolve()
            if candidate.is_dir():
                artifact_dir = candidate
        except (KeyError, TypeError, OSError, ValueError):
            pass
    path = artifact_dir / "detections.json"
    if not path.exists():
        raise FileNotFoundError(f"No hay detections.json en {artifact_dir}; procesa el proyecto.")
    return [Detection.model_validate(d) for d in read_json(path)]


def _score(
    predicted: list[Detection], labels: dict[str, list[str]], baseline: dict[str, float]
) -> list[TypeScore]:
    by_type: dict[str, Counter[str]] = {}
    for detection in predicted:
        by_type.setdefault(detection.detection_type.value, Counter())[_key(detection)] += 1
    scores = []
    for detection_type in sorted(set(labels) | set(by_type)):
        expected = Counter(labels.get(detection_type, []))
        got = by_type.get(detection_type, Counter())
        tp = sum((expected & got).values())
        fp = sum((got - expected).values())
        fn = sum((expected - got).values())
        precision = tp / (tp + fp) if tp + fp else (1.0 if not expected else 0.0)
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        base = baseline.get(detection_type, 0.0)
        scores.append(
            TypeScore(
                detection_type=detection_type,
                expected=sum(expected.values()),
                predicted=sum(got.values()),
                precision=round(precision, 4),
                recall=round(recall, 4),
                f1=round(f1, 4),
                baseline_f1=round(base, 4),
                passed=f1 + 1e-9 >= base,
            )
        )
    return scores


# ------------------------------------------------------------------ capture

def _engine_money(scratch: Path, settings: Settings, detections: list[Detection]) -> CostReport:
    """The presupuesto the pure engine produces for a run: default catalog,
    reference prices, default assumptions — no taller catálogo, no reviews —
    so two runs of the same engine on the same drawing agree to the cent."""
    processed = scratch / settings.processed_dir_name

    def optional(name: str) -> dict | None:
        path = processed / name
        return read_json(path) if path.exists() else None

    units_raw = optional("drawing_units.json") or {}
    units = DrawingUnits.model_validate(units_raw) if units_raw else DrawingUnits(
        unit="drawing_units", source="unknown", confidence=0.0
    )
    views = optional("views.json")
    dims = optional("dimensions.json")
    return generate_cost_report(
        scratch.name,
        detections,
        units,
        CostingConfig(),
        SheetSegmentation.model_validate(views) if views else None,
        DimensionInventory.model_validate(dims) if dims else None,
        schedule_specs=optional("schedules.json"),
    )


def _fresh_run(project_root: Path, settings: Settings) -> tuple[list[Detection], CostReport]:
    """Run the current engine on a scratch copy of the drawings: the
    detections and the pure-engine presupuesto."""
    scratch = Path(tempfile.mkdtemp(prefix="klave_gold_")) / project_root.name
    try:
        shutil.copytree(project_root / "drawings", scratch / "drawings")
        detections = run_full_pipeline(scratch, settings).detections
        return detections, _engine_money(scratch, settings, detections)
    finally:
        shutil.rmtree(scratch.parent, ignore_errors=True)


def money_from_report(report: CostReport) -> MoneyExpectation:
    """Capture every line's quantity and the direct cost as the fence."""
    concepts = {
        line.concept_code: QuantityExpectation(
            quantity=round(line.quantity, 3), unit=line.unit, source="engine",
        )
        for line in report.boq.lines
    }
    return MoneyExpectation(
        concepts=concepts,
        direct_cost=round(report.boq.direct_cost_total, 2),
        unpriced=sorted(line.concept_code for line in report.boq.lines if line.unpriced),
    )


def score_money(
    expected: MoneyExpectation, report: CostReport
) -> tuple[list[MoneyScore], bool | None, list[str]]:
    """Per-concept deviation against tolerance, the direct-cost verdict, and
    the concepts the engine now produces that the gold never saw."""
    actual = {line.concept_code: line for line in report.boq.lines}
    scores: list[MoneyScore] = []
    for code, want in sorted(expected.concepts.items()):
        line = actual.get(code)
        if line is None:
            scores.append(MoneyScore(
                concept_code=code, unit=want.unit, expected=want.quantity, actual=None,
                deviation_pct=None, tolerance_pct=want.tolerance_pct, source=want.source,
                passed=False,
            ))
            continue
        if want.quantity == 0:
            deviation = 0.0 if line.quantity == 0 else 100.0
        else:
            deviation = abs(line.quantity - want.quantity) / abs(want.quantity) * 100.0
        scores.append(MoneyScore(
            concept_code=code, unit=want.unit, expected=want.quantity,
            actual=round(line.quantity, 3), deviation_pct=round(deviation, 2),
            tolerance_pct=want.tolerance_pct, source=want.source,
            passed=deviation <= want.tolerance_pct and line.unit.upper() == want.unit.upper(),
        ))
    cost_passed: bool | None = None
    if expected.direct_cost is not None:
        if expected.direct_cost == 0:
            cost_passed = report.boq.direct_cost_total == 0
        else:
            drift = abs(report.boq.direct_cost_total - expected.direct_cost)
            cost_passed = drift / expected.direct_cost * 100.0 <= expected.direct_cost_tolerance_pct
    unexpected = sorted(code for code in actual if code not in expected.concepts)
    return scores, cost_passed, unexpected


def capture(
    project_root: Path,
    drawing_id: str,
    settings: Settings | None = None,
    *,
    fresh: bool = False,
) -> GoldEntry:
    """Fold a processed project's detections and reviews into a gold entry.
    With ``fresh`` the labels come from a current-engine run instead of the
    project's stored artifact, so a baseline never lags behind the parser."""
    settings = settings or get_settings()
    project_root = Path(project_root)
    money: MoneyExpectation | None = None
    if fresh:
        detections, report = _fresh_run(project_root, settings)
        money = money_from_report(report)
    else:
        detections = _active_detections(project_root, settings)
    reviews = load_reviews(project_root / settings.processed_dir_name)
    excluded = sorted(k for k, r in reviews.detections.items() if r.status == "excluded")
    confirmed = sorted(k for k, r in reviews.detections.items() if r.status == "confirmed")
    excluded_set = set(excluded)

    labels: dict[str, list[str]] = {}
    for detection in detections:
        if _key(detection) in excluded_set:
            continue
        labels.setdefault(detection.detection_type.value, []).append(_key(detection))
    for values in labels.values():
        values.sort()

    if reviews.verification.detections_confirmed_at is not None:
        status: Literal["baseline", "partial", "verified"] = "verified"
    elif reviews.detections:
        status = "partial"
    else:
        status = "baseline"

    # The entry's own starting point: excluded detections the engine still
    # produces lower precision here, which is exactly the debt to pay down.
    baseline = {s.detection_type: s.f1 for s in _score(detections, labels, {})}
    return GoldEntry(
        drawing_id=drawing_id,
        source=str(project_root),
        files=fingerprint(project_root),
        status=status,
        captured_at=datetime.now(UTC),
        labels=labels,
        confirmed=confirmed,
        excluded=excluded,
        baseline_f1=baseline,
        money=money,
    )


def capture_money(
    gold_dir: Path = GOLD_DIR, only: str | None = None, settings: Settings | None = None
) -> list[Path]:
    """Fresh engine run per entry; its quantities and direct cost become the
    entry's money fence. Human rows already in the entry are kept: only the
    engine's own rows are refreshed."""
    settings = settings or get_settings()
    saved: list[Path] = []
    for entry in load_entries(gold_dir):
        if only is not None and entry.drawing_id != only:
            continue
        source = Path(entry.source)
        if not (source / "drawings").is_dir():
            continue
        _detections, report = _fresh_run(source, settings)
        fresh = money_from_report(report)
        if entry.money is not None:
            for code, want in entry.money.concepts.items():
                if want.source == "human":
                    fresh.concepts[code] = want
            if entry.money.direct_cost_tolerance_pct != 5.0:
                fresh.direct_cost_tolerance_pct = entry.money.direct_cost_tolerance_pct
        entry.money = fresh
        saved.append(save_entry(entry, gold_dir))
    return saved


def save_entry(entry: GoldEntry, gold_dir: Path = GOLD_DIR) -> Path:
    gold_dir.mkdir(parents=True, exist_ok=True)
    path = gold_dir / f"{entry.drawing_id}.json"
    write_json(path, entry)
    return path


def load_entries(gold_dir: Path = GOLD_DIR) -> list[GoldEntry]:
    if not gold_dir.exists():
        return []
    return [GoldEntry.model_validate(read_json(p)) for p in sorted(gold_dir.glob("*.json"))]


# --------------------------------------------------------------------- run

def evaluate_entry(entry: GoldEntry, settings: Settings | None = None) -> EntryResult:
    """Re-run the pipeline on a scratch copy of the drawings and score it."""
    settings = settings or get_settings()
    source = Path(entry.source)
    if not (source / "drawings").is_dir():
        return EntryResult(
            drawing_id=entry.drawing_id, status=entry.status, available=False, passed=True,
            message=f"Plano no disponible localmente: {entry.source}",
        )
    matches = fingerprint(source) == entry.files
    scratch = Path(tempfile.mkdtemp(prefix="klave_gold_")) / entry.drawing_id
    try:
        shutil.copytree(source / "drawings", scratch / "drawings")
        result = run_full_pipeline(scratch, settings)
        predicted = result.detections
        report = _engine_money(scratch, settings, predicted) if entry.money else None
    finally:
        shutil.rmtree(scratch.parent, ignore_errors=True)

    keys = {_key(d) for d in predicted}
    scores = _score(predicted, entry.labels, entry.baseline_f1)
    confirmed_missing = [c for c in entry.confirmed if c not in keys]
    excluded_present = [x for x in entry.excluded if x in keys]
    if entry.status == "verified":
        passed = all(s.f1 == 1.0 for s in scores) and not confirmed_missing
    else:
        passed = all(s.passed for s in scores) and not confirmed_missing
    money_scores: list[MoneyScore] = []
    cost_passed: bool | None = None
    unexpected: list[str] = []
    cost_actual: float | None = None
    if entry.money is not None and report is not None:
        money_scores, cost_passed, unexpected = score_money(entry.money, report)
        cost_actual = round(report.boq.direct_cost_total, 2)
        passed = (
            passed and all(m.passed for m in money_scores)
            and cost_passed is not False and not unexpected
        )
    message = "" if matches else "El plano cambió desde la captura; recaptura el gold."
    return EntryResult(
        drawing_id=entry.drawing_id,
        status=entry.status,
        available=True,
        fingerprint_matches=matches,
        scores=scores,
        confirmed_missing=confirmed_missing,
        excluded_present=excluded_present,
        money_scores=money_scores,
        direct_cost_expected=entry.money.direct_cost if entry.money else None,
        direct_cost_actual=cost_actual,
        direct_cost_passed=cost_passed,
        concepts_unexpected=unexpected,
        passed=passed,
        message=message,
    )


def run(
    gold_dir: Path = GOLD_DIR,
    only: str | None = None,
    settings: Settings | None = None,
    reports_dir: Path | None = None,
) -> dict:
    settings = settings or get_settings()
    entries = [e for e in load_entries(gold_dir) if only is None or e.drawing_id == only]
    results = [evaluate_entry(entry, settings) for entry in entries]
    summary = {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "entries": [r.model_dump() for r in results],
        "all_passed": all(r.passed for r in results),
        "unavailable": [r.drawing_id for r in results if not r.available],
    }
    out = reports_dir or settings.reports_dir
    write_json(out / "gold_eval.json", summary)
    write_text(out / "gold_eval.md", render_markdown(summary))
    return summary


def render_markdown(summary: dict) -> str:
    lines = [
        "# Gold set",
        "",
        f"Overall: {'PASS' if summary['all_passed'] else 'FAIL'} — {summary['evaluated_at']}",
        "",
    ]
    for entry in summary["entries"]:
        lines.append(f"## {entry['drawing_id']} ({entry['status']})")
        lines.append("")
        if not entry["available"]:
            lines += [f"_{entry['message']}_", ""]
            continue
        if entry["message"]:
            lines += [f"**{entry['message']}**", ""]
        lines += ["| Tipo | Esperado | Predicho | P | R | F1 | F1 base | OK |",
                  "|---|---|---|---|---|---|---|---|"]
        for s in entry["scores"]:
            ok = "sí" if s["passed"] else "NO"
            lines.append(
                f"| {s['detection_type']} | {s['expected']} | {s['predicted']} | {s['precision']} "
                f"| {s['recall']} | {s['f1']} | {s['baseline_f1']} | {ok} |"
            )
        if entry["confirmed_missing"]:
            missing = ", ".join(entry["confirmed_missing"])
            lines += ["", f"Confirmadas que ya no aparecen: {missing}"]
        if entry["excluded_present"]:
            lines += ["", "Excluidas que el motor sigue produciendo: "
                      + ", ".join(entry["excluded_present"])]
        if entry.get("money_scores"):
            lines += ["", "### Cantidades y dinero", "",
                      "| Concepto | Unidad | Esperado | Motor | Desv. % | Tol. % | Fuente | OK |",
                      "|---|---|---|---|---|---|---|---|"]
            for m in entry["money_scores"]:
                actual = "—" if m["actual"] is None else f"{m['actual']:g}"
                dev = "—" if m["deviation_pct"] is None else f"{m['deviation_pct']:g}"
                ok = "sí" if m["passed"] else "NO"
                lines.append(
                    f"| {m['concept_code']} | {m['unit']} | {m['expected']:g} | {actual} | {dev} "
                    f"| {m['tolerance_pct']:g} | {m['source']} | {ok} |"
                )
            if entry.get("direct_cost_expected") is not None:
                verdict = "sí" if entry.get("direct_cost_passed") else "NO"
                lines += ["", f"Costo directo: esperado ${entry['direct_cost_expected']:,.2f}, "
                          f"motor ${entry.get('direct_cost_actual') or 0:,.2f} — OK: {verdict}"]
            if entry.get("concepts_unexpected"):
                lines += ["", "Conceptos nuevos que el gold no conoce: "
                          + ", ".join(entry["concepts_unexpected"])]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klave-gold")
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="capture a processed project into the gold set")
    cap.add_argument("project_root")
    cap.add_argument("--id", required=True, dest="drawing_id")
    cap.add_argument("--gold", default=str(GOLD_DIR))
    cap.add_argument(
        "--fresh", action="store_true",
        help="label from a current-engine run instead of the stored artifact",
    )
    money = sub.add_parser(
        "money", help="capture the engine's quantities and direct cost into existing entries"
    )
    money.add_argument("--gold", default=str(GOLD_DIR))
    money.add_argument("--only")
    runner = sub.add_parser("run", help="evaluate the engine against the gold set")
    runner.add_argument("--gold", default=str(GOLD_DIR))
    runner.add_argument("--only")
    args = parser.parse_args(argv)

    if args.command == "capture":
        entry = capture(Path(args.project_root), args.drawing_id, fresh=args.fresh)
        path = save_entry(entry, Path(args.gold))
        counts = {k: len(v) for k, v in entry.labels.items()}
        print(f"{entry.drawing_id}: {entry.status} — {counts} → {path}")
        return 0
    if args.command == "money":
        for path in capture_money(Path(args.gold), only=args.only):
            print(f"money → {path}")
        return 0
    summary = run(Path(args.gold), only=args.only)
    print(render_markdown(summary))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
