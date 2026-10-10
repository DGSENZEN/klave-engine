"""Asociación de la lectura estructural: a qué pieza pertenece cada texto del plano.

``ancla_texto`` da el punto donde el dibujante puso cada texto. ``asociar`` decide, sólo con la
geometría del dibujo, de qué marca es cada renglón de armado de un cuadro o de un detalle
(``8#6``, ``2E#3EXT@10`` y ``CENTRO@20`` son de ``K-11``):

- **Por pila** (lo medido en Marina): la etiqueta de la marca va pegada a una columna de renglones
  de armado, encima (Marina) o debajo (otras oficinas). El primer renglón empieza a lo más a 1.5
  altos de etiqueta de ella y cae, de lado, en lo que ocupa la etiqueta ensanchada 3 altos de
  renglón; cada renglón siguiente está a lo más a 1.5 altos de renglón del anterior y se encima de
  lado con los de la pila. La pila acaba en un hueco mayor o en un texto que no puede ser suyo:
  otra etiqueta, una nota de familia, una nota numerada, un texto que nombra su propia marca, la
  celda de un cuadro o una llamada (un texto con directriz es de lo que ésta señala). Cada
  etiqueta tiene a lo más una pila: la del lado más pegado (si empatan, la de arriba); lo del
  otro lado queda libre.
- **Por fila**: en un cuadro con títulos (MARCA | SECCIÓN | ARMADO | ESTRIBOS), las celdas de un
  renglón son de la marca de ese renglón.

Todo es por hoja (el marco que contiene el ancla del texto; sin marco, su archivo) y exclusivo:
un renglón que alcanzan dos marcas con huecos a menos de 10 % uno del otro es ambiguo y no es de
ninguna; si no, es de la más pegada. Un texto que nombra otra familia (LOSA, DALA, TRABE, MURO…)
nunca entra a una pila: es de la lectura de esa familia. Todo texto con forma de armado que no es
de nadie (ni de una pila, ni de una fila, ni de una nota numerada, ni de una nota de familia, ni
nombra su propia marca) sale como «sin dueño»: nada se queda sin leer en silencio."""

import bisect
import math
import re
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.detection.frames import SheetFrame
from klave_engine.detection.text_patterns import TextPatternConfig, match_category
from klave_engine.dxf.entities import EntityType, NormalizedEntity

# En «alineado» (3) y «ajustado» (5) el código 11 es donde TERMINA la línea base:
# el texto arranca en el ``insert``, así que ése es su ancla.
_HALIGN_CON_FINAL_EN_EL_PUNTO = (3, 5)

# Un texto con forma de armado: una varilla (``#4``), una separación (``@20``) o el renglón que
# sigue una zona de estribos (``CENTRO@20``, ``EXT…``).
ARMADO_RE = re.compile(r"#\s*\d|@\s*\d|^\s*CENTRO\b|^\s*EXT\b", re.I)

# Una marca: K-1, C-3, T-2, COL-1, CTA-3, Z-1, D-4B, P-4, MC-1, CE-1, CR-2, con su sufijo de
# variante (``K-15A.1`` es otra marca que ``K-15A``), o el tipo «X» con su guion (``K-X``, ``D-X``).
_MARCA_RE = re.compile(
    r"\b(K|C|T|COL|CT|CTA|TB|ZC|ZCM|Z|D|P|MC|CE|CR)"
    r"(?:\s*-?\s*(\d{1,2})([A-Z]?)(?:\.(\d))?|-(X))\b"
)
_PREFIJO_DE_ETIQUETA = re.compile(r"^(?:CASTILLO|COLUMNA)\s+")
_LARGO_DE_ETIQUETA = 10

