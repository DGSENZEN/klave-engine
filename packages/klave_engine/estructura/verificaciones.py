"""Las verificaciones del propio plano: lo que la lectura estructural no sabe, lo que el plano se
contradice a sí mismo y lo que el plano dibuja y la lectura no encontró, agrupado para que la
oficina actúe y ordenado por lo que está en juego.

Cada hallazgo (``Verificacion``) dice su número de verificación, su severidad —``bloquea`` (la
cantidad no se puede sacar), ``duda`` (se sacó con algo que alguien tiene que confirmar) o
``aviso``—, un mensaje en español que cita los textos del plano por su handle, las marcas, los
elementos y los datos que toca, y lo que está en juego (``en_juego``: el acero y el concreto que
dependen de él, en kg y m³, y las piezas). Su ``id`` es estable: sale del número, la marca, la
hoja y la clave del hallazgo (nunca de sus cuentas), así que una decisión que se tome sobre él
lo sigue encontrando en la siguiente corrida.

Las verificaciones de E0 (la numeración del diseño):

1. Una marca colocada en planta que no está definida: ``bloquea`` si ni una nota general de su
   familia la describe, ``duda`` si se usa la nota. Las colocaciones sin marca no son de esta
   cuenta: un ``aviso`` por familia dice cuántas son y qué les falta.
2. Una marca definida que nunca se coloca y cuyo texto no aparece en ninguna planta: ``aviso``.
7. Un dato crítico (``CRITICOS``) que falta, que es un supuesto, que sólo dice la IA, que sale de
   otra hoja porque la suya no se leyó, o unos estribos sin separación: ``bloquea`` si no hay
   supuesto, si no ``duda``. Las dudas de una colocación (vista, claro, marcador) se agrupan por
   hoja; las de un mismo dato de una marca, en un solo hallazgo con todas sus colocaciones.
8. El plano se contradice: dos lecturas de una marca que dicen valores distintos (una copia
   ilegible no es una contradicción), las reglas que no coinciden dentro del alcance de una misma
   hoja (la tabla de varillas que da traslape donde la nota manda soldar), un código de hoja que
   llevan dos marcos, y los entrepisos contados de dos maneras a la vez.
10. Una marca escrita en una planta estructural sin ningún elemento suyo colocado ahí (todo
    pilote escrito en planta debe tener su pila); y, como aviso, las detecciones estructurales
    que caen fuera de toda planta de estructura y no se cuentan.
11. Lo que nadie leyó: los textos de armado sin dueño (por hoja, por motivo y por clase de texto,
    con su cuenta y sus handles), los avisos de las lecturas de cada marca y de las reglas, el
    armado escrito junto a la sección de un detalle o en su esquina, las etiquetas de cuadro sin
    su pila (y las que se contaron como colocación), y los campos que sólo dice la IA junto a
    textos del plano que nadie leyó."""

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from klave_engine.costing.steel import SteelAssumptions
from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.results import Detection
from klave_engine.detection.schedules import ScheduleInventory, campos_de_fragmento
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.detection.views import SheetSegmentation
from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.acero import acero_elemento
from klave_engine.estructura.armado import (
    Armado,
    GrupoVarillas,
    JuegoEstribos,
    Parrilla,
    texto_estribos,
    texto_longitudinal,
    texto_parrillas,
    tiene_armado,
)
from klave_engine.estructura.dato import PRECEDENCIA, Dato, hojas_de, miembros
from klave_engine.estructura.definiciones import Definicion, normalizar_marca
from klave_engine.estructura.elementos import (
    _TOLERANCIA_DE_MURO_CM,
    FAMILIAS_ESTRUCTURALES,
    Elemento,
    excluidas,
    variante_de,
)
from klave_engine.estructura.marcas import marca_normalizada, marcas_nombradas
from klave_engine.estructura.reglas import Reglas
from klave_engine.estructura.textos import alto_de_texto, extension_de_texto
from klave_engine.geometry.bbox import BBox, bbox_center, bbox_contains_point

Severidad = Literal["bloquea", "duda", "aviso"]
_RANGO_DE_SEVERIDAD: dict[str, int] = {"bloquea": 0, "duda": 1, "aviso": 2}

# Los datos críticos de cada familia (diseño §4.1, los que el modelo de E0 lleva): el
# denominador de «lo que el plano dice». Una dala y un cerramiento también llevan su longitud (su
# concreto es su claro) y una zapata y un muro de concreto su peralte o su altura: el diseño los
# pide y el modelo los trae.
CRITICOS: dict[str, tuple[str, ...]] = {
    "castillo": ("seccion_cm", "altura_m", "longitudinales", "estribos"),
    "columna": ("seccion_cm", "altura_m", "longitudinales", "estribos"),
    "trabe": ("seccion_cm", "longitud_m", "longitudinales", "estribos"),
    "contratrabe": ("seccion_cm", "longitud_m", "longitudinales", "estribos"),
    "pilote": ("seccion_cm", "longitud_m", "longitudinales", "estribos"),
    "zapata": ("seccion_cm", "altura_m", "parrillas"),
    # Tarea 15b: un dado lleva sus lados en planta, su altura (la de su corte) y su armado de
    # columna corta: varillas verticales y estribos (diseño §4.1: «plan dimensions · peralte ·
    # verticals · stirrups»).
    "dado": ("seccion_cm", "altura_m", "longitudinales", "estribos"),
    "muro_concreto": ("seccion_cm", "altura_m", "longitud_m", "parrillas"),
    "dala": ("seccion_cm", "longitud_m", "longitudinales", "estribos"),
    "cerramiento": ("seccion_cm", "longitud_m", "longitudinales", "estribos"),
}

_NOMBRE: dict[str, str] = {
    "seccion_cm": "la sección",
    "altura_m": "la altura",
    "longitud_m": "la longitud",
    "longitudinales": "las varillas longitudinales",
    "estribos": "los estribos",
    "parrillas": "las parrillas",
    "recubrimiento_m": "el recubrimiento",
}
_CORTO: dict[str, str] = {
    "seccion_cm": "sección",
    "altura_m": "altura",
    "longitud_m": "longitud",
    "longitudinales": "varillas longitudinales",
    "estribos": "estribos",
    "parrillas": "parrillas",
    "recubrimiento_m": "recubrimiento",
}
_ARMADO = ("longitudinales", "estribos", "parrillas")
_GEOMETRIA = ("seccion_cm", "altura_m", "longitud_m")
_CON_ALTURA = frozenset({"castillo", "columna"})
# Las fuentes que leen el plano (o lo decide alguien): ni la IA ni el supuesto de Klave.
_LEIDAS = frozenset(PRECEDENCIA) - {"ia", "supuesto"}
# Un texto del plano está junto a la colocación de su marca si su caja no se aparta de la de la
# detección más que esto, en altos de su letra (una etiqueta repetida del mismo elemento).
_JUNTO_A_SU_COLOCACION = 10.0
# Una colocación sin marca está junto a un texto de marca si no se aparta más que esto, en altos.
_JUNTO_SIN_MARCA = 5.0
# Lo que se cita de un grupo grande, como ejemplo; todos sus handles van en ``textos``.
_EJEMPLOS = 12
# Una lectura IA de un detalle: los textos sin dueño cuyo título más cercano es el de su marca, a
# lo más esto en altos del título.
_ALCANCE_DEL_TITULO = 60.0
# El título de un corte («SECCIÓN 1») lleva su armado apilado: a lo más esto en altos, en su
# columna.
_ALCANCE_DEL_CORTE = 4.0
_FAMILIA_EN_TITULO = re.compile(
    r"^(?:(?:DADO|PILOTE|PILA|MURO|TRABE|CASTILLO|COLUMNA|CONTRATRABE|ZAPATA|DALA|CADENA|"
    r"CERRAMIENTO)S?\s+(?:DE\s+CONCRETO\s+)?)+"
)
_SOLO_CIFRAS = re.compile(r"^[\d.,\s]+$")
# Una ficha de un título: lo que puede ser el nombre de una marca («MC-C», «CM-1», «D-4A»).
_FICHA = re.compile(r"[A-Z0-9][A-Z0-9.\-]*[A-Z0-9]|[A-Z0-9]")
_COTAS_CERCANAS = re.compile(r"las cotas cercanas \(([^)]*)\) no se toman \(([^)]*)\)")


class Verificacion(BaseModel):
    """Un hallazgo del propio plano. ``id``: estable (sha1 del número, la marca, la hoja y la
    clave del hallazgo, 12 hex). ``marcas`` y ``elementos`` (``element_id``) son lo que toca;
    ``datos``, los valores en juego con su fuente; ``hoja`` y ``bbox``, dónde verlo (vacíos si es
    de toda una marca en varias hojas). ``campo`` es el dato del que trata (si trata de uno),
    ``textos`` los handles del plano que cita y ``en_juego`` lo que depende de él: ``acero_kg``
    (con desperdicio) y ``concreto_m3`` cuando hay cifra (lo que pesa o mide el dato en duda, o
    lo que cambia entre los valores que el plano dice), ``volumen_m3`` cuando no la hay (el
    concreto de las piezas a las que les falta el dato: de qué tamaño es lo que falta) y
    ``piezas``. ``cantidad`` dice si lo que está en juego tiene cifra (``conocida``), no la tiene
    (``desconocida``: lo que falta no se puede medir del plano) o es una cota que el plano permite
    (``estimada``)."""

    id: str
    numero: int
    severidad: Severidad
    mensaje: str
    marcas: list[str] = Field(default_factory=list)
    elementos: list[str] = Field(default_factory=list)
    datos: list[Dato] = Field(default_factory=list)
    hoja: str = ""
    bbox: BBox | None = None
    campo: str = ""
    textos: list[str] = Field(default_factory=list)
    en_juego: dict[str, float] = Field(default_factory=dict)
    cantidad: Literal["conocida", "desconocida", "estimada"] = "conocida"


def id_de_verificacion(numero: int, marca: str, hoja: str, clave: str) -> str:
    """El id estable de un hallazgo: sha1 de su número, su marca, su hoja y su clave — la
    identidad estable de lo que trata (su campo, o el nombre de la familia o la clase en los de
    familia o de hoja), nunca un texto del detalle, una cuenta ni el juego de campos que hoy
    junta —, sus primeros 12 hex. Las decisiones (Tarea 12) se guardan con él."""
    llave = "\x1f".join((str(numero), marca, hoja, clave))
    return hashlib.sha1(llave.encode("utf-8")).hexdigest()[:12]


def _hallazgo(
    numero: int,
    severidad: Severidad,
    mensaje: str,
    *,
    clave: str,
    marca: str = "",
    hoja: str = "",
    de_la_marca: bool = False,
    marcas: Iterable[str] = (),
    elementos: Iterable[str] = (),
    datos: Iterable[Dato] = (),
    bbox: BBox | None = None,
    campo: str = "",
    textos: Iterable[str] = (),
    en_juego: dict[str, float] | None = None,
    cantidad: Literal["conocida", "desconocida", "estimada"] = "conocida",
) -> Verificacion:
    """Un hallazgo. ``de_la_marca``: es de toda una marca (o una familia: todas sus colocaciones,
    en las hojas que sean), así que su id no lleva hoja aunque ``hoja`` diga la única en que
    está: una colocación más en otra hoja no le cambia el id."""
    lista_marcas = list(dict.fromkeys([*([marca] if marca else []), *marcas]))
    return Verificacion(
        id=id_de_verificacion(numero, marca, "" if de_la_marca else hoja, clave),
        numero=numero,
        severidad=severidad,
        mensaje=al_lenguaje_del_plano(mensaje),
        marcas=lista_marcas,
        elementos=list(dict.fromkeys(elementos)),
        datos=[d.model_copy(deep=True) for d in datos],
        hoja=hoja,
        bbox=bbox,
        campo=campo,
        textos=list(dict.fromkeys(textos)),
        en_juego={k: round(v, 4) for k, v in (en_juego or {}).items() if v},
        cantidad=cantidad,
    )


# Lo que el motor escribe de sus lecturas («T3-8 · sección dibujada no encontrada», «… se lee en
# E3») dicho como lo diría la oficina: ningún mensaje lleva cadenas del motor ni códigos de etapa.
_DEL_MOTOR: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(patron), reemplazo)
    for patron, reemplazo in (
        (
            r"«IA · hoja ([\w.-]+): ([^«»]*?)(?: · «([^«»]*)»)?»",
            r"la lectura IA de \1 («\2»)",
        ),
        (r"IA · hoja ([\w.-]+): ([^«»·;]*)", r"la lectura IA de \1 («\2»)"),
        (r"IA · hoja ([\w.-]+)", r"la lectura IA de \1"),
        (
            r"«?([A-Z][\w.-]*(?: \([^()«»]*\))?) · sección dibujada no encontrada»?",
            r"el detalle de \1 (su sección dibujada no se pudo leer)",
        ),
        (
            r"«?([A-Z][\w.-]*) · sección dibujada (compartida|dudosa)»?",
            r"el detalle de \1 (su sección dibujada, \2, no se pudo leer)",
        ),
        (
            r"«?([A-Z][^«»·;]*?) · señalada por flecha; se lee en E\d»?",
            r"el detalle de \1 (su sección la señala una flecha, por leer)",
        ),
        (
            r"«?([A-Z][\w.-]*) · par de cotas (\S+) sin contorno cerrado \(\d de 4 aristas "
            r"dibujadas\)»?",
            r"\2 acotada en el detalle de \1",
        ),
        (r"«?([A-Z][\w.-]*) · cotas de su sección (\S+)»?", r"\2 acotada en el detalle de \1"),
        (
            r"«?([A-Z][\w.-]*) · sección 1 (\S+), sección 2 (\S+) \(se toma la mayor\)»?",
            r"los cortes «SECCIÓN 1» \2 y «SECCIÓN 2» \3 de \1",
        ),
        (
            r"«?([A-Z][\w.-]*) · recubrimiento de ([\d.]+) cm acotado en las esquinas de su "
            r"sección»?",
            r"\2 cm acotados en las esquinas de la sección de \1",
        ),
        (r"«([A-Z][\w.-]*) · ([^«»·]+?) · bajo su sección»", r"«\2» bajo la sección de \1"),
        (r"«([A-Z][\w.-]*) · ([^«»·]*[#@][^«»·]*)»", r"«\2» de \1"),
        (r"sección dibujada no encontrada", "su sección dibujada no se pudo leer"),
        (r"la lectura IA la lectura IA de", "la lectura IA de"),
        # El nombre de una vista como lo junta el motor («ES-300 · ESTRUCTURA DE ROOF GARDEN»).
        (r"\b([A-Z]{1,3}-\d{3}) · ", r"\1, "),
        (r"; se lee en E\d", ", por leer"),
        (r"se lee en E\d", "queda por leer"),
    )
)


def al_lenguaje_del_plano(texto: str) -> str:
    """El mensaje sin cadenas internas del motor ni códigos de etapa: las notas de una lectura
    («K-1 · par de cotas 30x80 sin contorno cerrado …») dichas como las diría la oficina, y los
    renglones de una pila separados como textos («4#3», «E#2@15»)."""
    for patron, reemplazo in _DEL_MOTOR:
        texto = patron.sub(reemplazo, texto)
    # Un número con más de dos decimales es una medida del motor, no del plano: al décimo.
    texto = re.sub(
        r"(?<![\w.])(\d+\.\d{3,})(?![\w.])", lambda m: f"{round(float(m.group(1)), 1):g}", texto
    )
    texto = texto.replace("\n", " ")
    return re.sub(
        r"«([^«»]*?) / ([^«»]*?)»",
        r"«\1», «\2»",
        re.sub(r"«([^«»]*?) / ([^«»]*?) / ([^«»]*?)»", r"«\1», «\2», «\3»", texto),
    )


# ------------------------------------------------------------------------------- el contexto


def _handle_de(e: NormalizedEntity) -> str:
    """El handle con que se busca un texto en el CAD: el suyo, o el del bloque que lo trae
    («A7A6D#199», el texto 199 dentro del bloque A7A6D, se busca como A7A6D)."""
    return (e.raw_handle or e.entity_id).split("#", 1)[0]


