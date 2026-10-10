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
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity
from klave_engine.estructura.notas import leer_notas_con_renglones
from klave_engine.estructura.textos import alto_de_texto, ancla_texto, caja_de_texto

__all__ = [
    "ARMADO_RE",
    "Asociacion",
    "Rechazo",
    "ancla_texto",
    "asociar",
    "marca_en_texto",
]

# Un texto con forma de armado: una varilla (``#4``), una separación (``@20``) o el renglón que
# sigue una zona de estribos (``CENTRO@20``, ``EXT @10``); «CENTRO DE CARGA» no.
ARMADO_RE = re.compile(r"#\s*\d|@\s*\d|^\s*CENTRO\s*@|^\s*EXT\s*@", re.I)

# Una marca: K-1, C-3, T-2, COL-1, CTA-3, Z-1, D-4B, P-4, MC-1, CE-1, CR-2, con su sufijo de
# variante (``K-15A.1`` es otra marca que ``K-15A``), o el tipo «X» con su guion (``K-X``, ``D-X``).
_MARCA_RE = re.compile(
    r"\b(K|C|T|COL|CT|CTA|TB|ZC|ZCM|Z|D|P|MC|CE|CR)"
    r"(?:\s*-?\s*(\d{1,2})([A-Z]?)(?:\.(\d))?|-(X))\b"
)
_PREFIJO_DE_ETIQUETA = re.compile(r"^(?:CASTILLO|COLUMNA)\s+")
_LARGO_DE_ETIQUETA = 10
# Una etiqueta de varias marcas («K-1 Y K-2», «K-1, K-2», «K-1=K-2», «K-1/K-2», «K-1 A K-4»,
# «K-1 – K-4», «K-1 HASTA K-4»): lo que queda entre sus marcas son sólo separadores.
_ENTRE_MARCAS = re.compile(r"(?:\s|[,;/=&+\-–]|\b(?:Y|E|A|AL|HASTA)\b)*")
_LARGO_DE_VARIAS = 40
_JUNTAS = " Y "  # cómo se escribe la «marca» de una etiqueta de varias
# Un rango («K-1 A K-4», «K-1 AL K-4», «K-1 - K-4», «K-1 – K-4», «K-1 HASTA K-4», «DE K-1 A K-4»,
# «K-1 A 4», «K-1 A K-2 A K-3») se reporta como está escrito: no se adivinan las marcas de en
# medio (ni si las hay).
_CONECTOR_DE_RANGO = re.compile(r"\b(?:AL|A|HASTA)\b|[-–]")
_ABRE_RANGO = re.compile(r"(?:DE|DEL|DESDE)\s+")
# El fin de un rango escrito sólo con su número («K-1 A 4»), tras un conector entre espacios.
_FIN_DE_RANGO = re.compile(r"\s+(?:AL|A|HASTA|-|–)\s+(\d{1,2}[A-Z]?(?:\.\d)?)\b")
_RANGO = re.compile(r"\S (?:AL|A|HASTA|-|–) \S")
# Lo que remite a otra parte del plano no reclama una marca: «E#2@15 VER CORTE C-2» es un
# renglón de armado, no una nota de C-2.
_REFERENCIA = re.compile(
    r"\b(?:VER|V[EÉ]ASE|SEG[UÚ]N|IGUAL\s+A)\b\.?(?:\s+(?:EL|LA|LOS|LAS))?"
    r"(?:\s+(?:CORTE|DETALLE|DET\.?|SECCI[OÓ]N|PLANO|NOTA|CUADRO)\b\.?)?\s*[^\s,;]*"
    r"|\b(?:CORTE|DETALLE|DET\.)\s+[^\s,;]+",
    re.I,
)
# Lo que una nota sí lee de un texto (``detection.schedules._parse_annotations``): una sección
# (15x20, sin las piezas de 3 medidas) o varillas longitudinales (4#3, 6 VAR #4, V12#5).
_SECCION = re.compile(r"(?<![\dxX×])(\d{1,3})\s*[xX×]\s*(\d{1,3})(?![\dxX×])")
_PIEZA = re.compile(r"\d{1,3}\s*[xX×]\s*\d{1,3}\s*[xX×]\s*\d{1,3}")
_LONGITUDINALES = re.compile(r"(\d{1,2})\s*(?:V|VAR|VARS|VARILLAS)?\s*#\s*(\d)(?!\s*@)", re.I)
_MALLA = re.compile(r"(?<![E\d])#\s*(\d)\s*@\s*(\d{1,3})", re.I)
# Los estribos, como los quita ``schedules._parse_rebar`` antes de buscar malla y varillas
# («E #3@20», con espacio, no es una malla).
_ESTRIBOS = re.compile(r"E\s*#?\s*(\d)\s*@\s*(\d{1,3})", re.I)
_LADO_DE_SECCION_CM = (8, 400)

