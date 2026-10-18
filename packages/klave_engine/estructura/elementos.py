"""Elementos: cada colocación de una planta estructural con la definición de su marca y las
reglas de su hoja.

Una colocación es una detección de una familia estructural (``FAMILIAS_ESTRUCTURALES``) asignada
a una planta estructural (``SheetSegmentation.structural_plan_views``): nunca una marca de cuadro
(``role == "cuadro"``, una definición) ni lo que cae en un detalle, un corte o fuera de los
marcos. Lo que no llega a elemento no se tira: ``excluidas`` dice cuál y por qué (R71). Una
colocación sin marca también es un elemento (R70): ``marca=""``, con la definición de su familia
si la hay, y el aviso «sin marca».

La marca se junta con su definición por ``normalizar_marca``, la misma llave de las
definiciones, sin prefijos (K-15A no es K-15A.1). Sin definición de la marca, la de su familia (la
nota «DALA 15X25 …»), y el elemento lo dice: su marca sigue sin definir. Cada campo de la
definición se resuelve para la hoja del elemento (``para_hoja``: lo que dice su hoja manda, lo de
las demás queda como alternativa) y las reglas también (``Reglas.para``, una vez por hoja), R72.
La hoja es el código del marco, como en las reglas y las definiciones.

Cada valor lleva su fuente honesta. La sección propia que el plano dibuja y nadie leyó (ilegible)
nunca se cambia callada por otra: se toma la de la nota de la familia, si no la medida en planta,
si no la supuesta de la familia, siempre como ``supuesto``, con el aviso que dice por qué y una
duda, y la ilegible queda como alternativa (R113, R134). La altura de un castillo o una columna
sale de los niveles declarados (``nota``) y la de la planta más alta, que repite la de abajo, es
``supuesto`` (R73). El claro de una viga es el medido en planta (``medido``); sin él, ``None`` con
su aviso, nunca 0. El recubrimiento es el de las reglas de la hoja para la familia.

``resolver`` vuelve a juntar un elemento con las definiciones (después de una decisión): lo que
dice la colocación misma (``Colocacion``: lo medido en planta, la altura de su planta, sus avisos)
no cambia."""

import unicodedata
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.costing.referencias import element_id
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection, layer_matches
from klave_engine.detection.schedules import FAMILIAS_QUE_SE_ORDENAN
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.views import AlturaDeEntrepiso, SheetSegmentation, ViewKind
from klave_engine.estructura.armado import FAMILIAS_CON_PARRILLA
from klave_engine.estructura.dato import Dato, elegir, hojas_de, miembros, para_hoja
from klave_engine.estructura.definiciones import Definicion, normalizar_marca
from klave_engine.estructura.reglas import RECUBRIMIENTO_SUPUESTO, Reglas
from klave_engine.geometry.bbox import bbox_center

FAMILIAS_ESTRUCTURALES = (
    "castillo",
    "columna",
    "trabe",
    "contratrabe",
    "zapata",
    "pilote",
    "muro_concreto",
    "dala",
    "cerramiento",
)
# Las que se levantan por planta: su altura es la de su entrepiso.
_CON_ALTURA = frozenset({"castillo", "columna"})
# Las vigas: su longitud es el claro medido en planta.
_VIGAS = frozenset({"trabe", "contratrabe", "dala", "cerramiento"})
# Las que extienden en vertical lo que su definición llama «longitud» (la extensión del §3.2: el
# peralte de un dado, la altura de un muro): su altura.
_EXTENSION_ES_ALTURA = frozenset({"zapata", "muro_concreto"})

# La sección (b×h, cm) que Klave supone cuando nada la da: la misma de ``CostingAssumptions`` (sus
# áreas en m², escritas aquí como sus lados). Las demás familias no tienen sección supuesta: sin
# sección del plano ni medida, el elemento se queda sin ella y lo dice.
SECCION_SUPUESTA_CM: dict[str, tuple[int, int]] = {
    "castillo": (15, 20),
    "columna": (30, 30),
    "trabe": (25, 45),
    "contratrabe": (25, 50),
    "dala": (15, 25),
    "cerramiento": (15, 25),
}
# Un contorno de zapata con esta rectangularidad (área / área de su caja) es un rectángulo a ejes:
# los lados de su caja son sus dimensiones en planta.
_RECTANGULO = 0.98
_CAMPOS_DE_ARMADO = ("longitudinales", "estribos", "parrillas")
_CAMPO = {
    "seccion_cm": "sección",
    "longitud_m": "longitud",
    "longitudinales": "longitudinales",
    "estribos": "estribos",
    "parrillas": "parrillas",
}

Motivo = Literal[
    "cuadro", "titulo_de_detalle", "vista_excluida", "planta_no_estructural", "sin_vista"
]
# R142: las capas de un castillo o una columna en planta (nunca la de un dado).
_CAPAS_DE_CASTILLO = ["CASTILLO", "COLUMNA", "COLUMN", "COL", "COLS"]
# R144: las familias de las que es la cláusula de recubrimiento de la cimentación.
_DE_CIMENTACION = ("zapata", "dado", "pilote", "contratrabe", "losa_cimentacion")


class Colocacion(BaseModel):
    """Lo que dice la colocación misma, sin la definición: la sección medida en planta (las cotas
    junto a un castillo, el contorno de una zapata), el claro medido de una viga, la altura de su
    planta y los avisos de la detección (sin marca, claro dudoso, sin unidades)."""

    seccion_cm: Dato | None = None
    # R142: el área del contorno en planta de un castillo o una columna que no es un rectángulo,
    # en una capa de castillos o columnas (``{"area_cm2": …}``).
    seccion_no_rectangular: Dato | None = None
    longitud_m: Dato | None = None
    altura_m: Dato | None = None
    avisos: list[str] = Field(default_factory=list)
    # R168: el espesor del muro que corona una dala (cm), medido entre sus dos caras junto a la
    # etiqueta; o por qué no se midió.
    muro_cm: Dato | None = None
    muro_sin_medir: str | None = None
    # R193: el muro perpendicular más cercano a la etiqueta (cm, con sus caras), si lo hay.
    muro_perpendicular_cm: Dato | None = None


