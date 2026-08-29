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
import re
from collections import Counter

from pydantic import BaseModel

from klave_engine.common.ids import IdGenerator
from klave_engine.detection.instalaciones_symbols import (
    CorridaRegla,
    familia_de_capa,
    normaliza_diametro,
    normaliza_material,
)
from klave_engine.detection.results import DetectionType, DetectorOutput, make_detection
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point

_TRAZO = (EntityType.line, EntityType.polyline, EntityType.arc)

# El diámetro y el material, como se escriben en un plano mexicano: 1/2"Ø,
# Ø 32, 19 MM, PEAD, CPVC, COBRE. Es lo que separa «tubería de agua fría» —
# que nadie puede cotizar — de un concepto que sí tiene precio publicado.
_SPEC = re.compile(
    r'(\d+\s*(?:1/\d\s*)?"|\d+\s*/\s*\d+\s*"|Ø\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*MM\b|'
    r'\bPEAD\b|\bCPVC\b|\bPVC\b|\bCOBRE\b|\bGALVANIZAD\w*|\bPPR\b|\bFO\.?GO\.?\b)',
    re.I,
)
# Un rótulo de especificación vive pegado a su trazo. Más lejos que esto es el
# rótulo de otra tubería, y adjudicárselo sería peor que no leer ninguno.
_SPEC_REACH_M = 2.0

# Agua fría, caliente y retorno corren paralelas dentro del mismo muro, así
# que un rótulo cae a un metro de las tres y la cercanía no las distingue. Lo
# que sí las distingue es lo que el rótulo dice: «AF-1/2"Ø» es agua fría,
# diga lo que diga la geometría. Un rótulo que nombra otro sistema no es de
# esta corrida; uno que no nombra ninguno (un diámetro pelón) sirve para
# cualquiera.
_PREFIJO_SISTEMA: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("agua_fria", re.compile(r"\bA\.?F\.?\b|AGUA\s*FR[ÍI]A", re.I)),
    ("agua_caliente", re.compile(r"\bA\.?C\.?\b|AGUA\s*CALIENTE", re.I)),
    ("retorno", re.compile(r"\bR\.?A\.?C\.?\b|RETORNO", re.I)),
    ("pluvial", re.compile(r"\bB\.?A\.?P\.?\b|PLUVIAL", re.I)),
    ("sanitaria", re.compile(r"\bB\.?A\.?N\.?\b|SANITARI|ALBA[ÑN]AL", re.I)),
    ("gas", re.compile(r"\bGAS\b|\bPEAD\b", re.I)),
)


def _sistemas_nombrados(texto: str) -> set[str]:
    """Qué sistemas nombra el rótulo. Vacío = no nombra ninguno."""
    return {familia for familia, patron in _PREFIJO_SISTEMA if patron.search(texto)}


# Un rótulo suele cubrir el paquete entero de tuberías que van juntas por el
# muro: «AF-1/2"Ø AC-1/2"Ø RAC-1/2"Ø» son tres, no una. Cada corrida se lleva
# su pedazo y no el renglón completo.
_CHUNK = re.compile(r'\b(RAC|AF|AC|BAP|BAN)\b[\s.-]*([0-9/"\sØ.]*)', re.I)
_CHUNK_FAMILIA = {
    "AF": "agua_fria", "AC": "agua_caliente", "RAC": "retorno",
    "BAP": "pluvial", "BAN": "sanitaria",
}


# Lo que cada sistema mide de verdad, en pulgadas. No es una preferencia: una
# línea de refrigerante de 12" no existe, y un rótulo de 12" que cae junto a
# ella es el del ducto que corre al lado. Es lo único que distingue un
# diámetro pelón cuando la cercanía ya no alcanza.
_DIAMETRO_PLAUSIBLE: dict[str, tuple[float, float]] = {
    "agua_fria": (0.375, 4.0),
    "agua_caliente": (0.375, 4.0),
    "retorno": (0.375, 3.0),
    "sanitaria": (1.5, 12.0),
    "pluvial": (1.5, 12.0),
    "gas": (0.25, 3.0),
    "refrigerante": (0.25, 2.0),
    "ducto": (4.0, 72.0),
    "ducto_flexible": (4.0, 24.0),
    "conduit": (0.5, 6.0),
}
_PULGADA = re.compile(r'(\d+)?\s*(?:(\d+)\s*/\s*(\d+))?\s*"')
_MILIMETRO = re.compile(r'(\d+(?:\.\d+)?)\s*MM\b', re.I)


