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
from klave_engine.costing.reviews import load_reviews
from klave_engine.detection.results import Detection
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
    notes: str = ""


class EntryResult(BaseModel):
    drawing_id: str
    status: str
    available: bool
    fingerprint_matches: bool | None = None
    scores: list[TypeScore] = Field(default_factory=list)
    confirmed_missing: list[str] = Field(default_factory=list)
    excluded_present: list[str] = Field(default_factory=list)
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

def _fresh_detections(project_root: Path, settings: Settings) -> list[Detection]:
    """Run the current engine on a scratch copy of the drawings."""
    scratch = Path(tempfile.mkdtemp(prefix="klave_gold_")) / project_root.name
    try:
        shutil.copytree(project_root / "drawings", scratch / "drawings")
        return run_full_pipeline(scratch, settings).detections
    finally:
        shutil.rmtree(scratch.parent, ignore_errors=True)


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
    detections = (
        _fresh_detections(project_root, settings)
        if fresh
        else _active_detections(project_root, settings)
    )
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
    )


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
    message = "" if matches else "El plano cambió desde la captura; recaptura el gold."
    return EntryResult(
        drawing_id=entry.drawing_id,
        status=entry.status,
        available=True,
        fingerprint_matches=matches,
        scores=scores,
        confirmed_missing=confirmed_missing,
        excluded_present=excluded_present,
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
    summary = run(Path(args.gold), only=args.only)
    print(render_markdown(summary))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
