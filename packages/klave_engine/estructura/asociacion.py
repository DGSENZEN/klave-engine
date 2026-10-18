"""Asociación de la lectura estructural: a qué pieza pertenece cada texto del plano.

``asociar`` decide, sólo con la geometría del dibujo, de qué marca es cada renglón de armado de un
cuadro o de un detalle (``8#6``, ``2E#3EXT@10`` y ``CENTRO@20`` son de ``K-11``):

- **Por pila** (lo medido en Marina): la etiqueta de la marca va pegada a una columna de renglones
  de armado, encima (Marina) o debajo (otras oficinas). El primer renglón es el extremo de su
  columna (no tiene otro renglón pegado entre él y la etiqueta), empieza a lo más a 1.5 altos de
  etiqueta de ella y cae, de lado, en lo que ocupa la etiqueta ensanchada 3 altos de renglón;
  cada renglón siguiente está a lo más a 1.5 altos de renglón del anterior, se encima con él en al
  menos la mitad del más angosto y sigue dentro de la etiqueta ensanchada: una pila nunca se pasa
  a la columna de al lado. Acaba en un hueco mayor o en un texto que no puede ser suyo: otra
  etiqueta, una nota numerada, un texto que nombra su propia marca, una nota de familia, un texto
  de otra familia, la celda de un cuadro o una llamada (un texto con directriz es de lo que ésta
  señala).
- **Por fila**: en un cuadro con títulos (MARCA | SECCIÓN | ARMADO | ESTRIBOS), las celdas de un
  renglón son de la marca de ese renglón.

Todo es por hoja (el marco que contiene el ancla del texto; sin marco, su archivo) y exclusivo.
Cada etiqueta alcanza a lo más una columna de cada lado y las dos cuentan como reclamo: un
renglón que dos marcas alcanzan con huecos parecidos (10 % del mismo lado, 25 % de lados
opuestos) es ambiguo y no es de ninguna; si no, es de la más pegada, salvo que la geometría deje
dudas (ver ``_repartir``). Una etiqueta con columnas de los dos lados se queda con la que tiene
enfrente o la más pegada (si empatan, la de arriba), pero si ésa también la alcanza otra marca,
la etiqueta es ambigua: su lectura depende de cómo se reparta todo el grupo y no se adivina. Una
pila se toma entera o no se toma, y si al tomarla deja sin pila a otra etiqueta que la alcanzaba,
no se toma (R55: la geometría sola no sabe de cuál de las dos es). Lo que sigue de una columna más
allá de la etiqueta que la corta sigue siendo un reclamo de la dueña de la columna: sólo la que la
corta metida en la columna puede quedárselo, y cualquier otra marca que lo alcance empata. Una
columna que se junta con otra (su siguiente renglón sigue igual o más pegado a uno de al lado) o se
abre en dos queda en duda igual que una cortada, y dos o más etiquetas que se toman cada una la pila
que otra alcanza, en rueda, no se toman (R56). También queda en duda la pila que no se sigue limpio:
un renglón en la etiqueta ensanchada a la altura del siguiente (o entre la etiqueta y el primero)
que no se encima con el de junto en la mitad del más angosto, como en una pila con renglones
alineados unos a la izquierda, otros a la derecha o al centro, o un primer renglón junto a otra
etiqueta más pegada que no le queda enfrente; ése y lo que puede seguirlo siguen siendo reclamos
de la columna (R57): nunca un final limpio que deje el resto a otra etiqueta ni una pila a medias.
Un renglón al lado del que sigue limpio sólo es de la columna de al lado si otra etiqueta más cerca
de él lo tiene en su ensanche; y también dejan la pila en duda otra etiqueta junto a la columna que
tiene a su alcance el renglón que sigue, y un primer renglón con otro admitido a su lado, ninguno
sobre la etiqueta (R59).
Lo que no se pudo pegar sale como rechazo: ambiguo, de otra familia, sin lector (dice de quién es
pero ningún lector lo lee), de una etiqueta con varias marcas o sin dueño: nada se queda sin leer
en silencio."""

import bisect
import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.text_patterns import TextPatternConfig
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura._armado_texto import LADO, LADO_FINAL
from klave_engine.estructura.armado import parsear_armado, tiene_armado
from klave_engine.estructura.marcas import (
    MARCA_RE,
    es_rango,
    extremos_de_rango,
    leer_marcas,
    marca_en_rango,
    marca_sola,
    sin_referencias,
    titulos,
)
from klave_engine.estructura.marcas import escrita as _escrita
from klave_engine.estructura.notas import leer_notas_con_renglones
from klave_engine.estructura.textos import alto_de_texto, ancla_texto, caja_de_texto

__all__ = [
    "ARMADO_RE",
    "Asociacion",
    "Rechazo",
    "ancla_texto",
    "asociar",
    "asociar_secciones",
    "hoja_de",
    "hoja_y_llave",
    "lo_lee_una_nota",
    "extremos_de_rango",
    "leer_marcas",
    "marca_en_rango",
    "marca_en_texto",
    "marcas_en_nota",
    "nombra_varias",
    "sin_referencias",
]

# Un texto con forma de armado: una varilla (``#4``), una separación (``@20``) o el renglón que
# sigue una zona de estribos (``CENTRO@20``, ``EXT @10``); «CENTRO DE CARGA» no.
ARMADO_RE = re.compile(r"#\s*\d|@\s*\d|^\s*CENTRO\s*@|^\s*EXT\s*@", re.I)

_PREFIJO_DE_ETIQUETA = re.compile(r"^(?:CASTILLO|COLUMNA)\s+")
_LARGO_DE_ETIQUETA = 10
_LARGO_DE_VARIAS = 40
_JUNTAS = " Y "  # cómo se escribe la «marca» de una etiqueta de varias
# Lo que hace que la lectura de notas (``detection.schedules._parse_annotations``) tome un texto:
# una sección (15x20, sin las piezas de 3 medidas) o lo que el parser del armado lee en él.
_SECCION = re.compile(rf"(?<![\dxX×.])({LADO})\s*[xX×]\s*({LADO_FINAL})(?![\dxX×]|\.\d)")
_PIEZA = re.compile(rf"{LADO}\s*[xX×]\s*\d{{1,3}}(?:\.\d+)?\s*[xX×]\s*{LADO_FINAL}")
_LADO_DE_SECCION_CM = (8, 400)

# Un texto que nombra otra familia es de la lectura de esa familia (la losa, el muro, la nota de
# dalas): nunca entra a una pila, nunca es huérfano y una pila nunca sigue más allá de él.
_OTRA_FAMILIA = re.compile(r"\b(?:LOSA|DALA|CADENA|CONTRATRABE|TRABE|VIGA|MURO|ZAPATA)")
# Las notas de familia de castillos y columnas («CASTILLOS 15X15 4#3 E#2@20») tampoco entran a
# una pila: son de toda la familia, no de una marca. ARMEX es un armado prefabricado, no una
# familia (R107).
_NOTA_DE_FAMILIA = re.compile(r"\b(?:CASTILLO|COLUMNA)")
# Un renglón numerado («4.- SE PERMITE…», «5) …», «a).- …», «B) …», R110), en cualquier línea de un
# MTEXT.
_NOTA_NUMERADA = re.compile(
    r"^\s*(?:\d{1,2}[.\-)]+|[A-Za-z](?:\)[.\-]*|\.-)(?!\s*[#Ø\d]))(?:\s|$)", re.M
)

# Un cuadro con títulos (como lo lee ``detection.schedules``): un renglón de al menos tres títulos
# cortos, dos de ellos de cuadro, y debajo un renglón por marca.
_TITULO_DE_CUADRO = re.compile(
    r"MARCA|CLAVE|TIPO|CASTILLO|COLUMNA|SECC|DIMENS|ARMADO|REFUERZO|VARILLA|ESTRIBO", re.I
)
_COLUMNA_DE_MARCA = re.compile(r"MARCA|CLAVE|TIPO|CASTILLO|COLUMNA|TRABE", re.I)
_MISMO_RENGLON = 0.6  # × la mediana de los altos
_FIN_DEL_CUADRO = 4.0  # un hueco de más renglones acaba el cuadro
_TRAMO = 15.0  # un hueco de más altos entre dos textos del renglón: ya es otra parte de la hoja

# La pila. El primer renglón a lo más a 1.5 altos de etiqueta; los siguientes, a lo más a 1.5
# altos de renglón del anterior (Marina: 0.7–0.8 en castillos y columnas; 1.3 en el cuadro de
# pilotes, que deja más aire); de lado, la etiqueta se ensancha 3 altos de renglón y cada renglón
# se encima con el anterior en al menos la mitad del más angosto (en Marina, siempre entero).
_HUECO_DE_ETIQUETA = 1.5
_HUECO_ENTRE_RENGLONES = 1.5
_ENSANCHE = 3.0
_ENCIMA_MINIMO = 0.5
# Dos huecos son el mismo si difieren a lo más 10 % (o una décima de alto, para los que casi
# tocan); desde lados opuestos de la columna, 25 % (R54): una etiqueta pegada abajo de la pila de
# otra fila compite con la de esa pila.
_EMPATE = 0.10
_EMPATE_OPUESTO = 0.25
_EMPATE_ABSOLUTO = 0.1
# La costumbre de un cuadro (etiqueta debajo o encima de su pila) se sabe con al menos dos pilas
# sin disputa y 80 % de ellas del mismo lado.
_COSTUMBRE_MINIMA = 2
_COSTUMBRE_PARTE = 0.8
# Un texto está «encima» de otro aunque se le meta hasta una décima de alto.
_TRASLAPE = 0.1
# Una pila de enfrente apenas fuera del alcance (hasta el doble) y a menos del doble del hueco de
# la que sí alcanza hace dudar de ésta.
_CASI = 2.0
# Una etiqueta está metida entre dos renglones si al menos la mitad de su alto cae en el hueco.
_EN_EL_PASILLO = 0.5
# Dos textos iguales a menos de esto (× el alto) son el mismo texto dibujado dos veces.
_DUPLICADO = 0.25
# Una llamada: un texto del que sale una directriz (una línea abierta que pasa a menos de 0.6
# altos de él y llega a más de 2 altos) hacia lo que describe, p. ej. las varillas de un corte.
# Es de lo que señala, no de una pila. En Marina las directrices de los detalles de trabes tocan
# su texto a 0.17–0.29 altos y llegan a 6–8; ninguna línea pasa a menos de 2.5 altos de un
# renglón de sus pilas.
_PUNTA_DE_LLAMADA = 0.6
_LARGO_DE_LLAMADA = 2.0
# Textos girados hasta 1° de diferencia se leen en la misma dirección.
_MISMO_GIRO = 1


def marca_en_texto(texto: str, config: TextPatternConfig) -> str | None:
    """La marca que nombra ``texto`` cuando nombra una sola sin ambigüedad (R67, ``leer_marcas``):
    el texto entero si es una etiqueta de la configuración; si no, la marca acotada («T1-1 4#3» →
    T1-1, «K15A 4#3» → K15A, como la escribe la etiqueta). Una lista, un rango o una marca pegada
    a otra cosa no dan marca."""
    limpio = texto.strip().upper()
    if marca_sola(limpio, config) == limpio:
        return limpio
    lectura = leer_marcas(limpio, config)
    return lectura.marca if lectura.tipo == "unica" else None


class Asociacion(BaseModel):
    """Los textos de una marca en una hoja, leídos de su pila o de su fila del cuadro."""

    etiqueta_id: str  # el texto de la marca: una etiqueta que es definición, no colocación
    marca: str
    hoja: str
    # Un renglón por elemento, de arriba abajo (los de una fila, de izquierda a derecha); un
    # MTEXT de varios renglones da uno por renglón.
    textos: list[str]
    entidades: list[str]  # la entidad de cada elemento de ``textos`` (se repite en un MTEXT)
    via: Literal["pila", "fila"]
    # De una fila: el cuadro al que pertenece (la primera celda de su renglón de títulos).
    cuadro: str | None = None


class Rechazo(BaseModel):
    """Un texto con forma de armado que no se pegó a ninguna marca, o una etiqueta que se quedó
    sin la pila que alcanzaba; y por qué."""

    entidad_id: str
    texto: str
    hoja: str
    # ambigua: dos o más marcas lo pueden reclamar y no se puede decidir de cuál es (``marcas``);
    # otra_familia: está en la pila de una marca pero nombra otra familia; sin_lector: nombra su
    # marca (en ``marcas``) o su familia pero ningún lector lo lee («K-7 E#3@1S»); varias_marcas:
    # es de la pila de una etiqueta con varias marcas («K-1 Y K-2» → [K-1, K-2]) o un rango («K-1
    # A K-4» → [«K-1 A K-4»], como se escribió), o una nota que nombra varias, que E0 no lee;
    # sin_dueno: nada lo lee.
    motivo: Literal["ambigua", "otra_familia", "sin_lector", "varias_marcas", "sin_dueno"]
    marcas: list[str] = Field(default_factory=list)
    # Las familias que nombra un texto con armado que no es la nota de ninguna: su palabra no es
    # el sujeto («2 VARILLAS #5 ANCLADA AL MURO O CADENA …» → dala, muro; R83).
    familias: list[str] = Field(default_factory=list)
    # Un texto rechazado (por cualquier motivo, R116) en la columna de una etiqueta, más allá de
    # donde su pila se cortó (R111): puede ser de esa etiqueta. Bloquea su lectura IA en lo que el
    # texto dice; nunca es un dato.
    posibles: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------- qué es cada texto

_Clase = Literal[
    "etiqueta",
    "linea",
    "llamada",
    "ajena",
    "familia",
    "nota",
    "anotacion",
    "sin_lector",
    "nada",
]


