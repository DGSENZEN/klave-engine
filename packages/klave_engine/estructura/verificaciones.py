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
from klave_engine.estructura.elementos import FAMILIAS_ESTRUCTURALES, Elemento, excluidas
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
    ``piezas``."""

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


def id_de_verificacion(numero: int, marca: str, hoja: str, clave: str) -> str:
    """El id estable de un hallazgo: sha1 de su número, su marca, su hoja y su clave (el texto
    que lo identifica, nunca una cuenta), sus primeros 12 hex."""
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
) -> Verificacion:
    """Un hallazgo. ``de_la_marca``: es de toda una marca (o una familia: todas sus colocaciones,
    en las hojas que sean), así que su id no lleva hoja aunque ``hoja`` diga la única en que
    está: una colocación más en otra hoja no le cambia el id."""
    lista_marcas = list(dict.fromkeys([*([marca] if marca else []), *marcas]))
    return Verificacion(
        id=id_de_verificacion(numero, marca, "" if de_la_marca else hoja, clave),
        numero=numero,
        severidad=severidad,
        mensaje=mensaje,
        marcas=lista_marcas,
        elementos=list(dict.fromkeys(elementos)),
        datos=[d.model_copy(deep=True) for d in datos],
        hoja=hoja,
        bbox=bbox,
        campo=campo,
        textos=list(dict.fromkeys(textos)),
        en_juego={k: round(v, 4) for k, v in (en_juego or {}).items() if v},
    )


# ------------------------------------------------------------------------------- el contexto


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
    _reglas: dict[str, Reglas] = field(default_factory=dict)
    _acero: dict[str, float] = field(default_factory=dict)
    deteccion: dict[str, Detection] = field(default_factory=dict)

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
        return e.raw_handle if e is not None and e.raw_handle else entidad_id

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
) -> list[Verificacion]:
    """Las verificaciones del propio plano (ver el docstring del módulo), ordenadas: primero lo
    que bloquea, luego las dudas, luego los avisos; dentro de cada severidad, por lo que está en
    juego (``peso``). ``anclaje_m`` y ``desperdicio`` son los de la etapa del acero (los de
    ``SteelAssumptions`` si no se dan): con ellos se pesa lo que está en juego."""
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
    )
    escritas = _marcas_escritas_en_planta(ctx)
    hallazgos: list[Verificacion] = []
    hallazgos += _sin_definir(ctx)
    hallazgos += _sin_colocar(ctx, escritas)
    hallazgos += _escritas_sin_elemento(ctx, escritas)
    hallazgos += _detectadas_fuera(ctx)
    hallazgos += _criticos(ctx)
    hallazgos += _contradicciones(ctx)
    hallazgos += _sin_dueno(ctx)
    return ordenar(hallazgos, _totales(ctx))


def ordenar(
    hallazgos: list[Verificacion], totales: dict[str, float] | None = None
) -> list[Verificacion]:
    """Por severidad y, dentro de ella, por ``peso`` (lo que está en juego como parte del acero
    y del concreto de toda la estructura, ``totales``: ``acero_kg`` y ``concreto_m3``); a igual
    peso, por número, marca, hoja e id."""
    totales = totales or {}
    return sorted(
        hallazgos,
        key=lambda v: (
            _RANGO_DE_SEVERIDAD[v.severidad],
            -peso(v, totales),
            v.numero,
            v.marcas[:1],
            v.hoja,
            v.id,
        ),
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
                    f"{marca} está colocada en planta ({donde}) y no está definida en ninguna "
                    f"parte del plano: ni un cuadro, ni un detalle, ni una nota general de la "
                    f"familia {familia} la describen. {usa}",
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


def _marcas_escritas_en_planta(ctx: _Contexto) -> dict[str, list[_Escrita]]:
    """Los textos de una planta estructural que son una marca (con o sin su palabra de familia
    delante: «DADO D-1», «P-4»), que ninguna detección tomó, que no son etiquetas de cuadro ni
    títulos, y junto a los que no hay ninguna detección de esa marca: por marca normalizada. Una
    marca es lo que la gramática lee como marca o el nombre de una definición."""
    seg = ctx.segmentation
    if seg is None:
        return {}
    plantas = [v for v in seg.structural_plan_views() if v.bbox is not None]
    if not plantas:
        return {}
    archivo_de: dict[str, str] = {f.frame_id: f.source_file for f in ctx.frames}
    usadas = {i for d in ctx.detections for i in d.source_entities}
    de_cuadro = set(ctx.inv.cuadro_mark_entities) | set(ctx.inv.titulos_de_detalle)
    conocidas = {k for k in ctx.por_marca if not _SOLO_CIFRAS.match(k)}
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
        if marca is None:
            continue
        centro = bbox_center(e.bbox)
        if not any(
            v.bbox is not None
            and bbox_contains_point(v.bbox, centro)
            and archivo_de.get(v.view_id, "") in ("", e.source_file)
            for v in plantas
        ):
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


# ------------------------------------------------------------ 2: definida que no se coloca


def _sin_colocar(ctx: _Contexto, escritas: dict[str, list[_Escrita]]) -> list[Verificacion]:
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
    titulos = {v.view_id: v.title for v in ctx.segmentation.views} if ctx.segmentation else {}
    salida: list[Verificacion] = []
    for marca, definicion in sorted(ctx.por_marca.items()):
        if marca in colocadas or marca in escritas or not _del_plano(definicion):
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
            + ", ".join(titulos.get(v, v).split(" · ")[0] for v in en_cuadro)
            + "), nunca como colocación."
            if en_cuadro
            else ""
        )
        hojas = ", ".join(definicion.hojas) or "sin hoja"
        salida.append(
            _hallazgo(
                2,
                "aviso",
                f"{marca} ({definicion.familia}) está definida en el plano ({hojas}) y no se "
                f"coloca en ninguna planta: no entra en las cantidades.{solo} Si se construye, "
                "falta su colocación.",
                clave="definida sin colocar",
                marca=marca,
                datos=[
                    d
                    for campo in ("seccion_cm", *_ARMADO)
                    if (d := getattr(definicion, campo)) is not None
                ],
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
    ctx: _Contexto, escritas: dict[str, list[_Escrita]]
) -> list[Verificacion]:
    salida: list[Verificacion] = []
    colocadas = _por_marca(ctx.elementos)
    for marca, textos in sorted(escritas.items()):
        por_hoja = Counter(t.hoja for t in textos)
        donde = "; ".join(f"{h}: {_veces(n)}" for h, n in sorted(por_hoja.items()))
        definicion = ctx.por_marca.get(marca)
        if definicion is None:
            estado = "Tampoco está definida en el plano."
        elif not _del_plano(definicion):
            estado = "Sólo la define la lectura IA."
        else:
            estado = f"Está definida en {', '.join(definicion.hojas) or 'el plano'}."
        if colocadas.get(marca):
            otras = sorted({e.hoja for e in colocadas[marca]})
            estado += f" Sí tiene colocaciones en {', '.join(otras)}, no junto a estos textos."
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
        familia = definicion.familia if definicion is not None else ""
        if familia == "pilote" or marca.startswith("P-"):
            estado += " Todo pilote escrito en planta debe tener su pila: a éstos les falta."
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
                textos=[t.entidad.raw_handle for t in textos],
                en_juego={"piezas": float(len(textos))},
            )
        )
    return salida


_FUERA = {
    "sin_vista": "fuera de toda vista (lo que queda fuera de los marcos de hoja)",
    "planta_no_estructural": "en la planta de una hoja que no es de estructura",
}


def _detectadas_fuera(ctx: _Contexto) -> list[Verificacion]:
    """Las detecciones de una familia estructural que no llegan a elemento porque caen fuera de
    toda vista o en una planta que no es de estructura: el plano las dibuja y no se cuentan. Un
    aviso por motivo y familia (las de un detalle, un corte o un cuadro definen, no colocan)."""
    grupos: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for x in excluidas(ctx.detections, ctx.segmentation):
        if x.motivo in _FUERA:
            grupos[(x.motivo, x.familia)].append(x)
    salida = []
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


# Los datos que sólo da una definición: sin ninguna, su falta es la de la marca (verificación 1).
_DE_LA_DEFINICION = frozenset({"seccion_cm", *_ARMADO})
# Los estados en que a un dato de armado le falta su valor: los campos de armado de una marca en
# el mismo estado van en un solo hallazgo (la oficina lee de una vez el armado de esa marca).
_SIN_VALOR = frozenset({"falta", "por_leer"})


def _criticos(ctx: _Contexto) -> list[Verificacion]:
    grupos: dict[tuple[str, str, str, str], list[tuple[Elemento, str, _Estado]]] = defaultdict(list)
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
                    llave = ("", campo, estado.estado, f"{e.hoja}: {estado.detalle}")
                elif campo in _ARMADO and estado.estado in _SIN_VALOR:
                    llave = (e.marca, "armado", estado.estado, "")
                else:
                    llave = (e.marca, campo, estado.estado, "")
                grupos[llave].append((e, campo, estado))
        for estado in _variante(e):
            grupos[(e.marca, "variante", estado.estado, "")].append((e, "seccion_cm", estado))
    salida: list[Verificacion] = []
    cubiertas: set[tuple[str, str]] = set()  # (element_id, campo) que ya tienen su hallazgo
    for (marca, grupo, nombre, detalle), ternas in sorted(grupos.items()):
        for e, campo, _s in ternas:
            cubiertas.add((e.element_id, "variante" if grupo == "variante" else campo))
        salida.append(_hallazgo_critico(ctx, marca, nombre, detalle, ternas))
    salida += _dudosas_de_colocacion(ctx)
    salida += _dudas_sin_hallazgo(ctx, cubiertas)
    return salida


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
    return estados


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
    por el handle de su primera copia y cuántas copias tiene."""
    copias: dict[str, list[str]] = defaultdict(list)
    for e in ctx.entidades.values():
        if not e.is_textual or not e.text:
            continue
        for frase in _FRASE_DE_PILOTE.findall(_una_linea(e.text).upper()):
            if re.search(r"LONGITUD|MEC[AÁ]NICA DE SUELOS|DESPLANTE|PROFUNDIDAD", frase):
                copias[_una_linea(frase)].append(e.raw_handle)
    salida = []
    for frase, handles in sorted(copias.items(), key=lambda x: (-len(x[1]), x[0]))[:4]:
        corta = frase if len(frase) <= 160 else f"{frase[:157]}…"
        mas = f" (y {len(handles) - 1} copias)" if len(handles) > 1 else ""
        salida.append(f"«{corta}» {sorted(handles)[0]}{mas}")
    return salida


