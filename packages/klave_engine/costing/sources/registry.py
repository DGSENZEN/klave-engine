"""Known source documents and where they live locally.

Source files are downloaded into ``data/sources`` (never committed) and
listed in ``manifest.json`` with URL, size and hash. This registry maps a
stable source key to its parser and its provenance so an import is
reproducible and every adopted price can say exactly where it came from.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from klave_engine.costing.sources.cdmx_tabulador import parse_cdmx_tabulador
from klave_engine.costing.sources.sict_maquinaria import parse_sict_maquinaria

ReferenceRow = dict[str, object]


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    publisher: str
    region: str
    vigencia: str  # YYYY-MM
    kind: str  # precios_unitarios | costo_horario
    filename: str
    parser: Callable[[Path], Iterator[ReferenceRow]]
    url: str = ""


SOURCES: dict[str, SourceSpec] = {
    spec.key: spec
    for spec in [
        SourceSpec(
            key="cdmx-tabulador-2026-06",
            name="Tabulador General de Precios Unitarios CDMX — actualización junio 2026",
            publisher="Secretaría de Obras y Servicios, Gobierno de la Ciudad de México",
            region="MX-CMX",
            vigencia="2026-06",
            kind="precios_unitarios",
            filename="cdmx_tabulador_actualizacion_2026_junio.pdf",
            parser=parse_cdmx_tabulador,
            url="https://www.obras.cdmx.gob.mx/normas-tabulador/tabulador-general-de-precios-unitarios",
        ),
        SourceSpec(
            key="cdmx-tabulador-2026-03",
            name="Tabulador General de Precios Unitarios CDMX — edición 2026 (marzo)",
            publisher="Secretaría de Obras y Servicios, Gobierno de la Ciudad de México",
            region="MX-CMX",
            vigencia="2026-03",
            kind="precios_unitarios",
            filename="cdmx_tabulador_edicion_2026_marzo.pdf",
            parser=parse_cdmx_tabulador,
            url="https://www.obras.cdmx.gob.mx/normas-tabulador/tabulador-general-de-precios-unitarios",
        ),
        SourceSpec(
            key="sict-maquinaria-2026",
            name="Tabulador de costos horarios de maquinaria y equipo SICT 2026",
            publisher="Dirección General de Servicios Técnicos, SICT",
            region="MX",
            vigencia="2026-02",
            kind="costo_horario",
            filename="sict_tabulador_maquinaria_2026.pdf",
            parser=parse_sict_maquinaria,
            url="https://micrs.sct.gob.mx/images/DireccionesGrales/DGST/Tabulador/TCMaquinaria_2026.pdf",
        ),
    ]
}


def sources_dir(data_dir: Path) -> Path:
    return data_dir / "sources"


def local_manifest(data_dir: Path) -> dict:
    path = sources_dir(data_dir) / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def available_sources(data_dir: Path) -> list[dict]:
    """Every known source with whether its file is present locally."""
    manifest = local_manifest(data_dir)
    result = []
    for spec in SOURCES.values():
        path = sources_dir(data_dir) / spec.filename
        entry = manifest.get(spec.filename, {})
        result.append(
            {
                "key": spec.key,
                "name": spec.name,
                "publisher": spec.publisher,
                "region": spec.region,
                "vigencia": spec.vigencia,
                "kind": spec.kind,
                "filename": spec.filename,
                "url": spec.url,
                "available": path.exists(),
                "bytes": path.stat().st_size if path.exists() else None,
                "sha256": entry.get("sha256"),
                "fetched_at": entry.get("fetched_at"),
            }
        )
    return result