# Un texto que nombra otra familia es de la lectura de esa familia (la losa, el muro, la nota de
# dalas): nunca entra a la pila de una marca y, si la para, se reporta.
_OTRA_FAMILIA = re.compile(r"\b(?:LOSA|DALA|CADENA|CONTRATRABE|TRABE|VIGA|MURO|ZAPATA)")
# Las notas de familia de castillos y columnas («CASTILLOS 15X15 4#3 E#2@20») tampoco: son de
# toda la familia, no de una marca.
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
# pilotes, que deja más aire); de lado, la etiqueta se ensancha 3 altos de renglón.
_HUECO_DE_ETIQUETA = 1.5
_HUECO_ENTRE_RENGLONES = 1.5
_ENSANCHE = 3.0
# Dos huecos son el mismo si difieren a lo más 10 % (o una décima de alto, para los que casi
# tocan): entre dos etiquetas, el renglón es ambiguo; entre dos lados de una etiqueta, gana arriba.
_EMPATE = 0.10
_EMPATE_ABSOLUTO = 0.1
# Un texto está «encima» de otro aunque se le meta hasta una décima de alto.
_TRASLAPE = 0.1
# El ancho de un carácter, × el alto, para los textos cuyo ancho no viene en el dibujo (ROMANS en
# Marina mide 0.83–1.03, mediana 0.92; los centrados traen su ancho real).
_ANCHO_POR_CARACTER = 0.9
# El paso entre renglones de un MTEXT, × el alto (el interlineado normal de AutoCAD).
_PASO_DE_MTEXT = 5.0 / 3.0
# Dos textos iguales a menos de esto (× el alto) son el mismo texto dibujado dos veces.
_DUPLICADO = 0.25
# Una llamada: un texto del que sale una directriz (una línea abierta que pasa a menos de 0.6
# altos de él y llega a más de 2 altos) hacia lo que describe, p. ej. las varillas de un corte.
# Es de lo que señala, no de una pila. En Marina las directrices de los detalles de trabes tocan
# su texto a 0.17–0.29 altos y llegan a 6–8; ninguna línea pasa a menos de 2.5 altos de un
# renglón de sus pilas.
_PUNTA_DE_LLAMADA = 0.6
_LARGO_DE_LLAMADA = 2.0


def ancla_texto(e: NormalizedEntity) -> tuple[float, float]:
    """El punto donde el dibujante puso el texto, no la esquina de su caja.

    Un TEXT con alineación distinta de «izquierda-base» se coloca por su punto
    de alineación (código 11): el ``insert`` de esos textos queda en otro lado.
    Excepto «alineado» y «ajustado», donde el código 11 es el final de la línea
    base y el ancla sigue siendo el ``insert``. Si no hay alineación, el ancla
    es el ``insert``; sin él, la esquina inferior izquierda de la caja."""
    propiedades = e.properties
    halign = propiedades.get("halign", 0)
    if (
        e.entity_type == EntityType.text
        and halign not in _HALIGN_CON_FINAL_EN_EL_PUNTO
        and (halign != 0 or propiedades.get("valign", 0) != 0)
    ):
        punto = propiedades.get("align_point")
        if punto is not None:
            return (float(punto[0]), float(punto[1]))
    insercion = propiedades.get("insert")
    if insercion is not None:
        return (float(insercion[0]), float(insercion[1]))
    return (e.bbox[0], e.bbox[1])


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
    textos: list[str]  # de arriba abajo (los de una fila, de izquierda a derecha)
    entidades: list[str]  # en el orden de ``textos``
    via: Literal["pila", "fila"]


class Rechazo(BaseModel):
    """Un texto con forma de armado que no se pegó a ninguna marca, y por qué."""

    entidad_id: str
    texto: str
    hoja: str
    # ambigua: dos marcas lo alcanzan igual; otra_familia: está en la pila de una marca pero
    # nombra otra familia; sin_dueno: nada lo lee.
    motivo: Literal["ambigua", "otra_familia", "sin_dueno"]
    marcas: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------- qué es cada texto

_Clase = Literal["etiqueta", "linea", "llamada", "ajena", "familia", "nota", "anotacion", "nada"]


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


def _clase(
    e: NormalizedEntity, config: TextPatternConfig, de_notas: set[str]
) -> tuple[_Clase, str | None]:
    """Qué es un texto para la asociación: una etiqueta (con su marca), un renglón de armado que
    puede ir en una pila, o un texto de armado que ya tiene dueño (una nota numerada, uno que
    nombra su marca, uno de otra familia, una nota de castillos o columnas); lo demás, nada."""
    texto = e.text or ""
    marca = _marca_de_etiqueta(texto, config)
    if marca is not None:
        return "etiqueta", marca
    if ARMADO_RE.search(texto) is None:
        return "nada", None
    if e.entity_id in de_notas or _NOTA_NUMERADA.search(texto):
        return "nota", None
    if marca_en_texto(texto, config) is not None:
        return "anotacion", None  # «K-1 15x20 4#3 E#2@20»: dice de quién es
    mayusculas = texto.upper()
    if _OTRA_FAMILIA.search(mayusculas):
        return "ajena", None
    if _NOTA_DE_FAMILIA.search(mayusculas):
        return "familia", None
    return "linea", None


