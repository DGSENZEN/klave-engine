"""Project-level AI reading: render every sheet frame, read it, keep the
readings with provenance, and offer them to the rules as the lowest-
ranked source of element specs.

Files, all under the project's control dir (they outlive a run):
  renders/<code>.png   — the frame as the model saw it (also what the visor
                          shows as "imagen de la hoja")
  ai_reads.json        — status + one SheetReading per frame + token totals
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from klave_engine.common.io import read_json, write_json
from klave_engine.detection.frames import SheetFrame
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.llm.reader import (
    MODEL,
    Reader,
    SheetReading,
    failed_reading,
    read_frames,
)
from klave_engine.llm.render import render_region

AI_READS_FILENAME = "ai_reads.json"
RENDERS_DIRNAME = "renders"


class AiReads(BaseModel):
    status: str = "idle"  # idle | running | done | cancelled | failed | unavailable
    started_at: str | None = None
    finished_at: str | None = None
    run_id: str | None = None  # the detection run whose frames were read
    # How many frames the job set out to read; readings grow one by one.
    total_frames: int = 0
    readings: list[SheetReading] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    notes: list[str] = Field(default_factory=list)


def _load_entities(artifact_dir: Path) -> list[NormalizedEntity]:
    return [
        NormalizedEntity.model_validate(e)
        for e in read_json(artifact_dir / "normalized_entities.json")
    ]


def _load_frames(artifact_dir: Path) -> list[SheetFrame]:
    path = artifact_dir / "frames.json"
    if not path.exists():
        return []
    return [SheetFrame.model_validate(f) for f in read_json(path)]


def render_frame_png(
    artifact_dir: Path, control_dir: Path, code: str, *, long_side_px: int = 2600
) -> Path | None:
    """The PNG of one frame, rendered once and cached under the control dir."""
    renders = control_dir / RENDERS_DIRNAME
    target = renders / f"{code}.png"
    if target.exists():
        return target
    frames = _load_frames(artifact_dir)
    frame = next((f for f in frames if f.code == code), None)
    if frame is None:
        return None
    entities = [e for e in _load_entities(artifact_dir) if e.source_file == frame.source_file]
    rendered = render_region(entities, frame.bbox, long_side_px=long_side_px)
    renders.mkdir(parents=True, exist_ok=True)
    target.write_bytes(rendered.png)
    return target


def render_all_frames(
    artifact_dir: Path, control_dir: Path, *, long_side_px: int = 2600
) -> list[tuple[str, str, str, bytes]]:
    """(code, title, kind, png) for every frame, drawing from each frame's own file."""
    frames = _load_frames(artifact_dir)
    if not frames:
        return []
    entities = _load_entities(artifact_dir)
    by_file: dict[str, list[NormalizedEntity]] = {}
    for e in entities:
        by_file.setdefault(e.source_file, []).append(e)
    renders = control_dir / RENDERS_DIRNAME
    renders.mkdir(parents=True, exist_ok=True)
    out: list[tuple[str, str, str, bytes]] = []
    for frame in frames:
        target = renders / f"{frame.code}.png"
        if target.exists():
            png = target.read_bytes()
        else:
            rendered = render_region(
                by_file.get(frame.source_file, entities), frame.bbox, long_side_px=long_side_px
            )
            png = rendered.png
            target.write_bytes(png)
        out.append((frame.code, frame.title, frame.kind, png))
    return out


def load_ai_reads(control_dir: Path) -> AiReads:
    path = control_dir / AI_READS_FILENAME
    if not path.exists():
        return AiReads()
    try:
        return AiReads.model_validate(read_json(path))
    except (ValueError, json.JSONDecodeError):
        return AiReads(status="failed", error="ai_reads.json ilegible")


def save_ai_reads(control_dir: Path, reads: AiReads) -> None:
    write_json(control_dir / AI_READS_FILENAME, reads)


def failed_codes(reads: AiReads) -> list[str]:
    """The frames whose reading is a recorded failure — exactly what a retry
    should ask for again, leaving every sheet already read alone."""
    return [r.frame_code for r in reads.readings if failed_reading(r)]