def _pulgadas(texto: str) -> float | None:
    """El diámetro del rótulo en pulgadas, o None si no dice ninguno."""
    mm = _MILIMETRO.search(texto)
    if mm:
        return float(mm.group(1)) / 25.4
    inch = _PULGADA.search(texto)
    if not inch or not any(inch.groups()):
        return None
    entero = float(inch.group(1) or 0)
    if inch.group(2) and inch.group(3) and float(inch.group(3)):
        entero += float(inch.group(2)) / float(inch.group(3))
    return entero or None


def _diametro_plausible(texto: str, familia: str) -> bool:
    """Si el rótulo trae un diámetro, tiene que caber en lo que ese sistema
    mide. Sin diámetro legible se acepta: no dice nada, pero no miente."""
    rango = _DIAMETRO_PLAUSIBLE.get(familia)
    valor = _pulgadas(texto)
    if rango is None or valor is None:
        return True
    return rango[0] <= valor <= rango[1]


def _pedazo_de(texto: str, familia: str) -> str:
    """El trozo del rótulo que le toca a esta corrida, cuando el rótulo
    describe varias tuberías juntas."""
    pedazos = [
        (m.group(0).strip(), _CHUNK_FAMILIA.get(m.group(1).upper(), ""))
        for m in _CHUNK.finditer(texto)
    ]
    propios = [t for t, f in pedazos if f == familia]
    if propios and len(pedazos) > 1:
        return propios[0]
    return texto


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
        # Los segmentos del trazo mismo. La caja de una red cubre la planta
        # entera, así que «cerca de la caja» no quiere decir nada: el rótulo
        # de agua fría cae dentro de la caja del agua caliente y de la del
        # retorno. Se guardan segmentos y no vértices porque un tramo recto de
        # doce metros sólo tiene dos vértices, y su rótulo va a la mitad: a
        # seis metros de los dos.
        self.segments_xy: list[tuple[float, float, float, float]] = []

    def add(self, entity: NormalizedEntity, length: float) -> None:
        self.length_du += length
        self.segments += 1
        self.entities.append(entity.entity_id)
        self.source_file = self.source_file or entity.source_file
        points = entity.points or []
        for i in range(min(len(points) - 1, 16)):
            (ax, ay), (bx, by) = points[i][:2], points[i + 1][:2]
            self.segments_xy.append((float(ax), float(ay), float(bx), float(by)))
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

    etiquetas = _etiquetas_de_especificacion(entities)
    cortas = 0
    for (layer, _marco), grupo in grupos.items():
        regla = reglas[layer]
        metros = round(grupo.length_du * meters_factor, 2)
        if metros < config.min_length_m or grupo.bbox is None:
            cortas += 1
            continue
        familia, disciplina, que_es = regla.familia, regla.disciplina, regla.que_es
        tramos = _tramos_por_diametro(grupo, etiquetas, meters_factor, regla.familia)
        if len(tramos) >= 2:
            # La red cambia de diámetro a lo largo: cada tramo es un concepto
            # distinto, con sus propios metros — no una tubería entera con el
            # diámetro del rótulo más repetido.
            for spec_t, diametro_t, du_t, segs_t in tramos:
                metros_t = round(du_t * meters_factor, 2)
                if metros_t <= 0:
                    continue
                material_t = normaliza_material(spec_t) or normaliza_material(layer)
                output.detections.append(
                    make_detection(
                        detection_ids.next(),
                        DetectionType.pipe_run,
                        layer,
                        grupo.bbox,
                        0.78,
                        grupo.entities,
                        "layer_run",
                        [
                            f"{metros_t:,.2f} m de {que_es} en «{layer}», tramo de "
                            f"{diametro_t[1]}",
                            f"La capa trae {len(tramos)} diámetros rotulados; cada "
                            "segmento se adjudicó al rótulo legible más cercano y los "
                            "sin rótulo se sumaron al tramo mayor.",
                        ],
                        {
                            "run_family": familia,
                            "discipline": disciplina,
                            "layer": layer,
                            "estimated_length": round(du_t, 4),
                            "length_m": metros_t,
                            "segments": segs_t,
                            "spec": spec_t,
                            "diametro_mm": diametro_t[0],
                            "diametro": diametro_t[1],
                            "material": material_t[1] if material_t else "",
                            "material_clave": material_t[0] if material_t else "",
                        },
                        grupo.source_file,
                    )
                )
            continue
        spec = _spec_de(grupo, etiquetas, meters_factor, regla.familia)
        diametro = normaliza_diametro(spec)
        # El material sale del rótulo si lo dice, y si no, del nombre de la
        # capa: «AireTuboCu» declara cobre aunque ningún texto lo repita.
        material = normaliza_material(spec) or normaliza_material(layer)
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
                    f"{metros:,.2f} m de trazo en la capa «{layer}»: {que_es}"
                    + (f", {spec}" if spec else ""),
                    f"{grupo.segments} segmentos sumados"
                    + (
                        f"; «{spec}» leído del rótulo más cercano al trazo"
                        + (f", que es {diametro[1]}" if diametro else "")
                        + (f", de {material[1]}" if material else "")
                        + "."
                        if spec
                        else "; sin rótulo de diámetro cerca del trazo, así que el "
                        "diámetro queda sin leer y el precio no se puede fijar solo."
                    ),
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
                    # Diámetro y material leídos del plano. Vacío cuando el
                    # plano no los dice cerca del trazo: sin esto, «tubería de
                    # agua fría» no se puede cotizar contra ninguna
                    # publicación, porque nadie publica precio de una tubería
                    # sin diámetro.
                    "spec": spec,
                    # El diámetro nominal, escrito como lo escriben las
                    # publicaciones: «13 mm (1/2")». Sin esta forma, un precio
                    # publicado no se deja encontrar — nadie cotiza "tubería
                    # de agua fría" a secas.
                    "diametro_mm": diametro[0] if diametro else None,
                    "diametro": diametro[1] if diametro else "",
                    # La otra mitad del precio: el metro de cobre cuesta el
                    # doble que el de PP-R al mismo diámetro. Vacío cuando ni
                    # el rótulo ni la capa lo dicen — no declarar es lo normal
                    # y no se castiga, pero tampoco se inventa.
                    "material": material[1] if material else "",
                    "material_clave": material[0] if material else "",
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