@dataclass
class _Contexto:
    """Lo que todas las verificaciones consultan, calculado una vez."""

    por_marca: dict[str, Definicion]
    por_familia: dict[str, Definicion]
    elementos: list[Elemento]
    reglas: Reglas
    inv: ScheduleInventory
    entidades: dict[str, NormalizedEntity]
    detections: list[Detection]
    segmentation: SheetSegmentation | None
    frames: list[SheetFrame]
    config: TextPatternConfig
    anclaje_m: float
    desperdicio: float
    factor: float | None = None  # metros por unidad del dibujo
    _reglas: dict[str, Reglas] = field(default_factory=dict)
    _acero: dict[str, float] = field(default_factory=dict)
    deteccion: dict[str, Detection] = field(default_factory=dict)
    en_planta: set[str] | None = None
    de_armado: list[NormalizedEntity] | None = None
    # Calculados una vez (Tarea 12: el tiempo del pipeline): las frases de las notas sobre la
    # longitud de los pilotes y las cotas con valor de lado de sección, por archivo.
    notas_de_pilotes: list[str] | None = None
    cotas_de_lado: dict[str, list[tuple[float, NormalizedEntity]]] | None = None

    def __post_init__(self) -> None:
        self.deteccion = {d.detection_id: d for d in self.detections}

    def reglas_de(self, hoja: str) -> Reglas:
        if hoja not in self._reglas:
            self._reglas[hoja] = self.reglas.para(hoja)
        return self._reglas[hoja]

    def acero(self, e: Elemento) -> float:
        """El acero del elemento (kg, con desperdicio), como lo pesa la etapa del acero."""
        if e.element_id not in self._acero:
            self._acero[e.element_id] = self.acero_de(e)
        return self._acero[e.element_id]

    def acero_de(self, e: Elemento) -> float:
        try:
            a = acero_elemento(e, self.reglas_de(e.hoja), self.anclaje_m)
        except (ValueError, TypeError):
            return 0.0
        return a.total_kg() * (1 + self.desperdicio) if a is not None else 0.0

    def handle(self, entidad_id: str) -> str:
        e = self.entidades.get(entidad_id)
        return _handle_de(e) if e is not None else entidad_id

    def cita(self, entidad_id: str, texto: str | None = None) -> str:
        e = self.entidades.get(entidad_id)
        escrito = texto if texto is not None else (e.text if e is not None and e.text else "")
        return f"«{_una_linea(escrito)}» {self.handle(entidad_id)}"

    def hoja_de(self, e: NormalizedEntity) -> str:
        """El código del marco más chico de su archivo que contiene el texto; su archivo sin
        marcos (como las reglas y las definiciones)."""
        centro = bbox_center(e.bbox)
        dentro = [
            f for f in self.frames if f.source_file in ("", e.source_file) and f.contains(centro)
        ]
        if not dentro:
            return e.source_file
        marco = min(dentro, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        return marco.code or marco.frame_id


def verificar(
    por_marca: dict[str, Definicion],
    por_familia: dict[str, Definicion],
    elementos: list[Elemento],
    reglas: Reglas,
    inv: ScheduleInventory,
    entities: list[NormalizedEntity],
    detections: list[Detection],
    segmentation: SheetSegmentation | None,
    *,
    frames: list[SheetFrame] | None = None,
    config: TextPatternConfig | None = None,
    anclaje_m: float | None = None,
    desperdicio: float | None = None,
    meters_factor: float | None = None,
) -> list[Verificacion]:
    """Las verificaciones del propio plano (ver el docstring del módulo), ordenadas: primero lo
    que bloquea, luego las dudas, luego los avisos; dentro de cada severidad, por lo que está en
    juego (``ordenar``). ``anclaje_m`` y ``desperdicio`` son los de la etapa del acero (los de
    ``SteelAssumptions`` si no se dan): con ellos se pesa lo que está en juego.
    ``meters_factor`` (metros por unidad del dibujo) mide lo que se estima del dibujo (el largo de
    un muro sin elemento); sin él se toma la unidad del dibujo por metro."""
    supuestos = SteelAssumptions()
    ctx = _Contexto(
        por_marca=por_marca,
        por_familia=por_familia,
        elementos=elementos,
        reglas=reglas,
        inv=inv,
        entidades={e.entity_id: e for e in entities},
        detections=detections,
        segmentation=segmentation,
        frames=frames or [],
        config=config or TextPatternConfig(),
        anclaje_m=supuestos.anchorage_m if anclaje_m is None else anclaje_m,
        desperdicio=supuestos.waste_pct / 100 if desperdicio is None else desperdicio,
        factor=meters_factor,
    )
    titulos = _titulos_dibujados(ctx)
    nervadura = _marcas_de_nervadura(ctx, titulos)
    de_acero = {n for n, ts in titulos.items() if all(t.clase == "acero" for t in ts)}
    # Un nombre que el plano sólo titula solo (sin palabra de familia) y que es de la familia de
    # letras de las nervaduras escritas en planta («X1» junto a X0…X7) también es de la losa.
    letras = {m.group(0) for n in nervadura if (m := re.match(r"[A-Z]+", n))}
    de_la_losa = {
        n
        for n, ts in titulos.items()
        if (m := re.match(r"[A-Z]+(?=-?\d)", n)) is not None
        and m.group(0) in letras
        and not any(
            _TITULO_CON_FAMILIA.search(_una_linea(t.entidad.text or "").upper()) for t in ts
        )
        and not any(e.marca == n for e in ctx.elementos)
    }
    ajenas = set(nervadura) | de_acero | de_la_losa  # no son de esta lectura: tienen su aviso
    escritas = _marcas_escritas_en_planta(ctx, titulos, ajenas)
    hallazgos: list[Verificacion] = []
    hallazgos += _sin_definir(ctx)
    hallazgos += _sin_colocar(ctx, escritas, titulos, ajenas)
    hallazgos += _escritas_sin_elemento(ctx, escritas, titulos)
    hallazgos += _detectadas_fuera(ctx)
    hallazgos += _nervaduras(ctx, nervadura)
    hallazgos += _de_acero(ctx, titulos)
    criticos = _criticos(ctx)
    hallazgos += _contradicciones(ctx, ajenas)
    hallazgos += _juntar_por_marca(ctx, criticos, _sin_dueno(ctx), ajenas)
    hallazgos = _plegar_en_su_hallazgo(hallazgos, nervadura, ctx.config)
    return ordenar(_referencias_cruzadas(hallazgos), _totales(ctx))


def _plegar_en_su_hallazgo(
    hallazgos: list[Verificacion],
    nervadura: dict[str, list[NormalizedEntity]],
    config: TextPatternConfig,
) -> list[Verificacion]:
    """R234: lo que la verificación 11 dice de una marca va en el hallazgo que ya la trata: el de
    una marca de losa nervada («Z1», la marca «Z-1»), en el aviso de su familia (nunca un hallazgo
    estructural); el de una marca escrita en planta sin elemento, en ese hallazgo de la
    verificación 10."""
    por_id = {v.id: i for i, v in enumerate(hallazgos)}
    salida = list(hallazgos)
    quitar: set[int] = set()
    for i, v in enumerate(hallazgos):
        if v.numero != 11 or len(v.marcas) < 1:
            continue
        base = v.marcas[0].split(" (", 1)[0]
        if v.id != id_de_verificacion(11, base, "", ""):
            continue  # sólo el hallazgo de una marca (no los de una hoja o una clase)
        if base in nervadura or normalizar_marca(base, config) in nervadura:
            letra = m.group(0) if (m := re.match(r"[A-Z]+", base)) else base
            destino = por_id.get(id_de_verificacion(10, "", "", f"nervaduras: {letra}"))
        else:
            destino = por_id.get(id_de_verificacion(10, base, "", "escrita en planta sin elemento"))
        if destino is None:
            continue
        w = salida[destino]
        salida[destino] = w.model_copy(
            update={
                "mensaje": f"{w.mensaje} Además, de {base}: {v.mensaje}",
                "textos": list(dict.fromkeys([*w.textos, *v.textos])),
                "datos": [*w.datos, *v.datos][:8],
            }
        )
        quitar.add(i)
    return [v for i, v in enumerate(salida) if i not in quitar]


def ordenar(
    hallazgos: list[Verificacion], totales: dict[str, float] | None = None
) -> list[Verificacion]:
    """Por severidad y, dentro de ella, por lo que está en juego (``banda``): primero lo que pesa
    al menos 1 % del acero o del concreto de toda la estructura (``totales``: ``acero_kg`` y
    ``concreto_m3``), luego lo que no tiene cifra (``cantidad`` desconocida o sólo estimada: lo que
    falta no se puede medir, nunca por debajo de un hallazgo chico con cifra), luego lo demás;
    dentro de cada banda por ``peso`` (en la de sin cifra, por cuántas piezas y textos toca); a
    igual peso, por número, marca, hoja e id."""
    totales = totales or {}
    return sorted(
        hallazgos,
        key=lambda v: (
            _RANGO_DE_SEVERIDAD[v.severidad],
            *banda(v, totales),
            v.numero,
            v.marcas[:1],
            v.hoja,
            v.id,
        ),
    )


# Lo que pesa al menos esto del acero o del concreto de la estructura va primero.
_PESO_GRANDE = 0.01


def banda(v: Verificacion, totales: dict[str, float]) -> tuple[int, float, float]:
    """(banda, orden dentro de ella, desempate) de un hallazgo por lo que está en juego: 0 lo que
    se sabe y pesa al menos ``_PESO_GRANDE``; 1 lo que no tiene cifra (cantidad desconocida o una
    cota medida, R227, R232), por su tamaño (``tamano``); 2 lo demás. Nunca por cuántos textos
    cita."""
    piezas = -v.en_juego.get("piezas", 0.0)
    if v.cantidad != "conocida":
        return (1, -tamano(v), piezas)
    p = peso(v, totales)
    return (0 if p >= _PESO_GRANDE else 2, -p, piezas)


def tamano(v: Verificacion) -> float:
    """R233: el tamaño de lo que no tiene cifra: el concreto de sus piezas (o la cota medida de un
    muro); para lo que no tiene largo (los pilotes), su sección por las piezas, el concreto por
    metro."""
    return max(
        v.en_juego.get("volumen_m3", 0.0),
        v.en_juego.get("concreto_m3", 0.0),
        v.en_juego.get("concreto_por_metro_m3", 0.0),
    )


def peso(v: Verificacion, totales: dict[str, float]) -> float:
    """Lo que está en juego en un hallazgo como fracción de lo de toda la estructura: la mayor
    entre su acero y su concreto (sin precios: las cantidades, cada una contra su total) — o, si
    lo que falta no tiene cifra, el concreto de las piezas a las que les falta —; las piezas sólo
    desempatan."""
    partes = [
        v.en_juego.get(unidad, 0.0) / total
        for unidad, total in totales.items()
        if total > 0 and unidad != "piezas"
    ]
    concreto = totales.get("concreto_m3", 0.0)
    if concreto > 0:
        partes.append(v.en_juego.get("volumen_m3", 0.0) / concreto)
    return max(partes, default=0.0) + 1e-9 * v.en_juego.get("piezas", 0.0)


def _totales(ctx: "_Contexto") -> dict[str, float]:
    """El acero (con desperdicio) y el concreto de todos los elementos: contra ellos se pesa lo
    que está en juego en cada hallazgo."""
    return {
        "acero_kg": sum(ctx.acero(e) for e in ctx.elementos),
        "concreto_m3": sum(_volumen(e) or 0.0 for e in ctx.elementos),
    }


# ----------------------------------------------------------------------------------- valores


def _una_linea(texto: str) -> str:
    return " ".join((texto or "").split())


def _numero(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    return float(v)


def _cm(v: float) -> str:
    return f"{v:g}"


def _valor(campo: str, valor: Any) -> str:
    """Un valor como lo diría el plano: «20x40 cm», «3.2 m», «4#5+2#4», «2E#3 EXT@10 CENTRO@20»."""
    if valor is None:
        return "sin valor"
    try:
        if campo == "seccion_cm":
            if isinstance(valor, dict) and _numero(valor.get("area_cm2")) is not None:
                return f"no rectangular de {round(float(valor['area_cm2'])):g} cm²"
            if isinstance(valor, list | tuple) and len(valor) == 2:
                return f"{_cm(float(valor[0]))}x{_cm(float(valor[1]))} cm"
        if campo in ("altura_m", "longitud_m") and _numero(valor) is not None:
            return f"{float(valor):g} m"
        if campo == "recubrimiento_m" and _numero(valor) is not None:
            return f"{float(valor) * 100:g} cm"
        if campo == "longitudinales" and isinstance(valor, list):
            return texto_longitudinal(Armado(longitudinales=_grupos(valor))) or "ninguna"
        if campo == "estribos" and isinstance(valor, list):
            return texto_estribos(Armado(estribos=_juegos(valor))) or "ninguno"
        if campo == "parrillas" and isinstance(valor, list):
            return texto_parrillas(Armado(parrillas=_parrillas(valor))) or "ninguna"
    except (ValueError, TypeError):
        pass
    return str(valor)


def _grupos(valor: Any) -> list[GrupoVarillas]:
    return [GrupoVarillas.model_validate(g) for g in valor or []] if isinstance(valor, list) else []


def _juegos(valor: Any) -> list[JuegoEstribos]:
    return [JuegoEstribos.model_validate(j) for j in valor or []] if isinstance(valor, list) else []


def _parrillas(valor: Any) -> list[Parrilla]:
    return [Parrilla.model_validate(p) for p in valor or []] if isinstance(valor, list) else []


def _llave_de_valor(valor: Any) -> str:
    """El valor como clave: el mismo antes y después de pasar por JSON (R1)."""

    def volcar(objeto: Any) -> Any:
        if isinstance(objeto, BaseModel):
            return objeto.model_dump(mode="json")
        return repr(objeto)

    try:
        return json.dumps(valor, sort_keys=True, default=volcar)
    except (TypeError, ValueError):
        return repr(valor)


def _area_m2(valor: Any) -> float | None:
    if isinstance(valor, dict):
        area = _numero(valor.get("area_cm2"))
        return area / 10_000 if area is not None and area > 0 else None
    if isinstance(valor, list | tuple) and len(valor) == 2:
        a, b = _numero(valor[0]), _numero(valor[1])
        if a is not None and b is not None and a > 0 and b > 0:
            return a * b / 10_000
    return None


def _largo_m(e: Elemento) -> float | None:
    """La dimensión con la que se cuenta el concreto de un elemento: su altura (castillo,
    columna, zapata: su peralte), su longitud (vigas, pilotes)."""
    dato = e.altura_m if e.familia in (*_CON_ALTURA, "zapata") else e.longitud_m
    valor = _numero(dato.valor) if dato is not None else None
    return valor if valor is not None and valor > 0 else None


def _volumen(e: Elemento, seccion: Any = None, largo: float | None = None) -> float | None:
    """El concreto del elemento (m³) con su sección y su largo (o los que se den). Un muro: su
    espesor (el lado menor de su sección) por su altura y su longitud."""
    valor = seccion if seccion is not None else (e.seccion_cm.valor if e.seccion_cm else None)
    if e.familia == "muro_concreto":
        lados = valor if isinstance(valor, list | tuple) and len(valor) == 2 else None
        espesor = min(float(v) for v in lados) / 100 if lados else None
        alto = _numero(e.altura_m.valor) if e.altura_m is not None else None
        largo_muro = _numero(e.longitud_m.valor) if e.longitud_m is not None else None
        if espesor and alto and largo_muro:
            return espesor * alto * largo_muro
        return None
    area = _area_m2(valor)
    largo = largo if largo is not None else _largo_m(e)
    if area is None or largo is None:
        return None
    return area * largo


def _nombre_de_hoja(hoja: str) -> str:
    """El código de la hoja; sin marcos, el nombre del archivo (sin su carpeta)."""
    return hoja.rsplit("/", 1)[-1] if hoja else "sin hoja"


def _nombres_de_hojas(hojas: Iterable[str]) -> str:
    return ", ".join(dict.fromkeys(_nombre_de_hoja(h) for h in hojas))


def _hojas(elementos: Iterable[Elemento]) -> str:
    cuenta = Counter(_nombre_de_hoja(e.hoja) for e in elementos)
    return ", ".join(f"{h} ({n})" if n > 1 else h for h, n in sorted(cuenta.items()))


def _pzas(n: int) -> str:
    return f"{n} pieza{'s' if n != 1 else ''}"


def _colocaciones(n: int) -> str:
    return "1 colocación" if n == 1 else f"{n} colocaciones"


def _veces(n: int) -> str:
    return "una vez" if n == 1 else f"{n} veces"


def _listar(partes: list[str]) -> str:
    partes = [p for p in partes if p]
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _caja(cajas: Iterable[BBox | None]) -> BBox | None:
    lista = [c for c in cajas if c is not None]
    if not lista:
        return None
    return (
        min(c[0] for c in lista),
        min(c[1] for c in lista),
        max(c[2] for c in lista),
        max(c[3] for c in lista),
    )


def _hueco(a: BBox, b: BBox) -> float:
    dx = max(a[0] - b[2], 0.0, b[0] - a[2])
    dy = max(a[1] - b[3], 0.0, b[1] - a[3])
    return math.hypot(dx, dy)


def _caja_de(ctx: _Contexto, elementos: list[Elemento]) -> BBox | None:
    return _caja(
        ctx.deteccion[e.detection_id].bbox for e in elementos if e.detection_id in ctx.deteccion
    )


def _hoja_unica(elementos: list[Elemento]) -> str:
    hojas = {e.hoja for e in elementos}
    return next(iter(hojas)) if len(hojas) == 1 else ""


def _etiqueta(ctx: _Contexto, e: Elemento) -> str:
    """El handle de la etiqueta de la colocación (su primera entidad)."""
    d = ctx.deteccion.get(e.detection_id)
    if d is None or not d.source_entities:
        return e.element_id
    return ctx.handle(d.source_entities[0])


def _por_marca(elementos: Iterable[Elemento]) -> dict[str, list[Elemento]]:
    grupos: dict[str, list[Elemento]] = defaultdict(list)
    for e in elementos:
        grupos[e.marca].append(e)
    return grupos


# ------------------------------------------------------------------- 1: colocada sin definir


def _sin_definir(ctx: _Contexto) -> list[Verificacion]:
    salida: list[Verificacion] = []
    grupos: dict[tuple[str, str, str], list[Elemento]] = defaultdict(list)
    sin_marca: dict[str, list[Elemento]] = defaultdict(list)
    for e in ctx.elementos:
        if not e.marca:
            sin_marca[e.familia].append(e)
        elif e.definicion != "marca":
            grupos[(e.marca, e.familia, e.definicion)].append(e)
    for (marca, familia, definicion), els in sorted(grupos.items()):
        juego = {
            "acero_kg": sum(ctx.acero(e) for e in els),
            "concreto_m3": sum(_volumen(e) or 0.0 for e in els),
            "piezas": float(len(els)),
        }
        donde = f"{_pzas(len(els))} en {_hojas(els)}"
        if definicion == "ninguna":
            usa = _lo_que_usa(els[0])
            salida.append(
                _hallazgo(
                    1,
                    "bloquea",
                    f"{marca} está colocada en planta ({donde}) y el plano no la define: ningún "
                    f"cuadro, detalle ni nota general de la familia {familia} la describe. {usa}",
                    clave="sin definición",
                    marca=marca,
                    hoja=_hoja_unica(els),
                    de_la_marca=True,
                    elementos=[e.element_id for e in els],
                    bbox=_caja_de(ctx, els) if _hoja_unica(els) else None,
                    en_juego=juego,
                )
            )
            continue
        nota = ctx.por_familia.get(familia)
        textos = sorted(
            {
                d.texto
                for campo in ("seccion_cm", *_ARMADO)
                if nota is not None and (d := getattr(nota, campo)) is not None and d.texto
            }
        )
        dice = f" («{'»; «'.join(textos)}»)" if textos else ""
        salida.append(
            _hallazgo(
                1,
                "duda",
                f"{marca} está colocada en planta ({donde}) y no está definida en el plano; se "
                f"usa la nota general de la familia {familia}{dice}. Confirma que esa nota es "
                "la suya.",
                clave="sin definición, con nota general",
                marca=marca,
                hoja=_hoja_unica(els),
                de_la_marca=True,
                elementos=[e.element_id for e in els],
                datos=[
                    d
                    for campo in ("seccion_cm", *_ARMADO)
                    if nota is not None and (d := getattr(nota, campo)) is not None
                ],
                bbox=_caja_de(ctx, els) if _hoja_unica(els) else None,
                en_juego=juego,
            )
        )
    for familia, els in sorted(sin_marca.items()):
        faltan = []
        for campo in CRITICOS.get(familia, ()):
            vacios = sum(1 for e in els if _sin_valor(getattr(e, campo)))
            supuestos = sum(
                1 for e in els if (d := getattr(e, campo)) is not None and d.fuente == "supuesto"
            )
            if vacios:
                faltan.append(f"{_CORTO[campo]} en {vacios}")
            if supuestos:
                faltan.append(f"{_CORTO[campo]} supuesta en {supuestos}")
        definida = any(e.definicion == "familia" for e in els)
        usa = (
            f"usan la definición general de la familia {familia}"
            if definida
            else f"no hay definición de la familia {familia}"
        )
        falta = f"; les falta: {_listar(faltan)}" if faltan else ""
        salida.append(
            _hallazgo(
                1,
                "aviso",
                f"{len(els)} colocaciones de {familia} sin marca en planta ({_hojas(els)}): "
                f"ninguna se junta con la definición de una marca; {usa}{falta}. Etiquetas: "
                f"{', '.join(_etiqueta(ctx, e) for e in els)}.",
                clave=f"sin marca: {familia}",
                hoja=_hoja_unica(els),
                de_la_marca=True,
                elementos=[e.element_id for e in els],
                bbox=_caja_de(ctx, els) if _hoja_unica(els) else None,
                en_juego={
                    "concreto_m3": sum(_volumen(e) or 0.0 for e in els),
                    "piezas": float(len(els)),
                },
            )
        )
    return salida


def _sin_valor(dato: Dato | None) -> bool:
    return dato is None or dato.valor is None


def _lo_que_usa(e: Elemento) -> str:
    """Lo que el elemento usa sin definición: su sección (supuesta o medida) y si tiene armado."""
    partes = []
    if e.seccion_cm is not None and e.seccion_cm.valor is not None:
        de = "supuesta" if e.seccion_cm.fuente == "supuesto" else e.seccion_cm.fuente
        partes.append(f"Se usa la sección {_valor('seccion_cm', e.seccion_cm.valor)} ({de})")
    else:
        partes.append("No tiene sección")
    if all(_sin_valor(getattr(e, c)) for c in _ARMADO):
        partes.append("no tiene armado: su acero no se cuenta")
    return "; ".join(partes) + "."


# ------------------------------------------------------------ las marcas escritas en planta


@dataclass
class _Escrita:
    entidad: NormalizedEntity
    marca: str
    hoja: str
    junto_sin_marca: list[str]  # las familias de las colocaciones sin marca junto a él


def _marcas_escritas_en_planta(
    ctx: _Contexto, titulos: dict[str, list["_Titulo"]], ajenas: set[str]
) -> dict[str, list[_Escrita]]:
    """Los textos de una planta estructural que son una marca (con o sin su palabra de familia
    delante: «DADO D-1», «P-4»), que ninguna detección tomó, que no son etiquetas de cuadro ni
    títulos, y junto a los que no hay ninguna detección de esa marca: por marca normalizada. Una
    marca es lo que la gramática lee como marca, el nombre de una definición o un nombre que el
    plano titula en un dibujo de concreto (R222: «MURO DE CONCRETO MC-A», sin la gramática ni la
    IA). Las marcas de nervaduras y de acero (``ajenas``) no son de esta cuenta: tienen su aviso."""
    seg = ctx.segmentation
    if seg is None:
        return {}
    plantas = [v for v in seg.structural_plan_views() if v.bbox is not None]
    if not plantas:
        return {}
    usadas = {i for d in ctx.detections for i in d.source_entities}
    de_cuadro = set(ctx.inv.cuadro_mark_entities) | set(ctx.inv.titulos_de_detalle)
    conocidas = {k for k in ctx.por_marca if not _SOLO_CIFRAS.match(k)} | {
        n for n, ts in titulos.items() if any(t.clase == "concreto" for t in ts)
    }
    por_marca: dict[str, list[Detection]] = defaultdict(list)
    sin_marca: list[Detection] = []
    for d in ctx.detections:
        if d.family not in FAMILIAS_ESTRUCTURALES:
            continue
        if d.mark.strip():
            por_marca[normalizar_marca(d.mark, ctx.config)].append(d)
        else:
            sin_marca.append(d)
    salida: dict[str, list[_Escrita]] = defaultdict(list)
    for e in ctx.entidades.values():
        if not e.is_textual or not e.text or e.entity_id in usadas or e.entity_id in de_cuadro:
            continue
        marca = _marca_del_texto(e.text, ctx.config, conocidas)
        if marca is None or marca in ajenas:
            continue
        if not _en_planta(ctx, e):
            continue
        alto = alto_de_texto(e)
        if any(
            d.evidence.source in ("", e.source_file)
            and _hueco(d.bbox, e.bbox) <= _JUNTO_A_SU_COLOCACION * alto
            for d in por_marca.get(marca, [])
        ):
            continue
        junto = sorted(
            {
                d.family
                for d in sin_marca
                if d.evidence.source in ("", e.source_file)
                and _hueco(d.bbox, e.bbox) <= _JUNTO_SIN_MARCA * alto
            }
        )
        salida[marca].append(_Escrita(e, marca, ctx.hoja_de(e), junto))
    return salida


def _marca_del_texto(texto: str, config: TextPatternConfig, conocidas: set[str]) -> str | None:
    """La marca si el texto entero es una marca (tras su palabra de familia, si la lleva)."""
    limpio = _FAMILIA_EN_TITULO.sub("", " ".join(texto.upper().split())).strip()
    if not limpio or _SOLO_CIFRAS.match(limpio):
        return None
    normal = marca_normalizada(limpio, config)
    if normal is not None:
        return normal
    escrito = normalizar_marca(limpio, config)
    return escrito if escrito in conocidas else None


# ----------------------------------------------------- lo que el plano titula (sin la gramática)

# Un título dibujado: una palabra de familia y el nombre de lo que define («MURO DE CONCRETO MC-A»,
# «DADO D-3A», «COLUMNA CM-1», «CONEXIÓN CN-A», «PLACA PL-A», «VIGA V-E», «NERVADURA Z5»). El nombre
# lleva una cifra o un guion: «MURO BAJO», «PILOTE NO» no son nombres.
_TITULO_CON_FAMILIA = re.compile(
    r"(?<![A-ZÁÉÍÓÚÑ])(DADOS?|MUROS?(?:\s+DE\s+(?:CONCRETO|CONTENCI[OÓ]N))?|COLUMNAS?"
    r"(?:\s+MET[AÁ]LICAS?)?|CASTILLOS?|CONTRATRABES?|TRABES?|PILOTES?|ZAPATAS?|DALAS?|CADENAS?"
    r"(?:\s+DE\s+[A-ZÁÉÍÓÚ]+)?|CERRAMIENTOS?|PLACAS?(?:\s+BASE)?|CONEXI[OÓ]N(?:ES)?|VIGAS?|"
    r"NERVADURAS?)\s+(?:TIPO\s+)?([A-Z]{1,4}\d{0,2}-?[0-9A-Z]{1,3}'?)(?![A-Z0-9-])"
)
# El nombre solo, en la capa de los detalles («D-C», «Z2»), o con lo que es su vista («D-3A PLANTA»,
# «D-4A CORTE X-X'»).
_NOMBRE_SOLO = re.compile(
    r"^([A-Z]{1,4}\d{0,2}-?[0-9A-Z]{1,3}'?)(?:\s+(?:PLANTA|CORTE|ELEVACI[OÓ]N|SECCI[OÓ]N)\b.*)?$"
)
_DE_ACERO = re.compile(r"^(PLACA|CONEXI[OÓ]N|VIGA)")
_DE_NERVADURA = re.compile(r"^NERVADURA")


# Lo que empieza así remite a otro dibujo («DET-MB», «CORTE A-A»): no es el nombre de un elemento.
_REFERENCIA = re.compile(r"^(?:DET|DETALLE|CORTE|SECC|VER|FIG|NTC|NPT|NIV|EJE)")


def _nombre_de_marca(ficha: str) -> bool:
    return (
        bool(re.search(r"\d|-", ficha))
        and not _SOLO_CIFRAS.match(ficha)
        and not _REFERENCIA.match(ficha)
    )


@dataclass
class _Titulo:
    """Un título dibujado: el texto, su hoja y qué clase de elemento define."""

    entidad: NormalizedEntity
    hoja: str
    clase: Literal["concreto", "acero", "nervadura"]
    familia: str = ""  # la de su palabra de familia («DADO D-2A»: dado), si la lleva
    con_palabra: bool = True  # «DADO D-2A»; un nombre solo («D-C») no la lleva
    pila: list[str] = field(default_factory=list)  # el armado que encabeza un nombre solo

    @property
    def define(self) -> bool:
        """R234: un título con su palabra de familia, o un nombre solo que encabeza su pila de
        armado («D-C» sobre «6#3», «E#2@15»), define; un nombre solo sin pila (una llamada en un
        corte) sólo nombra."""
        return self.con_palabra or bool(self.pila)


def _en_planta(ctx: _Contexto, e: NormalizedEntity) -> bool:
    """Si el texto cae en una planta estructural (de su mismo archivo)."""
    if ctx.en_planta is None:
        seg = ctx.segmentation
        plantas = (
            [v for v in seg.structural_plan_views() if v.bbox is not None]
            if seg is not None
            else []
        )
        archivo_de = {f.frame_id: f.source_file for f in ctx.frames}
        ctx.en_planta = {
            x.entity_id
            for x in ctx.entidades.values()
            if x.is_textual
            and any(
                bbox_contains_point(v.bbox, bbox_center(x.bbox))  # type: ignore[arg-type]
                and archivo_de.get(v.view_id, "") in ("", x.source_file)
                for v in plantas
            )
        }
    return e.entity_id in ctx.en_planta


def _titulos_dibujados(ctx: _Contexto) -> dict[str, list[_Titulo]]:
    """Los nombres que el plano titula en un dibujo, sin la gramática de marcas ni la IA (R222):
    una palabra de familia y un nombre fuera de las plantas («MURO DE CONCRETO MC-A», en ES-302), o
    un nombre solo en la capa de los detalles, en cualquier hoja («D-C» sobre su armado en ES-200).
    Por nombre normalizado, con la clase de lo que define: concreto, acero (placas, conexiones,
    vigas metálicas) o nervadura (las nervaduras de una losa)."""
    salida: dict[str, list[_Titulo]] = defaultdict(list)
    sin_familia: dict[str, list[NormalizedEntity]] = {}
    # R259: el título que una lectura del plano tomó como el de una marca escrita de otra manera
    # («D-C» sobre su detalle, que es DC por su título DALA): se nombra como lo leyó la lectura.
    leido_como = {
        s.entidades[0]: normalizar_marca(s.mark, ctx.config)
        for s in ctx.inv.specs
        if s.source != "ia" and s.entidades
    }

    def nombre_de(e: NormalizedEntity, ficha: str) -> str:
        nombre = normalizar_marca(ficha.rstrip("'"), ctx.config)
        otro = leido_como.get(e.entity_id)
        if otro is not None and otro != nombre and otro == nombre.replace("-", ""):
            return otro
        return nombre

    for e in ctx.entidades.values():
        if not e.is_textual or not e.text:
            continue
        texto = _una_linea(e.text).upper()
        de_detalle = "DETALLE" in (e.layer or "").upper()
        en_planta = _en_planta(ctx, e)
        hallados: list[tuple[str, Literal["concreto", "acero", "nervadura"], str]] = []
        if not en_planta or de_detalle:
            for familia, ficha in _TITULO_CON_FAMILIA.findall(texto):
                if not _nombre_de_marca(ficha):
                    continue
                clase_t: Literal["concreto", "acero", "nervadura"] = (
                    "acero"
                    if _DE_ACERO.match(familia)
                    else "nervadura"
                    if _DE_NERVADURA.match(familia)
                    else "concreto"
                )
                hallados.append((ficha, clase_t, _familia_de_palabra(familia)))
        solos: list[str] = []
        if de_detalle and not hallados:
            m = _NOMBRE_SOLO.match(_FAMILIA_EN_TITULO.sub("", texto).strip())
            if m is not None and _nombre_de_marca(m.group(1)):
                solos.append(m.group(1))
        for ficha, clase, de_familia in hallados:
            salida[nombre_de(e, ficha)].append(_Titulo(e, ctx.hoja_de(e), clase, de_familia))
        for ficha in solos:
            sin_familia.setdefault(nombre_de(e, ficha), []).append(e)
    # Un nombre solo es de la clase que dicen sus títulos con palabra de familia («VIGA V-E» y
    # «V-E»: acero); si no tiene ninguno, de concreto.
    for nombre, es in sin_familia.items():
        clases = {t.clase for t in salida.get(nombre, [])}
        de_ellos: Literal["concreto", "acero", "nervadura"] = (
            "acero"
            if clases == {"acero"}
            else "nervadura"
            if clases == {"nervadura"}
            else "concreto"
        )
        salida[nombre] += [
            _Titulo(e, ctx.hoja_de(e), de_ellos, con_palabra=False, pila=_pila_bajo(ctx, e))
            for e in es
        ]
    return salida


# La pila de armado que encabeza un nombre solo: bajo él, en su columna, a lo más esto en altos.
_ALCANCE_DE_SU_PILA = 15.0


def _pila_bajo(ctx: _Contexto, titulo: NormalizedEntity) -> list[str]:
    """El armado escrito bajo un nombre solo, en su columna (las citas, de arriba abajo)."""
    if ctx.de_armado is None:
        ctx.de_armado = [
            e for e in ctx.entidades.values() if e.is_textual and e.text and tiene_armado(e.text)
        ]
    alto = alto_de_texto(titulo)
    x0, y0, x1, _y1 = titulo.bbox
    bajo = [
        e
        for e in ctx.de_armado
        if e.source_file == titulo.source_file
        and e.bbox[2] > x0 - alto
        and e.bbox[0] < x1 + alto
        and e.bbox[3] <= y0
        and y0 - e.bbox[3] <= _ALCANCE_DE_SU_PILA * alto
    ]
    return [ctx.cita(e.entity_id) for e in sorted(bajo, key=lambda e: -e.bbox[3])[:4]]


_FAMILIA_DE_PALABRA = (
    ("DADO", "dado"),
    ("MURO", "muro_concreto"),
    ("COLUMNA", "columna"),
    ("CASTILLO", "castillo"),
    ("CONTRATRABE", "contratrabe"),
    ("TRABE", "trabe"),
    ("PILOTE", "pilote"),
    ("ZAPATA", "zapata"),
    ("DALA", "dala"),
    ("CADENA", "dala"),
    ("CERRAMIENTO", "cerramiento"),
)


def _familia_de_palabra(palabra: str) -> str:
    """La familia que nombra la palabra de un título («DADOS» → dado); vacío si no es de una
    familia de concreto."""
    return next((f for p, f in _FAMILIA_DE_PALABRA if palabra.startswith(p)), "")


def _familia_titulada(titulos: list[_Titulo]) -> str:
    """La familia que dicen los títulos de un nombre, si todos dicen la misma."""
    familias = {t.familia for t in titulos if t.familia}
    return next(iter(familias)) if len(familias) == 1 else ""


def _donde_se_titula(ctx: _Contexto, titulos: list[_Titulo]) -> str:
    """«ES-302 (329E1, 8ED73)»: las hojas y los handles de los títulos de un nombre; el de un
    nombre solo con la pila que encabeza («AF02D, con «6#3» AF025, «E#2@15» AF026»)."""
    por_hoja: dict[str, list[str]] = defaultdict(list)
    for t in titulos:
        h = _handle_de(t.entidad)
        por_hoja[t.hoja].append(f"{h}, con {', '.join(t.pila)}" if t.pila else h)
    return "; ".join(
        f"{_nombre_de_hoja(h)} ({', '.join(sorted(set(hs))[:4])})"
        for h, hs in sorted(por_hoja.items())
    )


# Las capas de una losa: lo escrito en ellas son marcas de nervaduras, viguetas o tableros.
_CAPA_DE_LOSA = re.compile(r"LOSA|NERVAD|VIGUETA", re.IGNORECASE)
_FICHA_DE_NERVADURA = re.compile(r"^[A-Z]{1,3}-?\d{1,2}[A-Z]?'?$")
# R253: en la capa de una losa, dos letras sin número también son marcas de nervadura (Marina
# ES-400: NA…NG; ES-200: WI, XI, XO, una W1/X1/X0 escrita con letra); su familia es la primera.
_FICHA_DE_NERVADURA_SIN_NUMERO = re.compile(r"^[A-Z]{2}$")


def _marcas_de_nervadura(
    ctx: _Contexto, titulos: dict[str, list[_Titulo]]
) -> dict[str, list[NormalizedEntity]]:
    """Las marcas de las nervaduras de una losa escritas en planta (R226): las que van en la capa
    de una losa («EST-LOSA NERVADA»: W1, X2, Y4, Z2) y las que el plano titula «NERVADURA». Son de
    la losa, no elementos de esta lectura: un aviso por familia, nunca una marca sin colocar."""
    salida: dict[str, list[NormalizedEntity]] = defaultdict(list)
    nervaduras = {n for n, ts in titulos.items() if any(t.clase == "nervadura" for t in ts)}
    for e in ctx.entidades.values():
        if not e.is_textual or not e.text:
            continue
        texto = _una_linea(e.text).upper()
        de_losa = bool(_CAPA_DE_LOSA.search(e.layer or ""))
        sin_numero = de_losa and bool(_FICHA_DE_NERVADURA_SIN_NUMERO.match(texto))
        if not (_FICHA_DE_NERVADURA.match(texto) or sin_numero) or not _en_planta(ctx, e):
            continue
        nombre = texto if sin_numero else normalizar_marca(texto.rstrip("'"), ctx.config)
        if de_losa or nombre in nervaduras:
            salida[nombre].append(e)
    return salida


def _nervaduras(ctx: _Contexto, marcas: dict[str, list[NormalizedEntity]]) -> list[Verificacion]:
    familias: dict[str, dict[str, list[NormalizedEntity]]] = defaultdict(dict)
    for nombre, textos in marcas.items():
        # Sin número («NA», «WI»): la familia es su primera letra (R253).
        con_numero = re.search(r"\d", nombre)
        prefijo = re.match(r"[A-Z]+" if con_numero else r"[A-Z]", nombre)
        familias[prefijo.group(0) if prefijo else nombre][nombre] = textos
    salida = []
    for letra, de_ella in sorted(familias.items()):
        todos = [t for ts in de_ella.values() for t in ts]
        hojas = Counter(ctx.hoja_de(t) for t in todos)
        capas = sorted({t.layer for t in todos})
        # Como las escribe el plano («Z1», no la marca normalizada «Z-1»: no son zapatas).
        escritas = Counter(_una_linea(t.text or "").upper() for t in todos)
        cuantas = ", ".join(f"{n} ({c})" for n, c in sorted(escritas.items()))
        handles = list(dict.fromkeys(_handle_de(t) for t in todos))
        salida.append(
            _hallazgo(
                10,
                "aviso",
                f"Marcas de losa nervada sin lector, familia {letra}: {len(todos)} textos en "
                f"{', '.join(f'{h} ({n})' for h, n in sorted(hojas.items()))}, capa "
                f"{', '.join(capas)}: {cuantas}. Son de las nervaduras de la losa: la lectura "
                "estructural no las lee y sus cantidades no salen de aquí. Textos: "
                f"{', '.join(handles[:_EJEMPLOS])}"
                + (f" y {len(handles) - _EJEMPLOS} más" if len(handles) > _EJEMPLOS else "")
                + ". Cantidad desconocida.",
                clave=f"nervaduras: {letra}",
                marcas=sorted(escritas),
                textos=handles,
                en_juego={"piezas": float(len(todos))},
                cantidad="desconocida",
            )
        )
    return salida


# Los elementos de acero que esta lectura (de concreto) no lee, por familia (R231): columnas
# HSS/PTR, placas, conexiones y vigas metálicas.
_FAMILIAS_DE_ACERO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("columnas de acero (HSS, PTR)", re.compile(r"\b(?:HSS|PTR)\b")),
    ("placas base (PL)", re.compile(r"^(?:PLACA\s+(?:BASE\s+)?)?PL-[A-Z0-9]{1,3}\b")),
    ("conexiones (CN)", re.compile(r"^(?:CONEXI[OÓ]N\s+)?CN-[A-Z0-9]{1,3}\b|^CONEXI[OÓ]N\b")),
    (
        "vigas de acero (V-, IPR)",
        re.compile(r"\bIPR\b|\bIPS\b|\bVIGA\s+V-?[A-Z0-9]{1,3}\b|^V-[A-Z]$"),
    ),
)


def _de_acero(ctx: _Contexto, titulos: dict[str, list[_Titulo]]) -> list[Verificacion]:
    """Un aviso por familia de acero con lo que el plano escribe de ella en planta y en sus
    detalles (por handle): no es de esta lectura, y se dice. En la capa de las conexiones, lo que
    remite a otro dibujo («DET-MB») es la llamada a un detalle, no una conexión: se cita aparte. Las
    escaleras, igual: su aviso (R234)."""
    salida = []
    for nombre, patron in (*_FAMILIAS_DE_ACERO, _ESCALERAS):
        en_planta: list[NormalizedEntity] = []
        en_detalle: list[NormalizedEntity] = []
        remiten: list[NormalizedEntity] = []
        for e in ctx.entidades.values():
            if not e.is_textual or not e.text:
                continue
            texto = _una_linea(e.text).upper()
            de_su_capa = nombre.startswith("conexiones") and "CONEXI" in (e.layer or "").upper()
            if de_su_capa and _REFERENCIA.match(texto):
                remiten.append(e)
                continue
            if not patron.search(texto) and not de_su_capa:
                continue
            (en_planta if _en_planta(ctx, e) else en_detalle).append(e)
        if not en_planta and not en_detalle:
            continue

        def citas(es: list[NormalizedEntity]) -> str:
            lista = [f"{ctx.cita(e.entity_id)} ({_nombre_de_hoja(ctx.hoja_de(e))})" for e in es]
            return ", ".join(lista[:_EJEMPLOS]) + (
                f" y {len(lista) - _EJEMPLOS} más" if len(lista) > _EJEMPLOS else ""
            )

        partes = []
        if en_planta:
            partes.append(f"en planta {citas(en_planta)}")
        if en_detalle:
            partes.append(f"en sus detalles {citas(en_detalle)}")
        llamadas = f" Remite a sus detalles: {citas(remiten)}." if remiten else ""
        if nombre == _ESCALERAS[0]:
            cabeza = "Escaleras fuera de esta lectura: el plano las dibuja "
            cola = (
                ". La lectura estructural no lee escaleras (rampas, escalones, sus vigas): sus "
                "cantidades no salen de aquí. Cantidad desconocida."
            )
        else:
            cabeza = f"Elementos de acero fuera de esta lectura, {nombre}: el plano los escribe "
            cola = (
                f".{llamadas} Esta lectura es del concreto armado: sus cantidades no salen de "
                "aquí. Cantidad desconocida."
            )
        salida.append(
            _hallazgo(
                10,
                "aviso",
                cabeza + "; ".join(partes) + cola,
                clave=f"acero: {nombre}" if nombre != _ESCALERAS[0] else "escaleras",
                textos=[_handle_de(e) for e in [*en_planta, *en_detalle, *remiten]],
                en_juego={"piezas": float(len(en_planta))},
                cantidad="desconocida",
            )
        )
    return salida


_ESCALERAS = ("escaleras", re.compile(r"\bESCALERAS?\b"))


# ------------------------------------------------------------ 2: definida que no se coloca


def _sin_colocar(
    ctx: _Contexto,
    escritas: dict[str, list[_Escrita]],
    titulos: dict[str, list[_Titulo]],
    ajenas: set[str],
) -> list[Verificacion]:
    """Lo definido que nunca se coloca ni se escribe en planta: lo que una lectura del plano
    define, y lo que el plano titula en un dibujo aunque nadie lo haya leído (R224: «DADO D-2A»,
    o una definición que sólo da la IA y que el plano titula)."""
    colocadas = {e.marca for e in ctx.elementos}
    detectadas: dict[str, list[Detection]] = defaultdict(list)
    plantas = (
        {v.view_id for v in ctx.segmentation.structural_plan_views()}
        if ctx.segmentation is not None
        else set()
    )
    for d in ctx.detections:
        if d.mark.strip() and d.family in FAMILIAS_ESTRUCTURALES:
            detectadas[normalizar_marca(d.mark, ctx.config)].append(d)
    titulos_de_vista = (
        {v.view_id: v.title for v in ctx.segmentation.views} if ctx.segmentation else {}
    )
    de_concreto = {n: ts for n, ts in titulos.items() if any(t.clase == "concreto" for t in ts)}
    salida: list[Verificacion] = []
    for marca in sorted(set(ctx.por_marca) | set(de_concreto)):
        if marca in colocadas or marca in escritas or marca in ajenas:
            continue
        definicion = ctx.por_marca.get(marca)
        dibujados = de_concreto.get(marca, [])
        definen = [t for t in dibujados if t.define]
        nombran = [t for t in dibujados if not t.define]
        if (definicion is None or not _del_plano(definicion)) and not definen:
            continue
        en_cuadro = sorted(
            {
                ctx.segmentation.assignment.get(d.detection_id, "")
                for d in detectadas.get(marca, [])
                if ctx.segmentation is not None
                and ctx.segmentation.assignment.get(d.detection_id) in plantas
            }
        )
        solo = (
            " En planta sólo aparece como etiqueta de cuadro o título de detalle ("
            + ", ".join(titulos_de_vista.get(v, v).split(" · ")[0] for v in en_cuadro)
            + ")."
            if en_cuadro
            else ""
        )
        if definicion is not None and _del_plano(definicion):
            dice = (
                f"está definida en el plano ({_nombres_de_hojas(definicion.hojas) or 'sin hoja'})"
            )
            familia = definicion.familia
        else:
            dice = (
                f"el plano la define en {_donde_se_titula(ctx, definen)} y no se leyó su "
                "definición"
                + (f" (la nombra también en {_donde_se_titula(ctx, nombran)})" if nombran else "")
            )
            familia = definicion.familia if definicion is not None else _familia_titulada(definen)
        de_familia = f" ({familia})" if familia else ""
        salida.append(
            _hallazgo(
                2,
                "aviso",
                f"{marca}{de_familia} {dice}, y no se coloca en ninguna planta: no entra en las "
                f"cantidades.{solo} Si se construye, falta su colocación.",
                clave="definida sin colocar",
                marca=marca,
                datos=[
                    d
                    for campo in ("seccion_cm", *_ARMADO)
                    if definicion is not None and (d := getattr(definicion, campo)) is not None
                ],
                textos=[_handle_de(t.entidad) for t in dibujados],
                cantidad="desconocida",
            )
        )
    return salida


def _del_plano(d: Definicion) -> bool:
    """Si alguna lectura del plano (no sólo la IA) define la marca."""
    for campo in ("seccion_cm", "longitud_m", *_ARMADO):
        dato = getattr(d, campo)
        if dato is not None and any(m.fuente != "ia" for m in miembros(dato)):
            return True
    return bool(d.hojas)


# -------------------------------------------------------- 10: escrita en planta sin elemento


def _escritas_sin_elemento(
    ctx: _Contexto, escritas: dict[str, list[_Escrita]], titulos: dict[str, list[_Titulo]]
) -> list[Verificacion]:
    salida: list[Verificacion] = []
    colocadas = _por_marca(ctx.elementos)
    muros = {
        marca: textos
        for marca, textos in escritas.items()
        if _es_muro(marca, _familia_de_marca(ctx, marca, titulos), textos)
    }
    medidas, tope = _medir_muros(ctx, muros)
    if tope is not None:
        salida.append(
            _hallazgo(
                10,
                "aviso",
                "Muros de concreto escritos sin elemento: lo más que puede haber en cada planta "
                "que tocan sus cotas (todo su achurado de muro × su entrepiso, "
                f"{_DOS_LECTURAS}; la lectura no escoge). Las cotas de "
                f"{', '.join(tope.marcas)} no se suman entre sí: una región que comparten aparece "
                f"en cada una. {'; '.join(tope.lineas)}. En total: (A) a lo más "
                f"{tope.volumen_a_m3:.2f} m³; (B) a lo más {tope.volumen_b_m3:.2f} m³.",
                clave="muros: tope por planta",
                marcas=tope.marcas,
                en_juego={
                    "area_planta_m2": tope.area_m2,
                    "volumen_m3": max(tope.volumen_a_m3, tope.volumen_b_m3),
                },
                cantidad="estimada",
            )
        )
    for marca, textos in sorted(escritas.items()):
        por_hoja = Counter(t.hoja for t in textos)
        donde = "; ".join(f"{_nombre_de_hoja(h)}: {_veces(n)}" for h, n in sorted(por_hoja.items()))
        definicion = ctx.por_marca.get(marca)
        # El nombre en la capa de los detalles dentro de una planta puede ser la etiqueta de una
        # colocación («MC-1» junto a «20CM»): lo que está escrito en planta no es su propio título.
        # (Una pila de armado escrita en planta sí es su definición: R234.)
        propios = {t.entidad.entity_id for t in textos}
        de_concreto = [t for t in titulos.get(marca, []) if t.clase == "concreto"]
        dibujados = [t for t in de_concreto if t.define]
        nombran = [t for t in de_concreto if not t.define and t.entidad.entity_id not in propios]
        tambien = f" La nombra también en {_donde_se_titula(ctx, nombran)}." if nombran else ""
        if definicion is not None and _del_plano(definicion):
            estado = f"Está definida en {_nombres_de_hojas(definicion.hojas) or 'el plano'}."
        elif dibujados:
            # R223: el plano la titula; lo que falló fue leer su definición.
            estado = (
                f"El plano la define en {_donde_se_titula(ctx, dibujados)} y no se leyó su "
                "definición"
                + (" (sólo la lectura IA la lee)." if definicion is not None else ".")
                + tambien
            )
        elif nombran:
            estado = (
                f"El plano no la define: sólo la nombra en {_donde_se_titula(ctx, nombran)}"
                + ("; sólo la lectura IA la define." if definicion is not None else ".")
            )
        elif definicion is not None:
            estado = "Sólo la lectura IA la define; el plano no titula ningún dibujo suyo."
        else:
            estado = "Tampoco está definida en el plano: ningún dibujo la titula."
        if colocadas.get(marca):
            otras = sorted({_nombre_de_hoja(e.hoja) for e in colocadas[marca]})
            estado += f" Sus colocaciones están en {', '.join(otras)}, lejos de estos textos."
        estado += _etiqueta_disputada(ctx, marca, textos)
        junto = [t for t in textos if t.junto_sin_marca]
        if junto:
            familias = ", ".join(sorted({f for t in junto for f in t.junto_sin_marca}))
            cuales = (
                "El texto está"
                if len(textos) == 1
                else f"{len(junto)} de esos textos {'está' if len(junto) == 1 else 'están'}"
            )
            estado += (
                f" {cuales} junto a una colocación sin marca ({familias}): puede ser la suya, "
                "sin juntar con su marca."
            )
        familia = definicion.familia if definicion is not None else _familia_titulada(dibujados)
        if familia == "pilote" or marca.startswith("P-"):
            estado += " Todo pilote escrito en planta debe tener su pila: a éstos les falta."
        medida = medidas.get(marca)
        cantidad: Literal["conocida", "desconocida", "estimada"]
        if medida is not None:
            estado += f" {medida.texto}"
            juego = {"piezas": float(len(textos))}
            if medida.limpia:
                juego |= {"area_planta_m2": medida.area_m2, "volumen_m3": medida.volumen_m3}
            cantidad = "estimada" if medida.limpia else "desconocida"
        else:
            estado += f" Cantidad desconocida: {_veces(len(textos))} escrita, sin elemento."
            juego = {"piezas": float(len(textos))}
            cantidad = "desconocida"
        citas = [ctx.cita(t.entidad.entity_id) for t in textos]
        hoja = next(iter(por_hoja)) if len(por_hoja) == 1 else ""
        salida.append(
            _hallazgo(
                10,
                "duda",
                f"{marca} está escrita en planta {_veces(len(textos))} ({donde}) y ahí no hay "
                f"ningún elemento {marca} colocado: el plano la dibuja y la lectura no la "
                f"encontró. {estado} Textos: {', '.join(citas[:_EJEMPLOS])}"
                + (f" y {len(citas) - _EJEMPLOS} más" if len(citas) > _EJEMPLOS else "")
                + ".",
                clave="escrita en planta sin elemento",
                marca=marca,
                hoja=hoja,
                de_la_marca=True,
                bbox=_caja(t.entidad.bbox for t in textos) if hoja else None,
                textos=[_handle_de(t.entidad) for t in textos],
                en_juego=juego,
                cantidad=cantidad,
            )
        )
    return salida


def _etiqueta_disputada(ctx: _Contexto, marca: str, textos: list[_Escrita]) -> str:
    """Tarea 15b: lo que el detector dijo de una etiqueta de esta marca que no juntó con ningún
    contorno de su capa porque dos la alcanzan casi igual (``etiquetas_disputadas``), nombrando
    los dos; y si uno está dibujado dentro de otro que ya tiene su marca (``anidados``: D-X dentro
    de D-4), la pregunta, que la lectura no decide: ni lo junta ni lo cuenta aparte."""
    propios = {t.entidad.entity_id for t in textos}
    frases: list[str] = []
    for d in ctx.detections:
        props = d.properties or {}
        for disputa in props.get("etiquetas_disputadas") or []:
            if disputa.get("entidad") not in propios or disputa.get("marca") != marca:
                continue
            contornos = [str(c) for c in disputa.get("contornos") or []]
            if len(contornos) > 1:
                frase = (
                    f"La etiqueta {disputa.get('texto') or ''} queda casi a la misma distancia de "
                    f"dos contornos de su capa ({', '.join(contornos)}): no se junta con ninguno."
                )
            else:
                frase = (
                    f"La etiqueta {disputa.get('texto') or ''} y otra escogen el mismo contorno "
                    f"({', '.join(contornos)}): no se junta con él."
                )
            dentro = [
                a
                for a in props.get("anidados") or []
                if a.get("contorno") in contornos and marca in (a.get("marcas") or [])
            ]
            if dentro and d.mark.strip():
                factor = ctx.factor or 1.0
                lados = "x".join(f"{float(v) * factor * 100:g}" for v in dentro[0]["lados"])
                suyo = ctx.entidades.get(d.source_entities[0]) if d.source_entities else None
                de_quien = f"{d.mark} ({suyo.raw_handle})" if suyo is not None else d.mark
                frase += (
                    f" {marca} dentro de {d.mark}: ¿pedestal o dado aparte? Su contorno "
                    f"{dentro[0]['contorno']} ({lados}) está dibujado dentro del de {de_quien}; la "
                    f"lectura no lo decide: no lo cuenta aparte ni lo suma a {d.mark}."
                )
            if frase not in frases:
                frases.append(frase)
    return "".join(f" {f}" for f in frases)


def _familia_de_marca(ctx: _Contexto, marca: str, titulos: dict[str, list[_Titulo]]) -> str:
    definicion = ctx.por_marca.get(marca)
    if definicion is not None:
        return definicion.familia
    return _familia_titulada([t for t in titulos.get(marca, []) if t.clase == "concreto"])


def _es_muro(marca: str, familia: str, textos: list[_Escrita]) -> bool:
    return (
        familia == "muro_concreto"
        or marca.startswith("MC-")
        or any("MURO" in (t.entidad.layer or "").upper() for t in textos)
    )


# Un texto de muro va sobre su muro: la región achurada más cercana a lo más esto, en altos de
# su letra (dentro de ella, a distancia cero).
_SOBRE_SU_MURO = 3.0
_DOS_LECTURAS = "en las dos lecturas de los entrepisos"
# Las regiones del concreto de los muros: el achurado de la capa de muros de concreto.
_CAPA_DE_MURO = re.compile(r"MURO.*CONC|CONC.*MURO", re.IGNORECASE)

Punto = tuple[float, float]


@dataclass
class _Region:
    """Una región achurada de muro de concreto en una planta: su contorno menos sus huecos."""

    entidad: NormalizedEntity
    vista: str
    anillos: list[list[Punto]]
    huecos: list[bool]
    area_m2: float


@dataclass
class _Medida:
    """La cota medida del concreto de un muro escrito sin elemento (R232), o por qué no la hay."""

    texto: str
    volumen_m3: float  # la mayor de las dos lecturas de los entrepisos
    area_m2: float
    limpia: bool


@dataclass
class _Tope:
    """Lo más que pueden sumar los muros escritos sin elemento: todo el achurado de muro de cada
    planta que sus cotas tocan × su entrepiso, en las dos lecturas (cada región una vez: las cotas
    de las marcas no se suman entre sí, una región compartida aparece en cada una)."""

    lineas: list[str]
    area_m2: float
    volumen_a_m3: float
    volumen_b_m3: float
    marcas: list[str]


# Un trozo de achurado sin dueño más chico que esto (m², o esta parte de lo que achura su planta)
# es una astilla del dibujo: no vuelve desconocida la cota de un muro (sigue en el total achurado).
_ASTILLA_M2 = 0.1
_ASTILLA_PARTE = 0.01


def _regiones_de_muro(ctx: _Contexto) -> list[_Region]:
    """Las regiones achuradas de muro de concreto de las plantas estructurales, cada una con su
    área neta en m² (el contorno menos los huecos: un anillo cuenta lo que está entre sus dos
    contornos)."""
    salida = []
    factor = ctx.factor or 1.0
    for e in ctx.entidades.values():
        if e.entity_type.value != "hatch" or not _CAPA_DE_MURO.search(e.layer or ""):
            continue
        crudos = e.properties.get("anillos") or [e.points or []]
        anillos = [[(float(p[0]), float(p[1])) for p in r] for r in crudos if len(r) >= 3]
        if not anillos:
            continue
        vista = _vista_de(ctx, e)
        if vista is None:
            continue
        huecos = [
            sum(_dentro(r[0], o) for j, o in enumerate(anillos) if j != i) % 2 == 1
            for i, r in enumerate(anillos)
        ]
        area = sum(_area_de(r) * (-1 if h else 1) for r, h in zip(anillos, huecos, strict=True))
        salida.append(_Region(e, vista, anillos, huecos, max(area, 0.0) * factor * factor))
    return salida


def _area_de(anillo: list[Punto]) -> float:
    return (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(anillo, [*anillo[1:], anillo[0]], strict=True)
            )
        )
        / 2
    )


