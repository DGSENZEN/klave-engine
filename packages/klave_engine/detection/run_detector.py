"""Corridas de instalación: los metros de tubería, ducto y canalización.

Una red de instalación no se dibuja como elemento: se dibuja como trazo sobre
una capa que dice de qué sistema es — ``P-04IH-CPIP`` es agua fría,
``00-SANITARIA`` es albañal, ``AireDucto`` es lámina. El levantamiento ya
sumaba esos metros; lo que faltaba era que fueran un elemento del proyecto,
con su caja, su vista y su regla de cantidad, en vez de un número suelto que
alguien tenía que asignar a mano.

Una corrida aquí es **un sistema en un marco de hoja**: todo el trazo de agua
fría de esa planta es una detección, con sus metros sumados y la caja que los
envuelve. Esa es la unidad en que se presupuesta y en la que un residente
piensa; una detección por segmento serían mil objetos que no dicen nada.

Lo que la tabla de capas no reconoce no entra, y no se pierde: sigue contado
en el levantamiento. Y el fondo arquitectónico sobre el que se dibuja la
instalación — muros, columnas, plafones — nunca cuenta como tubería, aunque
esté en la misma hoja.
"""

import math

from pydantic import BaseModel

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.instalaciones_symbols import CorridaRegla, familia_de_capa
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point

_TRAZO = (EntityType.line, EntityType.polyline, EntityType.arc)


class RunDetectorConfig(BaseModel):
    enabled: bool = True
    # Menos de esto en un sistema entero no es una red: son restos de dibujo,
    # una viñeta de simbología o un detalle suelto.
    min_length_m: float = 3.0


def _length(entity: NormalizedEntity) -> float:
    points = entity.points or []
    if len(points) < 2:
        return 0.0
    total = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
    if entity.entity_type == EntityType.polyline and entity.is_closed:
        total += math.dist(points[-1], points[0])
    return total


class _Acumulado:
    def __init__(self) -> None:
        self.length_du = 0.0
        self.segments = 0
        self.entities: list[str] = []
        self.bbox: BBox | None = None
        self.source_file = ""

    def add(self, entity: NormalizedEntity, length: float) -> None:
        self.length_du += length
        self.segments += 1
        self.entities.append(entity.entity_id)
        self.source_file = self.source_file or entity.source_file
        if self.bbox is None:
            self.bbox = entity.bbox
        else:
            a, b = self.bbox, entity.bbox
            self.bbox = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def detect_runs(
    entities: list[NormalizedEntity],
    config: RunDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    meters_factor: float | None = None,
    frame_boxes: list[BBox] | None = None,
) -> DetectorOutput:
    """Un sistema de instalación por marco de hoja, con sus metros sumados.

    Sin factor de unidades no se emite nada: unos metros que en realidad son
    milímetros costarían mil veces de más, y ese error no se nota."""
    config = config or RunDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="run_detector")
    if not config.enabled:
        return output
    if meters_factor is None:
        # El levantamiento sigue contando en unidades de dibujo; aquí no se
        # emite nada, porque una corrida sin metros no puede costear.
        return output

    marcos = frame_boxes or []
    grupos: dict[tuple[str, int], _Acumulado] = {}
    reglas: dict[str, CorridaRegla] = {}

    for entity in entities:
        if entity.entity_type not in _TRAZO:
            continue
        regla = familia_de_capa(entity.layer)
        if regla is None:
            continue
        length = _length(entity)
        if length <= 0:
            continue
        centro = bbox_center(entity.bbox)
        marco = next(
            (i for i, box in enumerate(marcos) if bbox_contains_point(box, centro)), -1
        )
        clave = (entity.layer, marco)
        grupo = grupos.get(clave)
        if grupo is None:
            grupo = grupos[clave] = _Acumulado()
            reglas[entity.layer] = regla
        grupo.add(entity, length)

    cortas = 0
    for (layer, _marco), grupo in grupos.items():
        regla = reglas[layer]
        metros = round(grupo.length_du * meters_factor, 2)
        if metros < config.min_length_m or grupo.bbox is None:
            cortas += 1
            continue
        familia, disciplina, que_es = regla.familia, regla.disciplina, regla.que_es
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.pipe_run,
                layer,
                grupo.bbox,
                # El nombre de la capa dice de qué sistema es y la geometría
                # dice cuánto mide: las dos cosas se leyeron del archivo. Lo
                # que no dice el trazo es el diámetro, y eso no se inventa.
                0.78,
                grupo.entities,
                "layer_run",
                [
                    f"{metros:,.2f} m de trazo en la capa «{layer}»: {que_es}",
                    f"{grupo.segments} segmentos sumados; el diámetro no se lee del "
                    "trazo, viene en las notas de la hoja.",
                ],
                {
                    "run_family": familia,
                    "discipline": disciplina,
                    "layer": layer,
                    # En unidades de dibujo, como el resto de los detectores:
                    # la regla de cantidad las convierte con el factor del
                    # proyecto, y así una sola conversión manda sobre todas.
                    "estimated_length": round(grupo.length_du, 4),
                    "length_m": metros,
                    "segments": grupo.segments,
                },
                grupo.source_file,
            )
        )

    if cortas:
        output.warnings.append(
            f"{cortas} capas de instalación quedaron por debajo de "
            f"{config.min_length_m:g} m y no se tomaron como red: normalmente son "
            "viñetas de simbología o restos de dibujo. Siguen en el levantamiento."
        )
    return output