def _etiquetas_de_especificacion(
    entities: list[NormalizedEntity],
) -> list[tuple[tuple[float, float], str]]:
    """Los rótulos de diámetro y material de la hoja, con su posición.

    Los códigos de control de AutoCAD se traducen antes: %%C es Ø."""
    salida: list[tuple[tuple[float, float], str]] = []
    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        texto = " ".join(
            entity.text.replace("%%C", "Ø").replace("%%c", "Ø").split()
        )
        if len(texto) > 60 or not _SPEC.search(texto):
            continue
        salida.append((bbox_center(entity.bbox), texto))
    return salida


def _spec_de(
    grupo: "_Acumulado",
    etiquetas: list[tuple[tuple[float, float], str]],
    meters_factor: float,
    familia: str,
) -> str:
    """El rótulo que describe esta corrida: el más repetido entre los que caen
    cerca de su trazo.

    Se mide contra el trazo y no contra la caja: la caja de una red cubre la
    planta entera, así que el rótulo de agua fría cae dentro de la caja del
    agua caliente y del retorno, y las tres acabarían con el mismo diámetro.

    Entre los que sí están sobre el trazo gana el más repetido, no el más
    cercano: una red larga lleva su diámetro escrito varias veces a lo largo,
    y el que aparece una sola vez suele ser el de un ramal.
    """
    if not etiquetas or not grupo.segments_xy:
        return ""
    alcance = _SPEC_REACH_M / meters_factor if meters_factor else _SPEC_REACH_M
    cerca: Counter[str] = Counter()
    for (tx, ty), texto in etiquetas:
        nombrados = _sistemas_nombrados(texto)
        if nombrados and familia not in nombrados:
            continue  # el rótulo es de otra tubería, aunque pase al lado
        if not nombrados and not _diametro_plausible(texto, familia):
            continue  # un 12" pelón junto a una línea de refrigerante es del ducto
        for segmento in grupo.segments_xy:
            if _distancia_a_segmento(tx, ty, segmento) <= alcance:
                cerca[texto] += 1
                break
    if not cerca:
        return ""
    return _pedazo_de(cerca.most_common(1)[0][0], familia)