def _supuesto(ctx: _Contexto, e: Elemento, campo: str, dato: Dato) -> str:
    """El supuesto que se usa y, para una sección, lo que el plano acota cerca de su título."""
    detalle = _una_linea(dato.texto) or "supuesto de Klave"
    if campo != "seccion_cm":
        return detalle
    definicion = ctx.por_marca.get(e.marca)
    if definicion is None:
        return detalle
    acotado = []
    lados = {float(v) for v in dato.valor} if isinstance(dato.valor, list | tuple) else set()
    for aviso in definicion.avisos:
        m = _COTAS_CERCANAS.search(aviso)
        if m is None:
            continue
        valores = [v.strip() for v in m.group(1).split(",") if v.strip()]
        if any(_numero_texto(v) not in lados for v in valores):
            acotado.append(f"{', '.join(valores)} cm en {m.group(2)}")
    if acotado:
        detalle += (
            f"; cerca de su título el plano acota {'; '.join(acotado)}, que no se tomó: la "
            "supuesta no coincide con lo acotado"
        )
    return detalle


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
    if nombre == "falta":
        porque = dice or f"el plano no {pron} da"
        mensaje = (
            f"{sujeto} de {quien} ({donde}): {porque}; no hay un supuesto que {pron} sustituya: "
            f"{_consecuencia(campos)}."
        )
    elif nombre == "por_leer":
        por_campo = (
            "; ".join(f"{_CORTO[c]}: {detalles(c)}" for c in campos) if len(campos) > 1 else dice
        )
        leidos = "leyeron" if _plural(campos) else "leyó"
        mensaje = (
            f"{sujeto} de {quien} ({donde}): el plano {pron} escribe y no se {leidos} "
            f"({por_campo}); no hay un supuesto que {pron} sustituya: {_consecuencia(campos)}, "
            "por leer."
        )
    elif nombre == "supuesto" and campos == ["altura_m"]:
        hoja = detalle_de_grupo.split(":", 1)[0]
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
        mensaje = f"Los estribos de {quien} ({donde}): {dice}."
    elif nombre == "variante":
        mensaje = (
            f"{quien} tiene variantes por muro y en {_pzas(len(els))} ({_hojas(els)}) no se "
            f"sabe cuál toca: {dice}. Se usa su definición con las variantes juntas (sección "
            f"{_valor('seccion_cm', valor)}); confírmalo."
        )
    else:  # sin_estribos_declarados
        mensaje = f"{quien} ({donde}): {dice}."
    hoja = _hoja_unica(els)
    grupo = "variante" if nombre == "variante" else ",".join(campos)
    return _hallazgo(
        7,
        severidad,
        mensaje,
        clave=f"{grupo}: {nombre}" + (f": {detalle_de_grupo}" if detalle_de_grupo else ""),
        marca=marca,
        hoja=hoja,
        de_la_marca=bool(marca),
        marcas=sorted({e.marca for e in els}),
        elementos=[e.element_id for e in els],
        datos=list({id(s.dato): s.dato for s in estados if s.dato is not None}.values())[:4],
        bbox=_caja_de(ctx, els) if hoja else None,
        campo=",".join(campos),
        en_juego=_en_juego_de_campos(ctx, campos, nombre, els),
    )