# ----------------------------------------------------------------------- dónde está cada texto


def _ancho_dibujado(e: NormalizedEntity, giro: float) -> float | None:
    """El ancho de un TEXT alineado tal como lo calculó el CAD: la distancia, a lo largo del
    renglón, de su ``insert`` (inicio de la línea base) a su punto de alineación."""
    p = e.properties
    halign = p.get("halign") or 0
    insercion, punto = p.get("insert"), p.get("align_point")
    if e.entity_type != EntityType.text or not halign or insercion is None or punto is None:
        return None
    avance = (float(punto[0]) - float(insercion[0])) * math.cos(giro) + (
        float(punto[1]) - float(insercion[1])
    ) * math.sin(giro)
    if avance <= 1e-9:
        return None  # sin el insert calculado (p. ej. un DXF de ezdxf): no se sabe
    return 2.0 * avance if halign in (1, 4) else avance


def _alto(e: NormalizedEntity) -> float:
    alto = e.properties.get("height")
    if not isinstance(alto, int | float) or alto <= 0:
        alto = e.bbox[3] - e.bbox[1]
    return float(alto) if alto > 0 else 1e-6


def _forma_de_mtext(
    e: NormalizedEntity, texto: str, alto: float
) -> tuple[float, float, float, float, float]:
    """La caja de un MTEXT: su punto de inserción es una esquina, un lado o el centro de la
    caja (``attachment_point``); con columna (``column_width``), los párrafos van a la
    izquierda, al centro o a la derecha de ella (``paragraph_align``; si no la dice, según el
    punto de inserción) y los renglones largos se parten."""
    p = e.properties
    punto = int(p.get("attachment_point") or 1)
    punto = punto if 1 <= punto <= 9 else 1
    columna, fila = (punto - 1) % 3, (punto - 1) // 3
    renglones = [r.strip() for r in texto.split("\n")] or [""]
    por_caracter = _ANCHO_POR_CARACTER * alto
    ancho = por_caracter * max(len(r) for r in renglones)
    cuantos = len(renglones)
    ancho_de_columna = float(p.get("column_width") or 0.0)
    if ancho_de_columna > 0:
        cuantos = sum(
            max(1, math.ceil(por_caracter * len(r) / ancho_de_columna)) for r in renglones
        )
        ancho = min(ancho, ancho_de_columna)
        inicio = (0.0, -ancho_de_columna / 2, -ancho_de_columna)[columna]
        alineacion = p.get("paragraph_align") or "lcr"[columna]
        if alineacion == "c":
            dx0 = inicio + (ancho_de_columna - ancho) / 2
        elif alineacion == "r":
            dx0 = inicio + ancho_de_columna - ancho
        elif alineacion in ("j", "d"):
            dx0, ancho = inicio, ancho_de_columna  # justificado: ocupa la columna
        else:
            dx0 = inicio
    else:
        dx0 = (0.0, -ancho / 2, -ancho)[columna]
    total = alto + (cuantos - 1) * _PASO_DE_MTEXT * alto
    dy0 = (-total, -total / 2, 0.0)[fila]
    return dx0, dx0 + ancho, dy0, dy0 + total, alto


def _forma(e: NormalizedEntity, giro: float) -> tuple[float, float, float, float, float]:
    """La caja del texto respecto a su ancla, en la dirección del renglón:
    ``(dx0, dx1, dy0, dy1, alto de un renglón)``."""
    alto = _alto(e)
    texto = e.text or ""
    if e.entity_type == EntityType.mtext:
        return _forma_de_mtext(e, texto, alto)
    p = e.properties
    halign, valign = p.get("halign") or 0, p.get("valign") or 0
    ancho = _ancho_dibujado(e, giro) or _ANCHO_POR_CARACTER * alto * len(texto.strip())
    dx0 = {1: -ancho / 2, 2: -ancho, 4: -ancho / 2}.get(halign, 0.0)
    if halign == 4:
        dy0 = -alto / 2  # «medio»: centrado en las dos direcciones
    else:
        dy0 = {2: -alto / 2, 3: -alto}.get(valign, 0.0)
    return dx0, dx0 + ancho, dy0, dy0 + alto, alto


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
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _giro(e: NormalizedEntity) -> int:
    """La dirección del renglón en grados enteros (0 a 359)."""
    return round((e.rotation or 0.0) % 360.0) % 360


