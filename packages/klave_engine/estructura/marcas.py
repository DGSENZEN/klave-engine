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

Una cuenta de varillas no es una marca: una letra, un espacio y unas cifras pegadas a «#» («P
4#3») son 4 varillas del #3; «K 7 E#3@1S» sí es K-7 (a las cifras les sigue un espacio).

Las etiquetas de la configuración (``column_tag``, ``beam_tag``) se escriben como el plano
(«K15A», «T1-1»); las demás marcas como ``K-15A.1``: la misma llave en todos los lectores."""

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Literal

from klave_engine.detection.text_patterns import TextPatternConfig

_PREFIJOS = "K|C|T|COL|CT|CTA|TB|ZC|ZCM|Z|D|P|MC|CE|CR"

# Una marca dentro de un texto: K-1, C-3, T-2, COL-1, CTA-3, Z-1, D-4B, P-4, MC-1, CE-1, CR-2, con
# su sufijo de variante (``K-15A.1`` es otra marca que ``K-15A``), o el tipo «X» (``K-X``, ``D-X``).
MARCA_RE = re.compile(rf"\b({_PREFIJOS})(?:\s*-?\s*(\d{{1,2}})([A-Z]?)(?:\.(\d))?|-(X))\b")
# Una ficha que es toda una marca, sin espacios.
_COMPACTA = re.compile(rf"({_PREFIJOS})(?:-?(\d{{1,2}})([A-Z]?)(?:\.(\d))?|-(X))")
# «K-1-A»: la letra de la variante tras un guion. No una letra que empieza otra marca («P-5-P»,
# «T-1-T», «C-1-P»: lo que sigue puede ser otra marca a medias) ni la X del tipo.
_CON_LETRA = re.compile(rf"({_PREFIJOS})-?(\d{{1,2}})-([ABE-JL-OQ-SU-WY])")
# Una marca escrita con espacios («K 7», «T - 1», «K- 7»): sus cifras no van pegadas a «#» (eso
# es una cuenta de varillas, «P 4#3»).
_ESPACIADA = re.compile(
    rf"(?<![^\s:;,()=])({_PREFIJOS})(?:\s+-?\s*|\s*-\s+)(\d{{1,2}})([A-Z]?)"
    r"(?=$|[\s:;,()=]|\.(?:\s|$))"
)
# Donde empieza algo con forma de marca dentro de una ficha: la letra no va pegada a otra letra
# o cifra y le sigue un guion o una cifra.
_INICIO_DE_MARCA = re.compile(rf"(?<![A-Z0-9])(?:{_PREFIJOS})(?=[-\d])")
_ACOTA = re.compile(r"[:;,()=]")
# Lo que une las marcas de una ficha: un guion (rango) o «+», «&», «/» (lista).
_UNE_EN_FICHA = "-–—+&/"
_GUION = "-–—"

# Entre las marcas de una lista o un rango escrito con espacios.
ENTRE_MARCAS = re.compile(r"(?:\s|[,;/=&+\-–—]|\b(?:Y|E|A|AL|HASTA)\b)*")
CONECTOR_DE_RANGO = re.compile(r"\b(?:AL|A|HASTA)\b|[-–—]")
_ABRE_RANGO = re.compile(r"(?:DE|DEL|DESDE)\s+$")
# El fin de un rango escrito sólo con su número («K-1 A 4»), tras un conector entre espacios.
_FIN_DE_RANGO = re.compile(r"\s+(?:AL|A|HASTA|-|–|—)\s+(\d{1,2}[A-Z]?)(?=$|[\s:;,()=.])")
_RANGO_CON_ESPACIOS = re.compile(r"\S (?:AL|A|HASTA|-|–|—) \S")
# Una marca partida en lo de antes de su último número, el número y lo de después.
_PARTES = re.compile(r"(?P<pre>(?:.*\D)?)(?P<num>\d{1,3})(?P<suf>-?[A-Z]?)")

# Lo que remite a otra parte del plano no nombra una marca: «E#2@15 VER CORTE C-2».
_REFERENCIA = re.compile(
    r"\b(?:VER|V[EÉ]ASE|SEG[UÚ]N|IGUAL\s+A)\b\.?(?:\s+(?:EL|LA|LOS|LAS))?"
    r"(?:\s+(?:CORTE|DETALLE|DET\.?|SECCI[OÓ]N|PLANO|NOTA|CUADRO)\b\.?)?\s*[^\s,;]*"
    r"|\b(?:CORTE|DETALLE|DET\.)\s+[^\s,;]+",
    re.I,
)


def sin_referencias(texto: str) -> str:
    """El texto sin lo que remite a otra parte del plano («VER CORTE C-2», «SEGÚN DETALLE K-1»):
    la marca de una referencia no es la de quien lo dice."""
    return _REFERENCIA.sub(" ", texto)


@lru_cache(maxsize=64)
def _patrones(columnas: tuple[str, ...], trabes: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in (*columnas, *trabes))


def es_etiqueta(texto: str, config: TextPatternConfig) -> bool:
    """Si ``texto`` entero es una etiqueta de columna o de trabe de la configuración (como
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
    if es_etiqueta(ficha, config):
        return ficha
    compacta = _COMPACTA.fullmatch(ficha)
    if compacta is not None:
        return escrita(compacta)
    con_letra = _CON_LETRA.fullmatch(ficha)
    if con_letra is not None:
        return f"{con_letra.group(1)}-{int(con_letra.group(2))}-{con_letra.group(3)}"
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


def _leer_ficha(ficha: str, inicio: int, config: TextPatternConfig) -> list[_Pieza]:
    fin = inicio + len(ficha)
    sola = marca_sola(ficha, config)
    if sola is not None:
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
    rango = re.fullmatch(r"(.+)[-–—](\d{1,2})", ficha)
    if rango is not None:
        primera = marca_sola(rango.group(1), config)
        if primera is not None:
            candidatas.append(f"{primera} A {_con_ultimo_numero(primera, rango.group(2))}")
    if not candidatas:
        return []
    return [_Pieza(inicio, fin, "ambigua", piezas=list(dict.fromkeys(candidatas)), texto=ficha)]


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


def _leer_marcas(texto: str, config: TextPatternConfig) -> LecturaDeMarcas:
    limpio = " ".join(sin_referencias(texto).upper().split())
    limpio = _ESPACIADA.sub(lambda m: f"{m.group(1)}-{int(m.group(2))}{m.group(3)}", limpio)
    piezas: list[_Pieza] = []
    for inicio, _fin, ficha in _fichas(limpio):
        piezas += _leer_ficha(ficha, inicio, config)
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


# ------------------------------------------------------------------------------- rangos


def extremos_de_rango(rango: str, config: TextPatternConfig | None = None) -> list[str]:
    """Los extremos de un rango escrito, con o sin espacios: «K-1 A K-4» → [K-1, K-4]; un fin
    escrito sólo con su número cambia el último número de la primera («K-1 A 4» → K-4, «T1-1 A
    3» → T1-3); «K-1 A C-4» → [K-1, C-4]. Vacía si no es un rango. Con la configuración del
    proyecto (sus etiquetas, «T1-1»); sin ella, la de siempre."""
    config = config or TextPatternConfig()
    limpio = " ".join(rango.upper().split())
    limpio = _ESPACIADA.sub(lambda m: f"{m.group(1)}-{int(m.group(2))}{m.group(3)}", limpio)
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
    return re.sub(r"[\s\-–—‑.]", "", partes["pre"]), int(partes["num"])


def marca_en_rango(rango: str, marca: str, config: TextPatternConfig | None = None) -> bool:
    """Si ``marca`` cabe en un rango escrito: es uno de sus extremos o comparte con el primero lo
    de antes de su último número y ese número cae entre los de los extremos («K-1 A K-4» → K-2,
    K-2A, K-4A; «T1-1 A T1-3» → T1-2). Entre marcas de letras distintas, sólo los extremos. Sirve
    para no dejar que otra lectura cubra lo que el plano dice para todo el rango; nunca para
    leerlo."""
    extremos = extremos_de_rango(rango, config)
    if not extremos:
        return False
    propia = " ".join(marca.upper().split())
    if propia in extremos:
        return True
    desde, hasta, cual = _partes(extremos[0]), _partes(extremos[-1]), _partes(propia)
    if desde is None or hasta is None or cual is None or desde[0] != hasta[0]:
        return False
    return cual[0] == desde[0] and min(desde[1], hasta[1]) <= cual[1] <= max(desde[1], hasta[1])
