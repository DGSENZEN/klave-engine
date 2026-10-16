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
    comillas,
    es_seccion,
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
    """El diámetro del rótulo en pulgadas, o None si no dice ninguno. Lee el texto con su marca de
    pulgadas normalizada (R187: «6´´», «6’’», «6''», «6”» son 6"), como todo lector."""
    texto = comillas(texto)
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
        # R170: de qué trazo es cada segmento (su índice en ``puntas``) y las dos puntas de cada
        # trazo, para saber qué trazos se conectan.
        self.de_trazo: list[int] = []
        self.puntas: list[tuple[tuple[float, float], tuple[float, float]]] = []
        # R170: los trazos que son un spline (un ducto flexible): de un solo diámetro.
        self.curvas: list[bool] = []
        # R180: el handle de cada trazo, para nombrar el ducto en un aviso.
        self.handles: list[str] = []

    def add(self, entity: NormalizedEntity, length: float) -> None:
        self.length_du += length
        self.segments += 1
        self.entities.append(entity.entity_id)
        self.source_file = self.source_file or entity.source_file
        points = entity.points or []
        # R170: un spline (un ducto flexible), entero: decenas de segmentos y su rótulo a la
        # mitad. Otro trazo, sus primeros 16 segmentos, como siempre (lo repartido se escala).
        indice = len(self.puntas)
        props = entity.properties or {}
        # Un spline del espacio modelo; las curvas de un símbolo (un bloque) no son un ducto.
        curva = props.get("derived_from") == "SPLINE" and not props.get("parent_insert")
        for i in range(len(points) - 1 if curva else min(len(points) - 1, 16)):
            (ax, ay), (bx, by) = points[i][:2], points[i + 1][:2]
            self.segments_xy.append((float(ax), float(ay), float(bx), float(by)))
            self.de_trazo.append(indice)
        self.curvas.append(curva)
        self.handles.append(entity.raw_handle or entity.entity_id)
        if points:
            primero, ultimo = points[0][:2], points[-1][:2]
            self.puntas.append(
                ((float(primero[0]), float(primero[1])), (float(ultimo[0]), float(ultimo[1])))
            )
        else:
            self.puntas.append(((math.inf, math.inf), (math.inf, math.inf)))
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
        tramos = _tramos_por_diametro(grupo, etiquetas, meters_factor, regla.familia, layer)
        if tramos:
            # La red cambia de diámetro a lo largo: cada tramo es un concepto
            # distinto, con sus propios metros — no una tubería entera con el
            # diámetro del rótulo más repetido.
            for spec_t, diametro_t, du_t, segs_t, motivo_t in tramos:
                metros_t = round(du_t * meters_factor, 2)
                if metros_t <= 0:
                    continue
                material_t = normaliza_material(spec_t) or normaliza_material(layer)
                if diametro_t is None:
                    # R170, R180: los metros sin rótulo que no se conectan con ningún tramo
                    # rotulado, con los dos diámetros mayores casi parejos; o los ductos cuyos
                    # rótulos propios no se leen o no coinciden.
                    output.detections.append(
                        make_detection(
                            detection_ids.next(),
                            DetectionType.pipe_run,
                            layer,
                            grupo.bbox,
                            0.6,
                            grupo.entities,
                            "layer_run",
                            [
                                f"{metros_t:,.2f} m de {que_es} en «{layer}»: diámetro por "
                                "confirmar",
                                f"{motivo_t[:1].upper()}{motivo_t[1:]}.",
                            ],
                            {
                                "run_family": familia,
                                "discipline": disciplina,
                                "layer": layer,
                                "estimated_length": round(du_t, 4),
                                "length_m": metros_t,
                                "segments": segs_t,
                                "spec": "",
                                "diametro_mm": None,
                                "diametro": "",
                                "diametro_por_confirmar": True,
                                "material": material_t[1] if material_t else "",
                                "material_clave": material_t[0] if material_t else "",
                            },
                            grupo.source_file,
                        )
                    )
                    continue
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
                            f"La capa trae {sum(1 for t in tramos if t[1] is not None)} "
                            "diámetros rotulados; cada segmento se adjudicó al rótulo legible "
                            "más cercano (un ducto flexible entero, al suyo), un ducto sin "
                            "rótulo al del ducto con el que se conecta y lo demás al tramo "
                            "mayor (R170).",
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
) -> list[tuple[tuple[float, float], str, str, str]]:
    """Los rótulos de diámetro y material de la hoja, con su posición, su handle y su capa.

    Los códigos de control de AutoCAD se traducen antes: %%C es Ø."""
    salida: list[tuple[tuple[float, float], str, str, str]] = []
    for entity in entities:
        if not entity.is_textual or not entity.text:
            continue
        texto = " ".join(
            entity.text.replace("%%C", "Ø").replace("%%c", "Ø").split()
        )
        if len(texto) > 60 or not _SPEC.search(texto):
            continue
        asa = entity.raw_handle or entity.entity_id
        salida.append((bbox_center(entity.bbox), texto, asa, entity.layer))
    return salida