class Elemento(BaseModel):
    """Una colocación con su definición y sus reglas, campo por campo, cada uno un ``Dato`` con su
    fuente. ``marca`` es la normalizada («» sin marca); ``definicion`` dice de dónde salió lo que
    se usa: de la marca, de la familia (la marca no está definida) o de ninguna. ``avisos`` son lo
    que el elemento tiene que decir; ``dudas``, lo que alguien tiene que confirmar (un valor
    supuesto en lugar de uno que el plano dibuja)."""

    element_id: str
    detection_id: str
    marca: str
    familia: str
    vista: str | None = None
    hoja: str
    definicion: Literal["marca", "familia", "ninguna"]
    seccion_cm: Dato | None = None
    altura_m: Dato | None = None
    longitud_m: Dato | None = None
    longitudinales: Dato | None = None
    estribos: Dato | None = None
    parrillas: Dato | None = None
    recubrimiento_m: Dato | None = None
    avisos: list[str] = Field(default_factory=list)
    dudas: list[str] = Field(default_factory=list)
    colocacion: Colocacion = Field(default_factory=Colocacion)


class Excluida(BaseModel):
    """Una detección de una familia estructural que no es un elemento, y por qué (R71)."""

    detection_id: str
    marca: str
    familia: str
    vista: str | None = None
    motivo: Motivo
    texto: str


def excluidas(
    detections: list[Detection], segmentation: SheetSegmentation | None
) -> list[Excluida]:
    """Las detecciones de familias estructurales que no son colocaciones, cada una con su motivo:
    una marca de cuadro (define, no coloca), una en un detalle, un corte o fuera de los marcos, una
    en la planta de una hoja que no es de estructura, una que la segmentación no asignó."""
    return _separar(detections, segmentation)[1]


def construir_elementos(
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    por_marca: dict[str, Definicion],
    por_familia: dict[str, Definicion],
    reglas: Reglas,
    meters_factor: float | None,
    altura_supuesta_m: float,
    *,
    frames: list[SheetFrame] | None = None,
    config: TextPatternConfig | None = None,
) -> list[Elemento]:
    """Un elemento por colocación en una planta estructural (``excluidas`` da las demás). Sin
    segmentación, o con una sola planta, todo el plano es una planta (``vista=None``). La hoja de
    cada elemento es el código del marco de su vista (``frames``), o del marco que lo contiene; sin
    marcos, su archivo. ``config`` son las etiquetas del proyecto con que se normalizaron las marcas
    de las definiciones."""
    if frames is None and segmentation is not None and len(segmentation.views) > 1:
        # M-3, R141: sin los marcos no se sabe la hoja de cada vista y la resolución por hoja
        # (R72) se apagaría callada.
        raise ValueError(
            "construir_elementos: la segmentación tiene varias vistas; hacen falta los marcos "
            "(frames) para saber la hoja de cada elemento"
        )
    config = config or TextPatternConfig()
    colocadas, _ = _separar(detections, segmentation)
    alturas = segmentation.alturas_de_entrepiso() if segmentation is not None else {}
    asignacion = (
        segmentation.assignment if segmentation is not None and segmentation.is_segmented else {}
    )
    resolutor = _Resolutor(por_marca, por_familia, reglas, frames)
    elementos: list[Elemento] = []
    for d in colocadas:
        vista = asignacion.get(d.detection_id)
        familia = d.family
        marca = normalizar_marca(d.mark, config) if d.mark.strip() else ""
        avisos = _avisos_de_la_deteccion(d, familia, marca, meters_factor)
        if segmentation is not None and d.detection_id in segmentation.vistas_dudosas:
            avisos.append(segmentation.vistas_dudosas[d.detection_id])  # R165
        colocacion = Colocacion(
            seccion_cm=_seccion_medida(d, familia, meters_factor),
            seccion_no_rectangular=_contorno_no_rectangular(d, familia, meters_factor),
            longitud_m=_longitud_medida(d, familia, meters_factor),
            altura_m=_altura(familia, alturas.get(vista or ""), altura_supuesta_m),
            avisos=avisos,
            muro_cm=_muro_medido(d, meters_factor),
            muro_sin_medir=d.properties.get("muro_sin_medir"),
            muro_perpendicular_cm=_muro_perpendicular(d, meters_factor),
        )
        base = Elemento(
            element_id=element_id(d, meters_factor),
            detection_id=d.detection_id,
            marca=marca,
            familia=familia,
            vista=vista,
            hoja=_hoja(d, vista, frames or []),
            definicion="ninguna",
            colocacion=colocacion,
        )
        elementos.append(resolutor.resolver(base))
    return elementos


def resolver(
    elemento: Elemento,
    por_marca: dict[str, Definicion],
    por_familia: dict[str, Definicion],
    reglas: Reglas,
    *,
    frames: list[SheetFrame],
) -> Elemento:
    """El elemento vuelto a juntar con las definiciones y las reglas de su hoja (después de una
    decisión, por ejemplo): la definición que le toca, cada campo resuelto para su hoja, el
    recubrimiento de su familia. Lo de la colocación (``Colocacion``) no cambia. Devuelve un
    elemento nuevo. ``frames`` son los marcos de la corrida, siempre (vacío sólo si el plano no
    los tiene): dicen qué hojas son de cimentación (R144, R150)."""
    return _Resolutor(por_marca, por_familia, reglas, frames).resolver(elemento)