def _consecuencia(campos: list[str]) -> str:
    if any(c in _GEOMETRIA for c in campos):
        return "sin ella no se cuentan su concreto ni su acero"
    return "su acero no se cuenta"


def _en_juego_de_campos(
    ctx: _Contexto, campos: list[str], nombre: str, els: list[Elemento]
) -> dict[str, float]:
    """Lo que depende del dato: el concreto si es geométrico y el acero que se pesa con él (lo
    que se pierde si se quita). Sin valor no hay cifra que perder: el concreto de esas piezas
    (``volumen_m3``) dice de qué tamaño es lo que falta."""
    juego: dict[str, float] = {"piezas": float(len(els))}
    if nombre == "sin_estribos_declarados":
        return juego  # nada que falte: el plano no los declara
    if nombre in ("falta", "por_leer"):
        juego["volumen_m3"] = sum(_volumen(e) or 0.0 for e in els)
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
            "vista dudosa": "no se sabe bien a qué planta pertenecen (su altura y su nivel "
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


def _contradicciones(ctx: _Contexto) -> list[Verificacion]:
    salida: list[Verificacion] = []
    salida += _definiciones_que_no_coinciden(ctx)
    salida += _reglas_que_no_coinciden(ctx)
    salida += _codigos_de_hoja(ctx)
    salida += _entrepisos(ctx)
    return salida


