"""Vanos: las puertas, ventanas y canceles dibujados sobre los muros.

Un vano vale dos veces en un presupuesto, y hasta ahora no valía ninguna.

Vale como **partida propia**: cada cancel y cada puerta son una pieza que
alguien suministra y coloca, y sin este detector no existían — la cancelería
y la carpintería salían del presupuesto en blanco.

Y vale como **hueco**: la superficie de un muro no incluye sus puertas. El
detector de muros ya descontaba los huecos que alcanzaba a puentear entre
tramos colineales, pero en un plano real casi nunca los alcanza: en Marina
encontró **un** vano en 85 muros, así que el aplanado y el muro se estaban
midiendo casi enteros. Aquí el vano se lee del símbolo que lo dibuja — que es
donde de verdad está — y su ancho se le devuelve al muro sobre el que se
para, para que el descuento salga de una medición y no de un porcentaje
supuesto.

Lo que no se lee del plano no se inventa: la **altura** del vano no está en
la planta, está en el cuadro de puertas y ventanas. Por eso el concepto se
cuantifica por pieza y no por metro cuadrado — con el ancho medido escrito en
la evidencia, para que quien tenga el cuadro pueda cerrar la cuenta.

Un límite que conviene decir en voz alta: el vano sólo se le puede devolver a
un muro **de su misma hoja**, porque cada archivo es su propio espacio de
coordenadas. Cuando la cancelería se dibuja en una hoja aparte de la
arquitectónica — que es lo común — los vanos cuentan como piezas pero no
descuentan superficie de muro, y el detector lo dice en una advertencia en vez
de aparentar que sí.
"""

import re

from pydantic import BaseModel, Field

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.results import (
    Detection,
    DetectionType,
    DetectorOutput,
    make_detection,
)
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import bbox_center

# Puerta, ventana y cancel, por nombre de bloque o de capa. Lo específico
# antes que lo general: un "cancel de puerta" es cancelería, no carpintería.
_CANCEL = re.compile(r"CANCEL|CANC[_ -]|CRISTAL|VIDRIO|DOMO", re.I)
_VENTANA = re.compile(r"VENTAN|^V-?\d{1,2}[A-Z]?$|VITRAL|CELOS", re.I)
_PUERTA = re.compile(r"PUERTA|^PTAS?\b|^P-?\d{1,2}[A-Z]?$|ACCESO|POSTIGO|ABATIBLE|CORREDIZA", re.I)
# El aparato de la hoja, nunca obra. NOMENCLATURA va aquí y merece su
# explicación: es la capa donde vive el nombre de las cosas, y un nombre no es
# una cosa. En Marina hay 35 bloques CANC_ALUM sobre esa capa, todos de 0.73 m
# al centímetro — son las etiquetas que marcan cada cancel, no los canceles.
# Los canceles de verdad están en «PTAS CANCEL», y sus anchos varían entre
# 0.90 y 1.97 m, que es como se ve una lista real de vanos.
_ANOTACION = re.compile(
    r"PIE DE PLANO|CAJET|SIMBOLOG|LEYEND|COTA|^DIM|DEFPOINTS|ESCALA|NORTE|DETALLE|"
    r"NOMENCLAT|^NOM\b|ETIQUET",
    re.I,
)

_FAMILIAS = (
    ("cancel", _CANCEL, "cancelería"),
    ("ventana", _VENTANA, "ventana"),
    ("puerta", _PUERTA, "puerta"),
)


class OpeningDetectorConfig(BaseModel):
    enabled: bool = True
    # Un vano de obra mide entre medio metro y cinco. Fuera de eso es un
    # despiece, una fachada completa o un símbolo de otra cosa.
    min_width_m: float = 0.5
    max_width_m: float = 5.0
    # Distancia a la que un vano se considera parado sobre un muro, como
    # múltiplo del espesor de ese muro.
    wall_reach_factor: float = 3.0
    layer_hints: list[str] = Field(
        default_factory=lambda: ["PUERTA", "PTAS", "VENTAN", "CANCEL", "VANO", "MARCO"]
    )


def _familia(nombre: str, capa: str) -> tuple[str, str] | None:
    for familia, patron, que_es in _FAMILIAS:
        if patron.search(nombre):
            return familia, que_es
    for familia, patron, que_es in _FAMILIAS:
        if patron.search(capa):
            return familia, que_es
    return None


def _ancho(entity: NormalizedEntity) -> float:
    """El lado largo en planta: un vano se dibuja como un rectángulo delgado
    o un arco de barrido, y su ancho es el mayor de los dos lados."""
    return max(entity.bbox[2] - entity.bbox[0], entity.bbox[3] - entity.bbox[1])