# Un texto que nombra otra familia es de la lectura de esa familia (la losa, el muro, la nota de
# dalas): nunca entra a una pila, nunca es huérfano y una pila nunca sigue más allá de él.
_OTRA_FAMILIA = re.compile(r"\b(?:LOSA|DALA|CADENA|CONTRATRABE|TRABE|VIGA|MURO|ZAPATA)")
# Las notas de familia de castillos y columnas («CASTILLOS 15X15 4#3 E#2@20») tampoco entran a
# una pila: son de toda la familia, no de una marca.
_NOTA_DE_FAMILIA = re.compile(r"\b(?:CASTILLO|ARMEX|COLUMNA)")
# Un renglón numerado («4.- SE PERMITE…», «5) …»), en cualquier línea de un MTEXT.
_NOTA_NUMERADA = re.compile(r"^\s*\d{1,2}[.\-)]+(?:\s|$)", re.M)

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
    """La marca que nombra ``texto``: el texto entero si es una etiqueta de columna o de trabe de
    la configuración; si no, la primera marca que aparece en él, escrita ``K-15A.1``."""
    limpio = texto.strip().upper()
    if match_category(limpio, config, "column_tag") or match_category(limpio, config, "beam_tag"):
        return limpio
    m = _MARCA_RE.search(limpio)
    if m is None:
        return None
    if m.group(5):
        return f"{m.group(1)}-X"
    variante = f".{m.group(4)}" if m.group(4) else ""
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}{variante}"


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