# --------------------------------------------------------------------------------- colocaciones


def _segmentada(segmentation: SheetSegmentation | None) -> bool:
    return segmentation is not None and segmentation.is_segmented


def _separar(
    detections: list[Detection], segmentation: SheetSegmentation | None
) -> tuple[list[Detection], list[Excluida]]:
    """(las colocaciones, las excluidas con su motivo) entre las detecciones de las familias
    estructurales; las demás detecciones no son de esta cuenta."""
    segmentada = _segmentada(segmentation)
    vistas = {v.view_id: v for v in segmentation.views} if segmentation is not None else {}
    plantas = (
        {v.view_id for v in segmentation.structural_plan_views()}
        if segmentation is not None and segmentada
        else set()
    )
    colocadas: list[Detection] = []
    fuera: list[Excluida] = []
    for d in detections:
        if d.family not in FAMILIAS_ESTRUCTURALES:
            continue
        vista = (
            segmentation.assignment.get(d.detection_id)
            if segmentation is not None and segmentada
            else None
        )
        motivo: Motivo | None = None
        texto = ""
        if (d.properties or {}).get("titulo_de_detalle"):
            motivo = "titulo_de_detalle"
            texto = (
                "título de detalle: su sección está dibujada (o la señala una flecha); define la "
                "marca, no la coloca"
            )
        elif (d.properties or {}).get("role") == "cuadro":
            motivo = "cuadro"
            texto = "marca de cuadro o de detalle: define la marca, no la coloca"
        elif segmentada and vista is None:
            motivo = "sin_vista"
            texto = "la segmentación no la asignó a ninguna vista"
        elif segmentada and vista not in plantas:
            region = vistas.get(vista or "")
            if region is None:
                motivo, texto = "sin_vista", f"su vista «{vista}» no existe en la segmentación"
            elif region.kind == ViewKind.excluded:
                motivo = "vista_excluida"
                texto = (
                    f"en «{region.title}», que no es una planta (detalle, corte, cuadro o fuera)"
                )
            else:
                motivo = "planta_no_estructural"
                texto = f"en «{region.title}», planta de una hoja que no es de estructura"
        if motivo is None:
            colocadas.append(d)
        else:
            fuera.append(
                Excluida(
                    detection_id=d.detection_id,
                    marca=d.mark,
                    familia=d.family,
                    vista=vista,
                    motivo=motivo,
                    texto=texto,
                )
            )
    return colocadas, fuera