def run_ai_reading(
    artifact_dir: Path,
    control_dir: Path,
    reader: Reader,
    run_id: str | None = None,
    should_stop: Callable[[], bool] | None = None,
    model: str = MODEL,
    only_failed: bool = False,
    max_attempts: int = 3,
) -> AiReads:
    """Render and read every frame; persist after each sheet so the page can
    show progress, and stop between sheets when asked (keeping what was read).

    ``only_failed`` resumes instead of restarting: the sheets already read
    keep their readings and their token cost, and just the failures are asked
    for again. A saturated provider is retried without paying twice for the
    work it already did."""
    now = datetime.now(UTC).isoformat()
    kept: list[SheetReading] = []
    if only_failed:
        previous = load_ai_reads(control_dir)
        kept = [r for r in previous.readings if not failed_reading(r)]
    reads = AiReads(
        status="running",
        started_at=now,
        run_id=run_id,
        readings=list(kept),
        input_tokens=sum(r.input_tokens for r in kept),
        output_tokens=sum(r.output_tokens for r in kept),
    )
    save_ai_reads(control_dir, reads)
    try:
        renders = render_all_frames(artifact_dir, control_dir)
        reads.total_frames = len(renders)
        already = {r.frame_code for r in kept}
        pending = [r for r in renders if r[0] not in already]
        save_ai_reads(control_dir, reads)
        if not renders:
            reads.status = "done"
            reads.notes.append(
                "El dibujo no tiene marcos de hoja; no hay imágenes por hoja que leer."
            )
        elif only_failed and not pending:
            reads.status = "done"
            reads.notes.append(
                "Todas las hojas ya tienen lectura; no había nada que reintentar."
            )
        else:

            def on_reading(reading: SheetReading) -> None:
                reads.readings.append(reading)
                reads.input_tokens += reading.input_tokens
                reads.output_tokens += reading.output_tokens
                save_ai_reads(control_dir, reads)

            read_frames(
                pending, reader, on_reading=on_reading, should_stop=should_stop,
                model=model, max_attempts=max_attempts,
            )
            # Readings arrive in retry order; the page reads better in sheet order.
            position = {code: index for index, (code, *_rest) in enumerate(renders)}
            reads.readings.sort(key=lambda r: position.get(r.frame_code, len(renders)))
            cancelled = should_stop is not None and should_stop()
            partial = len(reads.readings) < len(renders)
            reads.status = "cancelled" if cancelled and partial else "done"
            if reads.status == "cancelled":
                reads.notes.append(
                    f"Lectura cancelada: {len(reads.readings)} de {len(renders)} hojas leídas "
                    "se conservan."
                )
            if only_failed:
                reads.notes.append(
                    f"Reintento de {len(pending)} hoja(s) sin lectura; las "
                    f"{len(kept)} ya leídas se conservaron sin volver a consultarlas."
                )
            failed = failed_codes(reads)
            if failed:
                reads.notes.append(
                    f"Hojas sin lectura ({len(failed)}): {', '.join(failed[:8])}"
                    + ("…" if len(failed) > 8 else "")
                    + ". Puedes reintentar solo esas."
                )
            reads.notes.append(
                "Lo leído por la IA es una sugerencia con procedencia; se aplica por debajo "
                "de cuadros, detalles y notas leídos por reglas, y solo al reprocesar."
            )
    except Exception as exc:  # noqa: BLE001 — the job must leave a record, not a trace
        reads.status = "failed"
        reads.error = str(exc)[:300]
    reads.finished_at = datetime.now(UTC).isoformat()
    save_ai_reads(control_dir, reads)
    return reads


def ai_element_specs(reads: AiReads) -> list[dict]:
    """Element specs as the schedule inventory understands them, source 'ia'."""
    specs: list[dict] = []
    for reading in reads.readings:
        for element in reading.read.elements:
            mark = element.mark.strip().upper()
            if not mark:
                continue
            section = None
            if element.section_cm:
                parts = element.section_cm.lower().replace("×", "x").split("x")
                try:
                    if len(parts) == 2:
                        section = (int(float(parts[0])), int(float(parts[1])))
                except ValueError:
                    section = None
            if (
                section is None and not element.rebar and not element.stirrups
                and not element.length_m
            ):
                continue
            specs.append(
                {
                    "mark": mark,
                    "family": element.family or "elemento",
                    "section_cm": section,
                    "rebar": element.rebar,
                    "stirrups": element.stirrups,
                    "length_m": element.length_m,
                    "mesh": None,
                    "source": "ia",
                    "source_text": (
                        f"IA · hoja {reading.frame_code}: "
                        f"{element.note or element.section_cm or ''}"
                    )[:120],
                    "confidence": round(min(max(element.confidence, 0.0), 1.0) * 0.6, 3),
                }
            )
    return specs