def _texto_local(e: NormalizedEntity, giro: int, clase: _Clase, marca: str | None) -> _Texto:
    """El texto en el marco de su renglón (girado ``giro`` grados): ahí una pila es vertical."""
    angulo = math.radians(giro)
    c, s = math.cos(angulo), math.sin(angulo)
    ax, ay = ancla_texto(e)
    lx, ly = ax * c + ay * s, -ax * s + ay * c
    dx0, dx1, dy0, dy1, alto = _forma(e, angulo)
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

        def local(x: float, y: float) -> tuple[float, float]:
            return x * c + y * s, -x * s + y * c

        def lejania(x: float, y: float) -> float:
            lx, ly = local(x, y)
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
    altos = [_alto(e) for e in textos]
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
    renglones: list[list[_Texto]] = []
    for t in sorted(textos, key=lambda t: (-t.cy, t.cx)):
        if renglones and abs(renglones[-1][0].cy - t.cy) <= tolerancia:
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
    y_previa = statistics.median(c.cy for c in cabeza)
    filas: list[tuple[_Texto, str, list[_Texto]]] = []
    for renglon in abajo:
        if y_previa - renglon[0].cy > alto * _FIN_DEL_CUADRO:
            break
        celdas: dict[str, list[_Texto]] = {}
        for c in renglon:
            x, titulo = min(columnas, key=lambda col: abs(col[0] - c.cx))
            if abs(x - c.cx) <= holgura:
                celdas.setdefault(titulo, []).append(c)
        if not celdas:
            continue  # lo de este renglón está en otra parte de la hoja
        y_previa = renglon[0].cy
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
    """Los textos que una pila puede tocar, ordenados para buscar por altura."""

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


def _casi_igual(a: float, b: float, alto: float) -> bool:
    return abs(a - b) <= max(_EMPATE * max(a, b), _EMPATE_ABSOLUTO * alto)


def _lejania(centro: float, t: _Texto) -> float:
    if t.x0 <= centro <= t.x1:
        return 0.0
    return min(abs(t.x0 - centro), abs(t.x1 - centro))


def _paso(
    indice: _Indice,
    borde: float,
    sentido: int,
    banda: tuple[float, float],
    alcance: float,
    alto: float,
    ensanche: float,
    centro: float,
    fuera: set[str],
) -> tuple[float, _Texto] | None:
    """El texto más pegado a ``borde`` en ``sentido`` (+1 arriba, -1 abajo) dentro del
    ``alcance`` que se encima de lado con ``banda`` (ensanchada ``ensanche`` altos del texto).
    Entre los que quedan igual de pegados, el que está más cerca del centro de la etiqueta."""
    holgura = _TRASLAPE * alto
    encontrados: list[tuple[float, _Texto]] = []
    for t in indice.cerca(borde, sentido, alcance, holgura):
        if t.id in fuera:
            continue
        hueco = t.y0 - borde if sentido > 0 else borde - t.y1
        if hueco < -_TRASLAPE * min(alto, t.alto) or hueco > alcance:
            continue
        margen = ensanche * t.alto
        if t.x1 < banda[0] - margen or t.x0 > banda[1] + margen:
            continue
        encontrados.append((max(hueco, 0.0), t))
    if not encontrados:
        return None
    menor = min(h for h, _ in encontrados)
    pegados = [(h, t) for h, t in encontrados if _casi_igual(h, menor, t.alto)]
    return min(pegados, key=lambda ht: (_lejania(centro, ht[1]), ht[0], ht[1].x0, ht[1].id))


@dataclass(eq=False)
class _Pila:
    etiqueta: _Texto
    sentido: int
    hueco: float  # de la etiqueta al primer renglón
    renglones: list[_Texto]
    tope: _Texto | None = None  # un texto de otra familia que la paró
    ganados: list[_Texto] = field(default_factory=list)