def _spec_de(
    grupo: "_Acumulado",
    etiquetas: list[tuple[tuple[float, float], str, str, str]],
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
    for (tx, ty), texto, _asa, _capa in etiquetas:
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
    etiquetas: list[tuple[tuple[float, float], str, str, str]],
    meters_factor: float,
    familia: str,
    capa: str = "",
) -> list[tuple[str, tuple[int, str] | None, float, int, str]]:
    """Los tramos de una corrida, partidos por diámetro nominal (R170, R180).

    Cada segmento de un trazo recto se adjudica al rótulo legible más cercano dentro del alcance
    — con los mismos filtros de sistema y plausibilidad que ``_spec_de`` —. Un ducto flexible (un
    spline del espacio modelo, muestreado entero) es de un solo diámetro: el de su rótulo más
    cercano (R170). R180: si ése no se lee, o el rótulo de su recorrido — el de su capa que le
    queda más cerca a él que a cualquier otro ducto — dice otro diámetro que el de su collarín,
    queda «por confirmar»; nunca el diámetro de la red. Un ducto sin rótulo toma el del ducto
    rotulado con el que se conecta, punta con punta. Lo demás va al diámetro con más metros
    rotulados, salvo que los dos primeros estén a menos de 10 %: ahí queda «por confirmar». Con
    menos de dos diámetros legibles cerca de la red no hay nada que partir y se regresa vacío (el
    camino de siempre decide).

    Regresa ``[(spec, (mm, texto) o None, metros_du, segmentos, motivo)]``: el motivo dice por qué
    un tramo sin diámetro quedó por confirmar.
    """
    if not etiquetas or not grupo.segments_xy:
        return []
    alcance = _SPEC_REACH_M / meters_factor if meters_factor else _SPEC_REACH_M
    # Los rótulos de diámetro que valen para esta corrida, legibles o no (R180: un 14" que no se
    # leía se pagaba como 12"); la sección de un ducto rectangular no es un diámetro.
    rotulos: list[tuple[tuple[float, float], str, tuple[int, str] | None, str, str]] = []
    # R185: los rótulos de la capa de la corrida que traen una medida y no dan un diámetro que se
    # pueda tomar (una sección «2 x 12"», «12" x 3», uno de otro sistema o fuera de rango): el ducto
    # del que son el rótulo más cercano queda por confirmar, nunca con el diámetro de la red.
    rechazados: list[tuple[tuple[float, float], str, str]] = []
    for (tx, ty), texto, asa, capa_r in etiquetas:
        medida = _pulgadas(texto) is not None or es_seccion(texto)
        de_su_capa = bool(capa) and capa_r == capa and medida
        nombrados = _sistemas_nombrados(texto)
        if nombrados and familia not in nombrados:
            if de_su_capa:
                rechazados.append(((tx, ty), texto, asa))
            continue
        if not nombrados and not _diametro_plausible(texto, familia):
            if de_su_capa:
                rechazados.append(((tx, ty), texto, asa))
            continue
        pedazo = _pedazo_de(texto, familia)
        diametro = normaliza_diametro(pedazo)
        if diametro is None and (_pulgadas(pedazo) is None or es_seccion(pedazo)):
            if de_su_capa:
                rechazados.append(((tx, ty), texto, asa))
            continue  # no dice un diámetro: un material, una sección rectangular
        rotulos.append(((tx, ty), texto, diametro, asa, capa_r))
    legibles = [(pos, texto, d) for pos, texto, d, _asa, _c in rotulos if d is not None]

    largos = [math.dist((ax, ay), (bx, by)) for ax, ay, bx, by in grupo.segments_xy]
    segs_de: dict[int, list[int]] = {}
    for k, t in enumerate(grupo.de_trazo):
        segs_de.setdefault(t, []).append(k)
    curvas = [t for t in segs_de if grupo.curvas[t]]

    # R180: cada ducto flexible, su rótulo más cercano (legible o no) y el de su recorrido: el de su
    # capa que le queda más cerca a él que a cualquier otro ducto.
    def distancia(t: int, tx: float, ty: float) -> float:
        return min(_distancia_a_segmento(tx, ty, grupo.segments_xy[k]) for k in segs_de[t])

    cercanos: dict[int, tuple[float, tuple[int, str] | None, str, str]] = {}
    recorrido: dict[int, tuple[float, tuple[int, str] | None, str, str]] = {}
    for (tx, ty), texto, diametro, asa, capa_r in rotulos:
        dueno: tuple[float, int] | None = None
        for t in curvas:
            d = distancia(t, tx, ty)
            if d > alcance:
                continue
            if t not in cercanos or d < cercanos[t][0]:
                cercanos[t] = (d, diametro, texto, asa)
            if dueno is None or d < dueno[0]:
                dueno = (d, t)
        if dueno is not None and capa and capa_r == capa:
            d, t = dueno
            if t not in recorrido or d < recorrido[t][0]:
                recorrido[t] = (d, diametro, texto, asa)
    # R185: el rótulo rechazado de su capa más cercano a cada ducto.
    rechazo: dict[int, tuple[float, str, str]] = {}
    for (tx, ty), texto, asa in rechazados:
        for t in curvas:
            d = distancia(t, tx, ty)
            if d <= alcance and (t not in rechazo or d < rechazo[t][0]):
                rechazo[t] = (d, texto, asa)
    del_ducto: dict[int, tuple[tuple[int, str], str]] = {}
    en_duda: dict[int, str] = {}
    for t, (_d, texto, asa) in rechazo.items():
        if t not in cercanos or _d < cercanos[t][0]:
            en_duda[t] = (
                f"el rótulo del ducto {grupo.handles[t]}, «{texto.strip()}» ({asa}), no da un "
                "diámetro que se pueda tomar (una sección, una cantidad, otro sistema)"
            )
    for t, (_d, diametro, texto, asa) in cercanos.items():
        if t in en_duda:
            continue
        suyo = recorrido.get(t)
        if diametro is None:
            en_duda[t] = (
                f"el rótulo del ducto {grupo.handles[t]}, «{texto.strip()}» ({asa}), no se lee"
            )
        elif suyo is not None and (suyo[1] is None or suyo[1][0] != diametro[0]):
            en_duda[t] = (
                f"el ducto {grupo.handles[t]} dice «{texto.strip()}» ({asa}) en su collarín y "
                f"«{suyo[2].strip()}» ({suyo[3]}) en su recorrido"
            )
        else:
            del_ducto[t] = (diametro, texto)
    # Con menos de dos diámetros legibles no hay nada que partir (el camino de siempre decide) —
    # salvo que un ducto traiga un rótulo propio que no se lee o no coincide (R184): ése nunca va al
    # diámetro de la red.
    if len({d[0] for _p, _t, d in legibles}) < 2 and not en_duda:
        return []

    rotulo_de_seg: list[tuple[float, tuple[int, str], str] | None] = []
    for k, (ax, ay, bx, by) in enumerate(grupo.segments_xy):
        t = grupo.de_trazo[k]
        if grupo.curvas[t]:
            rotulo_de_seg.append((0.0, *del_ducto[t]) if t in del_ducto else None)
            continue
        mejor_s: tuple[float, tuple[int, str], str] | None = None
        for (tx, ty), texto, diametro in legibles:
            d = _distancia_a_segmento(tx, ty, (ax, ay, bx, by))
            if d <= alcance and (mejor_s is None or d < mejor_s[0]):
                mejor_s = (d, diametro, texto)
        rotulo_de_seg.append(mejor_s)
    rotulado_por_dia: dict[int, float] = {}
    por_trazo: dict[int, dict[int, float]] = {}
    dia_por_mm: dict[int, tuple[int, str]] = {}
    texto_por_dia: dict[int, Counter] = {}
    for k, rotulo in enumerate(rotulo_de_seg):
        if rotulo is None or largos[k] <= 0:
            continue
        mm = rotulo[1][0]
        rotulado_por_dia[mm] = rotulado_por_dia.get(mm, 0.0) + largos[k]
        dias_t = por_trazo.setdefault(grupo.de_trazo[k], {})
        dias_t[mm] = dias_t.get(mm, 0.0) + largos[k]
        dia_por_mm[mm] = rotulo[1]
        texto_por_dia.setdefault(mm, Counter())[_pedazo_de(rotulo[2], familia)] += 1
    if not rotulado_por_dia and not en_duda:
        return []
    # El diámetro de cada trazo rotulado, para el ducto sin rótulo que se conecta con él. Un
    # segmento sin rótulo de un trazo que no es spline sigue su camino de siempre (el diámetro con
    # más metros rotulados, o «por confirmar» si los dos primeros están parejos).
    del_trazo = {t: max(dias, key=lambda mm: (dias[mm], -mm)) for t, dias in por_trazo.items()}
    rotulados = set(del_trazo) | set(en_duda)
    # R181: sólo un ducto flexible sin rótulo toma el diámetro por conexión; sin ninguno en la red
    # (una red sanitaria de miles de trazos rectos) no hay nada que conectar. R184: nunca a través
    # de un ducto por confirmar; el que sólo se alcanza por uno, queda por confirmar.
    tras_duda: dict[int, int] = {}
    if any(curva and t not in rotulados for t, curva in enumerate(grupo.curvas)):
        tras_duda = _por_conexion(
            del_trazo,
            grupo.puntas,
            _UNE_TRAZOS / meters_factor if meters_factor else 0.0,
            set(en_duda),
        )
    orden = sorted(rotulado_por_dia, key=lambda mm: -rotulado_por_dia[mm])
    parejos = (
        len(orden) > 1
        and rotulado_por_dia[orden[1]] >= (1 - _DIAMETROS_PAREJOS) * rotulado_por_dia[orden[0]]
    )
    largo_por_dia: dict[int | None, float] = {}
    segs_por_dia: dict[int | None, int] = {}
    motivos: list[str] = []
    for k, largo in enumerate(largos):
        if largo <= 0:
            continue
        rotulo = rotulo_de_seg[k]
        t = grupo.de_trazo[k]
        dia: int | None
        if rotulo is not None:
            dia = rotulo[1][0]
        elif t in en_duda:
            dia = None  # R180: sus rótulos propios no se leen o no coinciden; nunca la red
            if en_duda[t] not in motivos:
                motivos.append(en_duda[t])
        elif grupo.curvas[t] and t not in rotulados and t in del_trazo:
            dia = del_trazo[t]  # un ducto sin rótulo, por el rotulado con el que se conecta
        elif grupo.curvas[t] and t in tras_duda:
            dia = None  # R184: sólo se conecta a través de un ducto por confirmar
            motivo = (
                f"el ducto {grupo.handles[t]}, sin rótulo, sólo se conecta a través del ducto "
                f"{grupo.handles[tras_duda[t]]}, que está por confirmar"
            )
            if motivo not in motivos:
                motivos.append(motivo)
        elif not orden:
            dia = None  # R184: ningún diámetro legible en la red
            if _SIN_ROTULO_LEGIBLE not in motivos:
                motivos.append(_SIN_ROTULO_LEGIBLE)
        else:
            dia = None if parejos else orden[0]
            if dia is None and _SIN_ROTULO_PAREJOS not in motivos:
                motivos.append(_SIN_ROTULO_PAREJOS)
        largo_por_dia[dia] = largo_por_dia.get(dia, 0.0) + largo
        segs_por_dia[dia] = segs_por_dia.get(dia, 0) + 1
    # Lo repartido se escala para que la suma dé los metros reales del grupo (el segmento que
    # cierra una polilínea cerrada no está en ``segments_xy``).
    cubierto = sum(largo_por_dia.values())
    escala = grupo.length_du / cubierto if cubierto else 1.0
    return sorted(
        (
            (
                texto_por_dia[d].most_common(1)[0][0] if d is not None else "",
                dia_por_mm[d] if d is not None else None,
                largo_por_dia[d] * escala,
                segs_por_dia[d],
                "; ".join(motivos) if d is None else "",
            )
            for d in largo_por_dia
        ),
        key=lambda tramo: -tramo[2],
    )


