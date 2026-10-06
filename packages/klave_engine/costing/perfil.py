"""El perfil del taller: las costumbres de una oficina, aprendidas de sus
propias revisiones (spec «el lector que aprende» §4, segundo nivel).

Cada oficina dibuja a su modo: un bloque «CAST15» para sus castillos, una capa
cuyos elementos siempre excluye. Las reglas del motor no lo saben; la oficina
lo enseña cada vez que revisa. Aquí cada decisión suma a favor o en contra de
«este bloque (o capa) es esta familia». Con tres a favor y ninguna en contra
la entrada es **firme**:

- a favor: un bloque sin reclamar dibujado así entra a la lectura como esa
  familia — sólo las que se cuentan por pieza (castillo, columna, pilote),
  porque un bloque aprendido no da una longitud ni un área —, dicho y
  excluible como cualquier lectura;
- en contra: nunca se quita nada; el elemento entra con una duda que dice por
  qué.

Nada de esto sale del taller.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path, PurePath

from klave_engine.costing.catalog_store import CatalogStore
from klave_engine.costing.etiquetas import append_labels
from klave_engine.costing.omitted import FAMILY_TYPES
from klave_engine.detection.candidates import CANDIDATES_FILENAME
from klave_engine.detection.results import Detection, make_detection

FIRME = 3
POR_PIEZA = {"castillo", "columna", "pilote"}


def _centro_dentro(bbox: list[float], caja: list[float]) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return caja[0] <= cx <= caja[2] and caja[1] <= cy <= caja[3]


def aprender(store: CatalogStore, records: Iterable[dict], candidates: list[dict]) -> int:
    """Suma cada etiqueta nueva al perfil; devuelve cuántas decisiones contó."""
    contadas = 0
    for rec in records:
        accion = rec.get("action") or rec.get("verdict")
        el = rec.get("element") or {}
        props = el.get("properties") or {}
        tipo = el.get("type") or ""
        bloque = str(props.get("block_name") or "")
        capa = str(props.get("layer") or "")
        if rec.get("kind") == "deteccion" and accion in ("confirmed", "excluded") and tipo:
            familia = el.get("family") or ""
            for kind, value in (("bloque", bloque), ("capa", capa)):
                if value:
                    store.perfil_registrar(
                        kind, value, tipo, familia,
                        a_favor=1 if accion == "confirmed" else 0,
                        en_contra=1 if accion == "excluded" else 0,
                    )
                    contadas += 1
        elif accion == "reassign" and bloque:
            nueva = str(rec.get("verdict") or "")
            if nueva in FAMILY_TYPES:
                store.perfil_registrar(
                    "bloque", bloque, FAMILY_TYPES[nueva].value, nueva, a_favor=1
                )
                if tipo:
                    store.perfil_registrar("bloque", bloque, tipo, el.get("family") or "",
                                           en_contra=1)
                contadas += 1
        elif accion == "add_missed" and rec.get("bbox"):
            familia = str(rec.get("verdict") or "")
            caja = rec["bbox"]
            hit = next(
                (c for c in candidates if c.get("bloque") and _centro_dentro(c["bbox"], caja)),
                None,
            )
            if hit is not None and familia in FAMILY_TYPES:
                store.perfil_registrar(
                    "bloque", hit["bloque"], FAMILY_TYPES[familia].value, familia, a_favor=1
                )
                contadas += 1
    return contadas


def firmes(perfil: list[dict]) -> tuple[list[dict], list[dict]]:
    """Las entradas que ya actúan: a favor (≥3, ninguna en contra) y en contra."""
    positivas = [
        p for p in perfil
        if p["a_favor"] >= FIRME and p["en_contra"] == 0 and p["kind"] == "bloque"
        and p["family"] in POR_PIEZA
    ]
    negativas = [p for p in perfil if p["en_contra"] >= FIRME and p["a_favor"] == 0]
    return positivas, negativas


def aplicar_perfil(
    detections: list[Detection], candidates: list[dict], perfil: list[dict],
) -> tuple[list[Detection], int, int]:
    """Las detecciones con el perfil aplicado: las agregadas por bloques que el
    taller confirmó y las dudas por lo que el taller excluye. Devuelve la lista,
    cuántas se agregaron y cuántas quedaron en duda."""
    positivas, negativas = firmes(perfil)
    agregadas: list[Detection] = []
    fuente = {_hoja(d): d.evidence.source for d in detections}
    por_bloque = {p["value"]: p for p in positivas}
    for cand in candidates:
        entrada = por_bloque.get(cand.get("bloque") or "")
        if entrada is None:
            continue
        fam = entrada["family"]
        det = make_detection(
            f"perfil_{cand['entity_id']}", FAMILY_TYPES[fam], "",
            tuple(cand["bbox"]), 0.8,
            [cand["entity_id"]], "perfil_del_taller", [],
            {"block_name": cand["bloque"], "layer": cand.get("capa", ""),
             "familia_perfil": fam,
             "perfil": f"tu taller confirmó {entrada['a_favor']} veces que el bloque "
                       f"«{cand['bloque']}» es {fam}"},
            fuente.get(cand["hoja"], cand["hoja"]),
        )
        agregadas.append(det)
    dudas = 0
    salida: list[Detection] = []
    for d in detections + agregadas:
        props = d.properties or {}
        for neg in negativas:
            if neg["detection_type"] != d.detection_type.value:
                continue
            valor = props.get("block_name") if neg["kind"] == "bloque" else props.get("layer")
            if valor and str(valor) == neg["value"]:
                d = d.model_copy(update={"properties": {
                    **props,
                    "perfil_duda": f"tu taller excluyó {neg['en_contra']} como éste "
                                   f"({'bloque' if neg['kind'] == 'bloque' else 'capa'} "
                                   f"«{neg['value']}»)",
                }})
                dudas += 1
                break
        salida.append(d)
    return salida, len(agregadas), dudas


def _hoja(d: Detection) -> str:
    return PurePath(d.evidence.source or "").name


def etiquetar_y_aprender(
    control_dir: Path, records: list[dict], store: CatalogStore | None
) -> int:
    """Escribe las etiquetas y las suma al perfil del taller. Aprender nunca
    detiene una revisión: si el catálogo no abre, la etiqueta queda igual."""
    escritas = append_labels(control_dir, records)
    if store is None:
        return escritas
    candidatos: list[dict] = []
    path = control_dir / CANDIDATES_FILENAME
    if any(r.get("action") == "add_missed" for r in records) and path.exists():
        candidatos = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    try:
        aprender(store, records, candidatos)
    except Exception:  # noqa: BLE001 — el perfil es un extra; la revisión ya quedó
        pass
    return escritas
