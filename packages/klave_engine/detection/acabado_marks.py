"""La marca de acabado que sabe su clave.

Un plano de acabados mexicano no pinta regiones: paran una marca en cada
local — ``PI`` con la clave del piso, ``PL`` con la del plafón — y la
leyenda dice qué material es cada clave. La marca con su atributo son dos
hechos declarados por el plano; el área la pone el local donde está parada
(la suite de acabados la casa con los rooms). Una marca sin clave no
declara nada: se avisa con denominador y sigue en el levantamiento.
"""

from __future__ import annotations

import re

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity

_TIPO_POR_BLOQUE = {"PI": ("acabado_piso", "piso"), "PL": ("acabado_plafon", "plafon")}
_CLAVE = re.compile(r"^[A-Z0-9]{1,3}$")


def _clave_de(entity: NormalizedEntity) -> str | None:
    for value in ((entity.properties or {}).get("attributes") or {}).values():
        clave = str(value).strip().upper()
        if _CLAVE.match(clave):
            return clave
    return None


def detect_acabado_marks(
    entities: list[NormalizedEntity], detection_ids: IdGenerator | None = None
) -> DetectorOutput:
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="acabado_marks")
    sin_clave = 0
    for entity in entities:
        if entity.entity_type != EntityType.insert:
            continue
        tipo = _TIPO_POR_BLOQUE.get((entity.block_name or "").strip().upper())
        if tipo is None:
            continue
        familia, acabado_tipo = tipo
        clave = _clave_de(entity)
        if clave is None:
            sin_clave += 1
            continue
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.fixture,
                f"{entity.block_name}-{clave}",
                entity.bbox,
                0.85,
                [entity.entity_id],
                "acabado_clave",
                [
                    f"Marca «{entity.block_name}» con clave {clave}: el "
                    f"{acabado_tipo} que la leyenda del plano nombra."
                ],
                {"fixture_family": familia, "clave": clave, "acabado_tipo": acabado_tipo,
                 "block_name": entity.block_name},
                entity.source_file,
            )
        )
    if sin_clave:
        total = sin_clave + len(output.detections)
        output.warnings.append(
            f"{sin_clave} de {total} marcas de acabado sin clave legible: la marca "
            "no declara qué acabado lleva. Siguen en el levantamiento."
        )
    return output