# R180: lo que no se adjudica porque los dos diámetros con más metros rotulados están parejos.
_SIN_ROTULO_PAREJOS = (
    "trazos sin rótulo cerca que no se conectan con un tramo rotulado, y los dos diámetros con "
    "más metros rotulados están a menos de 10 %: no se adjudican a ninguno"
)
# R184: lo que no se adjudica porque la red no trae ningún diámetro legible.
_SIN_ROTULO_LEGIBLE = "trazos sin rótulo y ningún diámetro legible en la red"


# R170: dos trazos se conectan cuando una punta de uno está a esto (en metros) de una del otro.
_UNE_TRAZOS = 0.05
# R170: los dos diámetros con más metros rotulados a menos de esta parte: no hay mayor.
_DIAMETROS_PAREJOS = 0.10


def _por_conexion(
    del_trazo: dict[int, int],
    puntas: list[tuple[tuple[float, float], tuple[float, float]]],
    tolerancia: float,
    en_duda: set[int] | None = None,
) -> dict[int, int]:
    """R170: un trazo sin rótulo toma el diámetro del trazo rotulado con el que se conecta,
    punta con punta, a través de otros sin rótulo (el más cercano en saltos); si dos diámetros
    llegan en el mismo número de saltos, ninguno. Modifica ``del_trazo``. R184: nunca a través de
    un trazo por confirmar (``en_duda``); regresa los trazos sin rótulo que no tomaron diámetro y
    a los que se llega desde uno por confirmar sin pasar por un rotulado, con ese trazo."""
    dudosos = en_duda or set()
    vecinos = _vecinos_por_puntas(puntas, tolerancia)
    rotulados = set(del_trazo)
    frontera = {t: {mm} for t, mm in del_trazo.items()}
    llegado: dict[int, set[int]] = dict(frontera)
    while frontera:
        siguiente: dict[int, set[int]] = {}
        for t, dias in frontera.items():
            for v in vecinos[t]:
                if v in llegado or v in dudosos:
                    continue
                siguiente.setdefault(v, set()).update(dias)
        for v, dias in siguiente.items():
            llegado[v] = dias
            if len(dias) == 1:
                del_trazo[v] = next(iter(dias))
        frontera = {v: d for v, d in siguiente.items() if len(d) == 1}
    # R184: desde cada trazo por confirmar, por trazos sin rótulo que no tomaron diámetro.
    tras_duda: dict[int, int] = {}
    pendientes = [(t, t) for t in sorted(dudosos)]
    while pendientes:
        t, origen = pendientes.pop(0)
        for v in vecinos[t]:
            if v in dudosos or v in rotulados or v in del_trazo or v in tras_duda:
                continue
            tras_duda[v] = origen
            pendientes.append((v, origen))
    return tras_duda