def _dentro(p: Punto, anillo: list[Punto]) -> bool:
    x, y = p
    dentro = False
    for (x1, y1), (x2, y2) in zip(anillo, [*anillo[1:], anillo[0]], strict=True):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def _a_region(p: Punto, region: _Region) -> float:
    """La distancia de un punto a una región achurada: cero dentro de ella (no en un hueco)."""
    if sum(_dentro(p, r) for r in region.anillos) % 2 == 1:
        return 0.0
    return min(
        _a_tramo(p, a, b) for r in region.anillos for a, b in zip(r, [*r[1:], r[0]], strict=True)
    )


def _a_tramo(p: Punto, a: Punto, b: Punto) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    largo2 = dx * dx + dy * dy
    if largo2 <= 0:
        return math.dist(p, a)
    u = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / largo2))
    return math.dist(p, (a[0] + u * dx, a[1] + u * dy))


def _lecturas_de_entrepiso(
    ctx: _Contexto,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """El entrepiso de cada planta en las dos lecturas que el plano sostiene (verificación 8):
    (A) cada planta sube desde su losa hasta el nivel de arriba (la más alta no tiene); (B) cada
    planta está bajo su losa, desde el nivel de abajo (la más baja no tiene)."""
    seg = ctx.segmentation
    if seg is None:
        return {}, {}
    vistas = sorted(
        (v for v in seg.structural_plan_views() if v.npt_level is not None),
        key=lambda v: v.npt_level or 0.0,
    )
    niveles = [float(v.npt_level or 0.0) for v in vistas]
    sube: dict[str, float | None] = {}
    baja: dict[str, float | None] = {}
    for i, v in enumerate(vistas):
        sube[v.view_id] = round(niveles[i + 1] - niveles[i], 3) if i + 1 < len(vistas) else None
        baja[v.view_id] = round(niveles[i] - niveles[i - 1], 3) if i > 0 else None
    return sube, baja


def _medir_muros(
    ctx: _Contexto, muros: dict[str, list[_Escrita]]
) -> tuple[dict[str, _Medida], _Tope | None]:
    """R232: la cota medida del concreto de cada muro escrito sin elemento, o nada. Cada texto toma
    la región achurada de muro sobre la que está; cada región se cuenta una vez y la que toman
    varias marcas se dice junta («MC-1/MC-3: 6.01 m²»). El alto es el entrepiso de su planta en
    las dos lecturas de los entrepisos, las dos dichas (la lectura no escoge). Lo de cada planta
    nunca pasa de lo que esa planta achura. Si un texto no está sobre ninguna región y en su
    planta queda achurado sin dueño (no una astilla: ``_ASTILLA_M2``, ``_ASTILLA_PARTE``), no se
    puede atribuir: cantidad desconocida. Con las cotas, el tope de cada planta que tocan (todo su
    achurado de muro × su entrepiso), para que nadie sume las cotas de las marcas."""
    regiones = _regiones_de_muro(ctx)
    if not regiones:
        return {}, None
    por_vista: dict[str, list[_Region]] = defaultdict(list)
    for r in regiones:
        por_vista[r.vista].append(r)
    duenos: dict[int, set[str]] = defaultdict(set)  # id(region) → las marcas que la toman
    de_la_marca: dict[str, dict[str, list[_Region]]] = defaultdict(lambda: defaultdict(list))
    fuera: dict[str, list[_Escrita]] = defaultdict(list)
    for marca, textos in muros.items():
        for t in textos:
            vista = _vista_de(ctx, t.entidad)
            candidatas = por_vista.get(vista or "", [])
            centro = bbox_center(t.entidad.bbox)
            cerca = min(candidatas, key=lambda r: _a_region(centro, r), default=None)
            if cerca is None or _a_region(centro, cerca) > _SOBRE_SU_MURO * alto_de_texto(
                t.entidad
            ):
                fuera[marca].append(t)
                continue
            duenos[id(cerca)].add(marca)
            if cerca not in de_la_marca[marca][cerca.vista]:
                de_la_marca[marca][cerca.vista].append(cerca)
    sube, baja = _lecturas_de_entrepiso(ctx)
    nombre = (
        {v.view_id: v.title.split(" · ")[0] for v in ctx.segmentation.views}
        if ctx.segmentation is not None
        else {}
    )
    achurado_de = {v: sum(r.area_m2 for r in rs) for v, rs in por_vista.items()}
    # Un trozo sin dueño cuenta si no es una astilla del dibujo (R232, con la tarea 12).
    sin_dueno = {
        v
        for v, rs in por_vista.items()
        if any(
            not duenos.get(id(r)) and r.area_m2 >= max(_ASTILLA_M2, _ASTILLA_PARTE * achurado_de[v])
            for r in rs
        )
    }
    salida: dict[str, _Medida] = {}
    tocadas: dict[str, set[str]] = defaultdict(set)  # vista → las marcas con cota ahí
    for marca in muros:
        vistas = de_la_marca.get(marca, {})
        sueltos = fuera.get(marca, [])
        sueltos_txt = ", ".join(_handle_de(t.entidad) for t in sueltos[:_EJEMPLOS])
        esta = "está" if len(sueltos) == 1 else "están"
        if not vistas or any((_vista_de(ctx, t.entidad) or "") in sin_dueno for t in sueltos):
            motivo = (
                "ninguno de sus textos está sobre una región achurada de muro"
                if not vistas
                else f"{len(sueltos)} de sus textos ({sueltos_txt}) no {esta} sobre ninguna región "
                "achurada de muro y en su planta queda achurado sin dueño"
            )
            salida[marca] = _Medida(
                f"Cantidad desconocida: {motivo}, así que su concreto no se puede atribuir; "
                f"{_veces(len(muros[marca]))} escrita, "
                "sin elemento.",
                0.0,
                0.0,
                False,
            )
            continue
        partes: list[str] = []
        area_total = vol_a = vol_b = 0.0
        alto_a: list[str] = []
        alto_b: list[str] = []
        for vista, rs in sorted(vistas.items(), key=lambda x: nombre.get(x[0], x[0])):
            propias = [r for r in rs if duenos[id(r)] == {marca}]
            juntas: dict[tuple[str, ...], list[_Region]] = defaultdict(list)
            for r in rs:
                if duenos[id(r)] != {marca}:
                    juntas[tuple(sorted(duenos[id(r)]))].append(r)
            achurado = sum(r.area_m2 for r in por_vista[vista])
            # Cada región una vez y sólo las de esta planta: nunca más que lo que ella achura.
            area = sum(r.area_m2 for r in rs)
            area_total += area
            trozos = []
            if propias:
                trozos.append(
                    f"{sum(r.area_m2 for r in propias):.2f} m² suyos "
                    f"({', '.join(_handle_de(r.entidad) for r in propias[:_EJEMPLOS])})"
                )
            for quienes, js in sorted(juntas.items()):
                trozos.append(
                    f"{'/'.join(quienes)}: {sum(r.area_m2 for r in js):.2f} m² "
                    f"({', '.join(_handle_de(r.entidad) for r in js[:_EJEMPLOS])}), que se cuentan "
                    "una vez para todas"
                )
            hoja = nombre.get(vista, vista)
            partes.append(f"en {hoja}, {'; '.join(trozos)} (de {achurado:.2f} m² achurados ahí)")
            a, b = sube.get(vista), baja.get(vista)
            alto_a.append(f"{hoja} {a:g} m" if a else f"{hoja} no se cuenta")
            alto_b.append(f"{hoja} {b:g} m" if b else f"{hoja} no se cuenta")
            vol_a += area * (a or 0.0)
            vol_b += area * (b or 0.0)
        sueltos_dicho = (
            f" {len(sueltos)} de sus textos ({sueltos_txt}) no están sobre ninguna región "
            "achurada; toda región achurada de su planta ya la toma algún texto."
            if sueltos
            else ""
        )
        if not sube and not baja:
            texto = (
                f"Cota medida en planta: {'; '.join(partes)}. Sin niveles declarados no hay "
                f"entrepiso con qué darle alto: cantidad desconocida.{sueltos_dicho}"
            )
            salida[marca] = _Medida(texto, 0.0, area_total, False)
            continue
        texto = (
            f"Cota medida en planta (el muro achurado sobre el que están sus textos, cada región "
            f"una vez): {'; '.join(partes)}. Por su entrepiso, {_DOS_LECTURAS}: (A) cada planta "
            f"sube desde su losa ({', '.join(alto_a)}): a lo más "
            f"{vol_a:.2f} m³; (B) cada planta está bajo su losa ({', '.join(alto_b)}): a lo más "
            f"{vol_b:.2f} m³. La lectura no escoge.{sueltos_dicho}"
        )
        salida[marca] = _Medida(texto, max(vol_a, vol_b), area_total, True)
        for vista in vistas:
            tocadas[vista].add(marca)
    return salida, _tope(tocadas, achurado_de, sube, baja, nombre)


def _tope(
    tocadas: dict[str, set[str]],
    achurado_de: dict[str, float],
    sube: dict[str, float | None],
    baja: dict[str, float | None],
    nombre: dict[str, str],
) -> _Tope | None:
    """El tope de los muros por planta (``_Tope``): una línea por planta que las cotas tocan."""
    if not tocadas:
        return None
    lineas: list[str] = []
    area = vol_a = vol_b = 0.0
    for vista in sorted(tocadas, key=lambda v: nombre.get(v, v)):
        achurado = achurado_de[vista]
        a, b = sube.get(vista), baja.get(vista)
        area += achurado
        vol_a += achurado * (a or 0.0)
        vol_b += achurado * (b or 0.0)
        tope_a = f"{achurado * a:.2f} m³" if a else "no se cuenta"
        tope_b = f"{achurado * b:.2f} m³" if b else "no se cuenta"
        lineas.append(
            f"{nombre.get(vista, vista)}: {achurado:.2f} m² achurados; tope (A) {tope_a} / (B) "
            f"{tope_b}"
        )
    marcas = sorted({m for ms in tocadas.values() for m in ms})
    return _Tope(lineas, area, vol_a, vol_b, marcas)


def _vista_de(ctx: _Contexto, e: NormalizedEntity) -> str | None:
    seg = ctx.segmentation
    if seg is None:
        return None
    centro = bbox_center(e.bbox)
    plantas = seg.structural_plan_views()
    # Tarea 15c: dentro de la rejilla de una sola planta, es de esa planta (las cajas de las
    # vistas, la unión de sus detecciones, pueden traslaparse).
    suya = seg.vista_por_rejilla(centro)
    if suya is not None and any(v.view_id == suya for v in plantas):
        return suya
    for v in plantas:
        if v.bbox is not None and bbox_contains_point(v.bbox, centro):
            return v.view_id
    return None


_FUERA = {
    "sin_vista": "fuera de toda vista (lo que queda fuera de los marcos de hoja)",
    "planta_no_estructural": "en la planta de una hoja que no es de estructura",
}


def _detectadas_fuera(ctx: _Contexto) -> list[Verificacion]:
    """Las detecciones de una familia estructural que no llegan a elemento porque caen fuera de
    toda vista o en una planta que no es de estructura: el plano las dibuja y no se cuentan. Un
    aviso por motivo y familia (las de un detalle, un corte o un cuadro definen, no colocan)."""
    grupos: dict[tuple[str, str], list[Any]] = defaultdict(list)
    en_duda: dict[str, list[Any]] = defaultdict(list)
    for x in excluidas(ctx.detections, ctx.segmentation):
        if x.motivo in _FUERA:
            grupos[(x.motivo, x.familia)].append(x)
        elif x.motivo == "vista_en_duda":
            en_duda[x.familia].append(x)
    salida = [_en_duda(ctx, familia, xs) for familia, xs in sorted(en_duda.items())]
    for (motivo, familia), xs in sorted(grupos.items()):
        marcas = Counter(x.marca or "sin marca" for x in xs)
        etiquetas = [
            ctx.handle(ctx.deteccion[x.detection_id].source_entities[0])
            for x in xs
            if x.detection_id in ctx.deteccion and ctx.deteccion[x.detection_id].source_entities
        ]
        salida.append(
            _hallazgo(
                10,
                "aviso",
                f"{len(xs)} detecciones de {familia} {_FUERA[motivo]} no se cuentan: "
                + ", ".join(f"{m} ({n})" if n > 1 else m for m, n in sorted(marcas.items()))
                + f". Etiquetas: {', '.join(etiquetas[:_EJEMPLOS])}"
                + (f" y {len(etiquetas) - _EJEMPLOS} más" if len(etiquetas) > _EJEMPLOS else "")
                + ". Si son del proyecto, falta su planta.",
                clave=f"detectadas fuera: {motivo}: {familia}",
                marcas=sorted(m for m in marcas if m != "sin marca"),
                textos=etiquetas,
                en_juego={"piezas": float(len(xs))},
            )
        )
    return salida


def _en_duda(ctx: _Contexto, familia: str, xs: list[Any]) -> Verificacion:
    """Tarea 15c: las colocaciones que están dentro de las rejillas de dos plantas sin dibujo que
    diga de cuál son: ninguna de las dos las cuenta hasta que se decida (una duda de la 7: de su
    planta dependen su altura y su nivel)."""
    marcas = Counter(x.marca or "sin marca" for x in xs)
    etiquetas = [
        ctx.handle(ctx.deteccion[x.detection_id].source_entities[0])
        for x in xs
        if x.detection_id in ctx.deteccion and ctx.deteccion[x.detection_id].source_entities
    ]
    ejemplos = [f"{x.marca or 'sin marca'}: {x.texto}" for x in xs]
    return _hallazgo(
        7,
        "duda",
        f"{len(xs)} colocaciones de {familia} con vista en duda: no se sabe a qué planta "
        "pertenecen y no se cuentan en ninguna hasta que se decida. "
        + " | ".join(ejemplos[:_EJEMPLOS])
        + (f" | y {len(ejemplos) - _EJEMPLOS} más" if len(ejemplos) > _EJEMPLOS else ""),
        clave=f"vista en duda: {familia}",
        marcas=sorted(m for m in marcas if m != "sin marca"),
        campo="altura_m",
        textos=etiquetas,
        en_juego={"piezas": float(len(xs))},
    )


# ------------------------------------------------------------------- 7: los datos críticos

# Cómo se nombra cada dato en una frase: su género y su número (para «la da», «los estribos son»).
_GENERO: dict[str, tuple[str, bool]] = {
    "seccion_cm": ("f", False),
    "altura_m": ("f", False),
    "longitud_m": ("f", False),
    "longitudinales": ("f", True),
    "estribos": ("m", True),
    "parrillas": ("f", True),
    "recubrimiento_m": ("m", False),
}


def _plural(campos: list[str]) -> bool:
    return len(campos) > 1 or _GENERO[campos[0]][1]


def _pron(campos: list[str]) -> str:
    """«la», «las», «lo», «los»: el pronombre de los datos de la frase."""
    femenino = all(_GENERO[c][0] == "f" for c in campos)
    if _plural(campos):
        return "las" if femenino else "los"
    return "la" if femenino else "lo"


def _nombres(campos: list[str]) -> str:
    return _listar([_NOMBRE[c] for c in campos])


@dataclass
class _Estado:
    """Lo que tiene un dato crítico de un elemento, para agruparlo con los de su marca."""

    estado: str  # falta | por_leer | supuesto | ia | de_otra_hoja | medida_en_planta | …
    severidad: Severidad
    detalle: str  # lo que lo explica (igual para las colocaciones que se agrupan)
    dato: Dato | None = None
    valores: list[Any] = field(default_factory=list)  # las secciones de «dos_secciones»


# Los datos que sólo da una definición: sin ninguna, su falta es la de la marca (verificación 1).
_DE_LA_DEFINICION = frozenset({"seccion_cm", *_ARMADO})
# Los estados en que a un dato de armado le falta su valor: los campos de armado de una marca en
# el mismo estado van en un solo hallazgo (la oficina lee de una vez el armado de esa marca).
_SIN_VALOR = frozenset({"falta", "por_leer"})


def _criticos(ctx: _Contexto) -> list[Verificacion]:
    """Un hallazgo por marca y dato (R229: su id es la marca y el dato, nunca los estados ni los
    textos que hoy junta): los campos de armado a los que les falta su valor van juntos («armado»);
    la altura repetida de la planta más alta, uno por hoja. Cada estado de las colocaciones de ese
    dato (supuesto, de otra hoja, sin separación…) es una parte de su mensaje."""
    grupos: dict[tuple[str, str, str], dict[str, list[tuple[Elemento, str, _Estado]]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for e in ctx.elementos:
        if not e.marca:
            continue  # sin marca: su aviso por familia (verificación 1) dice lo que les falta
        for campo in CRITICOS.get(e.familia, ()):
            if e.definicion == "ninguna" and campo in _DE_LA_DEFINICION:
                # Sin definición ni nota de familia: lo dice su verificación 1 (con lo que usa).
                continue
            for estado in _estados(ctx, e, campo):
                if campo == "altura_m" and estado.estado == "supuesto":
                    # La altura que se repite en la planta más alta es de la hoja, no de la marca.
                    llave = ("", e.hoja, campo)
                    sub = f"{estado.estado}: {estado.detalle}"
                elif campo in _ARMADO and estado.estado in _SIN_VALOR:
                    llave, sub = (e.marca, "", "armado"), estado.estado
                else:
                    llave, sub = (e.marca, "", campo), estado.estado
                grupos[llave][sub].append((e, campo, estado))
        for estado in _variante(e):
            grupos[(e.marca, "", "variante")]["variante"].append((e, "seccion_cm", estado))
    salida: list[Verificacion] = []
    cubiertas: set[tuple[str, str]] = set()  # (element_id, campo) que ya tienen su hallazgo
    for (marca, hoja, grupo), por_estado in sorted(grupos.items()):
        partes = []
        for sub, ternas in sorted(
            por_estado.items(), key=lambda x: _ORDEN_DE_ESTADO.get(x[0].split(":")[0], 9)
        ):
            for e, campo, _s in ternas:
                cubiertas.add((e.element_id, "variante" if grupo == "variante" else campo))
            partes.append(_hallazgo_critico(ctx, marca, sub.split(":")[0], sub, ternas))
        salida.append(_combinar(partes, marca, hoja, grupo))
    salida += _dudosas_de_colocacion(ctx)
    salida += _dudas_sin_hallazgo(ctx, cubiertas)
    return salida


_ORDEN_DE_ESTADO = {
    "falta": 0,
    "por_leer": 1,
    "sin_separacion": 2,
    "dos_secciones": 3,
    "supuesto": 4,
    "ia": 5,
    "de_otra_hoja": 6,
    "medida_en_planta": 7,
    "variante": 8,
}


def _combinar(partes: list[Verificacion], marca: str, hoja: str, grupo: str) -> Verificacion:
    """Las partes de un mismo dato de una marca (o de una hoja) en un solo hallazgo, con el id de
    la marca, la hoja y el dato: su severidad es la peor, su mensaje el de cada parte, lo que está
    en juego el mayor de cada cifra (las partes tocan las mismas piezas)."""
    severidad = min((v.severidad for v in partes), key=lambda x: _RANGO_DE_SEVERIDAD[x])
    juego: dict[str, float] = {}
    for v in partes:
        for k, x in v.en_juego.items():
            juego[k] = max(juego.get(k, 0.0), x)
    cantidades = {v.cantidad for v in partes}
    cantidad: Literal["conocida", "desconocida", "estimada"] = (
        "desconocida" if "desconocida" in cantidades else "conocida"
    )
    elementos = list(dict.fromkeys(e for v in partes for e in v.elementos))
    unica = partes[0] if len(partes) == 1 else None
    campos = list(dict.fromkeys(c for v in partes for c in v.campo.split(",") if c))
    return Verificacion(
        id=id_de_verificacion(7, marca, hoja, grupo),
        numero=7,
        severidad=severidad,
        mensaje=" ".join(v.mensaje for v in partes),
        marcas=list(dict.fromkeys(m for v in partes for m in v.marcas)),
        elementos=elementos,
        datos=[d for v in partes for d in v.datos][:6],
        hoja=unica.hoja if unica is not None else (hoja or partes[0].hoja),
        bbox=unica.bbox if unica is not None else None,
        campo=grupo if grupo in ("armado", "variante") else ",".join(campos),
        textos=list(dict.fromkeys(t for v in partes for t in v.textos)),
        en_juego=juego,
        cantidad=cantidad,
    )


def _estados(ctx: _Contexto, e: Elemento, campo: str) -> list[_Estado]:
    dato: Dato | None = getattr(e, campo)
    familia = e.familia
    definicion = ctx.por_marca.get(e.marca)
    sin_leer = definicion.sin_leer.get(campo) if definicion is not None else None
    if campo == "estribos" and dato is None and not sin_leer and _una_varilla(e):
        # Una sola varilla sin estribos ni texto suyo sin leer: la forma de un castillo ahogado.
        return [
            _Estado(
                "sin_estribos_declarados",
                "aviso",
                "una sola varilla y ningún estribo escrito (la forma de un castillo ahogado): no "
                "lleva estribos que pesar",
            )
        ]
    if dato is None or dato.valor is None:
        textos = _textos_ilegibles(dato) if dato is not None else []
        if sin_leer:
            textos.append(sin_leer)
        if textos:  # el plano lo escribe y no se leyó
            return [_Estado("por_leer", "bloquea", ", ".join(_entre_comillas(textos)), dato)]
        return [_Estado("falta", "bloquea", _falta(ctx, e, campo), dato)]
    estados: list[_Estado] = []
    propias = [m for m in miembros(dato) if m.ilegible and e.hoja in hojas_de(m)]
    if dato.fuente == "supuesto":
        estados.append(_Estado("supuesto", "duda", _supuesto(ctx, e, campo, dato), dato))
    elif dato.fuente == "ia":
        estados.append(_Estado("ia", "duda", _una_linea(dato.texto), dato))
    elif dato.fuente == "medido" and any(a.ilegible for a in dato.alternativas):
        ilegibles = _textos_ilegibles(dato)
        estados.append(
            _Estado(
                "medida_en_planta",
                "duda",
                f"su detalle la dibuja y no se leyó ({', '.join(_entre_comillas(ilegibles))}); "
                f"se usa lo medido en planta: {_una_linea(dato.texto)}",
                dato,
            )
        )
    elif e.hoja and dato.hoja and e.hoja not in hojas_de(dato) and propias:
        estados.append(
            _Estado(
                "de_otra_hoja",
                "duda",
                f"su hoja {e.hoja} {_pron([campo])} dibuja y no se leyó "
                f"({', '.join(_entre_comillas(_una_linea(m.texto) for m in propias))}); se usa "
                f"lo leído en {', '.join(hojas_de(dato))}",
                dato,
            )
        )
    if campo == "estribos":
        estados += _sin_separacion(familia, dato)
    if campo == "seccion_cm":
        dos = _dos_secciones(ctx, e)
        if dos is not None:
            estados.append(dos)
    return estados


def _secciones_por_hoja(dato: Dato) -> dict[str, list[Dato]]:
    """Las secciones que el plano lee de una marca en cada hoja, distintas, del rango más alto que
    lee en esa hoja (una sección dibujada a escala no es otro corte de una acotada)."""
    por_hoja: dict[str, dict[int, dict[str, Dato]]] = defaultdict(lambda: defaultdict(dict))
    for m in miembros(dato):
        if m.fuente not in _LEIDAS or m.ilegible or m.valor is None:
            continue
        for h in hojas_de(m):
            de_rango = por_hoja[h][PRECEDENCIA[m.fuente]]
            llave = _llave_de_valor(m.valor)
            # La sección acotada en su corte, antes que la llamada que la nombra junto con la
            # otra («SECCIÓN 1 30X60, SECCIÓN 2 30X70»): así cada corte cita su propio título.
            if llave not in de_rango or (_es_llamada(de_rango[llave]) and not _es_llamada(m)):
                de_rango[llave] = m
    return {h: list(rangos[max(rangos)].values()) for h, rangos in por_hoja.items()}


def _es_llamada(m: Dato) -> bool:
    return "(se toma la mayor)" in (m.texto or "")


def _dos_secciones(ctx: _Contexto, e: Elemento) -> _Estado | None:
    """R225: el plano dibuja dos (o más) secciones de una marca en una misma hoja («SECCIÓN 1» y
    «SECCIÓN 2» de una contratrabe): no se contradice, dibuja dos cortes; se toma una (la mayor) y
    se dice, con lo que cambia en concreto."""
    definicion = ctx.por_marca.get(e.marca)
    if definicion is None or definicion.seccion_cm is None or definicion.variantes:
        return None  # las variantes por muro no son cortes: cada una es de su muro
    hojas = {h: ms for h, ms in _secciones_por_hoja(definicion.seccion_cm).items() if len(ms) > 1}
    if not hojas:
        return None
    partes, valores = [], []
    for h, ms in sorted(hojas.items()):
        titulos = {ctx.handle(m.entidades[0]) for m in ms if m.entidades}
        if len(titulos) == 1 and all(m.entidades for m in ms):
            # Un mismo título escribe los dos cortes: se cita una vez.
            lista = ", ".join(_valor("seccion_cm", m.valor) for m in ms) + (
                f" (título {next(iter(titulos))})"
            )
        else:
            lista = ", ".join(
                f"{_valor('seccion_cm', m.valor)}"
                + (f" (título {ctx.handle(m.entidades[0])})" if m.entidades else "")
                for m in ms
            )
        partes.append(f"en {h}: {lista}")
        valores += [m.valor for m in ms]
    return _Estado("dos_secciones", "duda", "; ".join(partes), e.seccion_cm, valores=valores)


def _entre_comillas(textos: Iterable[str]) -> list[str]:
    return [t if t.startswith("«") else f"«{t}»" for t in dict.fromkeys(textos) if t]


def _sin_separacion(familia: str, dato: Dato) -> list[_Estado]:
    """Unos estribos que no dicen su separación (o la remiten a un corte que no se lee): no se
    pesan. ``duda`` si Klave supone una separación para la familia, si no ``bloquea``."""
    sin_sep = [
        j
        for j in _juegos(dato.valor)
        if not j.zonas or any(z.separacion_m is None for z in j.zonas)
    ]
    if not sin_sep:
        return []
    supuesto = _separacion_supuesta(familia)
    partes = []
    for j in sin_sep:
        texto = texto_estribos(Armado(estribos=[j]))
        if j.referencia is not None and not j.zonas:
            partes.append(f"«{texto}» remite su separación a «{j.referencia}», que no se lee")
        else:
            partes.append(f"«{texto}» no dice su separación")
    if supuesto is not None:
        detalle = (
            f"{'; '.join(partes)}; el supuesto de la familia {familia} es @{supuesto:g} cm, que "
            "la cuenta de acero no aplica: esos estribos no se pesan"
        )
        return [_Estado("sin_separacion", "duda", detalle, dato)]
    detalle = (
        f"{'; '.join(partes)}, y la familia {familia} no tiene una separación supuesta: esos "
        "estribos no se pesan"
    )
    return [_Estado("sin_separacion", "bloquea", detalle, dato)]


def _una_varilla(e: Elemento) -> bool:
    valor = e.longitudinales.valor if e.longitudinales is not None else None
    return sum(g.cantidad for g in _grupos(valor)) == 1


def _textos_ilegibles(dato: Dato) -> list[str]:
    return list(
        dict.fromkeys(
            _una_linea(m.texto) for m in [dato, *dato.alternativas] if m.ilegible and m.texto
        )
    )


def _separacion_supuesta(familia: str) -> float | None:
    """La separación (cm) del armado que Klave supone para la familia, si supone uno."""
    supuestos = SteelAssumptions()
    armado = {"castillo": supuestos.default_castillo, "dala": supuestos.default_dala}.get(familia)
    if armado is None:
        return None
    m = re.search(r"@\s*(\d+(?:\.\d+)?)", armado[1])
    return float(m.group(1)) if m else None


def _falta(ctx: _Contexto, e: Elemento, campo: str) -> str:
    """Por qué falta un dato sin supuesto, con lo que el plano dice de él si dice algo; vacío si
    sólo no lo da."""
    if campo == "longitud_m" and e.familia == "pilote":
        notas = _notas_de_pilotes(ctx)
        dice = f"; lo que el plano dice de las longitudes: {'; '.join(notas)}" if notas else ""
        return f"el plano no declara la longitud del pilote{dice}"
    aviso = next((a for a in e.avisos if a.startswith(f"{_CORTO[campo]}:")), "")
    return aviso.split(":", 1)[1].strip() if aviso else ""


# Una frase de una nota que habla de la longitud de los pilotes.
_FRASE_DE_PILOTE = re.compile(r"[^.;]*\bPILOTES?\b[^.;]*")


def _notas_de_pilotes(ctx: _Contexto) -> list[str]:
    """Las frases de las notas que hablan de la longitud de los pilotes, cada una una vez, citada
    por el handle de su primera copia y cuántas copias tiene (una vez por corrida)."""
    if ctx.notas_de_pilotes is None:
        ctx.notas_de_pilotes = _leer_notas_de_pilotes(ctx)
    return list(ctx.notas_de_pilotes)


def _leer_notas_de_pilotes(ctx: _Contexto) -> list[str]:
    copias: dict[str, list[str]] = defaultdict(list)
    for e in ctx.entidades.values():
        if not e.is_textual or not e.text:
            continue
        for frase in _FRASE_DE_PILOTE.findall(_una_linea(e.text).upper()):
            if re.search(r"LONGITUD|MEC[AÁ]NICA DE SUELOS|DESPLANTE|PROFUNDIDAD", frase):
                copias[_una_linea(frase)].append(_handle_de(e))
    salida = []
    for frase, handles in sorted(copias.items(), key=lambda x: (-len(x[1]), x[0]))[:4]:
        corta = frase if len(frase) <= 160 else f"{frase[:157]}…"
        mas = f" (y {len(handles) - 1} copias)" if len(handles) > 1 else ""
        salida.append(f"«{corta}» {sorted(handles)[0]}{mas}")
    return salida


def _supuesto(ctx: _Contexto, e: Elemento, campo: str, dato: Dato) -> str:
    """El supuesto que se usa y, para una sección cuyo detalle no se leyó, las cotas que el plano
    escribe junto al título de ese detalle (por handle: CTA-11 acota «70» y «25» en ES-004)."""
    detalle = _una_linea(dato.texto) or "supuesto de Klave"
    if campo != "seccion_cm":
        return detalle
    definicion = ctx.por_marca.get(e.marca)
    if definicion is None or definicion.seccion_cm is None:
        return detalle
    lados = {float(v) for v in dato.valor} if isinstance(dato.valor, list | tuple) else set()
    acotado, ajenas = [], False
    for m in miembros(definicion.seccion_cm):
        if not m.ilegible or not m.entidades or m.entidades[0] not in ctx.entidades:
            continue
        titulo = ctx.entidades[m.entidades[0]]
        cotas = _cotas_junto_a(ctx, titulo)
        if not cotas:
            continue
        ajenas = ajenas or any(v not in lados for v, _h in cotas)
        lista = ", ".join(f"«{v:g}» {h}" for v, h in cotas)
        acotado.append(f"{lista} en {m.hoja or ctx.hoja_de(titulo)} (título {_handle_de(titulo)})")
    if acotado:
        detalle += (
            f"; junto al título de su detalle el plano acota {'; '.join(acotado)}, que no se tomó"
        )
        if ajenas:
            detalle += ": la supuesta no coincide con lo acotado"
    return detalle


# Las cotas junto al título de un detalle: a lo más esto, en altos del título, y del tamaño de un
# lado de sección (cm, como las escribe el plano).
_COTAS_DEL_TITULO = 20.0
_LADO_DE_SECCION = (8.0, 150.0)


def _cotas_junto_a(ctx: _Contexto, titulo: NormalizedEntity) -> list[tuple[float, str]]:
    """Las cotas de la sección junto a un título (su número escrito, redondeado al décimo, y su
    handle): la horizontal más cercana y las que miden su mismo tramo en x, la vertical más
    cercana y las que miden su mismo tramo en y (R234: una cota fuera del tramo de la sección es
    de otra pieza)."""
    alcance = _COTAS_DEL_TITULO * alto_de_texto(titulo)
    if ctx.cotas_de_lado is None:
        ctx.cotas_de_lado = defaultdict(list)
        for d in ctx.entidades.values():
            if d.entity_type.value != "dimension":
                continue
            valor = _numero(d.properties.get("display_value"))
            if valor is not None and _LADO_DE_SECCION[0] <= valor <= _LADO_DE_SECCION[1]:
                ctx.cotas_de_lado[d.source_file].append((valor, d))
    cerca = []
    for valor, d in ctx.cotas_de_lado.get(titulo.source_file, []):
        if _hueco(d.bbox, titulo.bbox) <= alcance:
            cerca.append((round(valor, 1), d, _hueco(d.bbox, titulo.bbox)))
    cerca.sort(key=lambda x: x[2])
    salida = []
    for eje in (0, 1):  # 0: horizontales (miden en x), 1: verticales (miden en y)
        de_eje = [c for c in cerca if _eje_de_cota(c[1]) == eje]
        if not de_eje:
            continue
        guia = de_eje[0][1].bbox
        salida += [
            c for c in de_eje if c[1].bbox[2 + eje] > guia[eje] and c[1].bbox[eje] < guia[2 + eje]
        ]
    salida += [c for c in cerca if _eje_de_cota(c[1]) is None]
    return [(v, _handle_de(d)) for v, d, _g in sorted(salida, key=lambda x: x[2])]


def _eje_de_cota(d: NormalizedEntity) -> int | None:
    """0 si la cota mide en x (horizontal), 1 si mide en y (vertical), ``None`` si no se sabe."""
    angulo = _numero(d.properties.get("angle"))
    if angulo is None:
        return None
    resto = angulo % 180
    return 0 if min(resto, 180 - resto) < 1 else 1 if abs(resto - 90) < 1 else None


def _numero_texto(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except ValueError:
        return None


def _variante(e: Elemento) -> list[_Estado]:
    """Una colocación de una marca con variantes por muro que no se sabe cuál toma."""
    dudas = [d for d in e.dudas if d.startswith("variante de ")]
    if not dudas:
        return []
    return [_Estado("variante", "duda", dudas[0].split(": ", 1)[-1], e.seccion_cm)]


def _hallazgo_critico(
    ctx: _Contexto,
    marca: str,
    nombre: str,
    detalle_de_grupo: str,
    ternas: list[tuple[Elemento, str, _Estado]],
) -> Verificacion:
    els = list({e.element_id: e for e, _c, _s in ternas}.values())
    campos = sorted({c for _e, c, _s in ternas}, key=lambda c: list(_NOMBRE).index(c))
    estados = [s for _e, _c, s in ternas]
    severidad = min((s.severidad for s in estados), key=lambda s: _RANGO_DE_SEVERIDAD[s])
    donde = f"{_pzas(len(els))} en {_hojas(els)}"
    pron = _pron(campos)
    nombres = _nombres(campos)
    sujeto = nombres[0].upper() + nombres[1:]
    quien = marca or _listar(sorted({e.marca for e in els}))
    son = "son" if _plural(campos) else "es"

    def detalles(campo: str | None = None) -> str:
        lista = list(
            dict.fromkeys(s.detalle for _e, c, s in ternas if s.detalle and campo in (None, c))
        )
        texto = "; ".join(lista[:4])
        return texto + (f" (y {len(lista) - 4} más)" if len(lista) > 4 else "")

    valor = next(
        (s.dato.valor for s in estados if s.dato is not None and s.dato.valor is not None), None
    )
    dice = detalles()
    texto_valor = _valor(campos[0], valor)
    desconocida = f" Cantidad desconocida: {_pzas(len(els))}."
    if nombre == "falta":
        porque = dice or f"el plano no {pron} da"
        mensaje = (
            f"{sujeto} de {quien} ({donde}): {porque}; no hay un supuesto que {pron} sustituya: "
            f"{_consecuencia(campos)}.{desconocida}"
        )
    elif nombre == "por_leer":
        por_campo = (
            "; ".join(f"{_CORTO[c]}: {detalles(c)}" for c in campos) if len(campos) > 1 else dice
        )
        leidos = "leyeron" if _plural(campos) else "leyó"
        mensaje = (
            f"{sujeto} de {quien} ({donde}): el plano {pron} escribe y no se {leidos} "
            f"({por_campo}); no hay un supuesto que {pron} sustituya: {_consecuencia(campos)}, "
            f"por leer.{desconocida}"
        )
    elif nombre == "supuesto" and campos == ["altura_m"]:
        hoja = _hoja_unica(els) or _hojas(els)
        mensaje = (
            f"La altura de los castillos y columnas de {hoja} ({len(els)} colocaciones de "
            f"{_listar(sorted({e.marca for e in els}))}) es un supuesto: {dice}. Confírmala."
        )
    elif nombre == "supuesto":
        mensaje = (
            f"{sujeto} de {quien} ({donde}) {son} un supuesto: se usa {texto_valor} ({dice}). "
            f"Confírma{pron}."
        )
    elif nombre == "ia":
        mensaje = (
            f"{sujeto} de {quien} ({donde}): sólo {pron} dice la lectura IA, {texto_valor} "
            f"({dice}); el plano no {pron} dice. Por confirmar."
        )
    elif nombre == "de_otra_hoja":
        por_hoja: dict[str, tuple[set[str], set[str], set[str]]] = defaultdict(
            lambda: (set(), set(), set())
        )
        for e, campo, s in ternas:
            if s.dato is None:
                continue
            ilegibles, leidas, valores = por_hoja[e.hoja]
            ilegibles |= {
                _una_linea(m.texto)
                for m in miembros(s.dato)
                if m.ilegible and e.hoja in hojas_de(m)
            }
            leidas |= set(hojas_de(s.dato))
            valores.add(_valor(campo, s.dato.valor))
        partes = [
            f"su hoja {h} {pron} dibuja y no se pudo leer "
            f"({', '.join(_entre_comillas(sorted(i)))}); se usa lo leído en "
            f"{', '.join(sorted(lh))}: {_listar(sorted(v))}"
            for h, (i, lh, v) in sorted(por_hoja.items())
        ]
        mensaje = (
            f"{sujeto} de {quien} ({donde}): {'; '.join(partes)}. Las hojas pueden decir cosas "
            f"distintas; confírma{pron}."
        )
    elif nombre == "medida_en_planta":
        sin_leer = sorted(
            {t for s in estados if s.dato is not None for t in _textos_ilegibles(s.dato)}
        )
        por_valor: dict[str, set[str]] = defaultdict(set)
        for e, _c, s in ternas:
            if s.dato is not None:
                por_valor[_valor(campos[0], s.dato.valor)].add(_nombre_de_hoja(e.hoja))
        medidas = [f"{v} ({', '.join(sorted(h))})" for v, h in sorted(por_valor.items())]
        mensaje = (
            f"{sujeto} de {quien} ({donde}): su detalle {pron} dibuja y no se leyó "
            f"({', '.join(_entre_comillas(sin_leer))}); se usa lo medido en planta, el contorno "
            f"de su colocación: {_listar(medidas)}. Confírma{pron}."
        )
    elif nombre == "sin_separacion":
        mensaje = f"Los estribos de {quien} ({donde}): {dice}." + (
            desconocida if severidad == "bloquea" else ""
        )
    elif nombre == "dos_secciones":
        usados = list(
            dict.fromkeys(
                _llave_de_valor(s.dato.valor)
                for s in estados
                if s.dato is not None and s.dato.valor
            )
        )
        cortes = [v for s in estados for v in s.valores]
        mayor = max(cortes, key=lambda v: _area_m2(v) or 0.0) if cortes else None
        tomadas = _listar(
            sorted({_valor("seccion_cm", s.dato.valor) for s in estados if s.dato is not None})
        )
        cual = ", la mayor" if mayor is not None and usados == [_llave_de_valor(mayor)] else ""
        mensaje = (
            f"{quien} ({donde}): el plano dibuja dos secciones de la marca; {dice}; se toma "
            f"{tomadas}{cual}. Confírmalo: si el elemento cambia de sección en su largo, cada "
            "tramo lleva la suya."
        )
    elif nombre == "variante":
        mensaje = (
            f"{quien} tiene variantes por muro y en {_pzas(len(els))} ({_hojas(els)}) no se "
            f"sabe cuál toca: {dice}. Se usa su definición con las variantes juntas (sección "
            f"{_valor('seccion_cm', valor)}); confírmalo."
        )
    else:  # sin_estribos_declarados
        mensaje = f"{quien} ({donde}): {dice}."
    hoja = _hoja_unica(els)
    return _hallazgo(
        7,
        severidad,
        mensaje,
        clave=detalle_de_grupo,  # sólo una parte: el id del hallazgo lo pone ``_combinar``
        marca=marca,
        hoja=hoja,
        de_la_marca=bool(marca),
        marcas=sorted({e.marca for e in els}),
        elementos=[e.element_id for e in els],
        datos=list({id(s.dato): s.dato for s in estados if s.dato is not None}.values())[:4],
        bbox=_caja_de(ctx, els) if hoja else None,
        campo=",".join(campos),
        en_juego=_en_juego_de_campos(ctx, campos, nombre, els, estados),
        cantidad="desconocida"
        if nombre in _SIN_VALOR or (nombre == "sin_separacion" and severidad == "bloquea")
        else "conocida",
    )


def _consecuencia(campos: list[str]) -> str:
    if any(c in _GEOMETRIA for c in campos):
        return "sin ella no se cuentan su concreto ni su acero"
    return "su acero no se cuenta"


def _en_juego_de_campos(
    ctx: _Contexto,
    campos: list[str],
    nombre: str,
    els: list[Elemento],
    estados: list[_Estado] | None = None,
) -> dict[str, float]:
    """Lo que depende del dato: el concreto si es geométrico y el acero que se pesa con él (lo
    que se pierde si se quita). Sin valor no hay cifra que perder: el concreto de esas piezas
    (``volumen_m3``) dice de qué tamaño es lo que falta."""
    juego: dict[str, float] = {"piezas": float(len(els))}
    if nombre == "sin_estribos_declarados":
        return juego  # nada que falte: el plano no los declara
    sin_cifra = nombre == "sin_separacion" and any(s.severidad == "bloquea" for s in estados or [])
    if nombre in ("falta", "por_leer") or sin_cifra:
        juego["volumen_m3"] = sum(_volumen(e) or 0.0 for e in els)
        # Las piezas sin largo (un pilote sin longitud): el concreto por metro, su sección por las
        # piezas, dice su tamaño (R233).
        juego["concreto_por_metro_m3"] = sum(
            _area_m2(e.seccion_cm.valor) or 0.0
            for e in els
            if _volumen(e) is None and e.seccion_cm is not None
        )
        return juego
    if nombre == "dos_secciones":
        # R225: lo que cambia entre las secciones dibujadas, en concreto, sobre sus colocaciones.
        valores = [v for s in estados or [] for v in s.valores]
        volumenes = [sum(_volumen(e, v) or 0.0 for e in els) for v in valores]
        if volumenes:
            juego["concreto_m3"] = max(volumenes) - min(volumenes)
        return juego
    if any(c in _GEOMETRIA for c in campos):
        juego["concreto_m3"] = sum(_volumen(e) or 0.0 for e in els)
    juego["acero_kg"] = sum(
        ctx.acero(e) - ctx.acero_de(e.model_copy(update={c: None for c in campos})) for e in els
    )
    return juego


_DUDOSAS = (
    ("claro_dudoso", "claro dudoso", "longitud_m", "duda"),
    ("marcador_dudoso", "marcador dudoso", "seccion_cm", "duda"),
    ("tramo_sin_etiqueta", "tramo sin etiqueta propia", "longitud_m", "aviso"),
)


def _dudosas_de_colocacion(ctx: _Contexto) -> list[Verificacion]:
    """Lo que la colocación misma no sabe (vista, claro, marcador dudosos; un claro partido a
    medio camino sin apoyo; un tramo sin etiqueta propia sumado), por hoja y por clase. Lo que
    está en juego en una duda es el concreto de esas piezas (su valor puede estar mal entero); en
    un aviso, sólo cuántas son (la línea se cuenta una vez: lo aproximado es el reparto)."""
    grupos: dict[tuple[str, str, str, str], list[tuple[Elemento, str]]] = defaultdict(list)
    vistas = ctx.segmentation.vistas_dudosas if ctx.segmentation is not None else {}
    for e in ctx.elementos:
        d = ctx.deteccion.get(e.detection_id)
        props = d.properties if d is not None else {}
        if e.detection_id in vistas:
            grupos[(e.hoja, "vista dudosa", "altura_m", "duda")].append((e, vistas[e.detection_id]))
        for clave, nombre, campo, severidad in _DUDOSAS:
            texto = props.get(clave)
            if texto:
                grupos[(e.hoja, nombre, campo, severidad)].append((e, str(texto)))
        compartido = str(props.get("claro_compartido") or "")
        if "a medio camino" in compartido:
            grupos[(e.hoja, "claro partido a medio camino", "longitud_m", "aviso")].append(
                (e, compartido)
            )
    salida: list[Verificacion] = []
    for (hoja, nombre, campo, severidad), pares in sorted(grupos.items()):
        els = [e for e, _ in pares]
        ejemplos = [f"{e.marca or 'sin marca'} {_etiqueta(ctx, e)}: {t}" for e, t in pares]
        que = {
            "vista dudosa": "no se sabe a qué planta pertenecen (su altura y su nivel "
            "dependen de ello)",
            "claro dudoso": "su claro se midió con una línea dudosa",
            "marcador dudoso": "su marcador (de donde se mide su sección en planta) lo alcanza "
            "otra etiqueta casi igual de cerca",
            "tramo sin etiqueta propia": "se les sumó un tramo de su línea que ninguna etiqueta "
            "toma",
            "claro partido a medio camino": "su línea la comparten varias etiquetas y se partió a "
            "medio camino donde no hay apoyo: su longitud es aproximada",
        }[nombre]
        salida.append(
            _hallazgo(
                7,
                severidad,  # type: ignore[arg-type]
                f"{_colocaciones(len(els))} en {hoja or 'sin hoja'} con {nombre}: {que}. "
                + " | ".join(ejemplos[:_EJEMPLOS])
                + (f" | y {len(ejemplos) - _EJEMPLOS} más" if len(ejemplos) > _EJEMPLOS else ""),
                clave=nombre,
                hoja=hoja,
                marcas=sorted({e.marca for e in els if e.marca}),
                elementos=[e.element_id for e in els],
                bbox=_caja_de(ctx, els),
                campo=campo,
                textos=[_etiqueta(ctx, e) for e in els],
                en_juego=(
                    {"concreto_m3": sum(_volumen(e) or 0.0 for e in els), "piezas": float(len(els))}
                    if severidad == "duda"
                    else {"piezas": float(len(els))}
                ),
            )
        )
    return salida


_CAMPO_DE_DUDA = {
    "sección de ": "seccion_cm",
    "longitudinales de ": "longitudinales",
    "estribos de ": "estribos",
    "parrillas de ": "parrillas",
    "longitud de ": "longitud_m",
    "altura de ": "altura_m",
    "variante de ": "variante",
}


def _dudas_sin_hallazgo(ctx: _Contexto, cubiertas: set[tuple[str, str]]) -> list[Verificacion]:
    """Ninguna duda de un elemento se queda sin decir: la que no cubrió un hallazgo de su dato,
    junta por marca."""
    por_marca: dict[str, list[tuple[Elemento, str]]] = defaultdict(list)
    for e in ctx.elementos:
        if not e.marca:
            continue
        for duda in e.dudas:
            campo = next((c for p, c in _CAMPO_DE_DUDA.items() if duda.startswith(p)), None)
            if campo is not None and (e.element_id, campo) in cubiertas:
                continue
            por_marca[e.marca].append((e, duda))
    salida = []
    for marca, pares in sorted(por_marca.items()):
        els = list({e.element_id: e for e, _ in pares}.values())
        dudas = list(dict.fromkeys(d for _, d in pares))
        salida.append(
            _hallazgo(
                7,
                "duda",
                f"{marca} ({_pzas(len(els))} en {_hojas(els)}): " + "; ".join(dudas) + ".",
                clave="otras dudas",
                marca=marca,
                elementos=[e.element_id for e in els],
                en_juego={"piezas": float(len(els))},
            )
        )
    return salida


# ---------------------------------------------------------------- 8: el plano se contradice


def _contradicciones(ctx: _Contexto, ajenas: set[str]) -> list[Verificacion]:
    salida: list[Verificacion] = []
    salida += _definiciones_que_no_coinciden(ctx, ajenas)
    salida += _reglas_que_no_coinciden(ctx)
    salida += _codigos_de_hoja(ctx)
    salida += _entrepisos(ctx)
    return salida


def _definiciones_que_no_coinciden(ctx: _Contexto, ajenas: set[str]) -> list[Verificacion]:
    """Dos lecturas del plano del mismo rango que dicen valores distintos de un campo de una
    marca (R12: por valor, nunca por cuántas alternativas hay; una copia ilegible no cuenta). Una
    marca con variantes por muro se compara variante por variante: sus variantes no se
    contradicen, cada una es de su muro. Dos secciones en una misma hoja son dos cortes dibujados
    (R225, verificación 7), no una contradicción; un valor que es de la llamada de otra marca en
    la misma hoja no es una lectura propia (R226); las marcas de nervaduras y de acero no son de
    esta lectura."""
    salida: list[Verificacion] = []
    colocadas = _por_marca(ctx.elementos)
    ajenos = _valores_de_llamadas(ctx)
    for marca, definicion in sorted(ctx.por_marca.items()):
        if marca in ajenas:
            continue
        partes = definicion.variantes or [definicion]
        for parte in partes:
            nombre = (
                f"{marca} (para muros de {_cm(parte.para_muro_cm)} cm)"
                if parte.para_muro_cm is not None
                else marca
            )
            for campo in ("seccion_cm", "longitud_m", *_ARMADO, "recubrimiento_m"):
                dato = getattr(parte, campo)
                if dato is None:
                    continue
                grupos = _propios(_valores_leidos(dato), marca, ajenos)
                if len(grupos) < 2 or _en_una_hoja(grupos):
                    continue
                els = [
                    e
                    for e in colocadas.get(marca, [])
                    if parte.para_muro_cm is None
                    or not definicion.variantes
                    or _toma_variante(e, parte)
                ]
                salida.append(_definicion_contradicha(ctx, marca, nombre, campo, dato, grupos, els))
    return salida


def _valores_de_llamadas(ctx: _Contexto) -> dict[tuple[str, str], set[str]]:
    """(hoja, valor) → las marcas cuya llamada de corte en esa hoja escribe esa sección
    («SECCIÓN 1 28X45», leída como «sección 1 28x45, sección 2 31x30»)."""
    salida: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in ctx.inv.specs:
        if s.metodo != "llamada" or s.source == "ia":
            continue
        for a, b in re.findall(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", s.source_text.lower()):
            valor = (_numero_texto(a), _numero_texto(b))
            salida[(s.hoja, _llave_de_valor([_entero(v) for v in valor]))].add(
                normalizar_marca(s.mark, ctx.config)
            )
    return salida


def _entero(v: float | None) -> float | int | None:
    return int(v) if v is not None and float(v).is_integer() else v


def _propios(
    grupos: list[list[Dato]], marca: str, ajenos: dict[tuple[str, str], set[str]]
) -> list[list[Dato]]:
    """Los grupos de valores quitando las lecturas que no son de la marca: las de una hoja cuya
    llamada de corte de otra marca escribe ese mismo valor (R226: Z-2 «28x45» de ES-101 es la
    «SECCIÓN 1» de T1-2)."""
    salida = []
    for grupo in grupos:
        propios = [
            m
            for m in grupo
            if not any(
                ajenos.get((h, _llave_de_valor(m.valor)), set()) - {marca} for h in hojas_de(m)
            )
        ]
        if propios:
            salida.append(propios)
    return salida


def _en_una_hoja(grupos: list[list[Dato]]) -> bool:
    """Si una misma hoja lee todos los valores (dos cortes de una marca, no una contradicción)."""
    hojas = [{h for m in g for h in hojas_de(m)} for g in grupos]
    return bool(set.intersection(*hojas)) if hojas else False


def _de(campo: str) -> str:
    """«de la sección», «del recubrimiento»."""
    nombre = _NOMBRE[campo]
    return f"del {nombre[3:]}" if nombre.startswith("el ") else f"de {nombre}"


def _toma_variante(e: Elemento, variante: Definicion) -> bool:
    return any(f"para muros de {_cm(variante.para_muro_cm or 0.0)} cm»" in a for a in e.avisos)


def _valores_leidos(dato: Dato) -> list[list[Dato]]:
    """Las lecturas del plano de un dato, agrupadas por valor, del rango más alto en que dicen dos
    valores o más (vacío si nunca se contradicen)."""
    por_rango: dict[int, dict[str, list[Dato]]] = defaultdict(dict)
    for m in miembros(dato):
        if m.fuente not in _LEIDAS or m.ilegible or m.valor is None:
            continue
        por_rango[PRECEDENCIA[m.fuente]].setdefault(_llave_de_valor(m.valor), []).append(m)
    for rango in sorted(por_rango, reverse=True):
        if len(por_rango[rango]) > 1:
            return list(por_rango[rango].values())
    return []


def _definicion_contradicha(
    ctx: _Contexto,
    marca: str,
    nombre: str,
    campo: str,
    dato: Dato,
    grupos: list[list[Dato]],
    els: list[Elemento],
) -> Verificacion:
    lecturas = []
    for grupo in grupos:
        hojas = sorted({h for m in grupo for h in hojas_de(m)})
        titulos = sorted({ctx.handle(m.entidades[0]) for m in grupo if m.entidades})
        lecturas.append(
            f"{_valor(campo, grupo[0].valor)} ({', '.join(hojas) or 'sin hoja'}"
            + (f"; título {', '.join(titulos)}" if titulos else "")
            + ")"
        )
    leen = {h for g in grupos for m in g for h in hojas_de(m)}
    cada_una = bool(els) and all(e.hoja in leen for e in els)
    usado = (
        "cada colocación toma la de su hoja; las de las hojas sin lectura propia, "
        f"{_valor(campo, dato.valor)}"
        if any(e.hoja in leen for e in els)
        else f"se usa {_valor(campo, dato.valor)}"
    )
    juego = _delta(ctx, campo, grupos, els)
    if campo == "recubrimiento_m" and cada_una:
        # Un recubrimiento que cada hoja acota a su modo y que cada colocación toma de su propia
        # hoja: dicho, no una duda (lo que cambia es poco y cada hoja manda sobre lo suyo).
        return _hallazgo(
            8,
            "aviso",
            f"{nombre} tiene {len(grupos)} valores distintos {_de(campo)} en el plano: "
            f"{_listar(lecturas)}. Cada hoja usa la suya.",
            clave=campo if nombre == marca else f"{campo}: {nombre}",
            marca=marca,
            elementos=[e.element_id for e in els],
            datos=[g[0] for g in grupos],
            campo=campo,
            textos=[ctx.handle(i) for g in grupos for m in g for i in m.entidades],
            en_juego=juego,
        )
    return _hallazgo(
        8,
        "duda",
        f"{nombre} tiene {len(grupos)} valores distintos {_de(campo)} en el plano: "
        f"{_listar(lecturas)}. {usado.capitalize()}; confírmalo.",
        clave=campo if nombre == marca else f"{campo}: {nombre}",
        marca=marca,
        elementos=[e.element_id for e in els],
        datos=[g[0] for g in grupos],
        campo=campo,
        textos=[ctx.handle(i) for g in grupos for m in g for i in m.entidades],
        en_juego=juego,
    )


def _delta(
    ctx: _Contexto, campo: str, grupos: list[list[Dato]], els: list[Elemento]
) -> dict[str, float]:
    """Lo que cambia entre los valores que el plano dice: el mayor Δ de concreto (sección) o de
    acero (recalculado con cada valor) sobre las colocaciones de la marca."""
    juego: dict[str, float] = {"piezas": float(len(els))}
    if not els:
        return juego
    valores = [g[0] for g in grupos]
    if campo == "seccion_cm":
        volumenes = [sum(_volumen(e, v.valor) or 0.0 for e in els) for v in valores]
        juego["concreto_m3"] = max(volumenes) - min(volumenes)
    if campo in (*_ARMADO, "seccion_cm", "recubrimiento_m"):
        pesos = [sum(ctx.acero_de(e.model_copy(update={campo: v})) for e in els) for v in valores]
        juego["acero_kg"] = max(pesos) - min(pesos)
    return juego


# Los campos cuyos valores en disputa cambian una cantidad (lo que está en juego, Tarea 12).
CAMPOS_EN_JUEGO = ("seccion_cm", "longitud_m", *_ARMADO, "recubrimiento_m")


def valores_en_disputa(v: Verificacion, por_marca: dict[str, Definicion]) -> list[Dato]:
    """Los valores que el plano da y entre los que duda un hallazgo abierto: los de una marca que
    el plano dice distinto (verificación 8, una duda: uno por valor) o los cortes que dibuja de
    ella en una misma hoja (verificación 7, R225). Vacío si el hallazgo no duda entre valores
    que el plano da (un supuesto, un dato que falta, un aviso)."""
    if v.severidad == "aviso" or not v.marcas:
        return []
    marca = v.marcas[0].split(" (", 1)[0]
    if v.numero == 8 and v.campo in CAMPOS_EN_JUEGO and len(v.datos) >= 2:
        return [d.model_copy(deep=True) for d in v.datos]
    if v.numero == 7 and "seccion_cm" in v.campo.split(","):
        definicion = por_marca.get(marca)
        if definicion is None or definicion.seccion_cm is None or definicion.variantes:
            return []
        valores: dict[str, Dato] = {}
        for ms in _secciones_por_hoja(definicion.seccion_cm).values():
            if len(ms) > 1:
                for m in ms:
                    valores.setdefault(_llave_de_valor(m.valor), m)
        return [d.model_copy(deep=True) for d in valores.values()] if len(valores) > 1 else []
    return []


def volumen(e: Elemento) -> float | None:
    """El concreto del elemento (m³) con su sección y su largo; ``None`` si le falta alguno."""
    return _volumen(e)


_REGLAS_SIMPLES: tuple[tuple[str, str], ...] = (
    ("soldar_desde_numero", "la varilla desde la que se suelda"),
    ("traslape_max_numero", "la varilla hasta la que se traslapa"),
    ("gancho_estribo", "el gancho de los estribos"),
    ("gancho_grapa", "el gancho de las grapas"),
    ("plantilla_espesor_m", "el espesor de la plantilla"),
    ("tabla_varillas", "la tabla de varillas"),
)
_REGLAS_POR_FAMILIA: tuple[tuple[str, str], ...] = (
    ("recubrimiento_m", "el recubrimiento de"),
    ("primer_estribo_m", "el primer estribo de"),
    ("anclajes_declarados_m", "el anclaje de"),
    ("fy_kg_cm2", "el fy del #"),
)


def _reglas_que_no_coinciden(ctx: _Contexto) -> list[Verificacion]:
    """Las reglas que el plano dice distinto DENTRO del alcance de una misma hoja (que la
    cimentación traslape hasta el #6 y las plantas hasta el #8 es de cada hoja, no una
    contradicción): dos copias de una regla en una hoja que no coinciden, la tabla de varillas de
    una hoja que da traslape donde su nota manda soldar, y una hoja con elementos que no trae su
    propia copia de una regla en la que las hojas no coinciden."""
    salida: list[Verificacion] = []
    reglas = ctx.reglas
    datos: list[tuple[str, Dato]] = []
    for atributo, nombre in _REGLAS_SIMPLES:
        dato = getattr(reglas, atributo)
        if dato is not None:
            datos.append((nombre, dato))
    for atributo, nombre in _REGLAS_POR_FAMILIA:
        for clave, dato in sorted(getattr(reglas, atributo).items()):
            datos.append((f"{nombre}{'' if nombre.endswith('#') else ' '}{clave}", dato))
    hojas_con_elementos = sorted({e.hoja for e in ctx.elementos if e.hoja})
    for nombre, dato in datos:
        por_hoja: dict[str, dict[str, Dato]] = defaultdict(dict)
        for m in miembros(dato):
            if m.fuente not in _LEIDAS or m.ilegible or m.valor is None:
                continue
            for h in hojas_de(m):
                por_hoja[h].setdefault(_llave_de_valor(m.valor), m)
        en_una = {h: list(v.values()) for h, v in por_hoja.items() if len(v) > 1}
        for _firma, hojas in _agrupar_hojas(en_una).items():
            valores = en_una[hojas[0]]
            salida.append(
                _hallazgo(
                    8,
                    "duda",
                    f"En {_listar(hojas)} el plano dice dos cosas distintas sobre {nombre}: "
                    + _listar([f"«{_una_linea(m.texto)}»" for m in valores])
                    + ". Una misma hoja no puede usar las dos; confirma cuál vale.",
                    clave=f"regla en una hoja: {nombre}",
                    hoja=hojas[0],
                    datos=valores,
                    textos=[ctx.handle(i) for m in valores for i in m.entidades],
                )
            )
        valores_distintos = {k for v in por_hoja.values() for k in v}
        if len(valores_distintos) > 1:
            sin_copia = [h for h in hojas_con_elementos if h not in por_hoja]
            if sin_copia:
                salida.append(
                    _hallazgo(
                        8,
                        "duda",
                        f"Las hojas no dicen lo mismo sobre {nombre} y {_listar(sin_copia)}, con "
                        f"elementos, no trae su propia copia: se usa «{_una_linea(dato.texto)}» "
                        f"({', '.join(hojas_de(dato))}). Confirma cuál vale para esa hoja.",
                        clave=f"regla sin copia propia: {nombre}",
                        hoja=sin_copia[0],
                        datos=[dato],
                        textos=[ctx.handle(i) for i in dato.entidades],
                    )
                )
    salida += _soldar_contra_tabla(ctx)
    return salida


def _agrupar_hojas(en_una: dict[str, list[Dato]]) -> dict[str, list[str]]:
    grupos: dict[str, list[str]] = defaultdict(list)
    for hoja, valores in sorted(en_una.items()):
        firma = " | ".join(sorted(_llave_de_valor(m.valor) for m in valores))
        grupos[firma].append(hoja)
    return grupos


def _soldar_contra_tabla(ctx: _Contexto) -> list[Verificacion]:
    """La tabla de varillas de una hoja da traslape para varillas que la nota de esa misma hoja
    manda soldar: dentro de la hoja, el plano se contradice."""
    soldar = ctx.reglas.soldar_desde_numero
    tabla = ctx.reglas.tabla_varillas
    if soldar is None or tabla.fuente != "cuadro":
        return []
    copias: dict[str, Dato] = {}
    for m in miembros(tabla):
        if m.fuente == "cuadro" and not m.ilegible and isinstance(m.valor, dict):
            for h in hojas_de(m):
                copias.setdefault(h, m)
    grupos: dict[tuple[str, tuple[str, ...]], list[str]] = defaultdict(list)
    notas: dict[tuple[str, tuple[str, ...]], Dato] = {}
    for nota in miembros(soldar):
        desde = _numero_texto(str(nota.valor)) if nota.valor is not None else None
        if nota.fuente not in _LEIDAS or nota.ilegible or desde is None:
            continue
        for hoja in hojas_de(nota):
            copia = copias.get(hoja)
            if copia is None:
                continue
            con_traslape = tuple(
                n
                for n, fila in sorted(copia.valor.items(), key=lambda x: float(x[0]))
                if float(n) >= desde and _traslape(fila)
            )
            if con_traslape:
                grupos[(str(nota.valor), con_traslape)].append(hoja)
                notas[(str(nota.valor), con_traslape)] = nota
    salida = []
    for (desde_txt, numeros), hojas in sorted(grupos.items()):
        nota = notas[(desde_txt, numeros)]
        salida.append(
            _hallazgo(
                8,
                "duda",
                f"En {_listar(sorted(hojas))} la tabla de varillas da traslape para "
                f"{_listar([f'#{n}' for n in numeros])}, pero la nota de esa misma hoja dice que "
                f"del #{desde_txt} en adelante se suelda («{_una_linea(nota.texto)}»): ¿se "
                "traslapan "
                "o se sueldan? Confírmalo.",
                clave="tabla contra soldadura",
                hoja=sorted(hojas)[0],
                datos=[nota],
                textos=[ctx.handle(i) for i in nota.entidades],
            )
        )
    return salida


def _traslape(fila: Any) -> bool:
    if isinstance(fila, BaseModel):
        fila = fila.model_dump()
    return isinstance(fila, dict) and any(fila.get(k) is not None for k in ("LT1", "LT2"))


def _codigos_de_hoja(ctx: _Contexto) -> list[Verificacion]:
    """Un código de hoja que llevan dos marcos distintos: lo que se lee en uno y en otro queda
    bajo el mismo nombre y no se puede separar."""
    marcos: dict[str, list[SheetFrame]] = defaultdict(list)
    for f in ctx.frames:
        if f.code:
            marcos[f.code].append(f)
    salida = []
    for codigo, mismos in sorted(marcos.items()):
        if len(mismos) < 2:
            continue
        nombres = ", ".join(
            f"{m.frame_id} de {(m.source_file or 'sin archivo').rsplit('/', 1)[-1]}" for m in mismos
        )
        salida.append(
            _hallazgo(
                8,
                "duda",
                f"La hoja «{codigo}» la llevan {len(mismos)} marcos distintos ({nombres}): sus "
                "lecturas y sus reglas quedan bajo el mismo nombre y no se pueden separar. "
                "Confirma cuál es cuál.",
                clave="código de hoja repetido",
                hoja=codigo,
            )
        )
    return salida


def _entrepisos(ctx: _Contexto) -> list[Verificacion]:
    """Los entrepisos contados de dos maneras a la vez: las alturas suponen que cada juego de
    castillos y columnas sube desde su losa (la planta más alta repite la altura de la de abajo,
    porque no hay nivel encima), pero las cantidades dejan fuera el juego de la cimentación como
    si fuera el mismo que el de la planta de arriba en su base. Se dicen las dos lecturas que sí
    se sostienen y lo que cada una cambia; no se escoge ninguna."""
    seg = ctx.segmentation
    if seg is None:
        return []
    alturas = seg.alturas_de_entrepiso()
    vistas = sorted(
        (
            v
            for v in seg.structural_plan_views()
            if v.npt_level is not None and v.view_id in alturas
        ),
        key=lambda v: v.npt_level or 0.0,
    )
    if len(vistas) < 2:
        return []
    cimentacion = [v for v in vistas if v.level_key == "cimentacion"]
    tope = vistas[-1]
    columnas = [e for e in ctx.elementos if e.familia in _CON_ALTURA]
    por_vista: dict[str, list[Elemento]] = defaultdict(list)
    for e in columnas:
        por_vista[e.vista or ""].append(e)
    if not cimentacion or not alturas[tope.view_id].repetida:
        return []
    if not any(por_vista.get(v.view_id) for v in cimentacion) or not por_vista.get(tope.view_id):
        return []
    if any(alturas[v.view_id].repetida for v in cimentacion):
        return []
    niveles = [float(v.npt_level or 0.0) for v in vistas]
    ids = [v.view_id for v in vistas]
    de_cimentacion = {v.view_id for v in cimentacion}
    hoy = {vid: (None if vid in de_cimentacion else alturas[vid].altura_m) for vid in ids}
    sube = {
        vid: (round(niveles[i + 1] - niveles[i], 3) if i + 1 < len(ids) else None)
        for i, vid in enumerate(ids)
    }
    baja = {
        vid: (round(niveles[i] - niveles[i - 1], 3) if i > 0 else None) for i, vid in enumerate(ids)
    }

    def cuenta(alturas_de: dict[str, float | None]) -> tuple[float, float]:
        kg = m3 = 0.0
        for vid, els in por_vista.items():
            alto = alturas_de.get(vid)
            if alto is None or alto <= 0:
                continue
            for e in els:
                copia = e.model_copy(update={"altura_m": Dato(valor=alto, fuente="nota")})
                kg += ctx.acero_de(copia)
                m3 += _volumen(e, largo=alto) or 0.0
        return kg, m3

    kg_hoy, m3_hoy = cuenta(hoy)
    kg_a, m3_a = cuenta(sube)
    kg_b, m3_b = cuenta(baja)
    nombre = {v.view_id: v.title.split(" · ")[0] for v in vistas}
    juegos = [nombre[v] for v in ids if por_vista.get(v)]
    lista_niveles = ", ".join(f"{n:+.2f}" for n in niveles)

    def alturas_txt(alturas_de: dict[str, float | None]) -> str:
        return ", ".join(
            f"{nombre[v]} {alturas_de[v]:g} m"
            for v in ids
            if alturas_de.get(v) and por_vista.get(v)
        )

    base = ", ".join(nombre[v] for v in ids if v in de_cimentacion)
    supuestas = {**sube, tope.view_id: alturas[tope.view_id].altura_m}
    mensaje = (
        f"Los entrepisos se cuentan de dos maneras a la vez. El plano declara {len(niveles)} "
        f"niveles ({lista_niveles}: {len(niveles) - 1} entrepisos) y dibuja "
        f"{len(juegos)} juegos de castillos y columnas, uno por planta ({', '.join(juegos)}). "
        f"Las alturas suponen que cada juego sube desde su losa ({alturas_txt(supuestas)}"
        f"; la de {nombre[tope.view_id]} repite la de abajo porque no hay nivel encima). Las "
        f"cantidades, en cambio, dejan fuera el juego de {base}: lo toman por el mismo de la "
        f"planta de arriba en su base. Las dos lecturas que se sostienen: (A) cada juego sube "
        f"desde su losa: el de {base} es el del primer entrepiso y sobre "
        f"{nombre[tope.view_id]} no se cuenta nada ({alturas_txt(sube)}): "
        f"acero {kg_a:,.2f} kg, concreto {m3_a:,.2f} m³; (B) "
        f"cada juego está bajo su losa: el de {base} no se cuenta y las alturas son "
        f"{alturas_txt(baja)}: acero {kg_b:,.2f} kg, concreto {m3_b:,.2f} m³. Hoy se cuenta "
        f"acero {kg_hoy:,.2f} kg y concreto {m3_hoy:,.2f} m³, que no es ninguna de las dos. "
        "Decide cuál vale; la lectura no la escoge."
    )
    afectados = [e for v in (*cimentacion, tope) for e in por_vista.get(v.view_id, [])]
    return [
        _hallazgo(
            8,
            "duda",
            mensaje,
            clave="entrepisos",
            marcas=sorted({e.marca for e in afectados if e.marca}),
            elementos=[e.element_id for e in afectados],
            campo="altura_m",
            en_juego={
                "acero_kg": max(abs(kg_a - kg_hoy), abs(kg_b - kg_hoy)),
                "concreto_m3": max(abs(m3_a - m3_hoy), abs(m3_b - m3_hoy)),
                "piezas": float(len(afectados)),
            },
        )
    ]


# ------------------------------------------------------------------- 11: lo que nadie leyó


def _sin_dueno(ctx: _Contexto) -> tuple[list[Verificacion], list[Verificacion], set[str]]:
    """(los hallazgos de la verificación 11 que son de una clase o de las reglas, los que son de
    una marca: lo escrito junto a su sección, lo que avisan sus lecturas, lo que sólo dice la
    IA; y los textos que ya cita lo escrito junto a su sección). Los de una marca se juntan con
    su hallazgo de dato crítico o en uno solo por marca, y los textos sin leer por hoja se cuentan
    después, sin lo que ya se dijo de una marca (``_juntar_por_marca``)."""
    de_marca, informativos = _avisos_de_lectura(ctx)
    junto, citados = _junto_a_su_seccion(ctx)
    globales = [*informativos, *_etiquetas_de_cuadro(ctx), *_avisos_de_reglas(ctx)]
    return globales, [*junto, *de_marca, *_solo_ia(ctx)], citados


def _juntar_por_marca(
    ctx: _Contexto,
    criticos: list[Verificacion],
    sin_dueno: tuple[list[Verificacion], list[Verificacion], set[str]],
    ajenas: set[str],
) -> list[Verificacion]:
    """R228, R148a: lo que la verificación 11 dice de una marca (sus textos sin leer, sus avisos,
    su lectura IA) va dentro del hallazgo de dato crítico de esa marca, si lo tiene, con sus
    handles; si no, en un solo hallazgo por marca. El nombre que la IA le da a una sección
    («CTA-3 (SECCIÓN 1)») es de su marca. Un texto sin leer que sólo puede ser de una marca y que
    su hallazgo de dato crítico ya nombra («8@15» de TE-A) se cita ahí, con su handle, y no se
    repite en la cuenta de su hoja."""
    globales, de_marca, citados = sin_dueno
    principal: dict[str, int] = {}
    for i, v in enumerate(criticos):
        if v.numero != 7 or len(v.marcas) != 1 or not v.marcas[0]:
            continue
        marca = v.marcas[0]
        actual = principal.get(marca)
        if actual is None or _prioridad(v) < _prioridad(criticos[actual]):
            principal[marca] = i
    salida = list(criticos)
    plegados: dict[int, list[Any]] = defaultdict(list)
    for r in ctx.inv.rechazos:
        if r.entidad_id in citados or r.entidad_id not in ctx.entidades:
            continue
        suyas = {*r.marcas, *r.posibles}
        if len(suyas) != 1 or (marca := next(iter(suyas))) not in principal:
            continue
        i = principal[marca]
        if all(c in salida[i].mensaje for c in re.findall(r"«[^«»]*»", _citas_de(r.texto))):
            plegados[i].append(r)
    for i, rs in plegados.items():
        w = salida[i]
        por_hoja: dict[str, list[str]] = defaultdict(list)
        for r in rs:
            por_hoja[r.hoja or "sin hoja"].append(ctx.cita(r.entidad_id, r.texto))
        donde = "; ".join(f"en {h}: {', '.join(cs)}" for h, cs in sorted(por_hoja.items()))
        salida[i] = w.model_copy(
            update={
                "mensaje": f"{w.mensaje} Esos textos en el plano, sin dueño: {donde}.",
                "textos": list(dict.fromkeys([*w.textos, *(ctx.handle(r.entidad_id) for r in rs)])),
            }
        )
    fuera = citados | {r.entidad_id for rs in plegados.values() for r in rs}
    por_marca: dict[str, list[Verificacion]] = defaultdict(list)
    for v in de_marca:
        base = (v.marcas[0] if v.marcas else "").split(" (", 1)[0]
        if base in principal:
            i = principal[base]
            w = salida[i]
            salida[i] = w.model_copy(
                update={
                    "mensaje": f"{w.mensaje} Además: {v.mensaje}",
                    "textos": list(dict.fromkeys([*w.textos, *v.textos])),
                    "datos": [*w.datos, *v.datos][:8],
                }
            )
        else:
            por_marca[base].append(v)
    for base, partes in sorted(por_marca.items()):
        severidad = min((v.severidad for v in partes), key=lambda x: _RANGO_DE_SEVERIDAD[x])
        hojas = {v.hoja for v in partes}
        salida.append(
            Verificacion(
                id=id_de_verificacion(11, base, "", ""),
                numero=11,
                severidad=severidad,
                mensaje=" ".join(v.mensaje for v in partes),
                marcas=list(dict.fromkeys(m for v in partes for m in v.marcas)),
                datos=[d for v in partes for d in v.datos][:8],
                hoja=next(iter(hojas)) if len(hojas) == 1 else "",
                bbox=partes[0].bbox if len(partes) == 1 else None,
                campo=",".join(dict.fromkeys(v.campo for v in partes if v.campo)),
                textos=list(dict.fromkeys(t for v in partes for t in v.textos)),
                cantidad="desconocida"
                if any(v.cantidad == "desconocida" for v in partes)
                else "conocida",
            )
        )
    return [*salida, *_rechazos_por_hoja(ctx, fuera), *globales]


def _citas_de(texto: str) -> str:
    """Cómo se cita un texto en un mensaje: «4#3 / E#2@15» se dice «4#3», «E#2@15»."""
    return al_lenguaje_del_plano(f"«{_una_linea(texto)}»")


def _prioridad(v: Verificacion) -> tuple[int, int]:
    """El hallazgo de una marca que recibe lo demás que se dice de ella: el de su armado por
    leer primero, luego el más grave."""
    return (0 if v.campo == "armado" else 1, _RANGO_DE_SEVERIDAD[v.severidad])


def _referencias_cruzadas(hallazgos: list[Verificacion]) -> list[Verificacion]:
    """La altura supuesta de la planta más alta y la contradicción de los entrepisos tratan de lo
    mismo: cada una nombra a la otra."""
    entrepisos = next(
        (v for v in hallazgos if v.id == id_de_verificacion(8, "", "", "entrepisos")), None
    )
    if entrepisos is None:
        return hallazgos
    alturas = [
        v
        for v in hallazgos
        if v.numero == 7 and v.campo == "altura_m" and v.hoja and "repite" in v.mensaje
    ]
    # R232: la cota de un muro da su alto en las dos lecturas de los entrepisos.
    muros = [v for v in hallazgos if v.numero == 10 and _DOS_LECTURAS in v.mensaje]
    salida = []
    for v in hallazgos:
        if v in muros:
            cual = f"la contradicción de los entrepisos ({entrepisos.id})"
            v = v.model_copy(update={"mensaje": f"{v.mensaje} Ver también {cual}."})
        elif v is entrepisos and alturas:
            donde = ", ".join(f"{a.hoja} ({a.id})" for a in alturas)
            v = v.model_copy(
                update={"mensaje": f"{v.mensaje} Ver también la altura supuesta de {donde}."}
            )
        elif v in alturas:
            cual = f"la contradicción de los entrepisos ({entrepisos.id})"
            v = v.model_copy(update={"mensaje": f"{v.mensaje} Ver también {cual}."})
        salida.append(v)
    return salida


def _avisos_de_reglas(ctx: _Contexto) -> list[Verificacion]:
    """Lo que la lectura de las reglas avisa (un rango de recubrimiento del que se toma el
    mínimo, una celda de la tabla que no se leyó, una regla que un texto nombra y no se supo
    leer, la tabla completada con la estándar): un solo hallazgo con todo."""
    avisos = [a for a in ctx.reglas.avisos if "marcos distintos llevan ese código" not in a]
    if not avisos:
        return []
    return [
        _hallazgo(
            11,
            "duda",
            "Las reglas del plano (notas y tabla de varillas) avisan: "
            + " ".join(a if a.endswith(".") else f"{a}." for a in avisos)
            + " Confirma lo que se tomó.",
            clave="avisos de las reglas",
        )
    ]


_MOTIVOS = {
    "sin_dueno": "nadie lee",
    "ambigua": "dos o más marcas pueden reclamar (no se decide de cuál son)",
    "otra_familia": "están en la pila de una marca pero nombran otra familia",
    "sin_lector": "nombran su marca o su familia y ningún lector lee",
    "varias_marcas": "son de varias marcas a la vez (una lista o un rango) y no se leen",
}
_MOTIVO_CORTO = {
    "sin_dueno": "sin dueño",
    "ambigua": "ambiguos",
    "otra_familia": "de otra familia",
    "sin_lector": "sin lector",
    "varias_marcas": "de varias marcas",
}
_CLASES = {
    "distribucion": "distribuciones de estribos por tramo (la forma «1@6,8@10,10@15», que la "
    "lectura todavía no lee)",
    "nota": "notas con armado",
    "seccion": "secciones",
    "armado": "textos de armado",
}
_DISTRIBUCION = re.compile(
    r"^\s*(?:\d+\s*@\s*\d+(?:\.\d+)?|@\s*\d+(?:\.\d+)?)(?:\s*,\s*\d+\s*@\s*\d+(?:\.\d+)?)*\s*$"
)


# R253: lo que hace de una nota un armado: una varilla o un estribo («#», «E#») o una separación.
_TOKEN_DE_ACERO = re.compile(r"[#@]")


def _clase_de_texto(texto: str) -> str:
    plano = _una_linea(texto).upper()
    if _DISTRIBUCION.match(plano):
        return "distribucion"
    if len(re.findall(r"[A-ZÁÉÍÓÚÑ]{3,}", plano)) >= 2:
        return "nota"
    if re.search(r"\d\s*[X×]\s*\d", plano) and "#" not in plano and "@" not in plano:
        return "seccion"
    return "armado"


def _rechazos_por_hoja(ctx: _Contexto, citados: set[str]) -> list[Verificacion]:
    """Los textos con armado que nadie leyó, por hoja, por motivo y por clase de texto: su cuenta,
    sus ejemplos y todos sus handles, con las marcas de las que pueden ser. Lo que ya cita el
    hallazgo de su marca (``citados``: lo escrito junto a su sección) no se repite aquí."""
    grupos: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for r in ctx.inv.rechazos:
        if r.entidad_id in citados:
            continue
        clase = _clase_de_texto(r.texto)
        if clase == "nota" and not _TOKEN_DE_ACERO.search(r.texto):
            # R253: una nota sin varilla ni estribo («FORMATO 20X20» de un piso) no es armado.
            continue
        grupos[(r.hoja or "sin hoja", r.motivo, clase)].append(r)
    salida = []
    for (hoja, motivo, clase), rechazos in sorted(grupos.items()):
        ejemplos = [ctx.cita(r.entidad_id, r.texto) for r in rechazos]
        marcas = Counter(m for r in rechazos for m in [*r.marcas, *r.posibles])
        de_quien = (
            f" Pueden ser de: {', '.join(f'{m} ({n})' for m, n in sorted(marcas.items()))}."
            if marcas
            else ""
        )
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"{len(rechazos)} {_CLASES[clase]} en {hoja} que {_MOTIVOS.get(motivo, motivo)}"
                f" ({_MOTIVO_CORTO.get(motivo, motivo)}): "
                + ", ".join(ejemplos[:_EJEMPLOS])
                + (f" y {len(ejemplos) - _EJEMPLOS} más" if len(ejemplos) > _EJEMPLOS else "")
                + f".{de_quien}",
                clave=f"rechazos: {motivo}: {clase}",
                hoja=hoja,
                marcas=sorted(marcas),
                bbox=_caja(
                    ctx.entidades[r.entidad_id].bbox
                    for r in rechazos
                    if r.entidad_id in ctx.entidades
                ),
                textos=[ctx.handle(r.entidad_id) for r in rechazos],
            )
        )
    return salida


def _campo_de_aviso(aviso: str) -> str | None:
    """El dato del que habla un aviso de lectura, por cómo empieza («sección dibujada …»,
    «estribos: …»), o ``None`` si no se sabe."""
    texto = unicodedata.normalize("NFD", aviso.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    for prefijo, campo in (
        ("seccion", "seccion_cm"),
        ("longitudinales", "longitudinales"),
        ("varillas", "longitudinales"),
        ("estribos", "estribos"),
        ("parrillas", "parrillas"),
        ("longitud", "longitud_m"),
    ):
        if texto.startswith(prefijo):
            return campo
    return None


def _parte(definicion: Definicion, muro: float | None) -> Definicion:
    """La variante para muros de ``muro`` cm (R168), o la definición de la marca si ``None``."""
    if muro is None:
        return definicion
    return next(v for v in definicion.variantes if v.para_muro_cm == muro)


def _partes_decididas(
    definicion: Definicion, campo: str, aviso: str
) -> tuple[float | None, ...] | None:
    """R241: las partes de la definición de las que es ``aviso`` (las variantes cuyas lecturas lo
    dicen, por su muro; si ninguna, la marca misma: ``(None,)``), si alguien ya decidió su
    ``campo`` en todas; si no, ``None`` (el aviso sigue siendo una duda)."""
    duenas = [v for v in definicion.variantes if aviso in v.avisos] or [definicion]
    for parte in duenas:
        dato = getattr(parte, campo, None)
        if dato is None or dato.fuente != "humano":
            return None
    return tuple(p.para_muro_cm if p is not definicion else None for p in duenas)


def _cuantas_tomaron(ctx: _Contexto, marca: str, definicion: Definicion, muro: float | None) -> str:
    """R241: en una marca con variantes por muro, cuántas de sus colocaciones tomaron la decisión
    de la parte ``muro``: las que resolvieron esa variante, o (``None``, la de la marca) las que no
    resolvieron ninguna (una decisión ``humano`` le gana a todo, así que todas las de la parte la
    toman); «» sin variantes (las toman todas)."""
    if not definicion.variantes:
        return ""
    suyas = [e for e in ctx.elementos if e.marca == marca]
    tomaron = 0
    for e in suyas:
        propia = variante_de(e)
        tomaron += (
            propia is None
            if muro is None
            else propia is not None and abs(propia - muro) <= _TOLERANCIA_DE_MURO_CM
        )
    return f"lo toman {tomaron} de {len(suyas)} colocaciones"


def _avisos_de_lectura(ctx: _Contexto) -> tuple[list[Verificacion], list[Verificacion]]:
    """Lo que las lecturas de cada marca avisan. Lo que pide que alguien mire (un texto vetado de
    su pila, un dibujo que no coincide con sus cotas, un corte que no se pudo escoger, un texto
    de la marca que nadie leyó, la sección que no se encontró y que nada más da) es una duda, un
    hallazgo por marca. Lo que sólo informa (la familia que dio la IA y coincide con el prefijo,
    unas cotas cercanas que no se tomaron, una lectura IA que no se usa) es un aviso, un hallazgo
    por clase de aviso con todas sus marcas: así no tapa lo demás. El código de hoja repetido es
    una contradicción (verificación 8) y no se repite aquí."""
    salida: list[Verificacion] = []
    agrupados: list[Verificacion] = []
    informativos: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for marca, definicion in sorted({**ctx.por_marca, **ctx.por_familia}.items()):
        avisos = [a for a in definicion.avisos if "marcos distintos llevan ese código" not in a]
        dudas = [a for a in avisos if _clase_de_aviso(a, definicion) is None]
        for a in avisos:
            clase = _clase_de_aviso(a, definicion)
            if clase is not None:
                informativos[clase].append((marca, a))
        # R241: lo que sus lecturas avisan de un dato que alguien ya decidió no es una duda nueva:
        # un aviso que dice quién lo decidió. En una marca con variantes por muro, sólo lo de la
        # parte que la decisión alcanzó (la marca, o la variante que nombró): lo que avisa la
        # lectura de otra variante sigue siendo su duda.
        decididas: dict[tuple[str, tuple[float | None, ...]], list[str]] = defaultdict(list)
        for a in list(dudas):
            campo = _campo_de_aviso(a)
            partes = _partes_decididas(definicion, campo, a) if campo is not None else None
            if campo is not None and partes is not None:
                decididas[(campo, partes)].append(a)
                dudas.remove(a)
        for (campo, muros), textos in sorted(
            decididas.items(), key=lambda kv: (kv[0][0], [m or 0.0 for m in kv[0][1]])
        ):
            # Una lectura que dicen varias variantes decididas: cada una con su valor y su cuenta.
            dichos = []
            for muro in muros:
                dato = getattr(_parte(definicion, muro), campo)
                quien = marca if muro is None else f"{marca} (para muros de {_cm(muro)} cm)"
                tomaron = _cuantas_tomaron(ctx, marca, definicion, muro)
                dichos.append(
                    f"{quien}: {_NOMBRE[campo]} es {_valor(campo, dato.valor)}, {dato.texto}"
                    + (f"; {tomaron}" if tomaron else "")
                )
            agrupados.append(
                _hallazgo(
                    11,
                    "aviso",
                    ". ".join(dichos)
                    + ". Lo que sus lecturas avisaban: "
                    + "; ".join(textos)
                    + ".",
                    clave=f"avisos de lectura: decidido: {campo}"
                    + "".join(f": muro {_cm(m)}" for m in muros if m is not None),
                    marca=marca,
                    campo=campo,
                    datos=[getattr(_parte(definicion, m), campo) for m in muros],
                )
            )
        if not dudas:
            continue
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"Las lecturas de {marca} avisan: " + "; ".join(dudas) + ".",
                clave="avisos de lectura",
                marca=marca,
                datos=[
                    d
                    for campo in ("seccion_cm", *_ARMADO)
                    if (d := getattr(definicion, campo)) is not None
                ],
            )
        )
    for clase, pares in sorted(informativos.items()):
        marcas = list(dict.fromkeys(m for m, _a in pares))
        detalle = "; ".join(f"{m}: {a}" for m, a in pares[:_EJEMPLOS])
        mas = f"; y {len(pares) - _EJEMPLOS} más" if len(pares) > _EJEMPLOS else ""
        agrupados.append(
            _hallazgo(
                11,
                "aviso",
                f"{_AVISOS_INFORMATIVOS[clase]} ({len(marcas)} marcas): {detalle}{mas}.",
                clave=f"avisos de lectura: {clase}",
                marcas=marcas,
            )
        )
    return salida, agrupados


_FAMILIA_DE_LA_IA = re.compile(
    r"^familia: el plano no la dice \(sólo el prefijo de la marca: (\w+)\); se toma la de la IA: "
    r"(\w+)$"
)
_FAMILIAS_NO_COINCIDEN = re.compile(r"^familia: las lecturas no coinciden — (.*); se toma (\w+)$")
_AVISOS_INFORMATIVOS = {
    "familia": "La familia sólo la dice el prefijo de la marca y la lectura IA dice la misma",
    "familia_ia": "La lectura IA dice otra familia que las lecturas del plano; se toma la del "
    "plano",
    "cotas": "Cotas cerca del título que no se toman como su sección (la sección sí se leyó)",
    "ia_no_se_toma": "Lecturas IA que no se toman porque el plano tiene texto para ese dato (lo "
    "que ese texto dice se verifica como dato crítico)",
    "seccion_leida": "Una copia de la marca no tiene su sección dibujada o señalada, pero otra sí "
    "se leyó",
    "ia_entera": "Lecturas IA que no se leen enteras (sólo cuentan como alternativa)",
    "recubrimiento": "Recubrimientos acotados que no se toman (el que se usa queda por confirmar "
    "en el acero)",
    "otro": "Avisos de lectura",
}


def _clase_de_aviso(aviso: str, definicion: Definicion) -> str | None:
    """La clase de un aviso que sólo informa, o ``None`` si pide que alguien mire."""
    m = _FAMILIA_DE_LA_IA.match(aviso)
    if m is not None:
        return "familia" if m.group(1) == m.group(2) else None
    m = _FAMILIAS_NO_COINCIDEN.match(aviso)
    if m is not None:
        del_plano = {
            familia
            for familia, quienes in re.findall(r"(\w+) \(([^)]*)\)", m.group(1))
            if any(q.strip() != "IA" for q in quienes.split(","))
        }
        return "familia_ia" if len(del_plano) <= 1 else None
    seccion_leida = definicion.seccion_cm is not None and definicion.seccion_cm.valor is not None
    if _COTAS_CERCANAS.search(aviso):
        return "cotas" if seccion_leida else None
    if "la lectura IA" in aviso and "no se toma" in aviso:
        return "ia_no_se_toma"
    if aviso.startswith("la lectura IA") and "no se lee entera" in aviso:
        return "ia_entera"
    if aviso.startswith("recubrimiento:"):
        return "recubrimiento"
    if (
        aviso.startswith("sección:")
        and seccion_leida
        and (
            "no se encontró" in aviso
            or "señalada por flecha" in aviso
            or "no hay sección dibujada" in aviso
            or "no es una sección" in aviso
        )
    ):
        return "seccion_leida"
    if aviso.startswith("ancho ") and "cotas en cadena" in aviso:
        return "otro"
    return None


def _junto_a_su_seccion(ctx: _Contexto) -> tuple[list[Verificacion], set[str]]:
    """El armado de una marca escrito junto a la sección de su detalle o en su esquina —no bajo
    ella, donde se lee su pila— que nadie leyó, y lo que bajo ella quedó en duda: por marca, cada
    texto por su handle. Un texto cuenta para la sección de su marca si se le atribuye
    (``posibles``) y no se aparta de ella más que su lado menor (lo que alcanza su pila)."""
    por_hoja: dict[str, list[Any]] = defaultdict(list)
    for r in ctx.inv.rechazos:
        if r.posibles and r.entidad_id in ctx.entidades:
            por_hoja[r.hoja].append(r)
    por_marca: dict[str, dict[str, tuple[Any, str, str, BBox]]] = defaultdict(dict)
    for seccion in ctx.inv.secciones_dibujadas:
        x0, y0, x1, y1 = seccion.caja
        alcance = min(x1 - x0, y1 - y0)
        for r in por_hoja.get(seccion.hoja, []):
            if seccion.marca not in r.posibles:
                continue
            caja = extension_de_texto(ctx.entidades[r.entidad_id])
            if _hueco(caja, seccion.caja) > alcance:
                continue
            en_columna = caja[2] > x0 and caja[0] < x1
            en_banda = caja[3] > y0 and caja[1] < y1
            donde = "bajo" if en_columna and not en_banda else "junto"
            por_marca[seccion.marca].setdefault(
                r.entidad_id, (r, donde, seccion.titulo_id, seccion.caja)
            )
    salida = []
    for marca, vistos in sorted(por_marca.items()):
        unicos = list(vistos.values())
        junto = [ctx.cita(r.entidad_id, r.texto) for r, d, _t, _c in unicos if d == "junto"]
        bajo = [ctx.cita(r.entidad_id, r.texto) for r, d, _t, _c in unicos if d == "bajo"]
        hojas = sorted({r.hoja for r, *_ in unicos})
        titulos = sorted({ctx.handle(t) for _r, _d, t, _c in unicos})
        donde = f"{', '.join(hojas)}; título {', '.join(titulos)}"
        partes = []
        if junto:
            partes.append(f"junto a la sección o en su esquina: {', '.join(junto)}")
        if bajo:
            partes.append(
                f"bajo la sección, en una pila que quedó en duda (otra sección o etiqueta la "
                f"alcanza): {', '.join(bajo)}"
            )
        cabeza = (
            f"Armado de {marca} escrito en esquina o junto a la sección de su detalle"
            if junto
            else f"Armado de {marca} escrito bajo la sección de su detalle"
        )
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"{cabeza} ({donde}), por leer: "
                + "; ".join(partes)
                + ". No se lee como su pila: se lee a mano o cuando se lean los cortes dibujados.",
                clave="armado junto a su sección",
                marca=marca,
                hoja=hojas[0] if len(hojas) == 1 else "",
                de_la_marca=True,
                bbox=_caja(c for *_x, c in unicos) if len(hojas) == 1 else None,
                textos=[ctx.handle(r.entidad_id) for r, *_ in unicos],
            )
        )
    return salida, {i for vistos in por_marca.values() for i in vistos}