def _pila(etiqueta: _Texto, sentido: int, indice: _Indice, libres: set[str]) -> _Pila | None:
    """La pila de ``etiqueta`` hacia ``sentido``: el renglón más pegado y los que le siguen."""
    borde = etiqueta.y1 if sentido > 0 else etiqueta.y0
    primero = _paso(
        indice,
        borde,
        sentido,
        (etiqueta.x0, etiqueta.x1),
        _HUECO_DE_ETIQUETA * etiqueta.alto,
        etiqueta.alto,
        _ENSANCHE,
        etiqueta.cx,
        {etiqueta.id},
    )
    if primero is None or primero[1].id not in libres:
        return None  # nada, u otra cosa (otra etiqueta, una nota, una celda) en su lugar
    hueco, actual = primero
    pila = _Pila(etiqueta, sentido, hueco, [actual])
    banda = (actual.x0, actual.x1)
    borde = actual.y1 if sentido > 0 else actual.y0
    while True:
        siguiente = _paso(
            indice,
            borde,
            sentido,
            banda,
            _HUECO_ENTRE_RENGLONES * actual.alto,
            actual.alto,
            0.0,
            etiqueta.cx,
            {etiqueta.id, *(r.id for r in pila.renglones)},
        )
        if siguiente is None:
            break
        actual = siguiente[1]
        if actual.id not in libres:
            if actual.clase == "ajena":
                pila.tope = actual
            break
        pila.renglones.append(actual)
        banda = (min(banda[0], actual.x0), max(banda[1], actual.x1))
        borde = max(borde, actual.y1) if sentido > 0 else min(borde, actual.y0)
    return pila


def _elegir_lado(arriba: _Pila | None, abajo: _Pila | None) -> _Pila | None:
    """Una etiqueta tiene una pila: la del lado más pegado; si empatan, la de arriba."""
    if arriba is None or abajo is None:
        return arriba or abajo
    alto = min(arriba.renglones[0].alto, abajo.renglones[0].alto)
    if arriba.hueco <= abajo.hueco or _casi_igual(arriba.hueco, abajo.hueco, alto):
        return arriba
    return abajo


def _pilas(textos: list[_Texto], de_filas: set[str]) -> tuple[list[_Pila], dict[str, list[str]]]:
    """Las pilas de un grupo de textos con la misma dirección, ya sin renglones compartidos.

    Devuelve las pilas (con ``ganados``: sus renglones, de la etiqueta hacia afuera, hasta el
    primero que no ganó) y los renglones ambiguos con las marcas que los alcanzan."""
    etiquetas = [t for t in textos if t.clase == "etiqueta" and t.id not in de_filas]
    libres = {t.id for t in textos if t.clase == "linea" and t.id not in de_filas}
    estorban = [t for t in textos if t.clase not in ("nada", "linea") or t.id in de_filas]
    indice = _Indice([t for t in textos if t.id in libres] + estorban)

    pilas: list[_Pila] = []
    for etiqueta in etiquetas:
        pila = _elegir_lado(
            _pila(etiqueta, +1, indice, libres), _pila(etiqueta, -1, indice, libres)
        )
        if pila is not None:
            pilas.append(pila)

    reclamos: dict[str, list[_Pila]] = defaultdict(list)
    for pila in pilas:
        for renglon in pila.renglones:
            reclamos[renglon.id].append(pila)
    ganador: dict[str, _Pila | None] = {}
    ambiguos: dict[str, list[str]] = {}
    for renglon_id, quienes in reclamos.items():
        menor = min(p.hueco for p in quienes)
        alto = next(r.alto for r in quienes[0].renglones if r.id == renglon_id)
        pegadas = [p for p in quienes if _casi_igual(p.hueco, menor, alto)]
        marcas = sorted({p.etiqueta.marca or "" for p in pegadas})
        if len(marcas) > 1:
            ganador[renglon_id] = None
            ambiguos[renglon_id] = marcas
        else:
            # La misma marca dibujada dos veces encima de sí misma no es una ambigüedad.
            ganador[renglon_id] = min(pegadas, key=lambda p: (p.hueco, p.etiqueta.id))
    for pila in pilas:
        for renglon in pila.renglones:
            if ganador.get(renglon.id) is not pila:
                break
            pila.ganados.append(renglon)
    return pilas, ambiguos