class Rechazo(BaseModel):
    """Un texto con forma de armado que no se pegó a ninguna marca, o una etiqueta que se quedó
    sin la pila que alcanzaba; y por qué."""

    entidad_id: str
    texto: str
    hoja: str
    # ambigua: dos o más marcas lo pueden reclamar y no se puede decidir de cuál es (``marcas``);
    # otra_familia: está en la pila de una marca pero nombra otra familia; sin_lector: nombra su
    # marca o su familia pero ningún lector lo lee (sólo estribos, p. ej.); varias_marcas: es de
    # la pila de una etiqueta con varias marcas («K-1 Y K-2» → [K-1, K-2]) o un rango («K-1 A K-4»
    # → [«K-1 A K-4»], como se escribió), que E0 no lee; sin_dueno: nada lo lee.
    motivo: Literal["ambigua", "otra_familia", "sin_lector", "varias_marcas", "sin_dueno"]
    marcas: list[str] = Field(default_factory=list)


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
    es una marca: una etiqueta de cuadro o de planta."""
    limpio = _PREFIJO_DE_ETIQUETA.sub("", " ".join(texto.split()).upper())
    if not limpio or len(limpio) > _LARGO_DE_ETIQUETA:
        return None
    if (
        match_category(limpio, config, "column_tag")
        or match_category(limpio, config, "beam_tag")
        or _MARCA_RE.fullmatch(limpio)
    ):
        return marca_en_texto(limpio, config)
    return None


def _varias_marcas(texto: str, config: TextPatternConfig) -> list[str] | None:
    """Las marcas de una etiqueta que nombra dos o más («K-1 Y K-2» → [K-1, K-2]), o ``None``."""
    limpio = _PREFIJO_DE_ETIQUETA.sub("", " ".join(texto.split()).upper())
    if len(limpio) > _LARGO_DE_VARIAS:
        return None
    # Cada marca, y el número que cierra un rango escrito sin la letra («K-1 A 4»).
    halladas = [m.span() for m in _MARCA_RE.finditer(limpio)]
    for _, fin in list(halladas):
        numero = _FIN_DE_RANGO.match(limpio, fin)
        if numero is not None and not any(
            a < numero.end(1) and numero.start(1) < b for a, b in halladas
        ):
            halladas.append(numero.span(1))
    halladas.sort()
    if len(halladas) < 2:
        return None
    entre = [limpio[a[1] : b[0]] for a, b in zip(halladas, halladas[1:], strict=False)]
    antes, despues = limpio[: halladas[0][0]], limpio[halladas[-1][1] :]
    if not all(_ENTRE_MARCAS.fullmatch(r) for r in [*entre, despues]):
        return None
    # Las marcas seguidas de un conector de rango van juntas: el rango, como se escribió.
    grupos: list[list[tuple[int, int]]] = [[halladas[0]]]
    for separa, marca in zip(entre, halladas[1:], strict=True):
        if _CONECTOR_DE_RANGO.search(separa):
            grupos[-1].append(marca)
        else:
            grupos.append([marca])
    abre = _ABRE_RANGO.fullmatch(antes)
    if not _ENTRE_MARCAS.fullmatch(antes) and (abre is None or len(grupos[0]) < 2):
        return None  # «DE K-1 A K-4» abre un rango; nada más va delante
    piezas: list[str] = []
    for k, grupo in enumerate(grupos):
        if len(grupo) == 1:
            a, b = grupo[0]
            if not _MARCA_RE.fullmatch(limpio[a:b]):
                return None  # un número suelto no es una marca
            piezas.append(marca_en_texto(limpio[a:b], config) or limpio[a:b])
        else:
            desde = 0 if k == 0 and abre is not None else grupo[0][0]
            piezas.append(limpio[desde : grupo[-1][1]])
    return list(dict.fromkeys(piezas))


def _marcas_de(marca: str) -> list[str]:
    """Las marcas de una etiqueta (una, o varias si es de varias; un rango, como se escribió)."""
    return marca.split(_JUNTAS)


def _es_de_varias(marca: str) -> bool:
    """Si la etiqueta nombra más de una marca: una lista o un rango."""
    return _JUNTAS in marca or _RANGO.search(marca) is not None


def _lo_lee_una_nota(texto: str) -> bool:
    """Si la lectura de notas toma algo de ``texto``: una sección (dos lados de 8 a 400 cm),
    varillas longitudinales o una malla («K-3 #4@20»). Un texto con sólo estribos («K-7 E#3@20»)
    no lo lee nadie."""
    piezas = [m.span() for m in _PIEZA.finditer(texto)]
    for m in _SECCION.finditer(texto):
        if any(a <= m.start() < b for a, b in piezas):
            continue
        lados = int(m.group(1)), int(m.group(2))
        if all(_LADO_DE_SECCION_CM[0] <= lado <= _LADO_DE_SECCION_CM[1] for lado in lados):
            return True
    # Como ``schedules._parse_rebar``: primero se quitan los estribos y en lo que queda se busca
    # una malla o varillas.
    estribos = _ESTRIBOS.search(texto)
    if estribos is not None:
        texto = texto[: estribos.start()] + texto[estribos.end() :]
    return _MALLA.search(texto) is not None or _LONGITUDINALES.search(texto) is not None


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
    if ARMADO_RE.search(texto) is None:
        return "nada", None
    if e.entity_id in de_notas or _NOTA_NUMERADA.search(texto):
        return "nota", None
    mayusculas = texto.upper()
    if _OTRA_FAMILIA.search(mayusculas):
        return "ajena", None
    if marca_en_texto(_REFERENCIA.sub(" ", texto), config) is not None:
        # «K-1 15x20 4#3 E#2@20» dice de quién es y lo lee la nota; «K-7 E#3@20», no.
        return ("anotacion" if _lo_lee_una_nota(texto) else "sin_lector"), None
    if _NOTA_DE_FAMILIA.search(mayusculas):
        return ("familia" if _lo_lee_una_nota(texto) else "sin_lector"), None
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
    return not any(ARMADO_RE.search(c.texto) or marca_en_texto(c.texto, config) for c in tramo)


def _filas_de_cuadros(
    textos: list[_Texto], config: TextPatternConfig
) -> list[tuple[_Texto, str, list[_Texto]]]:
    """Las filas de los cuadros con títulos: ``(celda de la marca, marca, demás celdas)``.

    Como ``detection.schedules``: un renglón de títulos abre el cuadro; cada renglón de abajo pone
    sus textos en la columna cuyo título le queda más cerca (a lo más media separación de
    columnas; lo que cae fuera no es del cuadro) y su marca es la de la columna de marcas (o la
    primera que aparezca); el cuadro acaba en un renglón sin marca o tras un hueco de más de
    cuatro renglones."""
    renglones = _renglones(textos)
    filas: list[tuple[_Texto, str, list[_Texto]]] = []
    for i, renglon in enumerate(renglones):
        for cabeza in _tramos(renglon):
            if _es_cabeza(cabeza, config):
                filas += _filas_bajo(cabeza, renglones[i + 1 :], config)
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
    for titulo, cs in celdas.items():
        if _COLUMNA_DE_MARCA.search(titulo):
            marca = marca_en_texto(" ".join(c.texto for c in cs), config)
            if marca is None:
                break
            duena = next((c for c in cs if marca_en_texto(c.texto, config)), cs[0])
            return duena, marca
    for cs in celdas.values():
        for c in cs:
            marca = marca_en_texto(c.texto, config)
            if marca is not None:
                return c, marca
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
    for sentido in (+1, -1):
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


def _pilas(textos: list[_Texto], de_filas: set[str]) -> _Reparto:
    """Las pilas de un grupo de textos con la misma dirección, ya repartidas."""
    etiquetas = [t for t in textos if t.clase == "etiqueta" and t.id not in de_filas]
    libres = {t.id for t in textos if t.clase == "linea" and t.id not in de_filas}
    lineas = [t for t in textos if t.id in libres]
    estorban = [t for t in textos if t.clase not in ("nada", "linea") or t.id in de_filas]
    indice, renglones = _Indice(lineas + estorban), _Indice(lineas)
    alcances = {
        e.id: [
            a
            for a in (_alcance(e, s, indice, renglones, libres, etiquetas) for s in (+1, -1))
            if a is not None
        ]
        for e in etiquetas
    }
    casi: dict[str, float] = {}  # etiqueta de un lado → hueco a la pila de enfrente del otro
    casi_de: dict[str, set[str]] = defaultdict(set)  # renglón → marcas que lo tienen enfrente
    for e in etiquetas:
        lados = {a.sentido for a in alcances[e.id]}
        for sentido in {+1, -1} - lados:
            cerca = _casi_alcanza(e, sentido, renglones)
            if cerca is None:
                continue
            casi_de[cerca[1].id].add(e.marca or "")
            if len(lados) == 1:
                casi[e.id] = cerca[0]
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
    entities: list[NormalizedEntity], frames: list[SheetFrame], config: TextPatternConfig
) -> tuple[list[Asociacion], list[Rechazo]]:
    """De qué marca es cada texto de armado, hoja por hoja; y lo que no se pudo pegar.

    Las ``Asociacion`` van por pila (la etiqueta pegada a su columna de renglones) o por fila
    (un renglón de un cuadro con títulos); su ``etiqueta_id`` es una etiqueta de definición, no
    una colocación. Los ``Rechazo`` son los renglones ambiguos, las etiquetas que se quedaron sin
    la pila que alcanzaban, los de otra familia que paraban una pila y todo texto con forma de
    armado que no lee nadie. Ver el docstring del módulo."""
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
    for llave, grupo in grupos.items():
        a, r = _asociar_hoja(grupo, hojas[llave], config, de_notas, lineas)
        asociaciones += a
        rechazos += r
    asociaciones.sort(key=lambda a: (a.hoja, a.marca, a.etiqueta_id))
    rechazos.sort(key=lambda r: (r.hoja, r.motivo, r.texto, r.entidad_id))
    return asociaciones, rechazos


def _asociacion(
    etiqueta: _Texto, marca: str, hoja: str, textos: list[_Texto], via: Literal["pila", "fila"]
) -> Asociacion:
    renglones = [(t.id, r) for t in textos for r in t.renglones]
    return Asociacion(
        etiqueta_id=etiqueta.id,
        marca=marca,
        hoja=hoja,
        textos=[r for _, r in renglones],
        entidades=[i for i, _ in renglones],
        via=via,
    )


def _asociar_hoja(
    grupo: list[NormalizedEntity],
    hoja: str,
    config: TextPatternConfig,
    de_notas: set[str],
    lineas: _Lineas,
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
    for giro in sorted(por_giro):
        locales = por_giro[giro]
        por_id = {t.id: t for t in locales}
        de_filas: set[str] = set()
        for etiqueta, marca, celdas in _filas_de_cuadros(locales, config):
            de_filas.add(etiqueta.id)
            de_filas.update(c.id for c in celdas)
            duenos += [c.e for c in celdas]
            if any(ARMADO_RE.search(c.texto) for c in celdas):
                asociaciones.append(_asociacion(etiqueta, marca, hoja, celdas, "fila"))
        reparto = _pilas(locales, de_filas)
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
            if _es_de_varias(alcance.marca):
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

    rechazos += _sin_dueno(grupo, hoja, clases, duenos, rechazados)
    return asociaciones, rechazos


def _sin_dueno(
    grupo: list[NormalizedEntity],
    hoja: str,
    clases: dict[str, tuple[_Clase, str | None]],
    duenos: list[NormalizedEntity],
    rechazados: set[str],
) -> list[Rechazo]:
    """Los textos de armado que nadie lee: los renglones sin pila ni fila (sin dueño) y los que
    nombran su marca o su familia sin nada que la nota lea (sin lector). Un texto dibujado dos
    veces encima de sí mismo es del dueño de su copia."""
    de_alguien = {e.entity_id for e in duenos}
    copias: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in duenos:
        copias[(e.text or "").strip()].append(ancla_texto(e))
    huerfanos: list[Rechazo] = []
    for e in grupo:
        clase = clases[e.entity_id][0]
        if clase not in ("linea", "llamada", "sin_lector"):
            continue
        if e.entity_id in de_alguien or e.entity_id in rechazados:
            continue
        texto = (e.text or "").strip()
        x, y = ancla_texto(e)
        limite = _DUPLICADO * alto_de_texto(e)
        if any(math.hypot(x - cx, y - cy) <= limite for cx, cy in copias.get(texto, [])):
            continue
        motivo: Literal["sin_lector", "sin_dueno"] = (
            "sin_lector" if clase == "sin_lector" else "sin_dueno"
        )
        huerfanos.append(Rechazo(entidad_id=e.entity_id, texto=texto, hoja=hoja, motivo=motivo))
    return huerfanos