def _etiquetas_de_cuadro(ctx: _Contexto) -> list[Verificacion]:
    """Una etiqueta de cuadro (``role=cuadro``, no un título de detalle) sin su pila, y una
    etiqueta que tiene su pila contada como colocación: las dos dicen que la asociación se
    equivocó en algo."""
    titulos = set(ctx.inv.titulos_de_detalle)
    etiquetas = [i for i in ctx.inv.cuadro_mark_entities if i not in titulos and i in ctx.entidades]
    pilas = Counter(
        (normalizar_marca(s.mark, ctx.config), s.hoja)
        for s in ctx.inv.specs
        if s.metodo in ("pila", "fila")
    )
    por_llave: dict[tuple[str, str], list[str]] = defaultdict(list)
    for i in etiquetas:
        e = ctx.entidades[i]
        marca = normalizar_marca(_una_linea(e.text or ""), ctx.config)
        por_llave[(marca, ctx.hoja_de(e))].append(i)
    salida = []
    for (marca, hoja), ids in sorted(por_llave.items()):
        faltan = len(ids) - pilas.get((marca, hoja), 0)
        if faltan <= 0:
            continue
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"{marca} es etiqueta de cuadro en {hoja} ({', '.join(ctx.handle(i) for i in ids)})"
                f" y {'no tiene' if faltan == len(ids) else f'a {faltan} les falta'} su pila de "
                "armado: o la pila no se encontró, o la etiqueta no es de cuadro.",
                clave="etiqueta de cuadro sin pila",
                marca=marca,
                hoja=hoja,
                bbox=_caja(ctx.entidades[i].bbox for i in ids),
                textos=[ctx.handle(i) for i in ids],
            )
        )
    de_cuadro = set(etiquetas)
    contadas = [
        e
        for e in ctx.elementos
        if (d := ctx.deteccion.get(e.detection_id)) is not None
        and d.source_entities
        and d.source_entities[0] in de_cuadro
    ]
    for marca, els in sorted(_por_marca(contadas).items()):
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"{marca}: {_pzas(len(els))} contadas como colocación ({_hojas(els)}) son "
                "etiquetas de cuadro con su pila de armado: una etiqueta que define la marca no la "
                f"coloca. Etiquetas: {', '.join(_etiqueta(ctx, e) for e in els)}.",
                clave="etiqueta de cuadro colocada",
                marca=marca,
                elementos=[e.element_id for e in els],
                textos=[_etiqueta(ctx, e) for e in els],
            )
        )
    return salida


