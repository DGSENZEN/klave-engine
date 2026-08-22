"""LibreDWG ``dwg2dxf`` adapter for server-side DWG→DXF conversion.

The ODA-shaped :class:`DwgToDxfConverter` converts whole directories; for the
web upload flow we convert a single file with GNU LibreDWG's ``dwg2dxf``.
Failures are returned, never raised.

Conversion is not "first readable wins" but "most complete wins": the
standard and ``--as r2000`` outputs are both produced (sub-second on real
drawings), probed with ezdxf, and ranked by what they contain — model-space
entities, texts, block definitions, layouts. Minimal mode (``-m``) is a last
resort only: it drops block definitions by design, which is exactly where
real drawings hide castillos and marks. A converter that exits 0 but writes
an unreadable DXF is a failed attempt, not a success the parser discovers
later.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import recover as ezdxf_recover
from ezdxf.lldxf.const import DXFStructureError

from klave_engine.common.logging import get_logger, log_stage

logger = get_logger(__name__)

_CANDIDATES: list[tuple[str, list[str]]] = [
    ("estándar", []),
    ("versión r2000", ["--as", "r2000"]),
]
_LAST_RESORT: tuple[str, list[str]] = ("modo mínimo", ["-m"])


def dwg2dxf_available() -> bool:
    return shutil.which("dwg2dxf") is not None


def dwg2dxf_version() -> str | None:
    executable = shutil.which("dwg2dxf")
    if executable is None:
        return None
    try:
        completed = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = (completed.stdout or completed.stderr).strip().splitlines()
    return first_line[0][:80] if first_line else None


def _load(path: Path) -> Any | None:
    try:
        return ezdxf.readfile(str(path))
    except (DXFStructureError, UnicodeDecodeError):
        try:
            doc, _auditor = ezdxf_recover.readfile(str(path))
            return doc
        except Exception:
            return None
    except OSError:
        return None


def _output_is_readable(path: Path) -> bool:
    """Cheap probe: the DXF must load strictly or in recovery mode."""
    return _load(path) is not None


def completeness(path: Path) -> dict[str, int] | None:
    """What the DXF contains, for ranking converter attempts."""
    doc = _load(path)
    if doc is None:
        return None
    modelspace = list(doc.modelspace())
    return {
        "entities": len(modelspace),
        "texts": sum(1 for e in modelspace if e.dxftype() in ("TEXT", "MTEXT")),
        "blocks": sum(1 for b in doc.blocks if not b.name.startswith("*")),
        "layouts": len(list(doc.layouts)),
    }


def _rank(counts: dict[str, int]) -> tuple[int, int, int, int]:
    return counts["entities"], counts["texts"], counts["blocks"], counts["layouts"]


def choose_best(candidates: dict[str, dict[str, int]]) -> str | None:
    """Label of the most complete candidate (stable on ties: first declared)."""
    if not candidates:
        return None
    order = list(candidates)
    return max(order, key=lambda label: (_rank(candidates[label]), -order.index(label)))


def _describe(counts: dict[str, int]) -> str:
    return (
        f"{counts['entities']:,} entidades, {counts['texts']:,} textos, "
        f"{counts['blocks']:,} bloques, {counts['layouts']} presentaciones"
    )


def _run(
    executable: str, extra_args: list[str], source: Path, output: Path, timeout_seconds: int
) -> str | None:
    """Run one attempt; return a failure description or None on success."""
    output.unlink(missing_ok=True)
    try:
        completed = subprocess.run(
            [executable, *extra_args, "-y", "-o", str(output), str(source)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"tiempo agotado ({timeout_seconds}s)"
    except OSError as exc:
        return str(exc)
    if completed.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        stderr_tail = (completed.stderr or "").strip().splitlines()
        return f"código {completed.returncode}" + (
            f" — {stderr_tail[-1][:160]}" if stderr_tail else ""
        )
    return None


def convert_dwg_to_dxf(
    source: Path, output: Path | None = None, timeout_seconds: int = 180
) -> tuple[Path | None, str]:
    """Convert one DWG to DXF (sibling by default). Returns (dxf_path or None, message)."""
    if source.suffix.lower() != ".dwg":
        return source, "Archivo ya es DXF; no requiere conversión."
    executable = shutil.which("dwg2dxf")
    if executable is None:
        return None, "Convertidor dwg2dxf (LibreDWG) no encontrado en el servidor."

    output = output or source.with_suffix(".dxf")
    output.parent.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    produced: dict[str, Path] = {}
    counts: dict[str, dict[str, int]] = {}
    for index, (label, extra_args) in enumerate(_CANDIDATES):
        attempt_output = output.with_name(f"{output.stem}.intento{index}.dxf")
        failure = _run(executable, extra_args, source, attempt_output, timeout_seconds)
        if failure is not None:
            failures.append(f"{label}: {failure}")
            attempt_output.unlink(missing_ok=True)
            continue
        probe = completeness(attempt_output)
        if probe is None:
            failures.append(f"{label}: produjo un DXF ilegible")
            attempt_output.unlink(missing_ok=True)
            continue
        produced[label] = attempt_output
        counts[label] = probe

    version = dwg2dxf_version()
    tool = "LibreDWG" + (f", {version}" if version else "")
    best = choose_best(counts)
    if best is not None:
        output.unlink(missing_ok=True)
        produced[best].replace(output)
        for label, path in produced.items():
            if label != best:
                path.unlink(missing_ok=True)
        message = f"Conversión exitosa ({tool}, intento {best}; {_describe(counts[best])})."
        lesser = [
            f"{label} habría dado {_describe(c)}"
            for label, c in counts.items()
            if label != best and _rank(c) != _rank(counts[best])
        ]
        if lesser:
            message += " Se eligió la salida más completa: " + "; ".join(lesser) + "."
        if failures:
            message += " Intentos fallidos: " + "; ".join(failures) + "."
        log_stage(
            logger, "dwg2dxf_completed", input_path=source, output_path=output,
            attempt=best, previous_failures=len(failures), **counts[best],
        )
        return output, message

    label, extra_args = _LAST_RESORT
    failure = _run(executable, extra_args, source, output, timeout_seconds)
    probe = completeness(output) if failure is None else None
    if failure is None and probe is not None:
        message = (
            f"Conversión en {label} ({tool}; {_describe(probe)}). Este modo omite "
            "definiciones de bloque: revisa la lectura del plano. Intentos previos fallidos: "
            + "; ".join(failures) + "."
        )
        log_stage(
            logger, "dwg2dxf_completed", input_path=source, output_path=output,
            attempt=label, previous_failures=len(failures), **probe,
        )
        return output, message
    failures.append(f"{label}: {failure or 'produjo un DXF ilegible'}")
    output.unlink(missing_ok=True)
    return None, "La conversión DWG→DXF falló en todos los intentos: " + "; ".join(failures)
