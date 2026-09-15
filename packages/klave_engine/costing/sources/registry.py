"""Known source documents and where they live locally.

Source files are downloaded into ``data/sources`` (never committed) and
listed in ``manifest.json`` with URL, size and hash. This registry maps a
stable source key to its parser and its provenance so an import is
reproducible and every adopted price can say exactly where it came from.
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from klave_engine.costing.sources.cdmx_tabulador import parse_cdmx_tabulador
from klave_engine.costing.sources.conagua import parse_conagua
from klave_engine.costing.sources.guanajuato import (
    parse_guanajuato_maquinaria,
    parse_guanajuato_materiales,
    parse_guanajuato_tabulador,
)
from klave_engine.costing.sources.inifech import parse_inifech
from klave_engine.costing.sources.sict_costo_directo import parse_sict_costo_directo
from klave_engine.costing.sources.sict_maquinaria import parse_sict_maquinaria

ReferenceRow = dict[str, object]


@dataclass(frozen=True)
class SourceSpec:
    key: str
    name: str
    publisher: str
    region: str
    vigencia: str  # YYYY-MM
    kind: str  # precios_unitarios | costo_horario | insumos | matrices
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
        SourceSpec(
            key="sict-costo-directo-2026",
            name="Tabulador a costo directo para infraestructura carretera SICT 2026",
            publisher="Dirección General de Servicios Técnicos, SICT",
            region="MX",
            vigencia="2026-02",
            kind="precios_unitarios",
            filename="sict_costo_directo_construccion_2026.pdf",
            parser=parse_sict_costo_directo,
            url="https://micrs.sct.gob.mx/infraestructura/direccion-general-de-servicios-tecnicos/tabulador/",
        ),
        SourceSpec(
            key="conagua-2026",
            name="Catálogo General de Precios Unitarios CONAGUA 2026 — agua y alcantarillado",
            publisher="Subdirección General de Agua Potable, Drenaje y Saneamiento, CONAGUA",
            region="MX",
            vigencia="2026-01",
            kind="precios_unitarios",
            filename="conagua_catalogo_precios_unitarios_2026.pdf",
            parser=parse_conagua,
            url="https://www.gob.mx/cms/uploads/attachment/file/1082456/Cat_logo_Gral._de_Agua_Potable_de_P.U._p_la_Const._de_Sist._de_Agua_Pot._y_Alcant._2026.pdf",
        ),
        SourceSpec(
            key="inifech-chiapas",
            name="Tabulador de Precios Unitarios INIFECH Chiapas — quince regiones",
            publisher="Instituto de la Infraestructura Física Educativa del Estado de Chiapas",
            region="MX-CHP",
            vigencia="2026-01",
            kind="precios_unitarios",
            filename="inifech_chiapas_tabulador.pdf",
            parser=parse_inifech,
            url="https://inifech.gob.mx/storage/Tabulador/TABULADOR.pdf",
        ),
        SourceSpec(
            key="guanajuato-uec-2026",
            name="Tabulador de Referencia 2026 UEC Guanajuato — seis regiones",
            publisher="Unidad Estatal de Costos, Secretaría de Obra Pública de Guanajuato",
            region="MX-GUA",
            vigencia="2026-02",
            kind="precios_unitarios",
            filename="guanajuato_uec_tabulador_2026_RI.xlsx",
            parser=parse_guanajuato_tabulador,
            url="https://obrapublica.guanajuato.gob.mx/unidad-estatal-de-costos/tabuladores-de-referencia/",
        ),
        SourceSpec(
            key="guanajuato-materiales-2026-09",
            name="Precios de mercado de materiales UEC Guanajuato — septiembre 2026",
            publisher="Unidad Estatal de Costos, Secretaría de Obra Pública de Guanajuato",
            region="MX-GUA",
            vigencia="2026-09",
            kind="insumos",
            filename="guanajuato_uec_materiales_2026_09.pdf",
            parser=parse_guanajuato_materiales,
            url="https://obrapublica.guanajuato.gob.mx/docs/8890/PUBLICACION_LISTADO_DE_REFERENCIA_MERCADEO_DE_MATERIA_-_SEPTIEMBRE_2026.pdf",
        ),
        SourceSpec(
            key="guanajuato-maquinaria-2026-09",
            name="Listado de costos horarios de maquinaria UEC Guanajuato — septiembre 2026",
            publisher="Unidad Estatal de Costos, Secretaría de Obra Pública de Guanajuato",
            region="MX-GUA",
            vigencia="2026-09",
            kind="costo_horario",
            filename="guanajuato_uec_maquinaria_2026_09.pdf",
            parser=parse_guanajuato_maquinaria,
            url="https://obrapublica.guanajuato.gob.mx/docs/8891/LISTADO_DE_MAQUINARIA_SEPTIEMBRE_2026.pdf",
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


def fetch_source(spec: SourceSpec, data_dir: Path, *, client: object | None = None) -> dict:
    """Descarga la publicación a `data/sources` y la asienta en el manifiesto
    (sha256, bytes, fecha). Escribe en `.part` y renombra al final: un corte
    a medias nunca deja un archivo que parezca completo. Sin URL, sin
    respuesta 2xx o con cuerpo vacío, dice por qué en vez de guardar nada."""
    import hashlib

    import httpx

    if not spec.url or not spec.url.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")):
        return {
            "ok": False, "filename": spec.filename,
            "problem": "La fuente no tiene un enlace directo al archivo; descárgalo a mano en "
                       f"data/sources/{spec.filename} desde {spec.url or 'la publicación'}.",
        }
    directory = sources_dir(data_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / spec.filename
    partial = directory / f"{spec.filename}.part"
    digest = hashlib.sha256()
    size = 0
    own_client = client is None
    http = client or httpx.Client(follow_redirects=True, timeout=120.0)
    try:
        with http.stream("GET", spec.url) as response:  # type: ignore[union-attr]
            if response.status_code >= 300:
                return {
                    "ok": False, "filename": spec.filename, "http": response.status_code,
                    "problem": f"La publicación respondió {response.status_code}.",
                }
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        return {"ok": False, "filename": spec.filename, "problem": f"No se pudo descargar: {exc}"}
    finally:
        if own_client:
            http.close()  # type: ignore[union-attr]
    if size == 0:
        partial.unlink(missing_ok=True)
        return {"ok": False, "filename": spec.filename, "problem": "La descarga vino vacía."}
    partial.replace(target)
    entry = {
        "url": spec.url, "http": "200", "bytes": size, "sha256": digest.hexdigest(), "ok": True,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    manifest = local_manifest(data_dir)
    manifest[spec.filename] = entry
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": True, "filename": spec.filename, **entry}


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