def _solo_ia(ctx: _Contexto) -> list[Verificacion]:
    """Los campos de una definición que sólo dice la lectura IA, un hallazgo por marca: una duda
    si junto al título de su marca, en la hoja de la lectura IA, el plano escribe textos de ese
    campo que nadie leyó (los que tienen ese título por el más cercano: la IA puede haber leído
    uno de ellos, o haberse equivocado; se ponen lado a lado, por handle); un aviso si no
    escribe nada que comparar. Nunca una IA en silencio. El nombre que la IA le da a una sección
    («CTA-3 (SECCIÓN 1)») cuenta con los títulos de su marca y con los de su corte («SECCIÓN
    1»)."""
    titulos = _titulos_por_hoja(ctx)
    cortes = {c for m in ctx.por_marca if (c := _nombres_de_titulo(m)[1])}
    rechazos: dict[str, list[Any]] = defaultdict(list)
    for r in ctx.inv.rechazos:
        if r.entidad_id in ctx.entidades:
            rechazos[r.hoja].append(r)
    salida = []
    for marca, definicion in sorted(ctx.por_marca.items()):
        campos = [
            c
            for c in ("seccion_cm", "longitud_m", *_ARMADO)
            if (d := getattr(definicion, c)) is not None
            and d.fuente == "ia"
            and d.valor is not None
        ]
        if not campos:
            continue
        partes, citados, cajas, datos = [], [], [], []
        hojas = []
        for campo in campos:
            dato = getattr(definicion, campo)
            datos.append(dato)
            hoja = dato.hoja
            hojas.append(hoja)
            de_la_hoja = titulos.get(hoja, [])
            cerca: list[tuple[str, str]] = []  # (entidad, texto)
            for entidad, texto in _candidatos_de_campo(ctx, campo, hoja, rechazos, definicion):
                caja = ctx.entidades[entidad].bbox
                if not _de_su_titulo(de_la_hoja, caja, marca, cortes):
                    continue
                cerca.append((entidad, texto))
                cajas.append(caja)
            citas = [ctx.cita(i, t) for i, t in cerca]
            citados += [ctx.handle(i) for i, _t in cerca]
            junto = (
                "; junto a su título el plano escribe, sin que nadie lo lea: "
                + ", ".join(citas[:_EJEMPLOS])
                + (f" y {len(citas) - _EJEMPLOS} más" if len(citas) > _EJEMPLOS else "")
                if citas
                else "; junto a su título el plano no escribe nada de ese dato que comparar"
            )
            partes.append(
                f"{_CORTO[campo]} {_valor(campo, dato.valor)} («{_una_linea(dato.texto)}», "
                f"{hoja or 'sin hoja'}){junto}{_lo_que_lee_su_base(ctx, marca, campo)}"
            )
        hoja = hojas[0] if len(set(hojas)) == 1 else ""
        severidad: Severidad = "duda" if citados else "aviso"
        cierre = " Compara y confírmalo." if citados else " Por confirmar."
        salida.append(
            _hallazgo(
                11,
                severidad,
                f"De {marca} sólo la lectura IA dice: " + " | ".join(partes) + "." + cierre,
                clave="sólo la IA",
                marca=marca,
                hoja=hoja,
                datos=datos,
                campo=",".join(campos),
                bbox=_caja(cajas) if hoja and cajas else None,
                textos=citados,
            )
        )
    return salida