def detect_openings(
    entities: list[NormalizedEntity],
    walls: list[Detection] | None = None,
    config: OpeningDetectorConfig | None = None,
    detection_ids: IdGenerator | None = None,
    meters_factor: float | None = None,
) -> DetectorOutput:
    """Cada símbolo de puerta, ventana o cancel, un vano.

    Cuando se le pasan los muros, además les devuelve el ancho de los vanos
    que se paran sobre ellos: el descuento de vanos deja de ser un porcentaje
    supuesto y pasa a ser una medición."""
    config = config or OpeningDetectorConfig()
    detection_ids = detection_ids or IdGenerator("det")
    output = DetectorOutput(detector_name="opening_detector")
    if not config.enabled:
        return output
    factor = meters_factor or 1.0

    candidatos: list[tuple[NormalizedEntity, str, str, float]] = []
    for entity in entities:
        if _ANOTACION.search(entity.layer):
            continue
        nombre = (entity.block_name or "").strip()
        if entity.entity_type == EntityType.insert:
            if not nombre or _ANOTACION.search(nombre):
                continue
        elif entity.entity_type in (EntityType.polyline, EntityType.arc, EntityType.line):
            # El trazo que salió de reventar un bloque ya se contó como el
            # bloque mismo: contarlo otra vez haría dos vanos de uno.
            if (entity.properties or {}).get("parent_insert"):
                continue
            # Sin bloque, sólo cuenta si la capa dice que es un vano: un
            # rectángulo suelto en una capa cualquiera no es una ventana.
            if not any(h in entity.layer.upper() for h in config.layer_hints):
                continue
        else:
            continue
        clasificado = _familia(nombre, entity.layer)
        if clasificado is None:
            continue
        ancho = _ancho(entity) * factor
        if not (config.min_width_m <= ancho <= config.max_width_m):
            continue
        candidatos.append((entity, clasificado[0], clasificado[1], ancho))

    if not candidatos:
        return output

    marcas = _marcas_cercanas(entities, candidatos, factor)
    muros = walls or []
    pegados = 0

    for entity, familia, que_es, ancho in candidatos:
        marca = marcas.get(entity.entity_id, "")
        muro = _muro_bajo(entity, muros, config.wall_reach_factor, factor)
        notas = [
            f"{que_es.capitalize()} de {ancho:.2f} m de ancho en la capa «{entity.layer}»"
            + (f" (bloque «{entity.block_name}»)" if entity.block_name else ""),
            "La altura del vano no está en la planta: viene en el cuadro de puertas y "
            "ventanas, por eso se cuantifica por pieza.",
        ]
        if muro is not None:
            pegados += 1
            _sumar_al_muro(muro, ancho / factor)
            notas.append(f"Se para sobre el muro {muro.display_label or muro.label}.")
        output.detections.append(
            make_detection(
                detection_ids.next(),
                DetectionType.opening,
                marca or entity.block_name or entity.layer,
                entity.bbox,
                # El símbolo dice que hay un vano y cuánto mide de ancho; no
                # dice su altura ni su acabado. Firme para contarlo.
                0.80 if entity.block_name else 0.68,
                [entity.entity_id],
                "opening_symbol",
                notas,
                {
                    "opening_family": familia,
                    "width_m": round(ancho, 3),
                    "mark": marca,
                    "layer": entity.layer,
                    "on_wall": muro.detection_id if muro is not None else "",
                },
                entity.source_file,
            )
        )

    if muros and output.detections:
        sueltos = len(output.detections) - pegados
        if sueltos:
            output.warnings.append(
                f"{sueltos} de {len(output.detections)} vanos no cayeron sobre ningún muro "
                "detectado: cuentan como pieza, pero no descuentan superficie de muro."
            )
    return output


def _marcas_cercanas(
    entities: list[NormalizedEntity],
    candidatos: list[tuple[NormalizedEntity, str, str, float]],
    factor: float,
) -> dict[str, str]:
    """La etiqueta del cuadro de vanos (P-01, V-03) escrita junto al símbolo."""
    marca_re = re.compile(r"^[PVC]-?\d{1,2}[A-Z]?$", re.I)
    textos = [
        (bbox_center(e.bbox), e.text.strip().upper())
        for e in entities
        if e.is_textual and e.text and marca_re.match(e.text.strip())
    ]
    if not textos:
        return {}
    alcance = 1.5 / factor if factor else 1.5  # 1.5 m alrededor del símbolo
    salida: dict[str, str] = {}
    for entity, _f, _q, _a in candidatos:
        cx, cy = bbox_center(entity.bbox)
        mejor: tuple[float, str] | None = None
        for (tx, ty), texto in textos:
            distancia = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
            if distancia <= alcance and (mejor is None or distancia < mejor[0]):
                mejor = (distancia, texto)
        if mejor is not None:
            salida[entity.entity_id] = mejor[1]
    return salida


def _muro_bajo(
    entity: NormalizedEntity, walls: list[Detection], reach_factor: float, factor: float
) -> Detection | None:
    """El muro sobre el que se para el vano: el más cercano cuyo alcance lo
    cubre. Sin muros detectados no hay a quién descontarle nada."""
    if not walls:
        return None
    cx, cy = bbox_center(entity.bbox)
    mejor: tuple[float, Detection] | None = None
    for wall in walls:
        x1, y1, x2, y2 = wall.bbox
        espesor = float(wall.properties.get("estimated_thickness") or 0.0) / (factor or 1.0)
        alcance = max(espesor * reach_factor, (0.35 / factor) if factor else 0.35)
        dx = max(x1 - cx, 0.0, cx - x2)
        dy = max(y1 - cy, 0.0, cy - y2)
        distancia = (dx * dx + dy * dy) ** 0.5
        if distancia <= alcance and (mejor is None or distancia < mejor[0]):
            mejor = (distancia, wall)
    return mejor[1] if mejor is not None else None


def _sumar_al_muro(wall: Detection, ancho_du: float) -> None:
    """El ancho del vano se le devuelve al muro, en unidades de dibujo, para
    que el descuento de vanos lo lea de donde siempre lo ha leído."""
    huecos = list(wall.properties.get("openings") or [])
    huecos.append(round(ancho_du, 3))
    wall.properties["openings"] = huecos
    wall.properties["opening_length"] = round(sum(huecos), 3)
