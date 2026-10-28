"""Bitácora local: lo que la aplicación gastó y lo que se le rompió.

Dos registros, un mismo mecanismo. Ambos son archivos JSONL por día bajo el
directorio de datos, y esa elección es deliberada:

* **Se queda en casa.** Un taller sube los planos de sus clientes, que son su
  activo más confidencial. Mandar trazas de error a un servicio de terceros
  significaría mandar nombres de obra, claves y rutas a alguien más; aquí no
  sale nada de la máquina del taller salvo que el operador configure un
  webhook a propósito.
* **Se puede leer con `cat`.** Cuando algo va mal a las once de la noche, un
  archivo de texto por día vence a cualquier panel.
* **No estorba.** Escribir una línea es barato y un fallo al escribirla nunca
  puede tumbar la petición que la originó: la bitácora observa, no participa.

Rotación por retención simple: los archivos más viejos que el plazo se borran
al escribir, así nadie tiene que acordarse de limpiar.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from klave_engine.common.diagnostics import sanitize_text

_LOCK = threading.Lock()

USO_DIRNAME = "bitacora/uso"
ERRORES_DIRNAME = "bitacora/errores"
RETENCION_DIAS = 90


def redactar(texto: str, limite: int = 600) -> str:
    """Redact token URLs, keys and email addresses before persistence."""
    return sanitize_text(texto, limite)


@dataclass
class UsoIA:
    """Una llamada al proveedor de IA, con lo que costó."""

    ts: str
    workspace: str
    project_id: str
    proveedor: str
    modelo: str
    tipo: str  # lectura_hoja | copiloto
    tokens_entrada: int
    tokens_salida: int
    # Estimación en USD con la tarifa declarada por el operador; nunca un
    # cargo real, y la interfaz lo dice así.
    costo_estimado_usd: float
    actor: str = ""


@dataclass
class ErrorRegistrado:
    """Algo que se rompió, con lo justo para encontrarlo otra vez."""

    ts: str
    request_id: str
    ruta: str
    metodo: str
    tipo: str  # la clase de la excepción
    mensaje: str
    traza: str = ""
    workspace: str = ""
    project_id: str = ""
    contexto: dict[str, Any] = field(default_factory=dict)
    user_id: str = ""
    job_id: str = ""
    run_id: str = ""
    operation: str = ""
    error_code: str = ""
    stage: str = ""


def _archivo(data_dir: Path, sub: str, dia: date | None = None) -> Path:
    dia = dia or datetime.now(UTC).date()
    carpeta = data_dir / sub
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta / f"{dia.isoformat()}.jsonl"


def _podar(carpeta: Path, dias: int = RETENCION_DIAS) -> None:
    """Los días más viejos que el plazo se van solos."""
    if not carpeta.is_dir():
        return
    corte = datetime.now(UTC).date() - timedelta(days=dias)
    for archivo in carpeta.glob("*.jsonl"):
        try:
            if date.fromisoformat(archivo.stem) < corte:
                archivo.unlink(missing_ok=True)
        except ValueError:
            continue


def _anotar(data_dir: Path, sub: str, registro: Any) -> None:
    """Una línea al archivo del día. Un fallo aquí no tumba a quien llama."""
    try:
        destino = _archivo(data_dir, sub)
        linea = json.dumps(asdict(registro), ensure_ascii=False)
        with _LOCK:
            with destino.open("a", encoding="utf-8") as fh:
                fh.write(linea + "\n")
            _podar(destino.parent)
    except Exception:  # noqa: BLE001 — observar nunca puede romper lo observado
        pass


def anotar_uso(data_dir: Path, uso: UsoIA) -> None:
    _anotar(data_dir, USO_DIRNAME, uso)


def anotar_error(data_dir: Path, error: ErrorRegistrado) -> None:
    # Do not persist arbitrary context or unsanitized details from any caller.
    from dataclasses import replace

    from klave_engine.common.diagnostics import sanitize_path

    _anotar(
        data_dir,
        ERRORES_DIRNAME,
        replace(
            error,
            ruta=sanitize_path(error.ruta),
            mensaje=redactar(error.mensaje),
            traza=redactar(error.traza, 2400),
            contexto={},
        ),
    )


def _leer(data_dir: Path, sub: str, desde: date, hasta: date) -> list[dict]:
    salida: list[dict] = []
    carpeta = data_dir / sub
    if not carpeta.is_dir():
        return salida
    dia = desde
    while dia <= hasta:
        archivo = carpeta / f"{dia.isoformat()}.jsonl"
        if archivo.exists():
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                try:
                    salida.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
        dia += timedelta(days=1)
    return salida


def uso_del_periodo(
    data_dir: Path, desde: date, hasta: date, workspace: str | None = None
) -> list[dict]:
    filas = _leer(data_dir, USO_DIRNAME, desde, hasta)
    if workspace:
        filas = [f for f in filas if f.get("workspace") == workspace]
    return filas


def errores_recientes(
    data_dir: Path, dias: int = 7, limite: int = 200, *, workspace: str | None = None
) -> list[dict]:
    hasta = datetime.now(UTC).date()
    filas = _leer(data_dir, ERRORES_DIRNAME, hasta - timedelta(days=dias), hasta)
    if workspace is not None:
        filas = [fila for fila in filas if fila.get("workspace") == workspace]
    filas.sort(key=lambda f: str(f.get("ts", "")), reverse=True)
    return filas[:limite]


def ruta_de_bitacora(data_dir: Path) -> dict[str, str]:
    """Dónde vive todo esto, para poder decírselo a quien administra."""
    return {
        "uso": str((data_dir / USO_DIRNAME).resolve()),
        "errores": str((data_dir / ERRORES_DIRNAME).resolve()),
        "retencion_dias": str(RETENCION_DIAS),
    }


def hostname() -> str:
    return os.uname().nodename if hasattr(os, "uname") else "—"