def _vecinos_por_puntas(
    puntas: list[tuple[tuple[float, float], tuple[float, float]]], tolerancia: float
) -> dict[int, list[int]]:
    """R181: los trazos cuyas puntas se tocan (a ``tolerancia`` o menos), por una rejilla de
    puntas de ese lado: cada punta sólo se compara con las de su celda y las ocho de alrededor —
    lineal, no cuadrático (los 7,291 trazos de «00_I PLUVIAL» eran 26 millones de pares)."""
    vecinos: dict[int, list[int]] = {i: [] for i in range(len(puntas))}
    lado = tolerancia if tolerancia > 0 else 1.0

    def celda(p: tuple[float, float]) -> tuple[int, int]:
        return (math.floor(p[0] / lado), math.floor(p[1] / lado))

    rejilla: dict[tuple[int, int], list[tuple[int, tuple[float, float]]]] = {}
    for i, extremos in enumerate(puntas):
        for p in extremos:
            rejilla.setdefault(celda(p), []).append((i, p))
    for i, extremos in enumerate(puntas):
        tocados: set[int] = set()
        for p in extremos:
            cx, cy = celda(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j, q in rejilla.get((cx + dx, cy + dy), ()):
                        if j > i and j not in tocados and math.dist(p, q) <= tolerancia:
                            tocados.add(j)
        for j in sorted(tocados):
            vecinos[i].append(j)
            vecinos[j].append(i)
    return vecinos


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