def _definiciones_que_no_coinciden(ctx: _Contexto) -> list[Verificacion]:
    """Dos lecturas del plano del mismo rango que dicen valores distintos de un campo de una
    marca (R12: por valor, nunca por cuántas alternativas hay; una copia ilegible no cuenta). Una
    marca con variantes por muro se compara variante por variante: sus variantes no se
    contradicen, cada una es de su muro."""
    salida: list[Verificacion] = []
    colocadas = _por_marca(ctx.elementos)
    for marca, definicion in sorted(ctx.por_marca.items()):
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
                grupos = _valores_leidos(dato)
                if len(grupos) < 2:
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
        cita = _una_linea(grupo[0].texto)
        lecturas.append(
            f"{_valor(campo, grupo[0].valor)} ({', '.join(hojas) or 'sin hoja'}"
            + (f"; «{cita}»" if cita else "")
            + ")"
        )
    usado = (
        "cada colocación toma la de su hoja; las de las hojas sin lectura propia, "
        f"{_valor(campo, dato.valor)}"
        if any(e.hoja in {h for g in grupos for m in g for h in hojas_de(m)} for e in els)
        else f"se usa {_valor(campo, dato.valor)}"
    )
    juego = _delta(ctx, campo, grupos, els)
    return _hallazgo(
        8,
        "duda",
        f"{nombre} tiene {len(grupos)} valores distintos {_de(campo)} en el plano: "
        f"{_listar(lecturas)}. {usado.capitalize()}; confírmalo.",
        clave=f"{campo}: {nombre}",
        marca=marca,
        marcas=[marca],
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
        for firma, hojas in _agrupar_hojas(en_una).items():
            valores = en_una[hojas[0]]
            salida.append(
                _hallazgo(
                    8,
                    "duda",
                    f"En {_listar(hojas)} el plano dice dos cosas distintas sobre {nombre}: "
                    + _listar([f"«{_una_linea(m.texto)}»" for m in valores])
                    + ". Una misma hoja no puede usar las dos; confirma cuál vale.",
                    clave=f"regla en una hoja: {nombre}: {firma}",
                    hoja=hojas[0] if len(hojas) == 1 else "",
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
                        hoja=sin_copia[0] if len(sin_copia) == 1 else "",
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
                clave=f"tabla contra soldadura: #{desde_txt}: {', '.join(numeros)}",
                hoja=hojas[0] if len(hojas) == 1 else "",
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
        f"; la de {nombre[tope.view_id]} repite la de abajo porque no hay nivel encima), pero "
        f"las cantidades dejan fuera el juego de {base} como si fuera el mismo de la planta de "
        f"arriba en su base. Las dos lecturas que se sostienen: (A) cada juego sube desde su "
        f"losa: el de {base} es el del primer entrepiso y sobre {nombre[tope.view_id]} no se "
        f"cuenta nada ({alturas_txt(sube)}): acero {kg_a:,.2f} kg, concreto {m3_a:,.2f} m³; (B) "
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


def _sin_dueno(ctx: _Contexto) -> list[Verificacion]:
    salida: list[Verificacion] = []
    salida += _rechazos_por_hoja(ctx)
    salida += _avisos_de_lectura(ctx)
    salida += _junto_a_su_seccion(ctx)
    salida += _etiquetas_de_cuadro(ctx)
    salida += _solo_ia(ctx)
    salida += _avisos_de_reglas(ctx)
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


def _clase_de_texto(texto: str) -> str:
    plano = _una_linea(texto).upper()
    if _DISTRIBUCION.match(plano):
        return "distribucion"
    if len(re.findall(r"[A-ZÁÉÍÓÚÑ]{3,}", plano)) >= 2:
        return "nota"
    if re.search(r"\d\s*[X×]\s*\d", plano) and "#" not in plano and "@" not in plano:
        return "seccion"
    return "armado"


def _rechazos_por_hoja(ctx: _Contexto) -> list[Verificacion]:
    """Los textos con armado que nadie leyó, por hoja, por motivo y por clase de texto: su cuenta,
    sus ejemplos y todos sus handles, con las marcas de las que pueden ser."""
    grupos: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
    for r in ctx.inv.rechazos:
        grupos[(r.hoja or "sin hoja", r.motivo, _clase_de_texto(r.texto))].append(r)
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


def _avisos_de_lectura(ctx: _Contexto) -> list[Verificacion]:
    """Lo que las lecturas de cada marca avisan. Lo que pide que alguien mire (un texto vetado de
    su pila, un dibujo que no coincide con sus cotas, un corte que no se pudo escoger, un texto
    de la marca que nadie leyó, la sección que no se encontró y que nada más da) es una duda, un
    hallazgo por marca. Lo que sólo informa (la familia que dio la IA y coincide con el prefijo,
    unas cotas cercanas que no se tomaron, una lectura IA que no se usa) es un aviso, un hallazgo
    por clase de aviso con todas sus marcas: así no tapa lo demás. El código de hoja repetido es
    una contradicción (verificación 8) y no se repite aquí."""
    salida = []
    informativos: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for marca, definicion in sorted({**ctx.por_marca, **ctx.por_familia}.items()):
        avisos = [a for a in definicion.avisos if "marcos distintos llevan ese código" not in a]
        dudas = [a for a in avisos if _clase_de_aviso(a, definicion) is None]
        for a in avisos:
            clase = _clase_de_aviso(a, definicion)
            if clase is not None:
                informativos[clase].append((marca, a))
        if not dudas:
            continue
        salida.append(
            _hallazgo(
                11,
                "duda",
                f"Las lecturas de {marca} avisan: " + "; ".join(dudas) + ".",
                clave="avisos de lectura",
                marca=marca if marca in ctx.por_marca else "",
                marcas=[marca],
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
        salida.append(
            _hallazgo(
                11,
                "aviso",
                f"{_AVISOS_INFORMATIVOS[clase]} ({len(marcas)} marcas): {detalle}{mas}.",
                clave=f"avisos de lectura: {clase}",
                marcas=marcas,
            )
        )
    return salida


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


def _junto_a_su_seccion(ctx: _Contexto) -> list[Verificacion]:
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
                f"{cabeza} ({donde}), por leer — "
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
    return salida


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
            cerca = []
            for r in rechazos.get(hoja, []):
                fragmento = {"seccion_cm": "seccion", "longitud_m": "longitud"}.get(campo, campo)
                if fragmento not in campos_de_fragmento(r.texto, definicion.familia):
                    continue
                caja = ctx.entidades[r.entidad_id].bbox
                if not _de_su_titulo(de_la_hoja, caja, marca, cortes):
                    continue
                cerca.append(r)
                cajas.append(caja)
            citas = [ctx.cita(r.entidad_id, r.texto) for r in cerca]
            citados += [ctx.handle(r.entidad_id) for r in cerca]
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
    "verificar",
]