# Una malla electrosoldada de losa («6x6-8/8», «MALLA ELECTROSOLDADA 6X6-10/10») no es la sección de
# un elemento; una sección escrita con pulgadas («10"X10"») o un perfil (HSS, PTR, IPR) sí.
_MALLA = re.compile(r"\d+\s*[xX×]\s*\d+\s*-\s*\d+\s*/\s*\d+|MALLA")
_SECCION_ESCRITA = re.compile(
    r"\d+(?:\.\d+)?\s*(?:\"|''|´´)\s*[xX×]\s*\d+(?:\.\d+)?|\b(?:HSS|PTR|IPR|OR)\b"
)


def _candidatos_de_campo(
    ctx: _Contexto,
    campo: str,
    hoja: str,
    rechazos: dict[str, list[Any]],
    definicion: Definicion,
) -> list[tuple[str, str]]:
    """Los textos de la hoja con los que se compara un campo que sólo dice la IA, filtrados por la
    clase del campo (R231): para una sección, las secciones sin dueño que no son una malla de losa
    y los textos que escriben una sección con pulgadas o un perfil de acero («COLUMNA HSS
    10"X10"»); para una parrilla, las mallas, nunca las distribuciones de estribos de una viga;
    para lo demás, los textos sin dueño que muestran ese campo."""
    fragmento = {"seccion_cm": "seccion", "longitud_m": "longitud"}.get(campo, campo)
    salida: list[tuple[str, str]] = []
    for r in rechazos.get(hoja, []):
        if fragmento not in campos_de_fragmento(r.texto, definicion.familia):
            continue
        texto = _una_linea(r.texto).upper()
        if campo == "seccion_cm" and _MALLA.search(texto):
            continue
        if campo == "parrillas" and _DISTRIBUCION.match(texto):
            continue
        salida.append((r.entidad_id, r.texto))
    if campo == "seccion_cm":
        vistos = {i for i, _t in salida}
        for e in ctx.entidades.values():
            if not e.is_textual or not e.text or e.entity_id in vistos:
                continue
            texto = _una_linea(e.text).upper()
            if (
                _SECCION_ESCRITA.search(texto)
                and not _MALLA.search(texto)
                and ctx.hoja_de(e) == hoja
            ):
                salida.append((e.entity_id, _una_linea(e.text)))
    return salida


