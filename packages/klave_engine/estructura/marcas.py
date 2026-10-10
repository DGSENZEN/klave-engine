"""Las marcas que nombra un texto: una sola gramática para todos los lectores (R67).

La usan la nota, las etiquetas de pila, las etiquetas de varias marcas, las filas de cuadro, la
clase de cada texto de la asociación y el bloqueo de la lectura IA. ``leer_marcas`` da una de:

- ``unica``: una marca sin ambigüedad. Va acotada a los dos lados por el principio o el fin, un
  espacio o «: ; , ( ) =» (un «.» final sólo antes de un espacio o del fin), y no hay otra marca
  fuera de las referencias («VER …», «IGUAL A …», «CORTE …»). «K-1.1», «K-15A», «T1-1», «K-1-A»,
  «D-X» y «K15A» son una sola marca. Es la única que se lee.
- ``varias``: una lista o un rango, con o sin espacios («K-1 Y K-2», «K-1 A K-4», «K-1 A 4»,
  «K-1-K-3», «K-1-A-K-3», «T-1+T-2»). No se lee: se reporta con las marcas y los rangos como se
  escribieron.
- ``ambigua``: una marca pegada a algo (una letra, una cifra, «#», «@», «-», «X»…): «T2-20X40»,
  «K-7E#3@20», «T1-4#3», «K-1-3». No se lee. Sus candidatas son cada prefijo que es una marca
  (T2 y T2-20; K-7 y K-7E; T1 y T1-4) y, si a la marca le sigue «-n» y nada más, el rango («K-1-3»
  → K-1 A K-3).
- ``ninguna``.

Una cuenta de varillas no es una marca (R68.2): lo que el parser del armado toma como un grupo
de varillas («P 4#3», «K 7 #3») y lo escrito con la palabra de la varilla delante («V4 #4», «V12
#5») se quita antes de buscar marcas (``sin_cuentas_de_varillas``); «K 7 E#3@1S» sí es K-7 y
«V-1 4#4» es V-1. Una marca escrita con espacios puede llevar delante cualquier cosa que no sea
una letra («3.-K 7», «"K 7"», «TRABE-T 1»: R68.3). Cualquier letra empieza una marca pegada,
también las de las etiquetas de la configuración («TL-1E#3@20» → TL-1, TL-1E: R68.4). La E o la
G de una cabeza de estribo antes de «#» no es la letra de una variante («K-7-E #3@20» y «K-7E
#3@20» son ambiguas entre K-7 y la marca con la letra: R68.5). «K-1, 2 Y 3» son K-1, K-2 y K-3
(R68.6). Los guiones de Unicode son guiones («K–7» es K-7: R68.7). En un texto con armado, la
palabra de un título o de una referencia («CORTE», «DET.», «DETALLE», «SECCIÓN», «VER») nombra
todas las marcas que le siguen y el texto no se lee (``titulo``, R97): «CORTE K-1 Y K-2 E#3@1S» es
de K-1 y de K-2; sin armado («VER CORTE C-2») no nombra a nadie.

Las etiquetas de la configuración (``column_tag``, ``beam_tag``) se escriben como el plano
(«K15A», «T1-1»); las demás marcas como ``K-15A.1``: la misma llave en todos los lectores.

Esta gramática decide qué se lee. El bloqueo de la IA no depende sólo de ella: un respaldo
(``detection.schedules``, R68.1) busca cada marca conocida en cada texto con armado, con una
comparación suelta, y bloquea lo que la gramática no alcanzó."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal

from klave_engine.detection.text_patterns import (
    FOOTING_MARK_PATTERN,
    PILE_MARK_PATTERN,
    TextPatternConfig,
)
from klave_engine.estructura._armado_texto import CONSUMIDO
from klave_engine.estructura.armado import sin_armado, tiene_armado

_PREFIJOS = "K|C|T|COL|CT|CTA|TB|ZC|ZCM|Z|D|P|MC|CE|CR"

# Los guiones con que se escribe una marca: el ASCII y los de Unicode («K–7», «K‑7», «K—7»,
# R68.7). Dentro de una marca todos son «-».
GUIONES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_G = f"[{re.escape(GUIONES)}]"
_A_GUION = str.maketrans({g: "-" for g in GUIONES})


def con_guion(texto: str) -> str:
    """``texto`` con cada guion de Unicode escrito «-»."""
    return texto.translate(_A_GUION)


# Una marca dentro de un texto: K-1, C-3, T-2, COL-1, CTA-3, Z-1, D-4B, P-4, MC-1, CE-1, CR-2, con
# su sufijo de variante (``K-15A.1`` es otra marca que ``K-15A``), o el tipo «X» (``K-X``, ``D-X``).
MARCA_RE = re.compile(rf"\b({_PREFIJOS})(?:\s*{_G}?\s*(\d{{1,2}})([A-Z]?)(?:\.(\d))?|{_G}(X))\b")
# Una ficha que es toda una marca, sin espacios.
_COMPACTA = re.compile(rf"({_PREFIJOS})(?:{_G}?(\d{{1,2}})([A-Z]?)(?:\.(\d))?|{_G}(X))")
# «K-1-A»: la letra de la variante tras un guion. No una letra que empieza otra marca («P-5-P»,
# «T-1-T», «C-1-P»: lo que sigue puede ser otra marca a medias) ni la X del tipo.
_CON_LETRA = re.compile(rf"({_PREFIJOS}){_G}?(\d{{1,2}}){_G}([ABE-JL-OQ-SU-WY])")
# Una marca escrita con espacios («K 7», «T - 1», «K- 7»). Delante, cualquier cosa que no sea
# una letra («3.-K 7», «"K 7"», «TRABE-T 1», «K-1/K 7», R68.3); detrás, el fin, un espacio, «:
# ; , ( ) = "», lo que une una lista («/ + &») o un «.» final. Sus cifras no van pegadas a «#»
# (eso es una cuenta de varillas, «P 4#3»; las cuentas ya no están: ``sin_cuentas_de_varillas``).
_ESPACIADA = re.compile(
    rf"(?<![A-Z])({_PREFIJOS})(?:\s+{_G}?\s*|\s*{_G}\s+)(\d{{1,2}})([A-Z]?)"
    r'(?=$|[\s:;,()="/+&]|\.(?:\s|$))'
)
# Una etiqueta de la configuración escrita con espacios («TL 1», «V 1», «TE A», R79): sus letras,
# un espacio o un guion, y su número o su letra suelta. Sólo cuenta si escrita con guion es una
# etiqueta de la configuración.
_ETIQUETA_ESPACIADA = re.compile(
    rf"(?<![A-Z])([A-Z]{{1,4}})(?:\s+{_G}?\s*|\s*{_G}\s+)(\d{{1,3}}[A-Z]?|[A-Z])"
    r'(?=$|[\s:;,()="/+&]|\.(?:\s|$))'
)
# Una letra suelta tras una marca («K-15 A 4#3», R78): puede ser su sufijo (K-15A) o no.
_LETRA_SUELTA = re.compile(r"\s+([A-Z])(?=$|[\s:;,()=\"])")
# Lo que sigue a esa letra y la hace un conector («K-1 A K-4», «K-1 A 4», «K-1 Y K-2»).
# El número que cierra un rango o sigue una lista («K-1 A 4», «K-1, 2 Y 3», R85, R91): un entero
# (con la letra de su variante, nunca la M de los metros) al que le sigue el fin, una puntuación,
# un conector u otra pieza con cifras (armado, ya enmascarado por el parser, o una sección);
# nunca una palabra («8 PZAS», «4 VARS», «20 CM», «40 CENTIMETROS», «3 ML») ni un decimal.
_NUMERO_DE_MARCA = (
    r"(\d{1,2}(?:[A-LN-Z](?![A-Z]))?)"
    r"(?=\s*$|\s*[:;()=&+/]|\s*,(?!\d)|\.(?:\s|$)|\s+(?:Y|E|A|AL|HASTA)\b"
    rf"|\s*{_G}|\s+[^\sA-Z]*\d|\s*{CONSUMIDO})"
)
_TRAS_CONECTOR = re.compile(rf"\s+(?:{_NUMERO_DE_MARCA}|[A-Z]{{1,5}}\s*{_G}?\s*\d)")
# Una palabra de varilla delante del número («V-4 #4»: ¿la marca V-4 o 4 varillas del #4?, R80).
_PALABRA_DE_VARILLA = re.compile(r"(?:VARS?|V)\W")
# Donde empieza algo con forma de marca dentro de una ficha: letras que no van pegadas a otra
# letra o cifra y a las que les sigue un guion o una cifra. Cualquier letra: también las
# etiquetas de la configuración («TL-1E#3@20», «V-1E#3@20», R68.4).
_INICIO_DE_MARCA = re.compile(rf"(?<![A-Z0-9])[A-Z]+(?={_G}|\d)")
# Lo que acota una ficha.
_ACOTA = re.compile(r'[:;,()="]')
# Lo que une las marcas de una ficha: un guion (rango) o «+», «&», «/» (lista).
_UNE_EN_FICHA = GUIONES + "+&/"
_GUION = GUIONES

# Entre las marcas de una lista o un rango escrito con espacios.
ENTRE_MARCAS = re.compile(rf"(?:\s|[,;/=&+]|{_G}|\b(?:Y|E|A|AL|HASTA)\b)*")
CONECTOR_DE_RANGO = re.compile(rf"\b(?:AL|A|HASTA)\b|{_G}")
_ABRE_RANGO = re.compile(r"(?:DE|DEL|DESDE)\s+$")
# El fin de un rango escrito sólo con su número («K-1 A 4»), tras un conector entre espacios.
_FIN_DE_RANGO = re.compile(rf"\s+(?:AL|A|HASTA|{_G})\s+{_NUMERO_DE_MARCA}")
# Lo que sigue a una marca en una lista escrita sólo con números («K-1, 2 Y 3», «T1-1 Y 2»,
# R68.6): cada número es otra marca, la primera con su último número cambiado.
_SIGUE_LISTA = re.compile(rf"(?:\s*[,&+]\s*|\s+Y\s+){_NUMERO_DE_MARCA}")
_RANGO_CON_ESPACIOS = re.compile(rf"\S (?:AL|A|HASTA|{_G}) \S")
# Una marca partida en lo de antes de su último número, el número y lo de después.
_PARTES = re.compile(rf"(?P<pre>(?:.*\D)?)(?P<num>\d{{1,3}})(?P<suf>{_G}?[A-Z]?)")
# La letra de una cabeza de estribo o de grapa: tras una marca y antes de «#» no es la letra de
# una variante («K-7-E #3@20», «K-7E #3@20», R68.5).
_CABEZA_DE_ESTRIBO = "EG"

# Lo que remite a otra parte del plano no nombra una marca («VER CORTE C-2»), salvo en un texto
# con armado, donde la palabra de un título o de una referencia nombra su marca (R97).
_REFERENCIA = re.compile(
    r"\b(?:VER|V[EÉ]ASE|SEG[UÚ]N|IGUAL\s+A)\b\.?(?:\s+(?:EL|LA|LOS|LAS))?"
    r"(?:\s+(?:CORTE|DETALLE|DET\.?|SECCI[OÓ]N|PLANO|NOTA|CUADRO)\b\.?)?\s*[^\s,;]*"
    r"|\b(?:CORTE|DETALLE|DET\.)\s+[^\s,;]+",
    re.I,
)
# El título de un dibujo que nombra su marca («CORTE K-1 15X20 4#3», «DET. K-1 4#3»): una
# referencia, no se lee, pero dice de quién es.
_TITULO = re.compile(r"\b(?:CORTE|DETALLE|DET\.)\s+([^\s,;]+)", re.I)
# R97: la palabra de un título o de una referencia («CORTE», «DET.», «DETALLE», «SECCIÓN», «VER»,
# «VER CORTE», «VER EL DETALLE»). En un texto con armado, las marcas que le siguen son todas
# suyas: «CORTE K-1 Y K-2 E#3@1S» nombra K-1 y K-2, y no se lee.
_PALABRA_DE_TITULO = re.compile(
    r"(?<![A-Z])(?:VER(?:\s+(?:EL|LA|LOS|LAS))?"
    r"(?:\s+(?:CORTES?|DETALLES?|DET\.?|SECCI[OÓ]N(?:ES)?)(?![A-Z]))?"
    r"|CORTES?|DETALLES?|DET\.?|SECCI[OÓ]N(?:ES)?)(?![A-Z])\.?",
    re.I,
)
_FICHA_SIGUIENTE = re.compile(r'\s*([^\s,;:()="]+)')
# Algo de armado escrito con «#» o «@» (como ``asociacion.ARMADO_RE``).
_CON_GATO = re.compile(r"[#Ø]\s*\d|@\s*\d")


def sin_referencias(texto: str) -> str:
    """El texto sin lo que remite a otra parte del plano («VER CORTE C-2», «SEGÚN DETALLE K-1»):
    la marca de una referencia no es la de quien lo dice."""
    return _REFERENCIA.sub(" ", texto)


@lru_cache(maxsize=64)
def _patrones(columnas: tuple[str, ...], trabes: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    # R94: las marcas que ponen los detectores, todas: columnas y trabes de la configuración, y
    # las zapatas y los pilotes de los detectores de cimentación (ZA-3, Z-100A, ZCM-100, P-4).
    return tuple(
        re.compile(p) for p in (*columnas, *trabes, FOOTING_MARK_PATTERN, PILE_MARK_PATTERN)
    )


def es_etiqueta(texto: str, config: TextPatternConfig) -> bool:
    """Si ``texto`` entero es una marca que un detector puede poner: una etiqueta de columna o de
    trabe de la configuración, o la marca de una zapata o de un pilote (R94; como
    ``match_category``: sus patrones anclados, sobre el texto sin espacios a los lados)."""
    limpio = texto.strip()
    patrones = _patrones(tuple(config.column_tag), tuple(config.beam_tag))
    return any(p.match(limpio) for p in patrones)


def escrita(m: re.Match[str]) -> str:
    """Una marca de ``MARCA_RE`` o de ``_COMPACTA`` escrita ``K-15A.1`` (o ``D-X``)."""
    if m.group(5):
        return f"{m.group(1)}-X"
    variante = f".{m.group(4)}" if m.group(4) else ""
    return f"{m.group(1)}-{int(m.group(2))}{m.group(3)}{variante}"


def marca_sola(ficha: str, config: TextPatternConfig) -> str | None:
    """La marca si ``ficha`` (sin espacios) es toda una marca: una etiqueta de la configuración
    tal cual («K15A», «T1-1»), una marca escrita ``K-15A.1`` o una con su letra tras un guion
    («K-1-A»); si no, ``None``."""
    if not ficha:
        return None
    ficha = con_guion(ficha)
    if es_etiqueta(ficha, config):
        return ficha
    compacta = _COMPACTA.fullmatch(ficha)
    if compacta is not None:
        return escrita(compacta)
    con_letra = _CON_LETRA.fullmatch(ficha)
    if con_letra is not None:
        return f"{con_letra.group(1)}-{int(con_letra.group(2))}-{con_letra.group(3)}"
    return None


def marca_normalizada(texto: str, config: TextPatternConfig) -> str | None:
    """La forma única de ``texto`` si es una sola marca, escrita como sea: en mayúsculas, sin
    espacios, con «-» por cualquier guion, las letras de su prefijo, «-» y lo demás tal cual
    («K15A.1», «k-15a.1», «K 15A.1» → K-15A.1; «C 1» → C-1; «K1» → K-1; «TL1» → TL-1; «K1-A» →
    K-1-A). Sólo junta maneras de escribir la misma marca: «K-1», «K-1A», «K-15A», «K-15A.1» y
    «K-1-A» son marcas distintas, «T1-1» no es «T-11» y los ceros de su número se dejan como se
    escribieron (K-07 es K-07). ``None`` si no es una marca."""
    ficha = con_guion("".join(texto.upper().split()))
    compacta = _COMPACTA.fullmatch(ficha)
    if compacta is not None:
        if compacta.group(5):
            return f"{compacta.group(1)}-X"
        variante = f".{compacta.group(4)}" if compacta.group(4) else ""
        return f"{compacta.group(1)}-{compacta.group(2)}{compacta.group(3)}{variante}"
    con_letra = _CON_LETRA.fullmatch(ficha)
    if con_letra is not None:
        return f"{con_letra.group(1)}-{con_letra.group(2)}-{con_letra.group(3)}"
    if es_etiqueta(ficha, config):
        # Una etiqueta de la configuración que ya lleva su guion queda como está («T1-1», «TE-A»);
        # si no, el guion va tras las letras de su prefijo («TL1» → TL-1).
        prefijo = re.match(r"[A-Z]+", ficha)
        if "-" in ficha or prefijo is None or prefijo.end() == len(ficha):
            return ficha
        return f"{ficha[: prefijo.end()]}-{ficha[prefijo.end() :]}"
    return None


@dataclass
class LecturaDeMarcas:
    """Lo que la gramática lee de un texto (ver el docstring del módulo)."""

    tipo: Literal["ninguna", "unica", "varias", "ambigua"]
    marca: str | None = None  # la de «unica»
    # «unica»: [la marca]; «varias»: las marcas y los rangos como se escribieron; «ambigua»: todas
    # las candidatas (las marcas limpias del texto, sus rangos y cada prefijo de las pegadas).
    piezas: list[str] = field(default_factory=list)
    pegadas: list[str] = field(default_factory=list)  # las fichas pegadas, tal cual
    solo_marcas: bool = False  # fuera de las marcas, el texto sólo trae separadores
    # R97: las marcas las nombra el título de un corte o una referencia en un texto con armado
    # («CORTE K-1 15X20 4#3», «E#2@15 VER CORTE C-2»): son suyas, pero el texto no se lee.
    titulo: bool = False

    @property
    def nombra(self) -> bool:
        return self.tipo != "ninguna"


@dataclass
class _Pieza:
    inicio: int
    fin: int
    tipo: Literal["marca", "numero", "varias", "ambigua"]
    marca: str | None = None
    piezas: list[str] = field(default_factory=list)
    texto: str = ""


def _fichas(limpio: str) -> list[tuple[int, int, str]]:
    """Las fichas del texto: lo que va entre espacios o «: ; , ( ) =», sin el «.» final de lo que
    acaba en un espacio o en el fin."""
    fichas: list[tuple[int, int, str]] = []
    for palabra in re.finditer(r"\S+", limpio):
        inicio, fin = palabra.start(), palabra.end()
        if fin - inicio > 1 and limpio[fin - 1] == ".":
            fin -= 1
        pos = inicio
        for corte in [*_ACOTA.finditer(limpio, inicio, fin), None]:
            hasta = corte.start() if corte is not None else fin
            if hasta > pos:
                fichas.append((pos, hasta, limpio[pos:hasta]))
            if corte is not None:
                pos = corte.end()
    return fichas


def _segmentar(ficha: str, config: TextPatternConfig) -> list[tuple[str, str]] | None:
    """La ficha como dos o más marcas unidas por un guion, «+», «&» o «/» («K-1-K-3»,
    «K-1-A-K-3», «T1-1-T1-3», «T-1+T-2»): [(marca, lo que la une con la anterior)], o ``None``.
    Primero la marca más larga a la izquierda."""

    def desde(resto: str, junta: str) -> list[tuple[str, str]] | None:
        entera = marca_sola(resto, config)
        if entera is not None:
            return [(entera, junta)]
        for i in range(len(resto) - 1, 0, -1):
            if resto[i] not in _UNE_EN_FICHA:
                continue
            izquierda = marca_sola(resto[:i], config)
            if izquierda is None:
                continue
            derecha = desde(resto[i + 1 :], resto[i])
            if derecha is not None:
                return [(izquierda, junta), *derecha]
        return None

    partes = desde(ficha, "")
    return partes if partes is not None and len(partes) >= 2 else None


def _con_ultimo_numero(marca: str, numero: str) -> str:
    """``marca`` con su último número cambiado por ``numero`` («T1-1», «3» → «T1-3»)."""
    partes = _PARTES.fullmatch(marca)
    if partes is None:
        return marca
    return f"{partes['pre']}{numero}"


def _prefijos(ficha: str, inicio: int, config: TextPatternConfig) -> list[str]:
    """Cada prefijo de ``ficha`` desde ``inicio`` que es una marca y no deja cortado un número
    (lo que le sigue no es una cifra ni «.cifra»)."""
    candidatas: list[str] = []
    for fin in range(inicio + 1, len(ficha) + 1):
        sigue = ficha[fin : fin + 2]
        if sigue[:1].isdigit() or (sigue[:1] == "." and sigue[1:2].isdigit()):
            continue
        marca = marca_sola(ficha[inicio:fin], config)
        if marca is not None:
            candidatas.append(marca)
    return candidatas


def _cabeza_tras(ficha: str, despues: str, config: TextPatternConfig) -> str | None:
    """Si ``ficha`` es una marca que acaba en la letra de una cabeza de estribo o de grapa, con o
    sin guion, y lo que sigue empieza con «#» («K-7-E #3@20», «K-7E #3@20», R68.5): la marca sin
    esa letra (K-7). No se sabe si es la marca K-7-E o K-7 con sus estribos. Si no, ``None``."""
    if ficha[-1:] not in _CABEZA_DE_ESTRIBO or re.match(r"\s*[#Ø]", despues) is None:
        return None
    base = con_guion(ficha[:-1]).rstrip("-")
    if not base[-1:].isdigit():
        return None
    return marca_sola(base, config)


def _leer_ficha(
    ficha: str, inicio: int, config: TextPatternConfig, despues: str = ""
) -> list[_Pieza]:
    fin = inicio + len(ficha)
    sola = marca_sola(ficha, config)
    if sola is not None:
        base = _cabeza_tras(ficha, despues, config)
        if base is not None:
            return [_Pieza(inicio, fin, "ambigua", piezas=[base, sola], texto=ficha)]
        if _PALABRA_DE_VARILLA.match(con_guion(ficha)) and re.match(r"\s*[#Ø]\s*\d", despues):
            # «V-4 #4»: la marca V-4 o una cuenta de varillas (R80).
            return [_Pieza(inicio, fin, "ambigua", piezas=[sola], texto=ficha)]
        return [_Pieza(inicio, fin, "marca", marca=sola, texto=ficha)]
    partes = _segmentar(ficha, config)
    if partes is not None:
        # Lo unido por guiones es un rango, como se escribió; lo unido por «+», «&», «/», marcas.
        piezas: list[str] = []
        grupo: list[str] = []
        for marca, junta in partes:
            if junta and junta in _GUION:
                grupo.append(junta + marca)
                continue
            if grupo:
                piezas.append("".join(grupo))
            grupo = [marca]
        piezas.append("".join(grupo))
        return [_Pieza(inicio, fin, "varias", piezas=piezas, texto=ficha)]
    candidatas: list[str] = []
    for m in _INICIO_DE_MARCA.finditer(ficha):
        candidatas += _prefijos(ficha, m.start(), config)
    rango = re.fullmatch(rf"(.+){_G}(\d{{1,2}})", ficha)
    if rango is not None:
        primera = marca_sola(rango.group(1), config)
        if primera is not None:
            candidatas.append(f"{primera} A {_con_ultimo_numero(primera, rango.group(2))}")
    if not candidatas:
        return []
    return [_Pieza(inicio, fin, "ambigua", piezas=list(dict.fromkeys(candidatas)), texto=ficha)]


def _acaba_en_marca(texto: str, config: TextPatternConfig) -> bool:
    """Si la última ficha de ``texto`` es una marca o varias unidas («K-1», «K-1-K-3»)."""
    previa = re.split(r'[\s:;,()="]', texto)[-1]
    return bool(previa) and (
        marca_sola(previa, config) is not None or _segmentar(previa, config) is not None
    )


def _con_espaciadas(limpio: str, config: TextPatternConfig) -> str:
    """Cada marca escrita con espacios («K 7», «T - 1»; y una etiqueta de la configuración, «TL
    1», «V 1», «TE A», R79) escrita «K-7». Si la pega a lo de
    delante algo que no es un espacio ni acota una ficha («3.-K 7», «TRABE-T 1»), se aparta con
    un espacio: es su propia ficha. No si lo de delante es otra marca unida por un guion, «/»,
    «+» o «&» («K-1/K 7», «K-1-K 3»): es una lista o un rango."""

    def juntar(
        texto: str, patron: re.Pattern[str], marca_de: Callable[[re.Match[str]], str | None]
    ) -> str:
        partes: list[str] = []
        pos = 0
        for m in patron.finditer(texto):
            marca = marca_de(m)
            if marca is None:
                continue
            partes.append(texto[pos : m.start()])
            hecho = "".join(partes)
            previo = hecho[-1:]
            une = previo in _UNE_EN_FICHA and _acaba_en_marca(hecho[:-1], config)
            if previo and not previo.isspace() and not _ACOTA.match(previo) and not une:
                marca = " " + marca
            partes.append(marca)
            pos = m.end()
        partes.append(texto[pos:])
        return "".join(partes)

    def etiqueta(m: re.Match[str]) -> str | None:
        escrita = f"{m.group(1)}-{m.group(2)}"
        return escrita if es_etiqueta(escrita, config) else None

    limpio = juntar(limpio, _ESPACIADA, lambda m: f"{m.group(1)}-{int(m.group(2))}{m.group(3)}")
    return juntar(limpio, _ETIQUETA_ESPACIADA, etiqueta)


def titulos(texto: str, config: TextPatternConfig) -> list[str]:
    """Las marcas que nombra un texto sólo en el título de un dibujo («CORTE K-1 15X20 4#3», «DET.
    K-1 4#3», R68.8): es una referencia y no se lee, pero dice de quién es. Una referencia que
    remite a otra parte («VER CORTE C-2») no es un título."""
    marcas: list[str] = []
    for m in _REFERENCIA.finditer(texto.upper()):
        titulo = _TITULO.fullmatch(m.group(0))
        if titulo is not None:
            marca = marca_sola(titulo.group(1).rstrip("."), config)
            if marca is not None:
                marcas.append(marca)
    return list(dict.fromkeys(marcas))


_LEIDAS: dict[tuple[str, tuple[str, ...], tuple[str, ...]], LecturaDeMarcas] = {}


def leer_marcas(texto: str, config: TextPatternConfig) -> LecturaDeMarcas:
    """Las marcas que nombra ``texto``, según la gramática del módulo. Un plano repite sus textos
    miles de veces: la lectura de cada uno se guarda (y se entrega como copia)."""
    clave = (texto, tuple(config.column_tag), tuple(config.beam_tag))
    leida = _LEIDAS.get(clave)
    if leida is None:
        if len(_LEIDAS) > 200_000:
            _LEIDAS.clear()
        leida = _leer_marcas(texto, config)
        _LEIDAS[clave] = leida
    return replace(leida, piezas=list(leida.piezas), pegadas=list(leida.pegadas))


def _palabras_de_titulo(texto: str, config: TextPatternConfig) -> list[tuple[int, int]]:
    """Dónde va cada palabra de título o de referencia (``_PALABRA_DE_TITULO``) a la que le sigue
    una marca: una sola, varias unidas («K-1-K-3») o una escrita con espacios («CORTE K 1»)."""
    tramos: list[tuple[int, int]] = []
    for m in _PALABRA_DE_TITULO.finditer(texto):
        siguiente = _FICHA_SIGUIENTE.match(texto, m.end())
        if siguiente is None:
            continue
        ficha = con_guion(siguiente.group(1).upper()).rstrip(".")
        resto = texto[m.end() :].lstrip().upper()
        espaciada = _ESPACIADA.match(resto)
        etiqueta = _ETIQUETA_ESPACIADA.match(resto)
        if (
            marca_sola(ficha, config) is not None
            or _segmentar(ficha, config) is not None
            or espaciada is not None
            or (etiqueta is not None and es_etiqueta(f"{etiqueta[1]}-{etiqueta[2]}", config))
        ):
            tramos.append(m.span())
    return tramos


def _leer_marcas(texto: str, config: TextPatternConfig) -> LecturaDeMarcas:
    # R97: en un texto con armado, la palabra de un título o de una referencia seguida de marcas
    # no las quita: se quita sólo la palabra, y las marcas que le siguen se nombran todas (una:
    # «unica»; varias: «varias»), con ``titulo``: no se lee. Sin armado («VER CORTE C-2») es una
    # referencia que no nombra a nadie.
    tramos = _palabras_de_titulo(texto, config) if _PALABRA_DE_TITULO.search(texto) else []
    if tramos and (_CON_GATO.search(texto) or tiene_armado(texto)):
        letras = list(texto)
        for a, b in tramos:
            letras[a:b] = " " * (b - a)
        lectura = _leer_sin_titulos("".join(letras), config)
        if lectura.nombra:
            return replace(lectura, titulo=True)
    return _leer_sin_titulos(texto, config)


def _leer_sin_titulos(texto: str, config: TextPatternConfig) -> LecturaDeMarcas:
    # Las cuentas de varillas no son marcas («V4 #4», «P 4#3»: R68.2): se quitan primero, con lo
    # que el parser del armado toma como un grupo de varillas.
    limpio = _con_espaciadas(sin_armado(sin_referencias(texto)), config)
    piezas: list[_Pieza] = []
    for inicio, fin, ficha in _fichas(limpio):
        piezas += _leer_ficha(ficha, inicio, config, limpio[fin:])
    # Una letra suelta tras una marca limpia («K-15 A 4#3», R78): ¿su sufijo (K-15A, K-15-A) o
    # no? No se sabe: ambigua. No si es la cabeza de unos estribos («K-8 E #3@20») o el conector
    # de un rango o una lista («K-1 A K-4», «K-1 A 4», «K-1 Y K-2»).
    for i, p in enumerate(piezas):
        letra = _LETRA_SUELTA.match(limpio, p.fin) if p.tipo == "marca" else None
        if letra is None or p.marca is None:
            continue
        despues = limpio[letra.end() :]
        if letra.group(1) in _CABEZA_DE_ESTRIBO and re.match(r"\s*[#Ø]", despues):
            continue
        if _TRAS_CONECTOR.match(despues):
            continue
        sufijos = [marca_sola(p.texto + letra.group(1), config)]
        sufijos.append(marca_sola(f"{con_guion(p.texto)}-{letra.group(1)}", config))
        candidatas = [p.marca, *(c for c in sufijos if c is not None)]
        piezas[i] = _Pieza(
            p.inicio,
            letra.end(),
            "ambigua",
            piezas=list(dict.fromkeys(candidatas)),
            texto=f"{p.texto} {letra.group(1)}",
        )
    # Una lista escrita sólo con números tras una marca limpia («K-1, 2 Y 3»): otras marcas.
    for p in [p for p in piezas if p.tipo == "marca"]:
        base, pos = p.marca or "", p.fin
        while (sigue := _SIGUE_LISTA.match(limpio, pos)) is not None and not any(
            q.inicio < sigue.end(1) and sigue.start(1) < q.fin for q in piezas
        ):
            marca = _con_ultimo_numero(base, sigue.group(1))
            piezas.append(_Pieza(sigue.start(1), sigue.end(1), "marca", marca=marca, texto=marca))
            pos = sigue.end(1)
    # El número que cierra un rango escrito sin su letra («K-1 A 4»), tras una marca limpia.
    for p in [p for p in piezas if p.tipo == "marca"]:
        numero = _FIN_DE_RANGO.match(limpio, p.fin)
        if numero is not None and not any(
            q.inicio < numero.end(1) and numero.start(1) < q.fin for q in piezas
        ):
            piezas.append(_Pieza(numero.start(1), numero.end(1), "numero", texto=numero.group(1)))
    piezas.sort(key=lambda p: p.inicio)
    if not piezas:
        return LecturaDeMarcas("ninguna")

    # Las marcas limpias unidas por un conector de rango van juntas: el rango, como se escribió.
    nombradas: list[str] = []
    grupo: list[_Pieza] = []

    def cerrar() -> None:
        if not grupo:
            return
        if len(grupo) == 1:
            if grupo[0].tipo == "marca" and grupo[0].marca is not None:
                nombradas.append(grupo[0].marca)
        else:
            a = grupo[0].inicio
            abre = _ABRE_RANGO.search(limpio, 0, a)
            nombradas.append(limpio[abre.start() if abre else a : grupo[-1].fin])
        grupo.clear()

    for p in piezas:
        if p.tipo in ("marca", "numero"):
            if grupo:
                entre = limpio[grupo[-1].fin : p.inicio]
                if not (ENTRE_MARCAS.fullmatch(entre) and CONECTOR_DE_RANGO.search(entre)):
                    cerrar()
            if p.tipo == "marca" or grupo:
                grupo.append(p)
        else:
            cerrar()
            if p.tipo == "varias":
                nombradas += p.piezas
    cerrar()

    huecos = [limpio[a.fin : b.inicio] for a, b in zip(piezas, piezas[1:], strict=False)]
    antes, despues = limpio[: piezas[0].inicio], limpio[piezas[-1].fin :].strip(".")
    solo_marcas = all(ENTRE_MARCAS.fullmatch(h) for h in [*huecos, despues]) and (
        ENTRE_MARCAS.fullmatch(antes) is not None
        or re.fullmatch(r"(?:DE|DEL|DESDE)\s+", antes) is not None
    )
    nombradas = list(dict.fromkeys(nombradas))
    ambiguas = [p for p in piezas if p.tipo == "ambigua"]
    if ambiguas:
        candidatas = list(dict.fromkeys(nombradas + [c for p in ambiguas for c in p.piezas]))
        return LecturaDeMarcas(
            "ambigua",
            piezas=candidatas,
            pegadas=[p.texto for p in ambiguas],
            solo_marcas=solo_marcas,
        )
    if not nombradas:
        return LecturaDeMarcas("ninguna")
    sola = [p for p in piezas if p.tipo == "marca"]
    if len(nombradas) == 1 and sola and nombradas[0] == sola[0].marca:
        return LecturaDeMarcas(
            "unica", marca=nombradas[0], piezas=nombradas, solo_marcas=solo_marcas
        )
    return LecturaDeMarcas("varias", piezas=nombradas, solo_marcas=solo_marcas)


def forma_de_marca(texto: str, config: TextPatternConfig) -> str:
    """Una marca en su forma única (``marca_normalizada``), o lo escrito en mayúsculas y con «-»
    por cualquier guion si no es una marca: para comparar una ficha con lo que nombra un texto."""
    return marca_normalizada(texto, config) or con_guion(texto.upper())


def marcas_de_ficha(ficha: str, config: TextPatternConfig) -> list[str]:
    """Las marcas, en su forma única, que forman una ficha sin espacios: varias unidas por un
    guion, «+», «&» o «/» («K-1-K-3», «T-1+T-2»); vacía si no es eso. Sólo para comparar con lo
    que nombra el texto entero (``marcas_nombradas``)."""
    partes = _segmentar(con_guion(ficha), config)
    return [forma_de_marca(m, config) for m, _ in partes] if partes else []


def marcas_nombradas(texto: str, config: TextPatternConfig) -> set[str]:
    """Las marcas que la gramática nombra en ``texto`` entero, en su forma única
    (``forma_de_marca``): la de una «unica»; cada marca y cada extremo de rango de «varias»; cada
    candidata de «ambigua»; las de sus títulos («CORTE K-1») y las de sus referencias («VER CORTE
    C-2»). Un pedazo del texto se compara con esto, nunca se lee aparte (R96): en «T-1 30X60
    E#3@15 LS V 3» la gramática nombra sólo T-1, y «V 3» son tres varillas."""
    lectura = leer_marcas(texto, config)
    nombres: list[str] = []
    for pieza in lectura.piezas:
        nombres += extremos_de_rango(pieza, config) if es_rango(pieza, config) else [pieza]
    nombres += titulos(texto, config)
    for m in _REFERENCIA.finditer(texto.upper()):
        partes = m.group(0).split()
        destino = marca_sola(con_guion(partes[-1]).rstrip(".:"), config) if partes else None
        if destino is not None:
            nombres.append(destino)
    return {forma_de_marca(n, config) for n in nombres}


# ------------------------------------------------------------------------------- rangos


def extremos_de_rango(rango: str, config: TextPatternConfig | None = None) -> list[str]:
    """Los extremos de un rango escrito, con o sin espacios: «K-1 A K-4» → [K-1, K-4]; un fin
    escrito sólo con su número cambia el último número de la primera («K-1 A 4» → K-4, «T1-1 A
    3» → T1-3); «K-1 A C-4» → [K-1, C-4]. Vacía si no es un rango. Con la configuración del
    proyecto (sus etiquetas, «T1-1»); sin ella, la de siempre."""
    config = config or TextPatternConfig()
    limpio = _con_espaciadas(" ".join(rango.upper().split()), config)
    marcas: list[str] = []
    fin: str | None = None
    pegado = False
    for _inicio, hasta, ficha in _fichas(limpio):
        sola = marca_sola(ficha, config)
        if sola is not None:
            marcas.append(sola)
            numero = _FIN_DE_RANGO.match(limpio, hasta)
            if numero is not None and len(marcas) == 1:
                fin = numero.group(1)
            continue
        partes = _segmentar(ficha, config)
        if partes is not None and all(junta in _GUION for _m, junta in partes[1:]):
            marcas += [m for m, _j in partes]
            pegado = True
    if not marcas:
        return []
    if not pegado and not _RANGO_CON_ESPACIOS.search(limpio):
        return []
    if len(marcas) > 1:
        return list(dict.fromkeys([marcas[0], marcas[-1]]))
    if fin is not None:
        return list(dict.fromkeys([marcas[0], _con_ultimo_numero(marcas[0], fin)]))
    return []


def es_rango(pieza: str, config: TextPatternConfig | None = None) -> bool:
    return bool(extremos_de_rango(pieza, config))


def _partes(marca: str) -> tuple[str, int] | None:
    """Lo de antes del último número (sin guiones, espacios ni puntos) y ese número: «T1-1» →
    («T1», 1), «K-2A» → («K», 2), «K-1-A» → («K», 1)."""
    partes = _PARTES.fullmatch(" ".join(marca.upper().split()))
    if partes is None or not partes["pre"]:
        return None
    return re.sub(rf"[\s{re.escape(GUIONES)}.]", "", partes["pre"]), int(partes["num"])


def marca_en_rango(rango: str, marca: str, config: TextPatternConfig | None = None) -> bool:
    """Si ``marca`` cabe en un rango escrito: es uno de sus extremos o comparte con el primero lo
    de antes de su último número y ese número cae entre los de los extremos («K-1 A K-4» → K-2,
    K-2A, K-4A; «T1-1 A T1-3» → T1-2). Entre marcas de letras distintas, sólo los extremos. Sirve
    para no dejar que otra lectura cubra lo que el plano dice para todo el rango; nunca para
    leerlo."""
    extremos = extremos_de_rango(rango, config)
    if not extremos:
        return False
    propia = con_guion(" ".join(marca.upper().split()))
    if propia in extremos:
        return True
    desde, hasta, cual = _partes(extremos[0]), _partes(extremos[-1]), _partes(propia)
    if desde is None or hasta is None or cual is None or desde[0] != hasta[0]:
        return False
    return cual[0] == desde[0] and min(desde[1], hasta[1]) <= cual[1] <= max(desde[1], hasta[1])
