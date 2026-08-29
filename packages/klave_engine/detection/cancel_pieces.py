"""La pieza de cancelería que sabe su clave.

Un plano de cancelería mexicano no dibuja cada ventana en planta: coloca el
globo de nomenclatura (un bloque tipo ``CANC_ALUM``) con su atributo — la
clave CA-01, PA-02 — donde va cada pieza, y dibuja el tipo una vez como
alzado acotado. La pieza colocada ES el insert con su clave: dos hechos
declarados por el plano (el bloque y su atributo), ninguno inventado.

La clave dice la familia por su prefijo: CA/CB es cancel, PA/PTA es puerta,
V/PV es ventana. Un prefijo desconocido cuenta como cancel con su nota —
la pieza existe, diga lo que diga la nomenclatura. Un globo sin clave no se
detecta (no declara qué es) pero tampoco se pierde: se avisa con
denominador, y sigue contado en el levantamiento.
"""

from __future__ import annotations

import re

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity

# Los bloques de nomenclatura de cancelería, como los nombran los planos.
_BLOQUE = re.compile(r"CANC|CANCEL|PTALOUVER|\bPTA\b|PTA-", re.I)
_CLAVE = re.compile(r"^[A-Z]{1,4}-?\d{1,3}[A-Z]?$")

_FAMILIA_POR_PREFIJO: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(PA|PTA|P)\d*-?", re.I), "puerta"),
    (re.compile(r"^(V|PV)\d*-?", re.I), "ventana"),
    (re.compile(r"^(CA|CB|C)\d*-?", re.I), "cancel"),
)


def _familia_de(clave: str) -> tuple[str, bool]:
    for patron, familia in _FAMILIA_POR_PREFIJO:
        if patron.match(clave):
            return familia, True
    return "cancel", False


def _clave_de(entity: NormalizedEntity) -> str | None:
    attributes = (entity.properties or {}).get("attributes") or {}
    for value in attributes.values():
        clave = str(value).strip().upper()
        if _CLAVE.match(clave):
            return clave
    return None


def detect_cancel_pieces(
    entities: list[NormalizedEntity], detection_ids: IdGenerator | None = None
) -> DetectorOutput:
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="cancel_pieces")
    sin_clave = 0
    for entity in entities:
        if entity.entity_type != EntityType.insert:
            continue
        if not _BLOQUE.search(entity.block_name or ""):
            continue
        clave = _clave_de(entity)
        if clave is None:
            sin_clave += 1
            continue
        familia, reconocido = _familia_de(clave)
        notes = [
            f"Globo de nomenclatura «{entity.block_name}» con clave {clave}: "
            f"una pieza de {familia} colocada.",
        ]
        if not reconocido:
            notes.append(
                f"El prefijo de {clave} no está en la tabla; se cuenta como cancel."
            )
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.opening,
                clave,
                entity.bbox,
                0.85,
                [entity.entity_id],
                "cancel_clave",
                notes,
                {"opening_family": familia, "clave": clave,
                 "block_name": entity.block_name},
                entity.source_file,
            )
        )
    if sin_clave:
        total = sin_clave + len(output.detections)
        output.warnings.append(
            f"{sin_clave} de {total} piezas de cancelería sin clave legible: "
            "el globo no declara qué pieza es. Siguen en el levantamiento."
        )
    return output