def _de_su_titulo(
    titulos: list[tuple[NormalizedEntity, set[str]]], caja: BBox, marca: str, cortes: set[str]
) -> bool:
    """Si un texto es del título de ``marca``: el título más cercano lo nombra y lo alcanza
    (``_alcanza``); o, si el más cercano es el título de un corte que no lo alcanza, el título de
    una marca más cercano es el de ``marca`` y lo alcanza."""
    nombres, corte = _nombres_de_titulo(marca)
    cercano = min(titulos, key=lambda t: _hueco(t[0].bbox, caja), default=None)
    if cercano is None:
        return False
    if cercano[1] & (nombres | ({corte} if corte else set())) and _alcanza(cercano, caja, marca):
        return True
    de_marca = [t for t in titulos if t[1] - cortes]
    otro = min(de_marca, key=lambda t: _hueco(t[0].bbox, caja), default=None)
    return (
        otro is not None
        and otro is not cercano
        and bool(otro[1] & nombres)
        and _alcanza(otro, caja, marca)
    )


def _alcanza(titulo: tuple[NormalizedEntity, set[str]], caja: BBox, marca: str) -> bool:
    """Si un texto está al alcance del título de su marca: a lo más ``_ALCANCE_DEL_TITULO`` altos
    de un título que nombra la marca, o —el de un corte («SECCIÓN 1»), que lleva su sección y su
    armado apilados debajo o encima— en su columna y a lo más ``_ALCANCE_DEL_CORTE`` altos."""
    entidad, dice = titulo
    alto = alto_de_texto(entidad)
    hueco = _hueco(entidad.bbox, caja)
    nombres, corte = _nombres_de_titulo(marca)
    if dice & nombres:
        return hueco <= _ALCANCE_DEL_TITULO * alto
    en_columna = caja[2] > entidad.bbox[0] and caja[0] < entidad.bbox[2]
    return corte in dice and en_columna and hueco <= _ALCANCE_DEL_CORTE * alto