def _marca_de_etiqueta(texto: str, config: TextPatternConfig) -> str | None:
    """La marca si el texto entero (a lo más 10 caracteres, sin «CASTILLO »/«COLUMNA » delante)
    es una marca: una etiqueta de cuadro o de planta (``marca_sola``, o escrita con espacios, «K
    1»)."""
    limpio = _PREFIJO_DE_ETIQUETA.sub("", " ".join(texto.split()).upper())
    if not limpio or len(limpio) > _LARGO_DE_ETIQUETA:
        return None
    sola = marca_sola(limpio, config)
    if sola is not None:
        return sola
    espaciada = MARCA_RE.fullmatch(limpio)
    return _escrita(espaciada) if espaciada is not None else None


def _varias_marcas(texto: str, config: TextPatternConfig) -> list[str] | None:
    """Las marcas de una etiqueta que nombra dos o más y nada más («K-1 Y K-2» → [K-1, K-2], «K-1
    A K-4», «K-1-K-3» como se escribieron), o ``None``. Una con una marca pegada a algo no es
    etiqueta."""
    limpio = _PREFIJO_DE_ETIQUETA.sub("", " ".join(texto.split()).upper())
    if len(limpio) > _LARGO_DE_VARIAS:
        return None
    lectura = leer_marcas(limpio, config)
    return lectura.piezas if lectura.tipo == "varias" and lectura.solo_marcas else None


def _marcas_de(marca: str) -> list[str]:
    """Las marcas de una etiqueta (una, o varias si es de varias; un rango, como se escribió)."""
    return marca.split(_JUNTAS)


def _es_de_varias(marca: str, config: TextPatternConfig) -> bool:
    """Si la etiqueta nombra más de una marca: una lista o un rango (también sin espacios,
    «K-1-K-3»)."""
    return _JUNTAS in marca or es_rango(marca, config)


def lo_lee_una_nota(texto: str) -> bool:
    """Si la lectura de notas (``detection.schedules``) toma ``texto``: tiene una sección (dos
    lados de 8 a 400 cm) o el parser del armado lee en ella varillas, una malla o un juego de
    estribos, como los escriba («K-1 4#3», «K-3 #4@20», «K-7 E#3@20», «K-1 4 VARS. N° 3», «K-1 4
    VARS 3/8"»: R91, un solo vocabulario). Lo que el parser reconoce y no lee («K-7 E#3@1S») no
    lo lee nadie: es un rechazo «sin_lector», con la marca que nombra."""
    if not re.search(r"\d", texto):
        return False  # sin cifras no hay sección ni armado: no se llama al parser
    piezas = [m.span() for m in _PIEZA.finditer(texto)]
    for m in _SECCION.finditer(texto):
        if any(a <= m.start() < b for a, b in piezas):
            continue
        lados = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        if all(_LADO_DE_SECCION_CM[0] <= lado <= _LADO_DE_SECCION_CM[1] for lado in lados):
            return True
    # Las mallas se leen en una familia que las lleva; varillas y estribos, en cualquiera.
    armado = parsear_armado([texto], "muro")
    return bool(armado.longitudinales or armado.estribos or armado.parrillas)


def marcas_en_nota(texto: str, config: TextPatternConfig) -> list[str]:
    """Lo que nombra un texto según la gramática de marcas (``leer_marcas``): su marca, o sus marcas
    y rangos como se escribieron, o, si alguna va pegada a algo, todas sus candidatas."""
    return leer_marcas(texto, config).piezas


def nombra_varias(marcas: list[str], config: TextPatternConfig | None = None) -> bool:
    """Si lo que nombra un texto (``marcas_en_nota``) es más de una marca: una lista o un rango."""
    return len(marcas) > 1 or any(es_rango(m, config or TextPatternConfig()) for m in marcas)


def _clase(
    e: NormalizedEntity, config: TextPatternConfig, de_notas: set[str]
) -> tuple[_Clase, str | None]:
    """Qué es un texto para la asociación: una etiqueta (con su marca), un renglón de armado que
    puede ir en una pila, o un texto de armado que tiene otro dueño (una nota numerada, uno que
    nombra su marca, uno de otra familia, una nota de castillos o columnas) o que dice de quién
    es pero nadie lo lee; lo demás, nada."""
    texto = e.text or ""
    marca = _marca_de_etiqueta(texto, config)
    if marca is not None:
        return "etiqueta", marca
    varias = _varias_marcas(texto, config)
    if varias is not None:
        # Reclama su pila como cualquier etiqueta (que ninguna vecina se la lleve), aunque E0
        # no lea definiciones de varias marcas.
        return "etiqueta", _JUNTAS.join(varias)
    if ARMADO_RE.search(texto) is None and not tiene_armado(texto):
        # R91: armado es lo que el parser reconoce, con «#» o sin él («K-1 4 VARS 3/8"»).
        return "nada", None
    if e.entity_id in de_notas or _NOTA_NUMERADA.search(texto):
        return "nota", None
    mayusculas = texto.upper()
    if _OTRA_FAMILIA.search(mayusculas):
        return "ajena", None
    if leer_marcas(texto, config).nombra:
        # «K-1 15x20 4#3 E#2@20» dice de quién es y lo lee la nota (si la nombra sin ambigüedad);
        # «K-7 E#3@1S», no. Una marca pegada a algo o varias también dicen de quién es.
        return ("anotacion" if lo_lee_una_nota(texto) else "sin_lector"), None
    if titulos(texto, config):
        # «CORTE K-1 15X20 4#3»: el título de otro dibujo dice de quién es; nadie lo lee y nunca
        # entra a la pila de otra marca (R68.8).
        return "sin_lector", None
    if _NOTA_DE_FAMILIA.search(mayusculas):
        # La nota de familia la lee (o la reporta con su aviso) la lectura de notas.
        lee = lo_lee_una_nota(texto) or tiene_armado(texto)
        return ("familia" if lee else "sin_lector"), None
    return "linea", None


# ----------------------------------------------------------------------- dónde está cada texto


@dataclass(eq=False)
class _Texto:
    e: NormalizedEntity
    clase: _Clase
    marca: str | None
    x0: float
    x1: float
    y0: float
    y1: float
    alto: float
    # Hacia dónde puede ir su pila: arriba (+1), abajo (-1). Una etiqueta, de los dos lados; la
    # sección de un título (R147), sólo del lado contrario al de su título.
    sentidos: tuple[int, ...] = (+1, -1)

    @property
    def id(self) -> str:
        return self.e.entity_id

    @property
    def texto(self) -> str:
        return (self.e.text or "").strip()

    @property
    def renglones(self) -> list[str]:
        return [r.strip() for r in self.texto.split("\n") if r.strip()]

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _giros(textos: list[NormalizedEntity]) -> dict[str, int]:
    """La dirección de cada texto en grados enteros; las que difieren en a lo más 1° (0° y 359°
    también) se juntan en la más común de su grupo."""
    redondeo = {e.entity_id: round((e.rotation or 0.0) % 360.0) % 360 for e in textos}
    cuantos = Counter(redondeo.values())
    valores = sorted(cuantos)
    grupos: list[list[int]] = []
    for v in valores:
        if grupos and v - grupos[-1][-1] <= _MISMO_GIRO:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    if len(grupos) > 1 and grupos[0][0] + 360 - grupos[-1][-1] <= _MISMO_GIRO:
        grupos[0] = grupos.pop() + grupos[0]
    representante = {}
    for grupo in grupos:
        comun = max(grupo, key=lambda g: (cuantos[g], -g))
        for v in grupo:
            representante[v] = comun
    return {i: representante[g] for i, g in redondeo.items()}


def _texto_local(e: NormalizedEntity, giro: int, clase: _Clase, marca: str | None) -> _Texto:
    """El texto en el marco de su renglón (girado ``giro`` grados): ahí una pila es vertical."""
    angulo = math.radians(giro)
    c, s = math.cos(angulo), math.sin(angulo)
    ax, ay = ancla_texto(e)
    lx, ly = ax * c + ay * s, -ax * s + ay * c
    dx0, dx1, dy0, dy1, alto = caja_de_texto(e, angulo)
    return _Texto(e, clase, marca, lx + dx0, lx + dx1, ly + dy0, ly + dy1, alto)


