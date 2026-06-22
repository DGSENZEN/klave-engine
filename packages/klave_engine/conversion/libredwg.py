"""LibreDWG ``dwg2dxf`` adapter for server-side DWG→DXF conversion.

The ODA-shaped :class:`DwgToDxfConverter` converts whole directories; for the
web upload flow we convert a single file with GNU LibreDWG's ``dwg2dxf``, which
is the converter available on this host. Failures are returned, never raised.
"""

import shutil
import subprocess
from pathlib import Path

from klave_engine.common.logging import get_logger, log_stage

logger = get_logger(__name__)


def dwg2dxf_available() -> bool:
    return shutil.which("dwg2dxf") is not None


def convert_dwg_to_dxf(source: Path, timeout_seconds: int = 180) -> tuple[Path | None, str]:
    """Convert one DWG to a sibling DXF. Returns (dxf_path or None, message)."""
    if source.suffix.lower() != ".dwg":
        return source, "Archivo ya es DXF; no requiere conversión."
    executable = shutil.which("dwg2dxf")
    if executable is None:
        return None, "Convertidor dwg2dxf (LibreDWG) no encontrado en el servidor."

    output = source.with_suffix(".dxf")
    try:
        completed = subprocess.run(
            [executable, "-o", str(output), str(source)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"Conversión falló: {exc}"

    if completed.returncode == 0 and output.exists():
        log_stage(logger, "dwg2dxf_completed", input_path=source, output_path=output)
        return output, "Conversión exitosa (LibreDWG)."
    return None, f"dwg2dxf salió con código {completed.returncode}: {completed.stderr[:200]}"