def _hoja(d: Detection, vista: str | None, frames: list[SheetFrame]) -> str:
    """El código del marco de la vista de la detección, o del marco más chico de su archivo que la
    contiene (su código o su id, como las reglas y las definiciones); sin marco, su archivo."""
    fuente = d.evidence.source or ""
    marco = next((f for f in frames if f.frame_id == vista), None) if vista else None
    if marco is None:
        centro = bbox_center(d.bbox)
        dentro = [f for f in frames if f.source_file in ("", fuente) and f.contains(centro)]
        if dentro:
            marco = min(dentro, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    if marco is not None:
        return marco.code or marco.frame_id
    return fuente


def _seccion_medida(d: Detection, familia: str, factor: float | None) -> Dato | None:
    """La sección que mide la colocación en planta: las cotas junto a un castillo o una columna
    (``section_source == "cota"``), o los lados de un contorno de zapata que es un rectángulo a
    ejes. Nunca la sección que ``apply_schedule`` copió de la definición ni el área de un marcador
    (la caja de un bloque puede ser la del bloque que lo contiene, R133; los marcadores son E2)."""
    props = d.properties or {}
    if familia in _CON_ALTURA and props.get("section_source") == "cota":
        lados = _lados(props.get("section_cm"))
        if lados is not None:
            a, b = sorted(lados) if familia in FAMILIAS_QUE_SE_ORDENAN else lados
            return Dato(
                valor=(a, b),
                fuente="medido",
                texto=f"cotas junto a la colocación en planta: {_cm(a)}x{_cm(b)}",
                entidades=list(d.source_entities),
            )
    if familia == "zapata" and factor:
        if float(props.get("rectangularity") or 0.0) >= _RECTANGULO:
            x0, y0, x1, y1 = d.bbox
            a = round(min(x1 - x0, y1 - y0) * factor * 100, 1)
            b = round(max(x1 - x0, y1 - y0) * factor * 100, 1)
            if a > 0 and b > 0:
                return Dato(
                    valor=(a, b),
                    fuente="medido",
                    texto=f"contorno rectangular en planta: {_cm(a)}x{_cm(b)} cm",
                    entidades=list(d.source_entities),
                )
    return None


def _contorno_no_rectangular(d: Detection, familia: str, factor: float | None) -> Dato | None:
    """R142: el área del contorno en planta de un castillo o una columna cuando no es un
    rectángulo y está en una capa de castillos o columnas (nunca un dado), en cm²."""
    props = d.properties or {}
    area = props.get("contorno_area_du2")
    capa = str(props.get("contorno_capa") or "")
    if (
        familia not in _CON_ALTURA
        or not factor
        or not isinstance(area, (int, float))
        or area <= 0
        or props.get("contorno_rectangular") is not False
        or not layer_matches(capa, _CAPAS_DE_CASTILLO)
    ):
        return None
    cm2 = round(float(area) * factor * factor * 10_000, 1)
    return Dato(
        valor={"area_cm2": cm2},
        fuente="medido",
        texto=f"contorno en planta no rectangular (capa {capa}): {cm2:g} cm²",
        entidades=list(props.get("contorno_entidades") or d.source_entities[1:]),
    )


def _lados(texto: object) -> tuple[float, float] | None:
    if not isinstance(texto, str) or "x" not in texto.lower():
        return None
    try:
        a, b = (float(v) for v in texto.lower().split("x"))
    except ValueError:
        return None
    return (_numero(a), _numero(b)) if a > 0 and b > 0 else None


def _numero(v: float) -> float:
    return int(v) if float(v).is_integer() else v


def _cm(v: float) -> str:
    return f"{v:g}"


def _muro_medido(d: Detection, factor: float | None) -> Dato | None:
    """R168: el espesor (cm) del muro que corona la dala de la colocación, medido junto a la
    etiqueta (``detect_beams``), con sus caras por su handle del dibujo. R193: dice cómo se midió
    — entre las dos caras que tienen la etiqueta en medio, o junto a la etiqueta, desde la cara
    más cercana a ella (la etiqueta no está sobre su muro) —; nunca «entre sus caras» cuando no
    fue así."""
    espesor = d.properties.get("muro_espesor")
    if not isinstance(espesor, int | float) or not factor:
        return None
    cm = round(float(espesor) * factor * 100.0, 1)
    caras = list(d.properties.get("muro_caras") or [])
    cercana = d.properties.get("muro_cara_cercana")
    if d.properties.get("muro_medido") == "junto" and cercana:
        otra = [c for c in caras if c != cercana]
        hasta = f" a {otra[0]}" if otra else ""
        texto = f"el muro junto a la etiqueta, desde su cara más cercana {cercana}{hasta}"
    elif len(caras) == 1:
        texto = f"el muro bajo la etiqueta, entre dos caras de {caras[0]}"
    else:
        texto = f"el muro bajo la etiqueta, entre sus caras {' y '.join(caras)}"
    return Dato(
        valor=_numero(cm),
        fuente="medido",
        texto=f"{texto}: {_cm(cm)} cm",
        entidades=list(d.source_entities),
    )


def _muro_perpendicular(d: Detection, factor: float | None) -> Dato | None:
    """R193, R198: el muro perpendicular más cercano a la etiqueta de una dala, con sus caras; su
    espesor (cm) sólo si dos caras seguidas lo acotan (``detect_beams``), si no sin número."""
    caras = list(d.properties.get("muro_perpendicular_caras") or [])
    if not caras or not factor:
        return None
    espesor = d.properties.get("muro_perpendicular_espesor")
    if isinstance(espesor, int | float):
        cm = round(float(espesor) * factor * 100.0, 1)
        de = f"caras {' y '.join(caras)}" if len(caras) > 1 else f"las dos caras de {caras[0]}"
        return Dato(
            valor=_numero(cm),
            fuente="medido",
            texto=f"un muro perpendicular de {_cm(cm)} cm junto a la etiqueta ({de})",
            entidades=list(d.source_entities),
        )
    return Dato(
        valor=None,
        fuente="medido",
        texto=f"un muro perpendicular junto a la etiqueta (cara {' y '.join(caras)}), sin dos "
        "caras seguidas que acoten su espesor",
        entidades=list(d.source_entities),
    )


def _longitud_medida(d: Detection, familia: str, factor: float | None) -> Dato | None:
    """El claro medido de una viga (la línea de su etiqueta) o el largo de un muro, en metros."""
    props = d.properties or {}
    clave = (
        "estimated_span_length"
        if familia in _VIGAS
        else "estimated_length"
        if familia == "muro_concreto"
        else None
    )
    if clave is None or not factor:
        return None
    medido = props.get(clave)
    if not isinstance(medido, (int, float)) or medido <= 0:
        return None
    metros = round(float(medido) * factor, 3)
    if familia in _VIGAS:  # la etiqueta y su línea: la medida es la línea
        que, entidades = "la línea de su etiqueta", d.source_entities[1:] or d.source_entities
    else:
        que, entidades = "el muro", d.source_entities
    return Dato(
        valor=metros,
        fuente="medido",
        texto=f"medido en planta ({que}): {metros:g} m",
        entidades=list(entidades),
    )


def _altura(familia: str, entrepiso: AlturaDeEntrepiso | None, supuesta_m: float) -> Dato | None:
    """La altura de un castillo o una columna: la de su entrepiso entre dos niveles declarados
    (``nota``), la repetida de la planta de abajo en la más alta (``supuesto``) o, sin niveles, la
    supuesta (R73)."""
    if familia not in _CON_ALTURA:
        return None
    if entrepiso is None:
        return Dato(
            valor=supuesta_m,
            fuente="supuesto",
            texto=f"el plano no declara los niveles de su planta: altura supuesta {supuesta_m:g} m",
        )
    return Dato(
        valor=entrepiso.altura_m,
        fuente="supuesto" if entrepiso.repetida else "nota",
        texto=entrepiso.texto,
    )


def _avisos_de_la_deteccion(
    d: Detection, familia: str, marca: str, factor: float | None
) -> list[str]:
    avisos: list[str] = []
    if not marca:
        avisos.append("sin marca: la colocación no tiene marca en planta")
    # R146: the detector's word on the span — doubtful, measured on the beam's axis between its
    # two faces, or its own tramo of a line several tags share; R166: and on a column's marker that
    # a tag of another mark reaches about as near.
    for clave in ("claro_dudoso", "claro_caras", "claro_compartido", "marcador_dudoso"):
        texto = (d.properties or {}).get(clave)
        if texto:
            avisos.append(str(texto))
    if familia in _VIGAS:
        if not factor:
            avisos.append("longitud: sin unidades confiables el claro no se mide")
        elif not isinstance((d.properties or {}).get("estimated_span_length"), (int, float)):
            avisos.append(
                str(
                    (d.properties or {}).get("sin_claro")
                    or "longitud: ninguna línea de claro junto a la etiqueta; sin longitud"
                )
            )
    return avisos


# ----------------------------------------------------------------------------- la resolución


class _Resolutor:
    """Junta elementos con las definiciones y las reglas, con las reglas de cada hoja calculadas
    una sola vez (``Reglas.para`` es un trabajo por hoja)."""

    def __init__(
        self,
        por_marca: dict[str, Definicion],
        por_familia: dict[str, Definicion],
        reglas: Reglas,
        frames: list[SheetFrame] | None = None,
    ) -> None:
        self.por_marca = por_marca
        self.por_familia = por_familia
        self.reglas = reglas
        self._por_hoja: dict[str, Reglas] = {}
        # R144: las hojas de cimentación (su título lo dice: «CIMENTACIÓN», «DETALLES DE
        # CIMENTACIÓN»), por su código como las demás.
        self.de_cimentacion = {
            f.code or f.frame_id for f in frames or [] if "CIMENTACION" in _sin_acentos(f.title)
        }

    def reglas_de(self, hoja: str) -> Reglas:
        if hoja not in self._por_hoja:
            self._por_hoja[hoja] = self.reglas.para(hoja)
        return self._por_hoja[hoja]

    def resolver(self, elemento: Elemento) -> Elemento:
        hoja, familia, marca = elemento.hoja, elemento.familia, elemento.marca
        col = elemento.colocacion
        propia = self.por_marca.get(marca) if marca else None
        de_familia = self.por_familia.get(familia)
        definicion: Literal["marca", "familia", "ninguna"] = (
            "marca" if propia is not None else "familia" if de_familia is not None else "ninguna"
        )
        avisos = list(col.avisos)
        dudas: list[str] = []
        if propia is not None and propia.variantes:
            propia = _variante(marca, propia, col, avisos, dudas)
        if marca and definicion == "familia":
            avisos.append(
                f"la marca {marca} no está definida en el plano; se usa la definición de la "
                f"familia {familia}"
            )
        elif marca and definicion == "ninguna":
            avisos.append(
                f"la marca {marca} no está definida en el plano y no hay nota de la familia "
                f"{familia}"
            )
        elif not marca and definicion == "familia":
            avisos.append(f"sin marca: se usa la definición de la familia {familia}")
        if propia is not None and propia.familia != familia:
            avisos.append(
                f"familia: la colocación es {familia}; la definición de {marca} dice "
                f"{propia.familia}"
            )

        def de(definicion_: Definicion | None, campo: str) -> Dato | None:
            dato = getattr(definicion_, campo) if definicion_ is not None else None
            if dato is None:
                return None
            propio, aviso = _de_la_hoja(dato, hoja)
            if aviso is not None:
                avisos.append(f"{_CAMPO[campo]}: {aviso}")
            return propio

        nota = _nota_de_familia(de_familia, hoja)
        quien = marca or "la colocación sin marca"
        seccion = self._seccion(
            familia, quien, propia, de(propia, "seccion_cm"), de(de_familia, "seccion_cm"),
            nota("seccion_cm"), col.seccion_cm, col.seccion_no_rectangular, avisos, dudas,
        )  # fmt: skip
        armado: dict[str, Dato | None] = {}
        for campo in _CAMPOS_DE_ARMADO:
            if propia is not None:
                armado[campo] = _de_la_marca_o_la_nota(
                    campo,
                    familia,
                    quien,
                    de(propia, campo),
                    nota(campo),
                    propia.sin_leer.get(campo),
                    avisos,
                    dudas,
                )
            else:
                armado[campo] = de(de_familia, campo)
        extension = de(propia or de_familia, "longitud_m")
        if familia in _CON_ALTURA:
            longitud = None
            altura = _con_la_definicion(col.altura_m, de(propia, "longitud_m"))
        elif familia in _EXTENSION_ES_ALTURA:
            longitud = col.longitud_m
            altura = extension
        else:
            longitud = self._longitud(familia, extension, col, avisos)
            altura = None
        return elemento.model_copy(
            update={
                "definicion": definicion,
                "seccion_cm": seccion,
                "altura_m": altura,
                "longitud_m": longitud,
                "longitudinales": armado["longitudinales"],
                "estribos": armado["estribos"],
                "parrillas": armado["parrillas"],
                "recubrimiento_m": self._recubrimiento(familia, hoja, propia, avisos),
                "avisos": list(dict.fromkeys(avisos)),
                "dudas": list(dict.fromkeys(dudas)),
            },
            deep=True,
        )

    def _seccion(
        self,
        familia: str,
        quien: str,
        propia: Definicion | None,
        de_la_marca: Dato | None,
        de_la_familia: Dato | None,
        nota: Dato | None,
        medida: Dato | None,
        no_rectangular: Dato | None,
        avisos: list[str],
        dudas: list[str],
    ) -> Dato | None:
        """La sección: la de la definición de la marca (o la de la familia, sin definición de la
        marca); la propia ilegible cae a la nota de la familia, la medida, la supuesta (R113,
        R134); la que nadie dice, a la medida, la nota de la familia, la supuesta. Un castillo o
        una columna cuya sección no se lee y cuyo contorno en planta no es un rectángulo toma el
        área de ese contorno, medida (R142)."""
        supuesta = SECCION_SUPUESTA_CM.get(familia)
        sin_leer = de_la_marca is None or de_la_marca.valor is None
        # R150: sólo si la definición dice que su sección dibujada no es un rectángulo.
        if (
            no_rectangular is not None
            and sin_leer
            and propia is not None
            and propia.seccion_no_rectangular
        ):
            avisos.append(
                "sección no rectangular: se usa el área de su contorno en planta "
                f"({no_rectangular.valor['area_cm2']:g} cm²)"
            )
            return no_rectangular.model_copy(
                update={"alternativas": _planas([d for d in (de_la_marca,) if d is not None])},
                deep=True,
            )
        if propia is None:
            con_valor = [
                d for d in (de_la_familia, medida) if d is not None and d.valor is not None
            ]
            if con_valor:
                elegida = elegir(con_valor)
                assert elegida is not None
                return elegida
            if supuesta is not None:
                avisos.append(f"sección: el plano no la declara; se supone {_lado(supuesta)} cm")
                return _supuesta(supuesta, familia, [])
            avisos.append(f"sección: el plano no la declara y la familia {familia} no tiene una "
                          "supuesta; sin sección")  # fmt: skip
            return None
        if de_la_marca is not None and de_la_marca.valor is not None:
            candidatos = [de_la_marca] + ([medida] if medida is not None else [])
            elegida = elegir(candidatos)
            assert elegida is not None
            return elegida
        if de_la_marca is not None and de_la_marca.ilegible:
            # R113, R134: la sección propia está dibujada y nadie la leyó.
            leyenda = f"«{de_la_marca.texto}»" if de_la_marca.texto else "su dibujo"
            if nota is not None:
                avisos.append(
                    "sección: la sección propia está dibujada y no se leyó; se usa la nota de "
                    f"familia («{nota.texto}», {_lado(nota.valor)} cm)"
                )
                dudas.append(
                    f"sección de {quien}: la propia está dibujada y no se leyó ({leyenda}); se "
                    f"supone {_lado(nota.valor)} cm de la nota de familia, por confirmar"
                )
                return _como_supuesto(
                    nota,
                    f"la sección propia está dibujada y no se leyó; se usa la nota de familia: "
                    f"«{nota.texto}»",
                    [de_la_marca, nota],
                )
            if medida is not None:
                avisos.append(
                    "sección: el plano la dibuja; no se leyó; se usa la medida en planta "
                    f"({_lado(medida.valor)} cm)"
                )
                dudas.append(
                    f"sección de {quien}: la propia está dibujada y no se leyó ({leyenda}); se "
                    f"supone la medida en planta, {_lado(medida.valor)} cm, por confirmar"
                )
                return _como_supuesto(
                    medida,
                    f"el plano la dibuja; no se leyó: se usa la medida en planta ({medida.texto})",
                    [de_la_marca, medida],
                )
            if supuesta is not None:
                avisos.append(
                    "sección: el plano la dibuja; no se leyó; se usa la sección supuesta de la "
                    f"familia ({_lado(supuesta)} cm)"
                )
                dudas.append(
                    f"sección de {quien}: la propia está dibujada y no se leyó ({leyenda}); se "
                    f"supone {_lado(supuesta)} cm, la de la familia {familia}, por confirmar"
                )
                return _supuesta(supuesta, familia, [de_la_marca], dibujada=True)
            avisos.append(
                "sección: el plano la dibuja; no se leyó, y no hay nota de la familia, medida ni "
                "sección supuesta: sin sección"
            )
            dudas.append(
                f"sección de {quien}: la propia está dibujada y no se leyó ({leyenda}); sin sección"
            )
            return de_la_marca
        # La marca está definida pero nada dice su sección.
        if medida is not None:
            avisos.append(
                "sección: la definición de la marca no la dice; se usa la medida en planta"
            )
            return medida
        if nota is not None:
            avisos.append(
                "sección: la definición de la marca no la dice; se supone la de la nota de "
                f"familia («{nota.texto}», {_lado(nota.valor)} cm)"
            )
            return _como_supuesto(
                nota,
                f"la definición de la marca no dice su sección; se supone la de la nota de "
                f"familia: «{nota.texto}»",
                [nota],
            )
        if supuesta is not None:
            avisos.append(f"sección: el plano no la declara; se supone {_lado(supuesta)} cm")
            return _supuesta(supuesta, familia, [])
        avisos.append(
            f"sección: el plano no la declara y la familia {familia} no tiene una supuesta; "
            "sin sección"
        )
        return None

    def _longitud(
        self, familia: str, de_la_definicion: Dato | None, col: Colocacion, avisos: list[str]
    ) -> Dato | None:
        """La longitud de una viga o un pilote: la que dice la definición (la de un pilote, la que
        declare una viga) o la medida en planta; una ilegible de la definición no tapa la medida:
        queda como su alternativa. Sin ninguna, ``None`` con su aviso (nunca 0)."""
        declarada = de_la_definicion
        medida = col.longitud_m
        if declarada is not None and declarada.valor is not None:
            elegida = elegir([declarada] + ([medida] if medida is not None else []))
            return elegida
        if medida is not None:
            if declarada is not None:  # ilegible: el plano la dice y no se leyó
                avisos.append(
                    f"longitud: el plano la escribe y no se leyó («{declarada.texto}»); se usa la "
                    "medida en planta"
                )
                return medida.model_copy(
                    update={"alternativas": [*medida.alternativas, declarada]}, deep=True
                )
            return medida
        if familia in _VIGAS:
            if not any(a.startswith("longitud:") for a in avisos):
                avisos.append("longitud: sin claro medido ni declarado; sin longitud")
            return declarada
        if familia == "pilote":
            avisos.append("longitud: el plano no declara la del pilote; sin longitud")
        return declarada

    def _recubrimiento(
        self, familia: str, hoja: str, propia: Definicion | None, avisos: list[str]
    ) -> Dato | None:
        """El recubrimiento de la familia como lo dicen las reglas de la hoja; una familia que las
        reglas no traen toma el supuesto; una que tampoco tiene supuesto se queda sin él, y se
        dice. Un muro de concreto que el plano no nombra en sus recubrimientos, colocado o
        detallado en una hoja de cimentación, toma la cláusula de los elementos de cimentación
        cuando las reglas la leen así (R144)."""
        reglas = self.reglas_de(hoja)
        dato = reglas.recubrimiento_m.get(familia)
        dibujado = propia.recubrimiento_m if propia is not None else None
        if dibujado is not None and dibujado.valor is not None:
            # R212: el que su sección dibujada acota en SU hoja; el de las reglas queda como
            # alternativa (gana por rango: ``seccion_dibujada`` > ``nota``). El de otra hoja no:
            # las hojas de Marina acotan recubrimientos distintos para la misma marca (K-6: 4 cm
            # en ES-100, 3 en ES-400).
            propio = para_hoja(dibujado, hoja)
            if hoja in hojas_de(propio):
                elegido = elegir([propio] + ([dato] if dato is not None else []))
                assert elegido is not None
                return elegido
            otras = ", ".join(
                f"{float(m.valor) * 100:g} cm en {', '.join(hojas_de(m))}"
                for m in miembros(dibujado)
                if m.valor is not None
            )
            avisos.append(
                f"recubrimiento: la sección dibujada de la hoja {hoja} no lo acota (o no se "
                f"leyó); el de otras hojas no se toma ({otras}); se usa el de las reglas"
            )
        if familia == "muro_concreto" and (dato is None or dato.fuente == "supuesto"):
            hojas = {hoja, *(propia.hojas if propia is not None else [])}
            if hojas & self.de_cimentacion:
                clausula = next(
                    (
                        d
                        for f in _DE_CIMENTACION
                        if (d := reglas.recubrimiento_m.get(f)) is not None
                        and d.fuente not in ("supuesto", "ia")
                        and "CIMENTACION" in _sin_acentos(d.texto)
                    ),
                    None,
                )
                if clausula is not None:
                    donde = ", ".join(sorted(hojas & self.de_cimentacion))
                    avisos.append(
                        f"recubrimiento: muro en una hoja de cimentación ({donde}); se usa la "
                        f"cláusula de los elementos de cimentación («{clausula.texto}»)"
                    )
                    return clausula.model_copy(deep=True)
        if dato is not None:
            return dato
        valor = RECUBRIMIENTO_SUPUESTO.get(familia)
        if valor is not None:
            return Dato(
                valor=valor,
                fuente="supuesto",
                texto=f"Recubrimiento estándar de {familia}: el plano no lo dice",
            )
        avisos.append(f"recubrimiento: ni el plano ni los supuestos lo dan para {familia}")
        return None


# R168: el muro medido corresponde a la variante que lo declara con esta tolerancia (cm).
_TOLERANCIA_DE_MURO_CM = 2.0


def _variante(
    marca: str, propia: Definicion, col: Colocacion, avisos: list[str], dudas: list[str]
) -> Definicion:
    """R168: la variante de una marca que su colocación toma: la que su detalle declara para el
    espesor del muro que corona, medido (±``_TOLERANCIA_DE_MURO_CM``), con un aviso que nombra el
    muro. Si ninguna o más de una coincide, o el muro no se midió, la definición de la marca (con
    sus variantes juntas: en conflicto) sigue, y se dice."""
    espesores = ", ".join(f"{_cm(v.para_muro_cm or 0.0)}" for v in propia.variantes)
    medido = col.muro_cm
    if medido is None or not isinstance(medido.valor, int | float):
        motivo = col.muro_sin_medir or "su muro no se midió"
        avisos.append(
            f"variante: {marca} tiene variantes por muro (para muros de {espesores} cm) y no se "
            f"sabe cuál es: {motivo}; su definición queda con sus variantes juntas"
        )
        dudas.append(f"variante de {marca}: el muro bajo la colocación no se midió ({motivo})")
        return propia
    suyas = [
        v
        for v in propia.variantes
        if v.para_muro_cm is not None
        and abs(v.para_muro_cm - medido.valor) <= _TOLERANCIA_DE_MURO_CM
    ]
    cruce = col.muro_perpendicular_cm
    if cruce is not None and (
        not isinstance(cruce.valor, int | float)
        or abs(float(cruce.valor) - float(medido.valor)) > _TOLERANCIA_DE_MURO_CM
    ):
        # R193: junto a la etiqueta llega otro muro, de otro espesor: la dala puede ser la suya.
        avisos.append(
            f"variante: {medido.texto}; pero {cruce.texto}: no se sabe cuál de los dos corona; "
            f"su definición queda con sus variantes juntas (para muros de {espesores} cm)"
        )
        dudas.append(
            f"variante de {marca}: el muro medido ({_cm(float(medido.valor))} cm) y "
            f"{cruce.texto}, por confirmar"
        )
        return propia
    if len(suyas) == 1:
        variante = suyas[0]
        avisos.append(
            f"variante: {marca} «para muros de {_cm(variante.para_muro_cm or 0.0)} cm»: "
            f"{medido.texto}"
        )
        return variante
    cuantas = "ninguna" if not suyas else "más de una"
    avisos.append(
        f"variante: {medido.texto}; {cuantas} de las variantes de {marca} (para muros de "
        f"{espesores} cm) es la suya: su definición queda con sus variantes juntas"
    )
    dudas.append(
        f"variante de {marca}: {cuantas} de sus variantes (para muros de {espesores} cm) es para "
        f"el muro bajo la colocación ({_cm(float(medido.valor))} cm), por confirmar"
    )
    return propia


def _nota_de_familia(de_familia: Definicion | None, hoja: str) -> Callable[[str], Dato | None]:
    """Los campos que la nota de la familia dice con valor (del plano, nunca de la IA), resueltos
    para la hoja: el respaldo de una marca que no los dice o no se leyó (R134)."""

    def campo(nombre: str) -> Dato | None:
        dato = getattr(de_familia, nombre) if de_familia is not None else None
        if dato is None or dato.valor is None or dato.ilegible or dato.fuente == "ia":
            return None
        return _de_la_hoja(dato, hoja)[0]

    return campo


def _de_la_hoja(dato: Dato, hoja: str) -> tuple[Dato, str | None]:
    """El dato como lo resuelve la hoja del elemento (``para_hoja``, R72 con R141), y el aviso
    cuando lo que dice esa hoja no se pudo leer y se usa lo que leyó otra."""
    propio = para_hoja(dato, hoja)
    suyas = [m for m in miembros(dato) if m.ilegible and hoja in hojas_de(m)]
    if suyas and propio.valor is not None and hoja not in hojas_de(propio):
        otras = ", ".join(hojas_de(propio)) or "otra hoja"
        return propio, (
            f"lo que dice la hoja {hoja} no se pudo leer («{suyas[0].texto}»); se usa lo que se "
            f"leyó en {otras}"
        )
    return propio, None


def _de_la_marca_o_la_nota(
    campo: str,
    familia: str,
    quien: str,
    de_la_marca: Dato | None,
    nota: Dato | None,
    bloqueada: str | None,
    avisos: list[str],
    dudas: list[str],
) -> Dato | None:
    """Un campo de armado de una marca definida: el suyo. Si el plano lo escribe y nadie lo leyó
    (ilegible: la flecha que señala su detalle, R139, o un texto suyo sin leer; o la IA bloqueada
    por un texto sin dueño junto a su sección, R140), el de la nota de su familia como
    ``supuesto``, con aviso y duda, y la ilegible como alternativa; sin nota se queda sin valor
    (no hay armado supuesto), con aviso y duda (R134). Si sólo no lo dice, el de la nota de la
    familia como ``supuesto``, con aviso."""
    if de_la_marca is not None and de_la_marca.valor is not None:
        return de_la_marca
    if campo == "parrillas" and familia not in FAMILIAS_CON_PARRILLA:
        # Una familia sin parrillas: lo que reclama una flecha por si acaso (R139) no le falta.
        return de_la_marca
    nombre = _CAMPO[campo]
    escrito = (
        f"«{de_la_marca.texto}»"
        if de_la_marca is not None and de_la_marca.ilegible
        else bloqueada
        if bloqueada
        else None
    )
    if escrito is not None:
        por = f"el plano lo escribe y no se leyó ({escrito})"
        if nota is None:
            avisos.append(f"{nombre}: {por}; no hay nota de familia: sin {nombre}")
            dudas.append(f"{nombre} de {quien}: {por}; sin {nombre}, por leer")
            return de_la_marca
        avisos.append(f"{nombre}: {por}; se usa la nota de familia («{nota.texto}»)")
        dudas.append(
            f"{nombre} de {quien}: {por}; se supone el de la nota de familia, por confirmar"
        )
        return _como_supuesto(
            nota,
            f"el plano lo escribe y no se leyó; se usa la nota de familia: «{nota.texto}»",
            [d for d in (de_la_marca, nota) if d is not None],
        )
    if nota is None:
        return de_la_marca
    avisos.append(
        f"{nombre}: la definición de la marca no lo dice; se supone el de la nota de "
        f"familia («{nota.texto}»)"
    )
    return _como_supuesto(
        nota,
        f"la definición de la marca no lo dice; se supone el de la nota de familia: «{nota.texto}»",
        [nota],
    )


def _con_la_definicion(colocacion: Dato | None, declarada: Dato | None) -> Dato | None:
    """La altura de la planta, o la que declare la definición de la marca si la declara (gana la
    de más rango; la otra queda como alternativa)."""
    if declarada is None or declarada.valor is None:
        return colocacion
    return elegir([declarada] + ([colocacion] if colocacion is not None else []))


def _como_supuesto(dato: Dato, texto: str, alternativas: list[Dato]) -> Dato:
    """El valor de ``dato`` usado como supuesto: con su hoja y sus entidades, el texto que dice por
    qué, y lo que había como alternativas (planas, como las deja ``elegir``)."""
    return Dato(
        valor=dato.valor,
        fuente="supuesto",
        hoja=dato.hoja,
        hojas=list(dato.hojas),
        texto=texto,
        entidades=list(dato.entidades),
        alternativas=_planas(alternativas),
    )


def _supuesta(
    lados: tuple[int, int], familia: str, alternativas: list[Dato], dibujada: bool = False
) -> Dato:
    por = "el plano la dibuja y no se leyó" if dibujada else "el plano no la declara"
    return Dato(
        valor=lados,
        fuente="supuesto",
        texto=f"sección supuesta de {familia}, {_lado(lados)} cm: {por}",
        alternativas=_planas(alternativas),
    )


def _planas(datos: list[Dato]) -> list[Dato]:
    """Cada dato sin sus alternativas, y luego ellas: nada se esconde un nivel más abajo (la IA
    que una definición dejó como alternativa sigue a la vista)."""
    salida: list[Dato] = []
    for d in datos:
        salida.append(d.model_copy(update={"alternativas": []}, deep=True))
        salida += [a.model_copy(deep=True) for a in d.alternativas]
    return salida


def _lado(valor: object) -> str:
    if isinstance(valor, (list, tuple)) and len(valor) == 2:
        return f"{_cm(valor[0])}x{_cm(valor[1])}"
    return str(valor)


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn"
    )