def _nombres_de_titulo(marca: str) -> tuple[set[str], str | None]:
    """Los nombres con que un título del plano nombra a una marca —la marca y, si la IA le dio a
    una sección un nombre compuesto («CTA-3 (SECCIÓN 1)»), su marca— y el nombre de su corte
    («SECCION 1», sin acentos), si lo tiene."""
    base, _, resto = marca.partition(" (")
    return {marca, base}, (_sin_acentos(resto.rstrip(")")) if resto else None)


def _lo_que_lee_su_base(ctx: _Contexto, marca: str, campo: str) -> str:
    """Lo que el plano lee de la marca a la que la IA le puso otro nombre («CI (15CM)» → CI)."""
    base = marca.split(" (", 1)[0]
    if base == marca or base not in ctx.por_marca:
        return ""
    definicion = ctx.por_marca[base]
    valores = sorted(
        {
            _valor(campo, d.valor)
            for p in [definicion, *definicion.variantes]
            if (d := getattr(p, campo)) is not None and d.fuente in _LEIDAS and d.valor is not None
        }
    )
    return f"; el plano lee {base} con {_listar(valores)}" if valores else ""


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn"
    )


def _titulos_por_hoja(ctx: _Contexto) -> dict[str, list[tuple[NormalizedEntity, set[str]]]]:
    """Los textos que nombran marcas y no traen armado (los títulos), por hoja, con los nombres
    que dicen: las marcas de la gramática, los nombres de las definiciones que no son marcas de
    la gramática («MC-C», «CM-1») y los cortes de los nombres compuestos («SECCIÓN 1»)."""
    bases = {m.split(" (", 1)[0] for m in ctx.por_marca}
    cortes = {
        _sin_acentos(resto.rstrip(")")) for m in ctx.por_marca if (resto := m.partition(" (")[2])
    }
    salida: dict[str, list[tuple[NormalizedEntity, set[str]]]] = defaultdict(list)
    for e in ctx.entidades.values():
        if not e.is_textual or not e.text or tiene_armado(e.text):
            continue
        texto = _una_linea(e.text).upper()
        nombres = {normalizar_marca(m, ctx.config) for m in marcas_nombradas(texto, ctx.config)}
        nombres |= bases & set(_FICHA.findall(texto))
        plano = _sin_acentos(texto)
        nombres |= {c for c in cortes if c == plano}
        if nombres:
            salida[ctx.hoja_de(e)].append((e, nombres))
    return salida


__all__ = [
    "CRITICOS",
    "Severidad",
    "Verificacion",
    "id_de_verificacion",
    "ordenar",
    "peso",
    "tamano",
    "verificar",
]