class _Lineas:
    """Los vértices de las líneas abiertas (líneas, polilíneas, directrices) en una rejilla,
    para saber qué textos son llamadas."""

    def __init__(self, entities: list[NormalizedEntity], celda: float) -> None:
        self.celda = celda
        self.trazos: list[list[tuple[float, float]]] = []
        self.rejilla: dict[tuple[str, int, int], list[tuple[float, float, int]]] = defaultdict(list)
        for e in entities:
            if e.entity_type not in (EntityType.line, EntityType.polyline) or e.is_closed:
                continue
            if not e.points or len(e.points) < 2:
                continue
            trazo = [(float(q[0]), float(q[1])) for q in e.points]
            n = len(self.trazos)
            self.trazos.append(trazo)
            for x, y in trazo:
                self.rejilla[(e.source_file, int(x // celda), int(y // celda))].append((x, y, n))

    def es_llamada(self, t: _Texto, giro: int) -> bool:
        """Si de ``t`` sale una directriz: una línea abierta con un vértice a menos de 0.6 altos
        de su caja y otro a más de 2 altos."""
        angulo = math.radians(giro)
        c, s = math.cos(angulo), math.sin(angulo)
        punta = _PUNTA_DE_LLAMADA * t.alto

        def lejania(x: float, y: float) -> float:
            lx, ly = x * c + y * s, -x * s + y * c
            return math.hypot(max(t.x0 - lx, 0.0, lx - t.x1), max(t.y0 - ly, 0.0, ly - t.y1))

        esquinas = [
            (x * c - y * s, x * s + y * c)
            for x in (t.x0 - punta, t.x1 + punta)
            for y in (t.y0 - punta, t.y1 + punta)
        ]
        xs, ys = [q[0] for q in esquinas], [q[1] for q in esquinas]
        archivo = t.e.source_file
        vistos: set[int] = set()
        for i in range(int(min(xs) // self.celda), int(max(xs) // self.celda) + 1):
            for j in range(int(min(ys) // self.celda), int(max(ys) // self.celda) + 1):
                for x, y, n in self.rejilla.get((archivo, i, j), ()):
                    if n in vistos or lejania(x, y) > punta:
                        continue
                    vistos.add(n)
                    if any(
                        lejania(qx, qy) >= _LARGO_DE_LLAMADA * t.alto for qx, qy in self.trazos[n]
                    ):
                        return True
        return False


def _lineas(entities: list[NormalizedEntity], textos: list[NormalizedEntity]) -> _Lineas:
    altos = [alto_de_texto(e) for e in textos]
    celda = 4.0 * statistics.median(altos) if altos else 1.0
    return _Lineas(entities, max(celda, 1e-6))


# ------------------------------------------------------------------------------------ hojas


def hoja_de(frames: list[SheetFrame]) -> Callable[[NormalizedEntity], str]:
    """La hoja de un texto como la nombra la asociación: el código del marco más chico de su
    archivo que contiene su ancla (o su id si no tiene código); sin marco, su archivo."""
    llave_y_hoja = _hoja_de(frames)
    return lambda e: llave_y_hoja(e)[1]


def hoja_y_llave(frames: list[SheetFrame]) -> Callable[[NormalizedEntity], tuple[str, str]]:
    """La hoja de un texto (su nombre, ``hoja_de``) y una llave única de ella (archivo y marco):
    dos marcos con el mismo código, o dos archivos sin marcos, son hojas distintas."""
    llave_y_hoja = _hoja_de(frames)

    def hoja(e: NormalizedEntity) -> tuple[str, str]:
        (archivo, marco), nombre = llave_y_hoja(e)
        return nombre, f"{archivo}#{marco or ''}"

    return hoja


def _hoja_de(frames: list[SheetFrame]) -> Callable[[NormalizedEntity], tuple[tuple, str]]:
    """La hoja de un texto: el marco más chico de su archivo que contiene su ancla (su código, o
    su id si no tiene); sin marco, el archivo. Devuelve también una llave única de esa hoja."""
    ordenados = sorted(frames, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    def hoja(e: NormalizedEntity) -> tuple[tuple, str]:
        punto = ancla_texto(e)
        for marco in ordenados:
            if marco.source_file in ("", e.source_file) and marco.contains(punto):
                return (e.source_file, marco.frame_id), marco.code or marco.frame_id
        return (e.source_file, None), e.source_file

    return hoja


# --------------------------------------------------------------------------------- cuadros


def _renglones(textos: list[_Texto]) -> list[list[_Texto]]:
    altos = [t.alto for t in textos if t.alto > 0]
    if not altos:
        return []
    tolerancia = statistics.median(altos) * _MISMO_RENGLON

    def centro(t: _Texto) -> float:
        return (t.y0 + t.y1) / 2

    renglones: list[list[_Texto]] = []
    for t in sorted(textos, key=lambda t: (-centro(t), t.cx)):
        if renglones and abs(centro(renglones[-1][0]) - centro(t)) <= tolerancia:
            renglones[-1].append(t)
        else:
            renglones.append([t])
    for renglon in renglones:
        renglon.sort(key=lambda t: t.cx)
    return renglones


def _tramos(renglon: list[_Texto]) -> list[list[_Texto]]:
    """Un renglón de la hoja partido donde hay un hueco de más de 15 altos: lo que está a la
    misma altura en otra vista no es parte del mismo cuadro."""
    alto = statistics.median(t.alto for t in renglon)
    tramos: list[list[_Texto]] = [[renglon[0]]]
    for t in renglon[1:]:
        if t.x0 - tramos[-1][-1].x1 > _TRAMO * alto:
            tramos.append([t])
        else:
            tramos[-1].append(t)
    return tramos


def _es_cabeza(tramo: list[_Texto], config: TextPatternConfig) -> bool:
    """Al menos tres títulos cortos, dos de cuadro (MARCA, SECCIÓN, ARMADO…), y ninguno nombra
    una marca ni trae armado (una fila de leyendas «K-1 / CASTILLO» no es un encabezado)."""
    if len(tramo) < 3 or any(len(c.texto.split()) > 3 for c in tramo):
        return False
    if sum(1 for c in tramo if _TITULO_DE_CUADRO.search(c.texto)) < 2:
        return False
    return not any(ARMADO_RE.search(c.texto) or leer_marcas(c.texto, config).nombra for c in tramo)


def _filas_de_cuadros(
    textos: list[_Texto], config: TextPatternConfig
) -> list[tuple[_Texto, str, list[_Texto], str]]:
    """Las filas de los cuadros con títulos: ``(celda de la marca, marca, demás celdas, cuadro)``,
    donde ``cuadro`` es la primera celda de su renglón de títulos.

    Como ``detection.schedules``: un renglón de títulos abre el cuadro; cada renglón de abajo pone
    sus textos en la columna cuyo título le queda más cerca (a lo más media separación de
    columnas; lo que cae fuera no es del cuadro) y su marca es la de la columna de marcas (o la
    primera que aparezca); el cuadro acaba en un renglón sin marca o tras un hueco de más de
    cuatro renglones."""
    renglones = _renglones(textos)
    filas: list[tuple[_Texto, str, list[_Texto], str]] = []
    for i, renglon in enumerate(renglones):
        for cabeza in _tramos(renglon):
            if _es_cabeza(cabeza, config):
                filas += [
                    (etiqueta, marca, celdas, cabeza[0].id)
                    for etiqueta, marca, celdas in _filas_bajo(cabeza, renglones[i + 1 :], config)
                ]
    return filas


def _filas_bajo(
    cabeza: list[_Texto], abajo: list[list[_Texto]], config: TextPatternConfig
) -> list[tuple[_Texto, str, list[_Texto]]]:
    columnas = [(c.cx, c.texto.upper()) for c in cabeza]
    xs = sorted(x for x, _ in columnas)
    holgura = 0.5 * statistics.median(b - a for a, b in zip(xs, xs[1:], strict=False))
    alto = statistics.median(c.alto for c in cabeza) or 1.0
    y_previa = statistics.median((c.y0 + c.y1) / 2 for c in cabeza)
    filas: list[tuple[_Texto, str, list[_Texto]]] = []
    for renglon in abajo:
        y = (renglon[0].y0 + renglon[0].y1) / 2
        if y_previa - y > alto * _FIN_DEL_CUADRO:
            break
        celdas: dict[str, list[_Texto]] = {}
        for c in renglon:
            x, titulo = min(columnas, key=lambda col: abs(col[0] - c.cx))
            if abs(x - c.cx) <= holgura:
                celdas.setdefault(titulo, []).append(c)
        if not celdas:
            continue  # lo de este renglón está en otra parte de la hoja
        y_previa = y
        etiqueta, marca = _marca_de_la_fila(celdas, config)
        if etiqueta is None or marca is None:
            break
        demas = sorted(
            (c for cs in celdas.values() for c in cs if c is not etiqueta), key=lambda c: c.x0
        )
        filas.append((etiqueta, marca, demas))
    return filas


def _marca_de_la_fila(
    celdas: dict[str, list[_Texto]], config: TextPatternConfig
) -> tuple[_Texto | None, str | None]:
    """La celda y la marca de una fila: la de la columna de marcas o, si no, la primera celda que
    nombra una. Sólo una marca sin ambigüedad (R67): una celda con varias o con una marca pegada a
    algo no da marca, y la fila no se lee."""
    for titulo, cs in celdas.items():
        if _COLUMNA_DE_MARCA.search(titulo):
            lectura = leer_marcas(" ".join(c.texto for c in cs), config)
            if lectura.tipo != "unica":
                break
            duena = next((c for c in cs if leer_marcas(c.texto, config).nombra), cs[0])
            return duena, lectura.marca
    for cs in celdas.values():
        for c in cs:
            lectura = leer_marcas(c.texto, config)
            if lectura.nombra:
                return (c, lectura.marca) if lectura.tipo == "unica" else (None, None)
    return None, None


# ------------------------------------------------------------------------------------ pilas


class _Indice:
    """Textos ordenados para buscar por altura."""

    def __init__(self, textos: list[_Texto]) -> None:
        self.por_base = sorted(textos, key=lambda t: t.y0)
        self.bases = [t.y0 for t in self.por_base]
        self.por_tope = sorted(textos, key=lambda t: t.y1)
        self.topes = [t.y1 for t in self.por_tope]

    def cerca(self, borde: float, sentido: int, alcance: float, holgura: float) -> list[_Texto]:
        if sentido > 0:  # los que empiezan arriba del borde
            a = bisect.bisect_left(self.bases, borde - holgura)
            b = bisect.bisect_right(self.bases, borde + alcance)
            return self.por_base[a:b]
        a = bisect.bisect_left(self.topes, borde - alcance)
        b = bisect.bisect_right(self.topes, borde + holgura)
        return self.por_tope[a:b]


def _hueco(desde: _Texto | float, t: _Texto, sentido: int) -> float:
    if isinstance(desde, _Texto):
        desde = desde.y1 if sentido > 0 else desde.y0
    return t.y0 - desde if sentido > 0 else desde - t.y1


def _casi_igual(a: float, b: float, alto: float, tolerancia: float = _EMPATE) -> bool:
    return abs(a - b) <= max(tolerancia * max(a, b), _EMPATE_ABSOLUTO * alto)


def _lejania(centro: float, t: _Texto) -> float:
    if t.x0 <= centro <= t.x1:
        return 0.0
    return min(abs(t.x0 - centro), abs(t.x1 - centro))


def _traslapa(t: _Texto, x0: float, x1: float) -> bool:
    return t.x1 >= x0 and t.x0 <= x1


def _se_enciman(a: _Texto, b: _Texto) -> bool:
    """Dos renglones de la misma columna: se enciman de lado en al menos la mitad del más
    angosto."""
    comun = min(a.x1, b.x1) - max(a.x0, b.x0)
    return comun >= _ENCIMA_MINIMO * min(a.x1 - a.x0, b.x1 - b.x0)


def _en_la_etiqueta(etiqueta: _Texto, t: _Texto, alto: float | None = None) -> bool:
    """Si ``t`` cae, de lado, en la etiqueta ensanchada 3 altos de renglón (los de ``t``, o
    ``alto`` si es menor: una etiqueta vecina no se ensancha con su letra más alta)."""
    margen = _ENSANCHE * (t.alto if alto is None else min(t.alto, alto))
    return _traslapa(t, etiqueta.x0 - margen, etiqueta.x1 + margen)


def _paso(
    indice: _Indice,
    borde: float,
    sentido: int,
    alcance: float,
    alto: float,
    centro: float,
    fuera: set[str],
    admite: Callable[[_Texto], bool],
    prefiere: Callable[[_Texto], bool] | None = None,
    empatados: list[_Texto] | None = None,
) -> _Texto | None:
    """El texto admitido más pegado a ``borde`` en ``sentido`` (+1 arriba, -1 abajo), a lo más a
    ``alcance``; si alguno cumple ``prefiere``, sólo entre ésos; entre los que quedan igual de
    pegados, el más cerca del centro de la etiqueta. En ``empatados`` deja todos los admitidos."""
    encontrados: list[tuple[float, _Texto]] = []
    for t in indice.cerca(borde, sentido, alcance, _TRASLAPE * alto):
        if t.id in fuera:
            continue
        hueco = _hueco(borde, t, sentido)
        if hueco < -_TRASLAPE * min(alto, t.alto) or hueco > alcance or not admite(t):
            continue
        encontrados.append((max(hueco, 0.0), t))
    if prefiere is not None and any(prefiere(t) for _, t in encontrados):
        encontrados = [(h, t) for h, t in encontrados if prefiere(t)]
    if not encontrados:
        return None
    menor = min(h for h, _ in encontrados)
    pegados = [(h, t) for h, t in encontrados if _casi_igual(h, menor, t.alto)]
    if empatados is not None:
        empatados.extend(t for _, t in encontrados)
    return min(pegados, key=lambda ht: (_lejania(centro, ht[1]), ht[0], ht[1].x0, ht[1].id))[1]


@dataclass(eq=False)
class _Alcance:
    """Lo que una etiqueta alcanza de un lado: una columna de renglones, de ella hacia afuera."""

    etiqueta: _Texto
    sentido: int
    hueco: float  # de la etiqueta al primer renglón
    renglones: list[_Texto]
    frontal: bool = True  # su primer renglón está sobre la etiqueta misma, no sólo en su ensanche
    tope: _Texto | None = None  # un texto de otra familia que la paró
    # Otra etiqueta metida entre dos renglones de la columna (``mas_alla`` es el que sigue): si
    # ésa no lo alcanza, la pila no se sabe dónde acaba.
    cortada: _Texto | None = None
    mas_alla: _Texto | None = None
    # La columna más allá del corte (desde ``mas_alla``): no es de la pila, pero sigue siendo un
    # reclamo de esta etiqueta; sólo la que la corta puede quedársela.
    despues: list[_Texto] = field(default_factory=list)
    # La que corta está metida en la columna (en la etiqueta ensanchada): una lista de etiquetas,
    # cada una con su pila. Una que sólo la tiene enfrente de lado (la punta de un renglón largo)
    # no corta limpio: la pila queda en duda y lo de más allá no es suyo sin oposición.
    corte_limpio: bool = True
    # La pila no se sabe dónde acaba: dos columnas que se juntan en un renglón que sigue igual de
    # pegado a las dos, una que se abre en dos (R56) o una que no se sigue limpio (R57).
    fusion: bool = False

    @property
    def marca(self) -> str:
        return self.etiqueta.marca or ""


def _sigue(etiqueta: _Texto, previo: _Texto, libres: set[str]) -> Callable[[_Texto], bool]:
    """Lo que puede seguir a ``previo`` en la pila, siempre dentro de la etiqueta ensanchada: un
    renglón encimado con ``previo`` en al menos la mitad del más angosto (no se pasa a la columna
    de al lado), o cualquier otro texto que se le encime de lado, que la para."""

    def admite(t: _Texto) -> bool:
        if t.id in libres:
            return _en_la_etiqueta(etiqueta, t) and _se_enciman(previo, t)
        return _en_la_etiqueta(etiqueta, t, previo.alto) and _traslapa(t, previo.x0, previo.x1)

    return admite


def _a_su_alcance(previo: _Texto, sentido: int, donde: _Indice) -> list[tuple[float, _Texto]]:
    """Los textos de ``donde`` a lo más a 1.5 altos de ``previo`` hacia ``sentido`` (sin los que
    van a su lado), con su hueco."""
    alcance = _HUECO_ENTRE_RENGLONES * previo.alto
    borde = previo.y1 if sentido > 0 else previo.y0
    cerca: list[tuple[float, _Texto]] = []
    for t in donde.cerca(borde, sentido, alcance, _TRASLAPE * previo.alto):
        hueco = _hueco(borde, t, sentido)
        if -_TRASLAPE * min(previo.alto, t.alto) <= hueco <= alcance:
            cerca.append((max(hueco, 0.0), t))
    return sorted(cerca, key=lambda ht: (ht[0], ht[1].id))


def _dudas(
    etiqueta: _Texto,
    previo: _Texto,
    sentido: int,
    renglones: _Indice,
    libres: set[str],
    fuera: set[str],
) -> list[tuple[float, _Texto]]:
    """Los renglones que podrían seguir a ``previo`` en la pila pero no lo siguen limpio (R57),
    con su hueco, del más pegado al más lejano: a lo más a 1.5 altos de él y en la etiqueta
    ensanchada, pero sin encimarse con él en la mitad del más angosto (una pila con renglones
    alineados unos a la izquierda y otros a la derecha, o al centro). Uno fuera del ensanche no:
    tampoco se seguiría alineado (``_sigue``), así que no es de esta pila de ningún modo (el
    renglón largo de una columna que apenas llega a la de al lado no la pone en duda)."""
    limpio = _sigue(etiqueta, previo, libres)
    return [
        (hueco, t)
        for hueco, t in _a_su_alcance(previo, sentido, renglones)
        if t.id not in fuera and t.id in libres and not limpio(t) and _en_la_etiqueta(etiqueta, t)
    ]


def _a_su_lado(a: _Texto, b: _Texto) -> bool:
    """Dos textos en el mismo renglón: se enciman de alto."""
    return min(a.y1, b.y1) > max(a.y0, b.y0)


def _no_mas_lejos(hueco: float, t: _Texto, hueco_de: float, de: _Texto) -> bool:
    """Si ``t`` (a ``hueco``) no queda más allá de ``de`` (a ``hueco_de``): más pegado, igual de
    pegado o a su lado."""
    return hueco <= hueco_de or _casi_igual(hueco, hueco_de, t.alto) or _a_su_lado(t, de)


def _en_su_columna(e: _Texto, t: _Texto, indice: _Indice, libres: set[str]) -> bool:
    """Si la etiqueta ``e`` alcanza ``t`` por su columna, de un lado o del otro: su primer renglón
    (el más pegado a lo más a 1.5 altos de ella, en su ensanche, primero el que tiene encima) y
    cada siguiente limpio (el más pegado a lo más a 1.5 altos del anterior, encimado con él en al
    menos la mitad del más angosto y en su ensanche), hasta un hueco o un texto que no es renglón
    (otra etiqueta, una nota…). Una columna que se abre en dos sigue por el más cerca de su
    centro: es la lectura más estrecha, la que menos le concede a ``e`` (R60)."""
    for sentido in e.sentidos:
        previo: _Texto | None = None
        visto = {e.id}
        while True:
            if previo is None:
                siguiente = _paso(
                    indice,
                    e.y1 if sentido > 0 else e.y0,
                    sentido,
                    _HUECO_DE_ETIQUETA * e.alto,
                    e.alto,
                    e.cx,
                    visto,
                    lambda x: _en_la_etiqueta(e, x),
                    lambda x: _se_enciman(x, e),
                )
            else:
                siguiente = _paso(
                    indice,
                    previo.y1 if sentido > 0 else previo.y0,
                    sentido,
                    _HUECO_ENTRE_RENGLONES * previo.alto,
                    previo.alto,
                    e.cx,
                    visto,
                    _sigue(e, previo, libres),
                )
            if siguiente is None or siguiente.id not in libres:
                break
            if siguiente.id == t.id:
                # Su primer renglón no: una etiqueta junto a la columna, a la altura de ``t``, no
                # sabe más de él que la que lee la pila (la familia p2near de R60).
                return previo is not None
            visto.add(siguiente.id)
            previo = siguiente
    return False


def _compite(
    t: _Texto,
    etiqueta: _Texto,
    siguiente: _Texto,
    etiquetas: list[_Texto],
    indice: _Indice,
    libres: set[str],
) -> bool:
    """Si ``t``, al lado de ``siguiente`` (lo que sigue limpio a la pila), puede ser el renglón de
    la pila y ``siguiente`` el de la columna de al lado: le queda al centro de la etiqueta igual o
    más cerca que él o, si más lejos, ninguna otra etiqueta más cerca de ``t`` lo tiene en su
    ensanche (R59) y lo alcanza por su columna (R60: una etiqueta lejana que sólo lo tiene de lado
    en su ensanche no sabe de quién es). Sólo así es de la columna de al lado: en los cuadros de
    Marina, el «2E#3EXT@10» de K-11 entra al ensanche de K-12 junto al de K-12, y K-11, más cerca,
    lo tiene en el suyo y lo alcanza (es el segundo renglón de su pila)."""
    if _lejania(etiqueta.cx, t) <= _lejania(etiqueta.cx, siguiente) + _EMPATE_ABSOLUTO * t.alto:
        return True
    return not any(
        e.id != etiqueta.id
        and e.marca != etiqueta.marca
        and _en_la_etiqueta(e, t)
        and _lejania(e.cx, t) < _lejania(etiqueta.cx, t)
        and _en_su_columna(e, t, indice, libres)
        for e in etiquetas
    )


def _junto_a_otra(
    etiqueta: _Texto, previo: _Texto, siguiente: _Texto, sentido: int, etiquetas: list[_Texto]
) -> bool:
    """Si otra etiqueta (de otra marca) está junto a ``previo``, a su altura, y tiene a
    ``siguiente`` en su ensanche y a su alcance: ``siguiente`` puede ser el primer renglón de su
    pila, que empieza junto a la columna (R59, semilla 61526)."""
    return any(
        e.id != etiqueta.id
        and e.marca != etiqueta.marca
        and _a_su_lado(e, previo)
        and _en_la_etiqueta(e, siguiente)
        and -_TRASLAPE * min(e.alto, siguiente.alto)
        <= _hueco(e, siguiente, sentido)
        <= _HUECO_DE_ETIQUETA * e.alto
        for e in etiquetas
    )


def _inundar(
    etiqueta: _Texto,
    semillas: list[_Texto],
    sentido: int,
    indice: _Indice,
    libres: set[str],
    fuera: set[str],
) -> list[_Texto]:
    """Lo que puede seguir una columna que ya no se sigue limpio (R57), desde ``semillas``: cada
    renglón a lo más a 1.5 altos de uno ya juntado y en la etiqueta ensanchada, y así, hasta un
    texto que no es renglón (otra etiqueta, una nota…) en medio. No es de la pila: sigue siendo un
    reclamo de ella, para que nadie se lleve sin oposición lo que puede ser suyo."""
    juntados = {*fuera, *(t.id for t in semillas)}
    salida = list(semillas)
    pendientes = list(semillas)
    while pendientes:
        previo = pendientes.pop()
        cerca = [
            (hueco, t)
            for hueco, t in _a_su_alcance(previo, sentido, indice)
            if t.id != etiqueta.id
            and (
                _en_la_etiqueta(etiqueta, t)
                if t.id in libres
                else _en_la_etiqueta(etiqueta, t, previo.alto)
                and _traslapa(t, previo.x0, previo.x1)
            )
        ]
        topes = [(h, t) for h, t in cerca if t.id not in libres]
        for hueco, t in cerca:
            if t.id not in libres or t.id in juntados:
                continue
            if not all(_no_mas_lejos(hueco, t, h, tope) for h, tope in topes):
                continue  # detrás de otra etiqueta, una nota…
            juntados.add(t.id)
            salida.append(t)
            pendientes.append(t)
    return salida


def _en_el_pasillo(
    a: _Texto,
    b: _Texto,
    etiquetas: list[_Texto],
    columna: _Texto | None = None,
) -> _Texto | None:
    """Una etiqueta (no ``columna``) metida entre dos renglones vecinos de una columna: al menos
    la mitad de su alto en el hueco entre ellos y, de lado, encimada con alguno de los dos
    en al menos la mitad del más angosto (y en la etiqueta ``columna`` ensanchada, si se da: la de
    la pila que se está leyendo)."""
    abajo, arriba = (a, b) if a.y0 <= b.y0 else (b, a)
    piso, techo = abajo.y1, arriba.y0
    if techo <= piso:
        return None
    for e in etiquetas:
        if columna is not None and e.id == columna.id:
            continue
        if min(e.y1, techo) - max(e.y0, piso) < _EN_EL_PASILLO * (e.y1 - e.y0):
            continue
        if not (_se_enciman(e, a) or _se_enciman(e, b)):
            continue
        if columna is not None and not _en_la_etiqueta(columna, e, min(a.alto, b.alto)):
            continue
        return e
    return None


def _de_frente(t: _Texto, sentido: int, etiquetas: list[_Texto], propia: _Texto) -> _Texto | None:
    """Otra etiqueta que tiene a ``t`` justo enfrente, del lado de donde viene la pila (debajo de
    él si la pila sube): encimada con él y a su alcance. ``t`` es el extremo de la pila de ésa."""
    for e in etiquetas:
        if e.id == propia.id or e.marca == propia.marca or not _se_enciman(t, e):
            continue
        hueco = _hueco(e, t, sentido)  # de la etiqueta a ``t``, hacia donde va la pila
        if -_TRASLAPE * min(e.alto, t.alto) <= hueco <= _HUECO_DE_ETIQUETA * e.alto:
            return e
    return None


def _alcance(
    etiqueta: _Texto,
    sentido: int,
    indice: _Indice,
    renglones: _Indice,
    libres: set[str],
    etiquetas: list[_Texto],
) -> _Alcance | None:
    """La columna que ``etiqueta`` alcanza hacia ``sentido``: su extremo más pegado y los
    renglones que le siguen en la misma columna, hasta un hueco o un texto que no es suyo."""

    def extremo(t: _Texto) -> bool:
        """Que entre ``t`` y la etiqueta no haya otro renglón de su columna: una etiqueta junto a
        la mitad de una pila ajena no la toma desde ahí (aunque le quede enfrente). Un renglón
        separado de ``t`` por una etiqueta metida entre los dos es de otra pila."""
        alcance = _HUECO_ENTRE_RENGLONES * t.alto
        return not any(
            g.id != t.id
            and _TRASLAPE * -min(t.alto, g.alto) <= _hueco(t, g, -sentido) <= alcance
            and _se_enciman(t, g)
            and _en_el_pasillo(t, g, etiquetas) is None
            for g in renglones.cerca(
                t.y0 if sentido > 0 else t.y1, -sentido, alcance, _TRASLAPE * t.alto
            )
        )

    def primero(t: _Texto) -> bool:
        return _en_la_etiqueta(etiqueta, t) and (t.id not in libres or extremo(t))

    def sobre_la_etiqueta(t: _Texto) -> bool:
        # El ensanche es holgura para los anchos estimados: lo que cae sobre la etiqueta misma
        # (encimado en al menos la mitad del más angosto) va primero: el renglón del vecino que
        # apenas entra al ensanche no le gana al suyo.
        return _se_enciman(t, etiqueta)

    borde = etiqueta.y1 if sentido > 0 else etiqueta.y0
    primeros: list[_Texto] = []  # todo lo admitido como primer renglón
    actual = _paso(
        indice,
        borde,
        sentido,
        _HUECO_DE_ETIQUETA * etiqueta.alto,
        etiqueta.alto,
        etiqueta.cx,
        {etiqueta.id},
        primero,
        sobre_la_etiqueta,
        empatados=primeros,
    )
    if actual is None:
        return None  # nada a su alcance
    tapada = actual.id not in libres
    if tapada:
        # Lo más pegado es otra cosa (otra etiqueta, una nota, una celda). Lo que está detrás de
        # ella no es de esta etiqueta; pero un renglón que podría ser el primero y que eso no
        # tiene enfrente (no se le encima de lado: está junto a él, no entre los dos) no queda
        # tapado (R57): la pila queda en duda y el renglón es un reclamo suyo, nunca el primero
        # limpio de otra etiqueta.
        primeros = []
        libre = _paso(
            renglones,
            borde,
            sentido,
            _HUECO_DE_ETIQUETA * etiqueta.alto,
            etiqueta.alto,
            etiqueta.cx,
            {etiqueta.id},
            primero,
            sobre_la_etiqueta,
            empatados=primeros,
        )
        if libre is None or _tapado(libre, etiqueta, borde, sentido, indice, libres, primero):
            return None
        actual = libre
    pila = _Alcance(
        etiqueta,
        sentido,
        max(_hueco(borde, actual, sentido), 0.0),
        [actual],
        frontal=sobre_la_etiqueta(actual),
        fusion=tapada,
    )
    # R57 en el primer renglón: entre la etiqueta y él, otro renglón que podría ir antes en la
    # columna sin seguirlo limpio (por eso ``actual`` pasó por extremo). La pila queda en duda y
    # ése sigue siendo un reclamo suyo.
    antes_del_primero = [
        g
        for _, g in _a_su_alcance(actual, -sentido, renglones)
        if g.id != actual.id
        and _hueco(borde, g, sentido) >= -_TRASLAPE * min(etiqueta.alto, g.alto)
        and _en_la_etiqueta(etiqueta, g)
        and _en_el_pasillo(actual, g, etiquetas) is None
    ]
    if antes_del_primero:
        pila.fusion = True
        pila.despues.extend(antes_del_primero)
    # R59: otro renglón admitido al lado del primero (a su altura) y ninguno de los dos sobre la
    # etiqueta: no se sabe cuál es el de la pila (la etiqueta toma el más cerca de su centro, y
    # el otro quedaba como el primero limpio de la vecina, semilla 71455). Duda, y los dos y lo
    # que puede seguirlos son reclamos suyos.
    al_lado = [
        t
        for t in primeros
        if t.id in libres
        and t.id != actual.id
        and not _es_copia(t, actual)
        and _a_su_lado(t, actual)
        and not sobre_la_etiqueta(t)
    ]
    if al_lado and not sobre_la_etiqueta(actual):
        pila.fusion = True
        ya = {etiqueta.id, actual.id, *(r.id for r in pila.despues)}
        pila.despues.extend(_inundar(etiqueta, al_lado, sentido, indice, libres, ya))
    # Tras un corte, la columna se sigue leyendo igual, pero en ``despues``.
    destino = pila.renglones
    while True:
        previo = actual
        fuera = {etiqueta.id, *(r.id for r in pila.renglones), *(r.id for r in pila.despues)}
        if pila.cortada is not None:
            fuera.add(pila.cortada.id)

        def buscar(
            donde: _Indice,
            previo: _Texto = previo,
            fuera: set[str] = fuera,
            empatados: list[_Texto] | None = None,
        ) -> _Texto | None:
            return _paso(
                donde,
                previo.y1 if sentido > 0 else previo.y0,
                sentido,
                _HUECO_ENTRE_RENGLONES * previo.alto,
                previo.alto,
                etiqueta.cx,
                fuera,
                _sigue(etiqueta, previo, libres),
                empatados=empatados,
            )

        def inundar(semillas: list[_Texto], fuera: set[str] = fuera) -> None:
            pila.despues.extend(_inundar(etiqueta, semillas, sentido, indice, libres, fuera))

        empatados: list[_Texto] = []
        siguiente = buscar(indice, empatados=empatados)
        dudas = _dudas(etiqueta, previo, sentido, renglones, libres, fuera)
        hueco_siguiente = 0.0 if siguiente is None else max(_hueco(previo, siguiente, sentido), 0.0)
        antes = [
            t
            for h, t in dudas
            if siguiente is None
            or (
                _no_mas_lejos(h, t, hueco_siguiente, siguiente)
                and (
                    not _a_su_lado(t, siguiente)
                    or _compite(t, etiqueta, siguiente, etiquetas, indice, libres)
                )
            )
        ]
        if (
            not antes
            and siguiente is not None
            and siguiente.id in libres
            and _junto_a_otra(etiqueta, previo, siguiente, sentido, etiquetas)
        ):
            # R59: otra etiqueta junto a ``previo`` tiene ``siguiente`` a su alcance: la columna
            # puede acabar aquí y seguir como la pila de ella. No se sabe: duda, como R57.
            antes = [siguiente]
        if antes:
            # R57: un renglón que podría seguir la pila y no la sigue limpio (cae en la etiqueta
            # ensanchada, pero de lado se encima poco o nada con el anterior). No se sabe si la
            # pila acaba aquí: queda en duda, y ese renglón y lo que puede seguirlo siguen siendo
            # reclamos suyos; nunca un final limpio que deje el resto como el primer renglón de
            # otra etiqueta. Aunque otra etiqueta tenga ese renglón enfrente: tomarlo como un
            # corte limpio deja pilas a medias (una etiqueta junto a una pila escalonada).
            if destino is pila.renglones:
                pila.fusion = True
            limpio = [t for t in [siguiente] if t is not None and t.id in libres and t not in antes]
            inundar([*antes, *limpio])
            break
        if siguiente is None:
            break
        lado_a_lado = [
            t
            for t in empatados
            if t.id in libres
            and t.id != siguiente.id
            and not _es_copia(t, siguiente)
            and min(t.y1, siguiente.y1) > max(t.y0, siguiente.y0)
        ]
        if siguiente.id in libres and lado_a_lado:
            # Dos renglones que siguen al anterior, uno al lado del otro: la columna se abre en
            # dos y no se sabe por cuál sigue. La pila queda en duda y los dos siguen siendo
            # reclamos suyos.
            if destino is pila.renglones:
                pila.fusion = True
                pila.despues.extend([siguiente, *lado_a_lado])
            break
        if siguiente.id not in libres:
            if destino is pila.despues:
                break
            if siguiente.clase == "ajena":
                pila.tope = siguiente
            elif siguiente.clase == "etiqueta":
                pila.mas_alla = buscar(renglones)  # la columna sigue más allá de ella
                if pila.mas_alla is not None:
                    pila.cortada = siguiente
                    destino = pila.despues
                    destino.append(pila.mas_alla)
                    actual = pila.mas_alla
                    continue
            break
        pasillo = _en_el_pasillo(previo, siguiente, etiquetas, etiqueta) or _de_frente(
            siguiente, sentido, etiquetas, etiqueta
        )
        if pasillo is not None:
            if destino is pila.despues:
                break
            pila.cortada, pila.mas_alla = pasillo, siguiente
            pila.corte_limpio = _en_la_etiqueta(etiqueta, pasillo, min(previo.alto, siguiente.alto))
            destino = pila.despues
            destino.append(siguiente)
            actual = siguiente
            continue
        otro = _otro_previo(siguiente, previo, sentido, renglones, pila.renglones + pila.despues)
        if otro is not None:
            # ``siguiente`` también sigue a otro renglón de al lado (R56): si está más pegado a
            # ése, o igual, la columna se junta con otra. No se sabe dónde acaba la pila, así que
            # queda en duda, y lo que sigue (ese renglón y los suyos) sigue siendo un reclamo de
            # ella, como más allá de un corte: la otra columna no se lo lleva sin oposición.
            del_otro = max(_hueco(otro, siguiente, sentido), 0.0)
            del_previo = max(_hueco(previo, siguiente, sentido), 0.0)
            empate = _casi_igual(del_otro, del_previo, siguiente.alto)
            if empate or del_otro < del_previo:
                if destino is pila.despues:
                    break
                pila.fusion = True
                destino = pila.despues
                destino.append(siguiente)
                actual = siguiente
                continue
        destino.append(siguiente)
        actual = siguiente
    return pila


def _tapado(
    t: _Texto,
    etiqueta: _Texto,
    borde: float,
    sentido: int,
    indice: _Indice,
    libres: set[str],
    admite: Callable[[_Texto], bool],
) -> bool:
    """Si entre ``etiqueta`` y el renglón ``t`` hay otra cosa (otra etiqueta, una nota…) que le
    queda enfrente: a lo más igual de pegada a la etiqueta que él y encimada de lado con él."""
    hueco_t = max(_hueco(borde, t, sentido), 0.0)
    alcance = _HUECO_DE_ETIQUETA * etiqueta.alto
    for b in indice.cerca(borde, sentido, alcance, _TRASLAPE * etiqueta.alto):
        if b.id in libres or b.id == etiqueta.id or not admite(b):
            continue
        hueco_b = _hueco(borde, b, sentido)
        if hueco_b < -_TRASLAPE * min(etiqueta.alto, b.alto):
            continue
        if _no_mas_lejos(max(hueco_b, 0.0), b, hueco_t, t) and _traslapa(b, t.x0, t.x1):
            return True
    return False


def _es_copia(a: _Texto, b: _Texto) -> bool:
    """El mismo texto dibujado dos veces encima de sí mismo."""
    return a.texto == b.texto and math.hypot(a.x0 - b.x0, a.y0 - b.y0) <= _DUPLICADO * a.alto


def _otro_previo(
    t: _Texto, previo: _Texto, sentido: int, renglones: _Indice, propios: list[_Texto]
) -> _Texto | None:
    """Otro renglón (no de la pila) que ``t`` también podría seguir en una columna: del lado de
    donde viene la pila, a lo más a 1.5 altos de ``t`` y encimado con él en al menos la mitad del
    más angosto. El más pegado de ellos."""
    ya = {r.id for r in propios} | {previo.id}
    borde = t.y0 if sentido > 0 else t.y1
    mejores = [
        (_hueco(q, t, sentido), q)
        for q in renglones.cerca(borde, -sentido, _HUECO_ENTRE_RENGLONES * t.alto, 0.0)
        if q.id not in ya
        and q.id != t.id
        and -_TRASLAPE * min(q.alto, t.alto)
        <= _hueco(q, t, sentido)
        <= _HUECO_ENTRE_RENGLONES * q.alto
        and _se_enciman(q, t)
    ]
    return min(mejores, key=lambda hq: (hq[0], hq[1].id))[1] if mejores else None


@dataclass
class _Reparto:
    """Lo que queda de las pilas de un grupo de textos: las tomadas (con sus renglones) y los
    renglones ambiguos con las marcas que los pueden reclamar."""

    tomadas: list[tuple[_Alcance, list[_Texto]]]
    ambiguos: dict[str, set[str]]


def _repartir(
    etiquetas: list[_Texto],
    alcances: dict[str, list[_Alcance]],
    casi: dict[str, float],
    casi_de: dict[str, set[str]],
) -> _Reparto:
    """Quién se queda cada renglón; ante la duda, nadie.

    Todo lo que una etiqueta alcanza, de los dos lados, es un reclamo. En cada renglón, la marca
    más pegada lo gana; lo empatan (y nadie lo gana) dos marcas con huecos parecidos (10 % del
    mismo lado, 25 % de lados opuestos), o cuando la más pegada va contra la costumbre del cuadro,
    sólo lo alcanza con el ensanche frente a una que lo tiene enfrente, tiene del otro lado una
    pila apenas fuera de su alcance, o está en la punta opuesta de una columna que para la otra es
    la única que tiene enfrente; también una etiqueta y la que se le mete en la columna.

    Un lado de una etiqueta está vivo si no pierde su primer renglón ante una marca que se lo
    queda (si la que se lo ganó al final no lo toma, vuelve a estar en disputa). Con un lado vivo,
    la etiqueta toma la pila entera sólo si gana todos sus renglones; con dos, la que tiene
    enfrente o, si las dos, la más pegada (si empatan, la de arriba), y si otra marca también la
    alcanza o la tiene enfrente apenas fuera de su alcance, o va contra la costumbre, la etiqueta
    es ambigua. Una pila cortada por otra etiqueta que no se queda con lo de más allá, que se abre
    en dos, se junta con otra o no se sigue limpio (R57), o que otra etiqueta tiene enfrente apenas
    fuera de su alcance, también. Lo de más allá de un corte o de donde la columna se junta con otra
    o deja de seguirse limpio sigue siendo un reclamo de la dueña de la columna, que empata con
    cualquiera menos con la que la corta metida
    en la columna; una pila que deja sin pila a otra etiqueta que alcanzaba alguno de sus renglones
    no se toma, ni las de etiquetas que se alcanzan la pila una a otra en rueda. Lo ambiguo se
    rechaza entero: nunca una pila a medias ni la de otra marca."""
    reclamos: dict[str, list[_Alcance]] = defaultdict(list)
    for lista in alcances.values():
        for a in lista:
            for r in a.renglones:
                reclamos[r.id].append(a)

    # Lo que sigue de una columna más allá de la etiqueta que la corta sigue siendo un reclamo de
    # la dueña de la columna: la que la corta puede quedárselo (una lista de etiquetas, cada una
    # con su pila); cualquier otra marca que lo alcance empata con ella.
    sombras: dict[str, list[_Alcance]] = defaultdict(list)
    for lista in alcances.values():
        for a in lista:
            for r in a.despues:
                sombras[r.id].append(a)

    def sombra(a: _Alcance, r: _Texto) -> set[str]:
        return {
            s.marca
            for s in sombras.get(r.id, ())
            if s.marca != a.marca
            and (s.cortada is None or not s.corte_limpio or s.cortada.marca != a.marca)
        }

    def ajenos(a: _Alcance) -> set[str]:
        return {b.marca for r in a.renglones for b in reclamos[r.id] if b.marca != a.marca} | {
            m for r in a.renglones for m in sombra(a, r)
        }

    # La costumbre del cuadro: de qué lado de su pila van las etiquetas cuya pila nadie disputa
    # (al menos dos y 80 % del mismo lado). Una etiqueta que va contra ella no le gana una pila
    # disputada a una que la sigue, por más pegada que esté: eso queda ambiguo.
    lados: Counter[int] = Counter()
    for lista in alcances.values():
        sin_disputa = [a for a in lista if not ajenos(a)]
        if len(sin_disputa) == 1:
            lados[sin_disputa[0].sentido] += 1
    costumbre = next(
        (
            lado
            for lado, n in lados.items()
            if n >= _COSTUMBRE_MINIMA and n >= _COSTUMBRE_PARTE * sum(lados.values())
        ),
        None,
    )

    # Una etiqueta metida en la columna de otra: lo que las dos alcanzan de esa columna no es de
    # ninguna, por más pegada que esté la de en medio.
    cortes = {
        frozenset((a.etiqueta.id, a.cortada.id))
        for lista in alcances.values()
        for a in lista
        if a.cortada is not None
    }

    def _sin_rival_mas_pegado(x: _Alcance) -> bool:
        """Que ninguna otra marca alcance el primer renglón de ``x`` claramente más pegada."""
        primero = x.renglones[0]
        return not any(
            b.marca != x.marca
            and b.hueco < x.hueco
            and not _casi_igual(
                b.hueco,
                x.hueco,
                primero.alto,
                _EMPATE if b.sentido == x.sentido else _EMPATE_OPUESTO,
            )
            for b in reclamos[primero.id]
        )

    def estado(a: _Alcance, r: _Texto) -> str:
        resultado = "empata" if sombra(a, r) else "gana"
        for b in reclamos[r.id]:
            if b.marca == a.marca:
                continue
            tolerancia = _EMPATE if b.sentido == a.sentido else _EMPATE_OPUESTO
            if _casi_igual(a.hueco, b.hueco, r.alto, tolerancia) or (
                frozenset((a.etiqueta.id, b.etiqueta.id)) in cortes
            ):
                resultado = "empata"
                continue
            cerca, lejos = (b, a) if b.hueco < a.hueco else (a, b)
            if costumbre is not None and cerca.sentido != costumbre == lejos.sentido:
                resultado = "empata"  # la más pegada va contra la costumbre del cuadro
            elif lejos.frontal and not cerca.frontal:
                resultado = "empata"  # la más pegada sólo la alcanza con el ensanche
            elif cerca.etiqueta.id in casi and lejos.etiqueta.id not in casi:
                # La más pegada tiene enfrente, del otro lado y apenas fuera de su alcance, otra
                # pila que puede ser la suya.
                resultado = "empata"
            elif cerca.sentido != lejos.sentido and not any(
                x is not lejos and x.frontal and _sin_rival_mas_pegado(x)
                for x in alcances[lejos.etiqueta.id]
            ):
                # Una columna entre dos etiquetas, una en cada punta, y para la más lejana es la
                # única pila que tiene enfrente: pueden ser dos pilas juntas, o la de cualquiera
                # de las dos. No se adivina por cuál está más pegada.
                resultado = "empata"
            elif cerca is b:
                return "pierde"
        return resultado

    def resolver(
        revividos: set[tuple[str, int]], anuladas: dict[str, set[str]]
    ) -> tuple[list[tuple[_Alcance, list[_Texto]]], dict[str, _Alcance], dict[str, set[str]]]:
        tomadas: list[tuple[_Alcance, list[_Texto]]] = []
        dudosas: dict[str, set[str]] = dict(anuladas)  # etiqueta → las marcas en disputa
        for etiqueta in etiquetas:
            if etiqueta.id in anuladas:
                continue
            vivos = [
                a
                for a in alcances[etiqueta.id]
                if (etiqueta.id, a.sentido) in revividos or estado(a, a.renglones[0]) != "pierde"
            ]
            if not vivos:
                continue
            elegido = vivos[0]
            if (
                len(alcances[etiqueta.id]) == 1
                and etiqueta.id in casi
                and (not elegido.frontal or casi[etiqueta.id] <= _CASI * elegido.hueco)
            ):
                # Del otro lado tiene enfrente una pila apenas fuera de su alcance, casi tan
                # cerca como la que alcanza (o la que alcanza sólo le queda de lado): su pila
                # puede ser aquélla.
                dudosas[etiqueta.id] = {elegido.marca} | ajenos(elegido)
                continue
            frente = {
                m for r in elegido.renglones for m in casi_de.get(r.id, ()) if m != elegido.marca
            }
            if len(vivos) == 1 and frente:
                # Otra etiqueta tiene esta pila enfrente, apenas fuera de su alcance: puede ser
                # la suya.
                dudosas[etiqueta.id] = {elegido.marca} | frente | ajenos(elegido)
                continue
            if len(vivos) == 2:
                arriba, abajo = sorted(vivos, key=lambda a: -a.sentido)
                alto = min(arriba.renglones[0].alto, abajo.renglones[0].alto)
                if arriba.frontal != abajo.frontal:
                    # La que está enfrente de la etiqueta, no la que sólo alcanza de lado.
                    elegido = arriba if arriba.frontal else abajo
                else:
                    elegido = (
                        arriba
                        if arriba.hueco <= abajo.hueco
                        or _casi_igual(arriba.hueco, abajo.hueco, alto)
                        else abajo
                    )
                # La disputan otras marcas que la alcanzan, o que la tienen enfrente apenas
                # fuera de su alcance (puede ser su pila).
                disputa = ajenos(elegido) | {
                    m
                    for r in elegido.renglones
                    for m in casi_de.get(r.id, ())
                    if m != elegido.marca
                }
                if disputa:
                    dudosas[etiqueta.id] = (
                        disputa | {elegido.marca} | ajenos(arriba) | ajenos(abajo)
                    )
                    continue
                if costumbre is not None and elegido.sentido != costumbre:
                    # Entre sus dos lados, la más pegada va contra la costumbre del cuadro.
                    dudosas[etiqueta.id] = {elegido.marca} | ajenos(arriba) | ajenos(abajo)
                    continue
            if elegido.fusion:
                # Su columna se junta con otra o se abre en dos: la disputan también las marcas
                # que alcanzan lo que sigue.
                dudosas[etiqueta.id] = (
                    {elegido.marca}
                    | ajenos(elegido)
                    | {b.marca for r in elegido.despues for b in reclamos[r.id]}
                )
                continue
            cortada, mas_alla = elegido.cortada, elegido.mas_alla
            if (
                cortada is not None
                and mas_alla is not None
                and (
                    not elegido.corte_limpio
                    or not any(mas_alla in a.renglones for a in alcances.get(cortada.id, []))
                )
            ):
                # Otra etiqueta metida en la columna que no se queda con lo de más allá, o una que
                # sólo la tiene enfrente de lado: no se sabe dónde acaba esta pila.
                dudosas[etiqueta.id] = {elegido.marca, cortada.marca or ""}
                continue
            if all(estado(elegido, r) == "gana" for r in elegido.renglones):
                tomadas.append((elegido, list(elegido.renglones)))
            else:
                # Nunca a medias: si otra marca le gana o le empata algún renglón de su pila, la
                # pila entera queda en duda.
                dudosas[etiqueta.id] = {elegido.marca} | ajenos(elegido)

        # La misma marca dibujada dos veces encima de sí misma: el renglón es de una sola.
        dueno: dict[str, _Alcance] = {}
        finales: list[tuple[_Alcance, list[_Texto]]] = []
        for a, prefijo in sorted(tomadas, key=lambda ap: (ap[0].hueco, ap[0].etiqueta.id)):
            propios: list[_Texto] = []
            for r in prefijo:
                if r.id in dueno:
                    break
                propios.append(r)
            for r in propios:
                dueno[r.id] = a
            if propios:
                finales.append((a, propios))
        return finales, dueno, dudosas

    # Un lado que perdió su primer renglón contra una marca que al final no se lo quedó (porque
    # quedó ambigua o tomó su otro lado) no está muerto: sigue en disputa, y la etiqueta vuelve a
    # tener dos lados. Y una pila que deja sin pila a otra etiqueta que alcanzaba alguno de sus
    # renglones no se toma (R55): la geometría sola no distingue a la dueña de la que se quedó
    # sin nada. Tampoco dos o más que se toman cada una una pila que otra alcanza en rueda (R56:
    # cambiarlas de dueña es igual de coherente, y sólo las separa qué tan pegadas quedan). Se
    # repite hasta que nada cambia (cada vuelta sólo agrega dudas).
    marca_de = {e.id: e.marca or "" for e in etiquetas}
    revividos: set[tuple[str, int]] = set()
    anuladas: dict[str, set[str]] = {}
    while True:
        finales, dueno, dudosas = resolver(revividos, anuladas)
        nuevos = {
            (etiqueta.id, a.sentido)
            for etiqueta in etiquetas
            for a in alcances[etiqueta.id]
            if (etiqueta.id, a.sentido) not in revividos
            and estado(a, a.renglones[0]) == "pierde"
            and a.renglones[0].id not in dueno
        }
        con_pila = {a.etiqueta.id for a, _ in finales}
        nuevas: dict[str, set[str]] = defaultdict(set)
        alcanza: dict[str, set[str]] = defaultdict(set)  # con pila → las de las pilas que alcanza
        for etiqueta in etiquetas:
            for a in alcances[etiqueta.id]:
                for r in a.renglones:
                    ganadora = dueno.get(r.id)
                    if ganadora is None or ganadora.marca == a.marca:
                        continue
                    if etiqueta.id in con_pila:
                        alcanza[etiqueta.id].add(ganadora.etiqueta.id)
                    else:
                        nuevas[ganadora.etiqueta.id] |= {ganadora.marca, a.marca}
        for etiqueta_id, rueda in _en_rueda(alcanza).items():
            nuevas[etiqueta_id] |= {marca_de[i] for i in rueda}
        nuevas = {i: m for i, m in nuevas.items() if not m <= anuladas.get(i, set())}
        if not nuevos and not nuevas:
            break
        revividos |= nuevos
        for i, m in nuevas.items():
            anuladas.setdefault(i, set()).update(m)

    # Un renglón que nadie se queda es ambiguo si lo pueden reclamar dos marcas: las que lo
    # alcanzan (con las que les disputan su pila) y, más allá de un corte, la dueña de la columna
    # y la etiqueta que la corta.
    ambiguos: dict[str, set[str]] = {}
    for renglon_id in [*reclamos, *(r for r in sombras if r not in reclamos)]:
        if renglon_id in dueno:
            continue
        marcas: set[str] = set()
        for a in reclamos.get(renglon_id, []):
            marcas |= {a.marca} | dudosas.get(a.etiqueta.id, set())
        for a in sombras.get(renglon_id, []):
            marcas |= {a.marca, (a.cortada.marca if a.cortada is not None else None) or a.marca}
        if len(marcas) > 1:
            ambiguos[renglon_id] = marcas
    return _Reparto(finales, ambiguos)


def _en_rueda(alcanza: dict[str, set[str]]) -> dict[str, set[str]]:
    """Las etiquetas que están en una rueda de ``alcanza`` (una alcanza la pila de otra, ésa la
    de otra… y la última la de la primera), cada una con todas las de sus ruedas."""
    cerradura: dict[str, set[str]] = {}
    for inicio in alcanza:
        vistas: set[str] = set()
        pendientes = list(alcanza[inicio])
        while pendientes:
            i = pendientes.pop()
            if i not in vistas:
                vistas.add(i)
                pendientes.extend(alcanza.get(i, ()))
        cerradura[inicio] = vistas
    ruedas: dict[str, set[str]] = {}
    for x, desde_x in cerradura.items():
        juntas = {y for y in desde_x if y != x and x in cerradura.get(y, set())}
        if juntas:
            ruedas[x] = juntas | {x}
    return ruedas


def _pilas(textos: list[_Texto], de_filas: set[str], titulos: set[str] | None = None) -> _Reparto:
    """Las pilas de un grupo de textos con la misma dirección, ya repartidas. Con ``titulos``
    (R189, las pilas bajo secciones: los ids de los títulos de las secciones), lo que cada
    etiqueta o sección casi alcanza es su columna entera, no sólo su primer renglón: ver abajo."""
    etiquetas = [t for t in textos if t.clase == "etiqueta" and t.id not in de_filas]
    libres = {t.id for t in textos if t.clase == "linea" and t.id not in de_filas}
    lineas = [t for t in textos if t.id in libres]
    estorban = [t for t in textos if t.clase not in ("nada", "linea") or t.id in de_filas]
    indice, renglones = _Indice(lineas + estorban), _Indice(lineas)
    alcances = {
        e.id: [
            a
            for a in (_alcance(e, s, indice, renglones, libres, etiquetas) for s in e.sentidos)
            if a is not None
        ]
        for e in etiquetas
    }
    casi: dict[str, float] = {}  # etiqueta de un lado → hueco a la pila de enfrente del otro
    casi_de: dict[str, set[str]] = defaultdict(set)  # renglón → marcas que lo tienen enfrente
    for e in etiquetas:
        if titulos is not None and (
            e.id in titulos
            or (isinstance(e, _Seccion) and e.seccion is not None and e.seccion.de_cuadro)
        ):
            # R189: el título de una sección no tiene otra pila que casi alcance: la suya es la
            # de su sección; ni la sección de una etiqueta de cuadro, cuya pila ya leyó su
            # etiqueta (R195).
            continue
        lados = {a.sentido for a in alcances[e.id]}
        for sentido in set(e.sentidos) - lados:
            cerca = _casi_alcanza(e, sentido, renglones)
            if cerca is None:
                continue
            casi_de[cerca[1].id].add(e.marca or "")
            if len(lados) == 1:
                casi[e.id] = cerca[0]
    if titulos is not None:
        # R189: un renglón es de una sección sólo si nadie más puede tenerlo. El principio de
        # «casi» (R56: lo que otra etiqueta tiene enfrente apenas fuera de su alcance puede ser
        # suyo) vale para su columna entera: cada etiqueta y cada sección, hacia cada uno de sus
        # lados, con el doble de su alcance, tiene enfrente toda la columna que tomaría —sus
        # renglones y los que siguen más allá de donde se corta—. Una pila con uno de ellos
        # queda en duda (``frente``); con el alcance de una sección (su lado menor, hasta 22
        # altos de letra) la columna de una vecina llega a menudo bajo otra. El título de una
        # sección no: su armado va bajo su sección, del otro lado; el título de un detalle va a
        # menudo justo bajo la pila del detalle de arriba (CE-4 bajo CE-2 en ES-300). Del lado
        # de su título, una sección compite aparte (``_lo_que_alcanza_cada_seccion``).
        # La sección de una etiqueta de cuadro tampoco (R195): su pila ya la leyó su etiqueta;
        # nada más allá de su alcance puede ser la suya.
        for e in etiquetas:
            if e.id in titulos or (
                isinstance(e, _Seccion) and e.seccion is not None and e.seccion.de_cuadro
            ):
                continue
            for sentido in e.sentidos:
                lejos = _alcance(
                    replace(e, alto=_CASI * e.alto), sentido, indice, renglones, libres, etiquetas
                )
                for t in [*lejos.renglones, *lejos.despues] if lejos is not None else []:
                    casi_de[t.id].add(e.marca or "")
    return _repartir(etiquetas, alcances, casi, casi_de)


def _casi_alcanza(
    etiqueta: _Texto, sentido: int, renglones: _Indice
) -> tuple[float, _Texto] | None:
    """El renglón de enfrente de ``etiqueta`` hacia ``sentido`` que queda apenas fuera de su
    alcance (hasta el doble), con su hueco; o ``None``."""
    alcance = _HUECO_DE_ETIQUETA * etiqueta.alto
    borde = etiqueta.y1 if sentido > 0 else etiqueta.y0
    cercanos = [
        (_hueco(borde, t, sentido), t)
        for t in renglones.cerca(borde, sentido, _CASI * alcance, 0.0)
        if _se_enciman(t, etiqueta)
    ]
    cercanos = [(h, t) for h, t in cercanos if alcance < h <= _CASI * alcance]
    return min(cercanos, key=lambda ht: (ht[0], ht[1].id)) if cercanos else None


# --------------------------------------------------------------------------------- asociar


def asociar(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    config: TextPatternConfig,
    posibles: dict[str, set[str]] | None = None,
) -> tuple[list[Asociacion], list[Rechazo]]:
    """De qué marca es cada texto de armado, hoja por hoja; y lo que no se pudo pegar.

    Las ``Asociacion`` van por pila (la etiqueta pegada a su columna de renglones) o por fila
    (un renglón de un cuadro con títulos); su ``etiqueta_id`` es una etiqueta de definición, no
    una colocación. Los ``Rechazo`` son los renglones ambiguos, las etiquetas que se quedaron sin
    la pila que alcanzaban, los de otra familia que paraban una pila y todo texto con forma de
    armado que no lee nadie. Ver el docstring del módulo. En ``posibles`` deja, por texto, las
    etiquetas en cuya columna queda más allá de donde su pila se cortó (R111)."""
    textos = [e for e in entities if e.is_textual and e.text and e.text.strip()]
    hoja_de = _hoja_de(frames)
    hojas: dict[tuple, str] = {}
    hoja_por_id: dict[str, str] = {}
    grupos: dict[tuple, list[NormalizedEntity]] = defaultdict(list)
    for e in textos:
        llave, hoja = hoja_de(e)
        hojas[llave] = hoja
        hoja_por_id[e.entity_id] = hoja
        grupos[llave].append(e)
    _, _, de_notas = leer_notas_con_renglones(textos, lambda e: hoja_por_id[e.entity_id])
    lineas = _lineas(entities, textos)

    asociaciones: list[Asociacion] = []
    rechazos: list[Rechazo] = []
    posibles = posibles if posibles is not None else {}
    for llave, grupo in grupos.items():
        a, r = _asociar_hoja(grupo, hojas[llave], config, de_notas, lineas, posibles)
        asociaciones += a
        rechazos += r
    asociaciones.sort(key=lambda a: (a.hoja, a.marca, a.etiqueta_id))
    rechazos.sort(key=lambda r: (r.hoja, r.motivo, r.texto, r.entidad_id))
    return asociaciones, rechazos


def _asociacion(
    etiqueta: _Texto,
    marca: str,
    hoja: str,
    textos: list[_Texto],
    via: Literal["pila", "fila"],
    cuadro: str | None = None,
) -> Asociacion:
    renglones = [(t.id, r) for t in textos for r in t.renglones]
    return Asociacion(
        etiqueta_id=etiqueta.id,
        marca=marca,
        hoja=hoja,
        textos=[r for _, r in renglones],
        entidades=[i for i, _ in renglones],
        via=via,
        cuadro=cuadro,
    )


def _asociar_hoja(
    grupo: list[NormalizedEntity],
    hoja: str,
    config: TextPatternConfig,
    de_notas: set[str],
    lineas: _Lineas,
    posibles: dict[str, set[str]],
) -> tuple[list[Asociacion], list[Rechazo]]:
    clases = {e.entity_id: _clase(e, config, de_notas) for e in grupo}
    giros = _giros(grupo)
    por_giro: dict[int, list[_Texto]] = defaultdict(list)
    for e in grupo:
        giro = giros[e.entity_id]
        clase, marca = clases[e.entity_id]
        t = _texto_local(e, giro, clase, marca)
        if clase == "linea" and lineas.es_llamada(t, giro):
            t.clase = "llamada"
            clases[e.entity_id] = ("llamada", None)
        por_giro[giro].append(t)

    asociaciones: list[Asociacion] = []
    rechazos: list[Rechazo] = []
    duenos: list[NormalizedEntity] = []
    rechazados: set[str] = set()
    columnas: list[tuple[list[_Texto], _Texto, list[_Texto], int | None, set[str]]] = []
    for giro in sorted(por_giro):
        locales = por_giro[giro]
        por_id = {t.id: t for t in locales}
        de_filas: set[str] = set()
        for etiqueta, marca, celdas, cuadro in _filas_de_cuadros(locales, config):
            de_filas.add(etiqueta.id)
            de_filas.update(c.id for c in celdas)
            duenos += [c.e for c in celdas]
            # Una fila con armado, o sólo con su sección («K-2 | 20X30»): también define la marca.
            if any(ARMADO_RE.search(c.texto) or _SECCION.search(c.texto) for c in celdas):
                asociaciones.append(_asociacion(etiqueta, marca, hoja, celdas, "fila", cuadro))
        reparto = _pilas(locales, de_filas)
        pila_de = {a.etiqueta.id: (a.sentido, propios) for a, propios in reparto.tomadas}
        for t in locales:
            if (
                t.clase == "etiqueta"
                and t.id not in de_filas
                and not _es_de_varias(t.marca or "", config)
            ):
                sentido, propios = pila_de.get(t.id, (None, []))
                columnas.append((locales, t, propios, sentido, de_filas))
        for renglon_id, marcas in reparto.ambiguos.items():
            rechazados.add(renglon_id)
            rechazos.append(
                Rechazo(
                    entidad_id=renglon_id,
                    texto=por_id[renglon_id].texto,
                    hoja=hoja,
                    motivo="ambigua",
                    marcas=sorted({m for marca in marcas for m in _marcas_de(marca)}),
                )
            )
        topes: dict[str, set[str]] = defaultdict(set)
        for alcance, propios in reparto.tomadas:
            if _es_de_varias(alcance.marca, config):
                # La pila de una etiqueta de varias marcas: nadie más se la lleva, y se dice.
                for r in propios:
                    rechazados.add(r.id)
                    rechazos.append(
                        Rechazo(
                            entidad_id=r.id,
                            texto=r.texto,
                            hoja=hoja,
                            motivo="varias_marcas",
                            marcas=_marcas_de(alcance.marca),
                        )
                    )
                continue
            duenos += [r.e for r in propios]
            orden = propios[::-1] if alcance.sentido > 0 else propios
            asociaciones.append(_asociacion(alcance.etiqueta, alcance.marca, hoja, orden, "pila"))
            if alcance.tope is not None and len(propios) == len(alcance.renglones):
                topes[alcance.tope.id].add(alcance.marca)
        for tope_id, marcas_del_tope in topes.items():
            rechazos.append(
                Rechazo(
                    entidad_id=tope_id,
                    texto=por_id[tope_id].texto,
                    hoja=hoja,
                    motivo="otra_familia",
                    marcas=sorted(marcas_del_tope),
                )
            )

    de_alguien = {e.entity_id for e in duenos}
    for locales, etiqueta, propios, sentido, filas in columnas:
        for t in _mas_alla_del_corte(locales, etiqueta, propios, sentido, de_alguien | filas):
            posibles.setdefault(t.id, set()).add(etiqueta.marca or "")
    sin_dueno = _sin_dueno(grupo, hoja, clases, duenos, rechazados, config)
    # R116: todo rechazo (sea cual sea su motivo) más allá del corte lleva la etiqueta.
    for rechazo in [*rechazos, *sin_dueno]:
        rechazo.posibles = sorted(posibles.get(rechazo.entidad_id, set()))
    return asociaciones, rechazos + sin_dueno


def _mas_alla_del_corte(
    textos: list[_Texto],
    etiqueta: _Texto,
    pila: list[_Texto],
    sentido: int | None,
    de_alguien: set[str],
) -> list[_Texto]:
    """R111: los textos con armado o una sección que siguen en la columna de ``etiqueta`` más allá
    de donde su pila se cortó (de renglón en renglón, a lo más 1.5 altos, encimados de lado con la
    columna), sin dueño: pueden ser suyos. Sin pila se mira de los dos lados. Para en otra
    etiqueta, en un texto con dueño, en uno de otra familia o en una nota, y en uno sin armado."""
    x0 = min([etiqueta.x0, *(r.x0 for r in pila)])
    x1 = max([etiqueta.x1, *(r.x1 for r in pila)])
    indice = _Indice(textos)
    fuera = {etiqueta.id, *(r.id for r in pila)}
    salida: list[_Texto] = []
    inicios = (
        [(sentido, max(pila, key=lambda r: sentido * r.cy))]
        if pila and sentido
        else [
            (+1, etiqueta),
            (-1, etiqueta),
        ]
    )
    for lado, desde in inicios:
        actual = desde
        while True:
            cerca = [
                t
                for _h, t in _a_su_alcance(actual, lado, indice)
                if t.id not in fuera and _traslapa(t, x0, x1)
            ]
            if not cerca:
                break
            t = cerca[0]
            con_armado = (
                ARMADO_RE.search(t.texto) is not None
                or _SECCION.search(t.texto) is not None
                or tiene_armado(t.texto)
            )
            if (
                t.clase in ("etiqueta", "ajena", "familia", "nota")
                or t.id in de_alguien
                or not con_armado
            ):
                break
            salida.append(t)
            fuera.add(t.id)
            actual = t
    return salida


def _nota_que_nombra(e: NormalizedEntity, hoja: str, config: TextPatternConfig) -> list[Rechazo]:
    """Una nota numerada o un texto de otra familia que nombra una marca y trae armado o una
    sección que la nota no lee («3.- K-7 E#3@1S», «TRABE-T 1 E#3@1S», R77): nadie lo lee, pero
    dice de quién es. Un rechazo «sin_lector» por renglón con su marca; ninguno si la nota lo lee
    («3.- K-7 15X20»)."""
    texto = " ".join((e.text or "").split())
    if lo_lee_una_nota(texto):
        return []
    rechazos: list[Rechazo] = []
    for renglon in (e.text or "").split("\n"):
        renglon = renglon.strip()
        if (
            ARMADO_RE.search(renglon) is None
            and _SECCION.search(renglon) is None
            and not tiene_armado(renglon)
        ):
            continue
        marcas = marcas_en_nota(renglon, config) or titulos(renglon, config)
        if marcas:
            rechazos.append(
                Rechazo(
                    entidad_id=e.entity_id,
                    texto=renglon,
                    hoja=hoja,
                    motivo="sin_lector",
                    marcas=marcas,
                )
            )
    return rechazos


def _sin_dueno(
    grupo: list[NormalizedEntity],
    hoja: str,
    clases: dict[str, tuple[_Clase, str | None]],
    duenos: list[NormalizedEntity],
    rechazados: set[str],
    config: TextPatternConfig,
) -> list[Rechazo]:
    """Los textos de armado que nadie lee: los renglones sin pila ni fila (sin dueño) y los que
    nombran su marca o su familia sin nada que la nota lea (sin lector, con las marcas que nombra:
    nadie más puede cubrir lo que el plano dice de ellas). Un texto dibujado dos veces encima de
    sí mismo es del dueño de su copia."""
    de_alguien = {e.entity_id for e in duenos}
    copias: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in duenos:
        copias[(e.text or "").strip()].append(ancla_texto(e))
    huerfanos: list[Rechazo] = []
    for e in grupo:
        clase = clases[e.entity_id][0]
        if clase in ("nota", "ajena") and e.entity_id not in de_alguien:
            huerfanos += _nota_que_nombra(e, hoja, config)
            continue
        if clase not in ("linea", "llamada", "sin_lector"):
            continue
        if e.entity_id in de_alguien or e.entity_id in rechazados:
            continue
        texto = (e.text or "").strip()
        x, y = ancla_texto(e)
        limite = _DUPLICADO * alto_de_texto(e)
        if any(math.hypot(x - cx, y - cy) <= limite for cx, cy in copias.get(texto, [])):
            continue
        if clase == "sin_lector":
            varias = leer_marcas(texto, config).tipo == "varias"
            huerfanos.append(
                Rechazo(
                    entidad_id=e.entity_id,
                    texto=texto,
                    hoja=hoja,
                    # Una nota de varias marcas se reporta como tal (R63), se pueda leer o no.
                    motivo="varias_marcas" if varias else "sin_lector",
                    marcas=marcas_en_nota(texto, config) or titulos(texto, config),
                )
            )
        else:
            huerfanos.append(
                Rechazo(entidad_id=e.entity_id, texto=texto, hoja=hoja, motivo="sin_dueno")
            )
    return huerfanos


# ---------------------------------------------------------- R147: la pila bajo una sección


@dataclass(frozen=True)
class SeccionDeTitulo:
    """R147: una sección dibujada que un título tiene (``lee``: su armado se lee de debajo de
    ella, como la pila de una etiqueta), o que sólo reclama o que no es de nadie (compite, para
    que su armado nunca se lo lleve una vecina, y nada se lee de ella). ``caja`` es su rectángulo
    en el dibujo; ``archivo`` y el centro de la caja dicen su hoja; ``sentidos``, de qué lado
    puede estar su pila (el contrario al de su título: abajo, -1, si su título va encima)."""

    marca: str
    caja: tuple[float, float, float, float]
    archivo: str
    titulo_id: str = ""
    lee: bool = True
    sentidos: tuple[int, ...] = (+1, -1)
    # La familia que dice su título (R130), si la dice: con la que se lee su armado.
    familia: str | None = None
    # R195: la sección de una etiqueta de cuadro que ya tiene su pila (Tarea 6): compite de su
    # lado, nunca del de su etiqueta (lo de ahí ya lo leyó su etiqueta), y no cuenta para la
    # costumbre de los títulos.
    de_cuadro: bool = False


@dataclass(eq=False)
class _Seccion(_Texto):
    """Una sección en el lugar de una etiqueta (R147): su caja es la de la sección; su «alto», el
    que hace que su primer renglón pueda estar a lo más a su lado menor (la columna de un
    detalle: el armado escrito bajo su sección, más allá del dibujo que cuelga de ella)."""

    ident: str = ""
    seccion: SeccionDeTitulo | None = None

    @property
    def id(self) -> str:
        return self.ident

    @property
    def texto(self) -> str:
        return self.marca or ""

    @property
    def renglones(self) -> list[str]:
        return []


def _lo_que_alcanza_cada_seccion(
    secciones: list[_Seccion], textos: list[_Texto], estorban: set[str]
) -> dict[str, list[tuple[_Seccion, float]]]:
    """R189, R196, R201: por renglón, las secciones que lo alcanzan de frente o de lado (su
    ensanche: el alcance con que leen), de cualquiera de sus dos lados (el de su título también:
    puede estar del lado equivocado), con el doble de su alcance (lo que casi alcanza, R56), sin
    nada en medio más que otros renglones libres (ningún otro texto, salvo su propio título, ni
    la caja de otra sección), con su hueco a él; y, del lado de su título, la columna entera que
    tomaría con ese doble (R196: el mismo casi que del lado que lee), con el hueco de su primer
    renglón. La sección de un cuadro no (su pila ya la leyó su etiqueta)."""
    lineas = [t for t in textos if t.clase == "linea" and t.id not in estorban]
    obstaculos = [t for t in textos if not (t.clase == "linea" and t.id not in estorban)]
    alcanzan: dict[str, list[tuple[_Seccion, float]]] = defaultdict(list)
    for sec in secciones:
        if sec.seccion is not None and sec.seccion.de_cuadro:
            continue
        propio = sec.seccion.titulo_id if sec.seccion is not None else ""
        lejos = _CASI * _HUECO_DE_ETIQUETA * sec.alto
        estorbos = [t for t in obstaculos if t.id != propio] + [
            o for o in secciones if o is not sec
        ]
        for t in lineas:
            # R201: con el alcance con que lee: de frente o de lado (en su ensanche).
            if not (_se_enciman(t, sec) or _en_la_etiqueta(sec, t)):
                continue
            if t.y0 >= sec.y1:
                bajo, alto = sec.y1, t.y0
            elif t.y1 <= sec.y0:
                bajo, alto = t.y1, sec.y0
            else:
                continue
            if alto - bajo > lejos:
                continue
            # Lo que estorba es lo que está en medio en la franja que comparten (la vista de la
            # sección al renglón), no lo que sólo cae junto a uno de los dos.
            f0, f1 = max(sec.x0, t.x0), min(sec.x1, t.x1)
            if f1 <= f0:  # de lado: la franja es la del renglón
                f0, f1 = t.x0, t.x1
            if any(
                u.y1 > bajo
                and u.y0 < alto
                and min(u.x1, f1) - max(u.x0, f0) >= _ENCIMA_MINIMO * min(u.x1 - u.x0, f1 - f0)
                for u in estorbos
            ):
                continue
            alcanzan[t.id].append((sec, alto - bajo))
    # Y del lado de su título, la columna entera que tomaría con ese doble (su primer renglón y
    # los que le siguen): su hueco es el de su primer renglón.
    renglones = _Indice(lineas)
    libres = {t.id for t in lineas}
    etiquetas = [t for t in textos if t.clase == "etiqueta" and t.id not in estorban]
    for sec in secciones:
        if sec.seccion is not None and sec.seccion.de_cuadro:
            continue
        propio = sec.seccion.titulo_id if sec.seccion is not None else ""
        indice = _Indice([*lineas, *(t for t in obstaculos if t.id != propio)])
        rivales = [*(t for t in etiquetas if t.id != propio), *secciones]
        for lado in (+1, -1):
            if lado in sec.sentidos:
                continue
            a = _alcance(
                replace(sec, alto=_CASI * sec.alto), lado, indice, renglones, libres, rivales
            )
            if a is None:
                continue
            for t in [*a.renglones, *a.despues]:
                alcanzan[t.id].append((sec, a.hueco))
    return alcanzan


def _la_tiene_otra_mas_cerca(
    seccion: _Seccion,
    pila: list[_Texto],
    alcanzan: dict[str, list[tuple[_Seccion, float]]],
) -> bool:
    """R189, R196, R209: si otra sección que alcanza un renglón de la pila de ``seccion``
    (``_lo_que_alcanza_cada_seccion``, de cualquier lado: el de su título también) está igual de
    pegada: sólo la distancia decide; el renglón es de ``seccion`` si está claramente más pegado a
    ella (más allá del empate de lados opuestos de la Tarea 6, 25 %); si no, la pila queda en
    duda. La costumbre de la hoja nunca gana una pila disputada, y tener su propia lectura no
    exime a la otra de disputarla (R209: dos secciones así se cambiaban las pilas, la semilla
    45408 de la rejilla)."""
    for t in pila:
        propio = t.y0 - seccion.y1 if t.y0 >= seccion.y1 else seccion.y0 - t.y1
        for otra, suyo in alcanzan.get(t.id, ()):
            if otra is seccion:
                continue
            if not (propio < suyo and not _casi_igual(propio, suyo, t.alto, _EMPATE_OPUESTO)):
                return True
    return False


def _deja_sin_lectura(
    seccion: _Seccion,
    pila: list[_Texto],
    alcanzan: dict[str, list[tuple[_Seccion, float]]],
    campos_de: dict[str, set[str]],
) -> bool:
    """R200, R205: si la pila de ``seccion`` dejaría sin su lectura de un campo a otra sección
    que se lee y alcanza uno de sus renglones (con el doble de su alcance, de cualquier lado, de
    frente o de lado): la que lo necesita (no tiene, en lo que se lee, lectura propia de ese
    campo). La distancia nunca le da a una sección la pila que otra necesita. Una reclamada o
    libre (que nunca se lee) no la necesita: compite sólo por la distancia."""
    return any(
        otra is not seccion
        and otra.seccion is not None
        and otra.seccion.lee
        and not (_campos_del_renglon(t) <= campos_de.get(otra.id, set()))
        for t in pila
        for otra, _hueco in alcanzan.get(t.id, ())
    )


# R200: lo que dice un renglón de una pila, para saber qué campo daría a su sección: un juego de
# estribos (con su cabeza: «E#4@10», «2E#3EXT@10», «EYG#3@15») o una distribución («CENTRO@20»,
# «1@6,8@10»), y un juego de varillas («4#3», «12#8+8#6»: los «+» lo juntan en uno).
_CABEZA_DE_ESTRIBO = re.compile(r"(?:\d*E(?:YG)?|G)\s*#\s*\d")
_VARILLAS = re.compile(r"(?<![#@\dEG])\d+\s*#\s*\d+(?!\s*@)")


def _campos_del_renglon(t: _Texto) -> set[str]:
    texto = t.texto.upper()
    campos = set()
    if _CABEZA_DE_ESTRIBO.search(texto) or "@" in texto:
        campos.add("estribos")
    if _VARILLAS.search(_CABEZA_DE_ESTRIBO.sub(" ", texto)):
        campos.add("longitudinales")
    return campos


def _campo_doble(
    seccion: _Seccion,
    pila: list[_Texto],
    alcanzan: dict[str, list[tuple[_Seccion, float]]],
) -> bool:
    """R200, R206: si la pila le daría a su sección dos juegos del mismo campo (dos renglones con
    varillas, no juntos por «+», que van en un renglón; o dos con cabeza de estribo) que pueden
    ser de dos pilas juntas: si no van seguidos en la columna (otro renglón entre ellos) o si otra
    sección alcanza alguno. Seguidos y sólo suyos, son una pila: «3#8 LECHO INF.» / «2#6 LECHO
    SUP.», «4#4» / «3#8» / «2#8+2#6», «E#4@15» / «G#3@30», «2E#3@15» / «E#3@15 RESTO»; el lector
    los junta, o dice lo que no entiende (``_pilas_de_secciones``)."""
    orden = sorted(pila, key=lambda t: abs(t.cy - seccion.cy))
    for campo in ("varillas", "estribos"):
        lugares = []
        for n, t in enumerate(orden):
            texto = t.texto.upper()
            if campo == "estribos":
                tiene = bool(_CABEZA_DE_ESTRIBO.search(texto))
            else:
                tiene = bool(_VARILLAS.search(_CABEZA_DE_ESTRIBO.sub(" ", texto)))
            if tiene:
                lugares.append(n)
        if len(lugares) < 2:
            continue
        if lugares[-1] - lugares[0] != len(lugares) - 1:
            return True  # otro renglón entre ellos
        for n in lugares:
            if any(otra is not seccion for otra, _h in alcanzan.get(orden[n].id, ())):
                return True
    return False


def _columna_abierta(
    seccion: _Texto, sentido: int, pila: list[_Texto], otros: list[_Texto]
) -> bool:
    """R189: si la pila de ``seccion`` no acaba limpia: si a su último renglón le sigue, a menos de
    un hueco entre renglones, otro texto (o la caja de otra sección) encimado de lado con él en al
    menos la mitad del más angosto. La columna llega a otro detalle, o sigue en algo que no es un
    renglón libre: lo del final puede ser de él, o la pila seguir."""
    ids = {t.id for t in pila} | {seccion.id}
    ultimo = max(pila, key=lambda t: sentido * t.cy)
    margen = _HUECO_ENTRE_RENGLONES * ultimo.alto
    lejos = (ultimo.y1, ultimo.y1 + margen) if sentido > 0 else (ultimo.y0 - margen, ultimo.y0)
    for u in otros:
        if u.id in ids or u.y1 <= lejos[0] or u.y0 >= lejos[1]:
            continue
        comun = min(u.x1, ultimo.x1) - max(u.x0, ultimo.x0)
        if comun >= _ENCIMA_MINIMO * min(u.x1 - u.x0, ultimo.x1 - ultimo.x0):
            return True
    return False


def asociar_secciones(
    entities: list[NormalizedEntity],
    frames: list[SheetFrame],
    config: TextPatternConfig,
    secciones: list[SeccionDeTitulo],
    libres: set[str],
) -> tuple[list[Asociacion], dict[str, set[str]]]:
    """R147: el armado de un título que tiene una sección dibujada, leído de debajo de ESA
    sección con las reglas de la pila (Tarea 6: banda, hueco entre renglones, alineación) y sus
    reglas de reclamo y duda (R54–R61): la sección toma el lugar de la etiqueta. Compiten todas
    las secciones de la hoja (las que se leen, las reclamadas y las que no son de nadie) y todas
    las etiquetas, así que dos secciones vecinas nunca mezclan sus textos: lo dudoso no es de
    nadie. Sólo son renglones los textos de ``libres`` (los que nadie leyó ni nombra: «sin
    dueño»); todo lo demás —leído, rechazado con marcas, notas, llamadas— estorba. Sólo los
    textos derechos (a 0°) apilan bajo una sección.

    R189, R196, R200, el principio: un renglón es de una sección sólo si ningún otro lector
    puede tenerlo. Una pila queda en duda —no se lee, y sus renglones llevan las marcas como
    «posible»— si: otra etiqueta o sección la tiene enfrente con el doble de su alcance (lo que
    casi alcanza, R56, con su columna entera); otra sección alcanza uno de sus renglones, de
    frente o de lado, de cualquiera de sus lados (el de su título puede ser el equivocado), con
    ese mismo doble y sin nada en medio, y el renglón no está claramente (25 %) más pegado a
    ésta (sólo la distancia decide); su primer renglón no está enfrente de la sección (sólo en su
    ensanche: una caja dibujada no se ensancha); no acaba limpia (algo la sigue a menos de un
    hueco entre renglones); tomaría un texto del dibujo de una sección (R203: encimado en su caja
    o en su esquina, a su lado); le daría dos juegos de un mismo campo que pueden ser dos pilas
    juntas (R206: no van seguidos, u otra sección alcanza alguno); o dejaría sin su lectura de
    ese campo a otra sección que se lee y la alcanza (la distancia nunca le da a una sección la
    pila que otra necesita; R205: una que nunca se lee compite sólo por la distancia).
    Devuelve las pilas tomadas por las secciones que se leen
    (por su título: ``etiqueta_id`` es el título, ``marca`` la suya) y los renglones en disputa
    entre una sección y otra marca (con sus marcas)."""
    textos = [e for e in entities if e.is_textual and e.text and e.text.strip()]
    if not secciones or not textos:
        return [], {}
    hoja_de = _hoja_de(frames)
    ordenados = sorted(frames, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    grupos: dict[tuple, list[NormalizedEntity]] = defaultdict(list)
    hojas: dict[tuple, str] = {}
    hoja_por_id: dict[str, str] = {}
    for e in textos:
        llave, hoja = hoja_de(e)
        grupos[llave].append(e)
        hojas[llave] = hoja
        hoja_por_id[e.entity_id] = hoja
    de_la_hoja: dict[tuple, list[tuple[int, SeccionDeTitulo]]] = defaultdict(list)
    for n, sec in enumerate(secciones):
        centro = ((sec.caja[0] + sec.caja[2]) / 2, (sec.caja[1] + sec.caja[3]) / 2)
        marco = next(
            (f for f in ordenados if f.source_file in ("", sec.archivo) and f.contains(centro)),
            None,
        )
        de_la_hoja[(sec.archivo, marco.frame_id if marco is not None else None)].append((n, sec))
    _, _, de_notas = leer_notas_con_renglones(textos, lambda e: hoja_por_id[e.entity_id])
    lineas = _lineas(entities, textos)
    asociaciones: list[Asociacion] = []
    disputados: dict[str, set[str]] = {}
    for llave, grupo in grupos.items():
        suyas = de_la_hoja.get(llave)
        if not suyas:
            continue
        giros = _giros(grupo)
        # Los títulos de las secciones: su pila es la de su sección (no casi alcanzan otra).
        del_titulo = {sec.titulo_id for _n, sec in suyas if sec.titulo_id}
        locales: list[_Texto] = []
        for e in grupo:
            if giros[e.entity_id] != 0:
                continue
            clase, marca = _clase(e, config, de_notas)
            t = _texto_local(e, 0, clase, marca)
            if clase == "linea" and lineas.es_llamada(t, 0):
                t.clase = "llamada"
            locales.append(t)
        if not locales:
            continue
        # Lo que no es un renglón libre estorba: lo que otro ya leyó o rechazó con su marca.
        estorban = {t.id for t in locales if t.clase == "linea" and t.id not in libres}
        por_id: dict[str, _Seccion] = {}
        for n, sec in suyas:
            x0, y0, x1, y1 = sec.caja
            lado_menor = min(x1 - x0, y1 - y0)
            if lado_menor <= 0:
                continue
            titulo = next((e for e in grupo if e.entity_id == sec.titulo_id), grupo[0])
            seccion = _Seccion(
                titulo, "etiqueta", f"{sec.marca}§{n}", x0, x1, y0, y1,
                lado_menor / _HUECO_DE_ETIQUETA, sentidos=sec.sentidos,
                ident=f"§seccion:{n}", seccion=sec,
            )  # fmt: skip
            por_id[seccion.id] = seccion
        if not por_id:
            continue
        # R203: un texto encimado en la caja de una sección (dentro, o cruzando su orilla: el
        # «E#4» de CTA-1 en su esquina, a su lado, en su ensanche) es de su dibujo: nunca es renglón
        # de una pila. Una pila que lo tomaría queda en duda. Nunca corta una columna ni tapa a una
        # sección lo que disputa: cortada ahí, una pila quedaría a medias (la semilla 806 de
        # «zigzag»), y una sección que no ve un renglón por él no lo disputa y otra lo lee (la
        # semilla 7626 de la rejilla). La suya (R194: en su esquina, no lo lee) sigue compitiendo
        # por lo que le sigue.
        dibujo: dict[str, set[str]] = defaultdict(set)
        for t in locales:
            if t.clase != "linea" or t.id in estorban:
                continue
            for dibujada in por_id.values():
                if t.y0 < dibujada.y1 and t.y1 > dibujada.y0 and _en_la_etiqueta(dibujada, t):
                    dibujo[t.id].add(dibujada.id)
        reparto = _pilas([*locales, *por_id.values()], estorban, titulos=set(del_titulo))
        alcanzan = _lo_que_alcanza_cada_seccion(list(por_id.values()), locales, estorban)
        candidatas: list[tuple[_Seccion, SeccionDeTitulo, _Alcance, list[_Texto]]] = []
        for alcance, propios in reparto.tomadas:
            la_seccion = por_id.get(alcance.etiqueta.id)
            dato = la_seccion.seccion if la_seccion is not None else None
            if la_seccion is None or dato is None or not dato.lee:
                continue
            if (
                not alcance.frontal
                or any(t.id in dibujo for t in propios)
                or _campo_doble(la_seccion, propios, alcanzan)
                or _columna_abierta(
                    la_seccion, alcance.sentido, propios, [*locales, *por_id.values()]
                )
                or _la_tiene_otra_mas_cerca(la_seccion, propios, alcanzan)
            ):
                disputados.update({t.id: {dato.marca} for t in propios})
                continue
            candidatas.append((la_seccion, dato, alcance, propios))
        # R200, R205: nunca una pila que deja sin su lectura de un campo a otra sección que se lee
        # y la alcanza (la que la necesita). Lo que se quita puede dejar sin su lectura a otra:
        # hasta que nada cambie.
        while True:
            campos_de: dict[str, set[str]] = defaultdict(set)
            for lectora, _dato, _alcance, propios in candidatas:
                for t in propios:
                    campos_de[lectora.id] |= _campos_del_renglon(t)
            huerfanas = [
                c for c in candidatas if _deja_sin_lectura(c[0], c[3], alcanzan, campos_de)
            ]
            if not huerfanas:
                break
            for c in huerfanas:
                candidatas.remove(c)
                disputados.update({t.id: {c[1].marca} for t in c[3]})
        for _la_seccion, dato, alcance, propios in candidatas:
            orden = propios[::-1] if alcance.sentido > 0 else propios
            renglones = [(t.id, r) for t in orden for r in t.renglones]
            asociaciones.append(
                Asociacion(
                    etiqueta_id=dato.titulo_id,
                    marca=dato.marca,
                    hoja=hojas[llave],
                    textos=[r for _i, r in renglones],
                    entidades=[i for i, _r in renglones],
                    via="pila",
                )
            )
        for renglon, marcas in reparto.ambiguos.items():
            reales = {m.split("§")[0] for m in marcas}
            if any("§" in m for m in marcas):
                disputados[renglon] = {m for m in reales if m}
    asociaciones.sort(key=lambda a: (a.hoja, a.marca, a.etiqueta_id))
    return asociaciones, disputados
