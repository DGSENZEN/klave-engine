"""LibreDWG ``dwg2dxf`` adapter for server-side DWG→DXF conversion.

The ODA-shaped :class:`DwgToDxfConverter` converts whole directories; for the
web upload flow we convert a single file with GNU LibreDWG's ``dwg2dxf``.
Failures are returned, never raised.

Conversion is a retry ladder, because LibreDWG's default output fails on some
producer quirks while an explicit target version or minimal mode succeeds:

1. default invocation;
2. ``--as r2000`` (widely readable DXF target);
3. ``-m`` minimal DXF (geometry-first last resort).

Every produced file is probe-read with ezdxf before being accepted — a
converter that exits 0 but writes an unreadable DXF is treated as a failed
attempt, not a success the parser discovers later.
"""

import shutil
import subprocess
from pathlib import Path

import ezdxf
from ezdxf import recover as ezdxf_recover
from ezdxf.lldxf.const import DXFStructureError

from klave_engine.common.logging import get_logger, log_stage

logger = get_logger(__name__)

_ATTEMPTS: list[tuple[str, list[str]]] = [
    ("estándar", []),
    ("versión r2000", ["--as", "r2000"]),
    ("modo mínimo", ["-m"]),
]


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


def _output_is_readable(path: Path) -> bool:
    """Cheap probe: the DXF must load strictly or in recovery mode."""
    try:
        ezdxf.readfile(str(path))
        return True
    except (DXFStructureError, UnicodeDecodeError):
        try:
            ezdxf_recover.readfile(str(path))
            return True
        except Exception:
            return False
    except OSError:
        return False


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
    for label, extra_args in _ATTEMPTS:
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
            failures.append(f"{label}: tiempo agotado ({timeout_seconds}s)")
            continue
        except OSError as exc:
            failures.append(f"{label}: {exc}")
            continue
        if completed.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            stderr_tail = (completed.stderr or "").strip().splitlines()
            failures.append(
                f"{label}: código {completed.returncode}"
                + (f" — {stderr_tail[-1][:160]}" if stderr_tail else "")
            )
            continue
        if not _output_is_readable(output):
            failures.append(f"{label}: produjo un DXF ilegible")
            continue
        version = dwg2dxf_version()
        message = "Conversión exitosa (LibreDWG"
        if version:
            message += f", {version}"
        message += f", intento {label})."
        if failures:
            message += " Intentos previos fallidos: " + "; ".join(failures) + "."
        log_stage(
            logger,
            "dwg2dxf_completed",
            input_path=source,
            output_path=output,
            attempt=label,
            previous_failures=len(failures),
        )
        return output, message

    output.unlink(missing_ok=True)
    return None, "La conversión DWG→DXF falló en todos los intentos: " + "; ".join(failures)