def _tramos_por_diametro(
    grupo: "_Acumulado",
    etiquetas: list[tuple[tuple[float, float], str]],
    meters_factor: float,
    familia: str,
) -> list[tuple[str, tuple[int, str], float, int]]:
    """Los tramos de una corrida, partidos por diámetro nominal.

    Cada segmento del trazo se adjudica al rótulo legible más cercano dentro
    del alcance — con los mismos filtros de sistema y plausibilidad que
    ``_spec_de`` — y los metros se suman por diámetro. Los segmentos sin
    rótulo cerca se van al tramo con más metros: partirlos sería inventar
    dónde cambia el diámetro. Con menos de dos diámetros rotulados no hay
    nada que partir y se regresa vacío (el camino de siempre decide).

    Regresa ``[(spec, (mm, texto), metros_du, segmentos)]``.
    """
    if not etiquetas or not grupo.segments_xy:
        return []
    alcance = _SPEC_REACH_M / meters_factor if meters_factor else _SPEC_REACH_M
    legibles: list[tuple[tuple[float, float], str, tuple[int, str]]] = []
    for (tx, ty), texto in etiquetas:
        nombrados = _sistemas_nombrados(texto)
        if nombrados and familia not in nombrados:
            continue
        if not nombrados and not _diametro_plausible(texto, familia):
            continue
        diametro = normaliza_diametro(_pedazo_de(texto, familia))
        if diametro is None:
            continue
        legibles.append(((tx, ty), texto, diametro))
    if len({d[0] for _p, _t, d in legibles}) < 2:
        return []

    largo_por_dia: dict[int, float] = {}
    segs_por_dia: dict[int, int] = {}
    texto_por_dia: dict[int, Counter] = {}
    dia_por_mm: dict[int, tuple[int, str]] = {}
    sin_rotulo = 0.0
    sin_rotulo_segs = 0
    for ax, ay, bx, by in grupo.segments_xy:
        largo = math.dist((ax, ay), (bx, by))
        if largo <= 0:
            continue
        mejor: tuple[float, tuple[int, str], str] | None = None
        for (tx, ty), texto, diametro in legibles:
            d = _distancia_a_segmento(tx, ty, (ax, ay, bx, by))
            if d <= alcance and (mejor is None or d < mejor[0]):
                mejor = (d, diametro, texto)
        if mejor is None:
            sin_rotulo += largo
            sin_rotulo_segs += 1
            continue
        mm = mejor[1][0]
        largo_por_dia[mm] = largo_por_dia.get(mm, 0.0) + largo
        segs_por_dia[mm] = segs_por_dia.get(mm, 0) + 1
        texto_por_dia.setdefault(mm, Counter())[_pedazo_de(mejor[2], familia)] += 1
        dia_por_mm[mm] = mejor[1]
    if len(largo_por_dia) < 2:
        return []
    mayor = max(largo_por_dia, key=lambda mm: largo_por_dia[mm])
    largo_por_dia[mayor] += sin_rotulo
    segs_por_dia[mayor] += sin_rotulo_segs
    # segments_xy guarda a lo más 16 tramos por entidad: lo repartido se
    # escala para que la suma dé los metros reales del grupo.
    cubierto = sum(largo_por_dia.values())
    escala = grupo.length_du / cubierto if cubierto else 1.0
    return sorted(
        (
            (texto_por_dia[mm].most_common(1)[0][0], dia_por_mm[mm],
             largo_por_dia[mm] * escala, segs_por_dia[mm])
            for mm in largo_por_dia
        ),
        key=lambda tramo: -tramo[2],
    )


def _distancia_a_segmento(
    px: float, py: float, segmento: tuple[float, float, float, float]
) -> float:
    """Distancia de un punto al segmento, no a sus extremos."""
    ax, ay, bx, by = segmento
    dx, dy = bx - ax, by - ay
    largo = dx * dx + dy * dy
    if largo == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / largo))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
