"""Muebles y salidas de instalaciones: cada símbolo insertado, un elemento.

Un W.C., un contacto, un difusor o una descarga sanitaria se dibujan como
bloques insertados sobre una capa de su disciplina. Hasta ahora el motor los
contaba en el levantamiento y ahí se quedaban: un número en una lista, sin
caja, sin confianza, sin vista, sin poder costear solo.

Aquí cada inserción se vuelve una detección como cualquier columna: se ve en
el visor, se le puede pedir evidencia, se asigna a su planta y alimenta un
concepto por regla de cantidad. Lo que la tabla de símbolos no reconoce no se
pierde — sigue contado en el levantamiento, para que alguien lo asigne.

Una sola cosa se cuida con celo: no contar dos veces. Un bloque que ya
detectaron los detectores estructurales (un castillo dibujado como bloque, un
pilote) no vuelve a entrar aquí, y las capas de anotación del plano —
cajetín, cotas, simbología — nunca cuentan como obra.
"""

import re

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.instalaciones_symbols import familia_de_bloque
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity

# El aparato de la hoja, no la obra: cajetines, nortes, niveles, ejes, y los
# bloques anónimos que deja AutoCAD.
_ANOTACION = re.compile(
    r"PIE DE PLANO|CAJET|TITLE|NORTE|^N$|^NPT$|^NIVEL|^EJE$|^EJES?\b|^A\$C|^\*|XREF|LOGO|"
    r"ESCALA|SIMBOLOG|LEYENDA|DETALLE|^DET\b",
    re.I,
)
_ANOTACION_CAPA = re.compile(
    r"COTA|DIM|PIE DE PLANO|CAJET|PAPEL|DEFPOINTS|UBICA|MARCO|FRAME|SIMBOLOG|LEYENDA|"
    r"^TEXTO|^TEXT\b",
    re.I,
)


class FixtureDetectorConfig(BaseModel):
    enabled: bool = True
    # Un símbolo de instalación mide decenas de centímetros. Más grande que
    # esto es un dibujo de detalle o un despiece, no una pieza en planta.
    max_size_m: float = 3.0
    min_size_m: float = 0.0
    # Disciplinas cuyos símbolos se detectan; el resto queda en levantamiento.
    disciplinas: list[str] = Field(
        default_factory=lambda: ["hidrosanitaria", "electrica", "aire", "gas"]
    )


def detect_fixtures(
    entities: list[NormalizedEntity],
    config: FixtureDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    meters_factor: float | None = None,
    claimed_entities: set[str] | None = None,
) -> DetectorOutput:
    """Cada bloque insertado que la tabla de símbolos reconoce, un elemento.

    ``claimed_entities`` son las entidades que ya se llevó otro detector: un
    mismo bloque no puede ser un castillo y un contacto."""
    config = config or FixtureDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="fixture_detector")
    if not config.enabled:
        return output
    claimed = claimed_entities or set()
    disciplinas = set(config.disciplinas)
    sin_reconocer: set[str] = set()

    for entity in entities:
        if entity.entity_type != EntityType.insert or entity.entity_id in claimed:
            continue
        nombre = (entity.block_name or "").strip()
        if not nombre or _ANOTACION.search(nombre) or _ANOTACION_CAPA.search(entity.layer):
            continue
        regla = familia_de_bloque(nombre, entity.layer)
        if regla is None:
            sin_reconocer.add(nombre)
            continue
        if regla.disciplina not in disciplinas:
            continue
        ancho = entity.bbox[2] - entity.bbox[0]
        alto = entity.bbox[3] - entity.bbox[1]
        if meters_factor is not None:
            lado = max(ancho, alto) * meters_factor
            if lado > config.max_size_m or lado < config.min_size_m:
                continue
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.fixture,
                nombre,
                entity.bbox,
                # El nombre del bloque lo escribió quien dibujó: es evidencia
                # fuerte de qué es, pero no dice cuántas salidas trae ni de
                # qué diámetro. Firme para contar, no para todo lo demás.
                0.82,
                [entity.entity_id],
                "block_symbol",
                [f"Bloque «{nombre}» en la capa «{entity.layer}»: {regla.que_es}"],
                {
                    "fixture_family": regla.familia,
                    "discipline": regla.disciplina,
                    "block_name": nombre,
                    "layer": entity.layer,
                },
                entity.source_file,
            )
        )

    if sin_reconocer:
        muestra = ", ".join(sorted(sin_reconocer)[:6])
        output.warnings.append(
            f"{len(sin_reconocer)} nombres de bloque no están en la tabla de símbolos "
            f"({muestra}{'…' if len(sin_reconocer) > 6 else ''}). Siguen contados en el "
            "levantamiento: asígnalos a un concepto desde Lectura del plano."
        )
    return output