# --------------------------------------------------------------------------------- asociar


def asociar(
    entities: list[NormalizedEntity], frames: list[SheetFrame], config: TextPatternConfig
) -> tuple[list[Asociacion], list[Rechazo]]:
    """De qué marca es cada texto de armado, hoja por hoja; y lo que no se pudo pegar.

    Las ``Asociacion`` van por pila (la etiqueta pegada a su columna de renglones) o por fila
    (un renglón de un cuadro con títulos); su ``etiqueta_id`` es una etiqueta de definición, no
    una colocación. Los ``Rechazo`` son los renglones ambiguos (dos marcas los alcanzan igual),
    los de otra familia que paraban una pila y todo texto con forma de armado que no es de nadie.
    Ver el docstring del módulo."""
    # Evita el ciclo: ``notas`` usa ``ancla_texto`` de aquí.
    from klave_engine.estructura.notas import leer_notas_con_renglones

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


def _asociar_hoja(
    grupo: list[NormalizedEntity],
    hoja: str,
    config: TextPatternConfig,
    de_notas: set[str],
    lineas: _Lineas,
) -> tuple[list[Asociacion], list[Rechazo]]:
    clases = {e.entity_id: _clase(e, config, de_notas) for e in grupo}
    por_giro: dict[int, list[_Texto]] = defaultdict(list)
    for e in grupo:
        giro = _giro(e)
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
        de_filas: set[str] = set()
        for etiqueta, marca, celdas in _filas_de_cuadros(locales, config):
            de_filas.add(etiqueta.id)
            de_filas.update(c.id for c in celdas)
            duenos += [c.e for c in celdas]
            if any(ARMADO_RE.search(c.texto) for c in celdas):
                asociaciones.append(
                    Asociacion(
                        etiqueta_id=etiqueta.id,
                        marca=marca,
                        hoja=hoja,
                        textos=[c.texto for c in celdas],
                        entidades=[c.id for c in celdas],
                        via="fila",
                    )
                )
        pilas, ambiguos = _pilas(locales, de_filas)
        por_id = {t.id: t for t in locales}
        for renglon_id, marcas in ambiguos.items():
            t = por_id[renglon_id]
            rechazados.add(renglon_id)
            rechazos.append(
                Rechazo(
                    entidad_id=renglon_id, texto=t.texto, hoja=hoja, motivo="ambigua", marcas=marcas
                )
            )
        topes: dict[str, set[str]] = defaultdict(set)
        for pila in pilas:
            if not pila.ganados:
                continue
            duenos += [r.e for r in pila.ganados]
            orden = pila.ganados[::-1] if pila.sentido > 0 else pila.ganados
            asociaciones.append(
                Asociacion(
                    etiqueta_id=pila.etiqueta.id,
                    marca=pila.etiqueta.marca or "",
                    hoja=hoja,
                    textos=[r.texto for r in orden],
                    entidades=[r.id for r in orden],
                    via="pila",
                )
            )
            if pila.tope is not None and len(pila.ganados) == len(pila.renglones):
                topes[pila.tope.id].add(pila.etiqueta.marca or "")
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
    """Los renglones de armado que nadie leyó. Un texto dibujado dos veces encima de sí mismo es
    del dueño de su copia."""
    de_alguien = {e.entity_id for e in duenos}
    copias: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for e in duenos:
        copias[(e.text or "").strip()].append(ancla_texto(e))
    huerfanos: list[Rechazo] = []
    for e in grupo:
        if clases[e.entity_id][0] not in ("linea", "llamada"):
            continue
        if e.entity_id in de_alguien or e.entity_id in rechazados:
            continue
        texto = (e.text or "").strip()
        x, y = ancla_texto(e)
        limite = _DUPLICADO * _alto(e)
        if any(math.hypot(x - cx, y - cy) <= limite for cx, cy in copias.get(texto, [])):
            continue
        huerfanos.append(
            Rechazo(entidad_id=e.entity_id, texto=texto, hoja=hoja, motivo="sin_dueno")
        )
    return huerfanos
