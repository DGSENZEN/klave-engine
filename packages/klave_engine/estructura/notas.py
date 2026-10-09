"""Las notas numeradas del plano: renglones de texto que el dibujante numeró y encabezó.

Un plano estructural trae sus notas como texto suelto, un renglón por texto, a la izquierda, bajo
un encabezado («NOTAS GENERALES DE ESTRUCTURA.», «MATERIALES :», «REFUERZO :»). La numeración
reinicia con cada encabezado y una nota larga se parte en varios renglones: el primero lleva el
número («4.  NO SE PERMITIRA…») y los demás van debajo, alineados o con sangría. Aquí se juntan
por su número y se leen tal como están escritas.

Los bloques de notas se insertan una vez por hoja, así que cada nota viene en tantas copias como
hojas; las copias iguales se cuentan y las que no dicen lo mismo se reportan: nunca se escoge una
en silencio. Sólo se leen los renglones de texto (un texto de varias líneas no se parte aquí)."""

import difflib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel

from klave_engine.dxf.entities import NormalizedEntity
from klave_engine.estructura.asociacion import ancla_texto

# Un renglón de la misma nota está debajo del anterior a lo más a esto (× el alto) de hueco
# libre; alineado a la izquierda (a lo más 1 alto de diferencia) o con sangría (a lo más 4).
_HUECO_MAXIMO = 1.5
_ALINEADO = 1.0
_SANGRIA = 4.0
# Dos textos a menos de esto (× el alto) de diferencia en vertical están en la misma línea.
_MISMA_LINEA = 0.25
# Un texto bastante más alto que el renglón de arriba no es su continuación: es un título.
_MAS_ALTO = 1.3
# Un encabezado manda sobre las notas que están debajo, a lo más a esto (× el alto) de lado.
_ALCANCE_DEL_ENCABEZADO = 8.0
# Dos redacciones de una nota son versiones de la misma si se parecen a lo menos así; las que no
# se parecen son dos notas distintas que comparten número, no una contradicción.
_PARECIDO_MINIMO = 0.6
# Dos cambios entre los que hay hasta estas palabras iguales se citan como uno solo.
_PALABRAS_QUE_UNEN = 2
# Cuántos tramos que cambian se citan en una contradicción.
_TRAMOS_MAXIMOS = 4

_NUMERADA = re.compile(r"(\d{1,2})[.\-)]+(?:\s+(.*))?")
_ENCABEZADO = re.compile(r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ ]{2,}\s*[:.]")
_CODIGOS_DE_ACAD = re.compile(r"%%(?:%|[cCdDpPuUoO]|\d{3})")
_CODIGOS_DE_MTEXT = re.compile(r"\\[Pp~]|\\[A-Za-z][^;\\]*;|[{}]")
_ACAD = {"%": "%", "c": "Ø", "d": "°", "p": "±", "u": "", "o": ""}


class Nota(BaseModel):
    """Una nota numerada: ``texto`` es el de todos sus renglones, sin el número.

    ``hoja`` y ``entidades`` son los de la primera copia (la de la hoja menor); ``copias`` cuenta
    las veces que el plano la trae igual y ``hojas`` dice dónde. Dos redacciones distintas de la
    misma nota son dos ``Nota`` con el mismo ``seccion`` y ``numero``."""

    seccion: str
    numero: int
    texto: str
    hoja: str
    entidades: list[str]
    copias: int = 1
    hojas: list[str] = []


def limpiar_texto(texto: str) -> str:
    """El texto como lo lee quien mira el plano: sin los códigos de AutoCAD (``%%%`` es «%»,
    ``%%C`` «Ø», ``%%D`` «°»), sin los de MTEXT (``\\P``, ``\\A1;``) y con los espacios en uno."""

    def acad(m: re.Match[str]) -> str:
        codigo = m.group(0)[2:]
        return chr(int(codigo)) if codigo.isdigit() else _ACAD[codigo.lower()]

    texto = _CODIGOS_DE_ACAD.sub(acad, texto)
    texto = _CODIGOS_DE_MTEXT.sub(" ", texto)
    return " ".join(texto.split())


def mayusculas_sin_acentos(texto: str) -> str:
    """Para buscar frases en el texto sin pensar en acentos ni en mayúsculas. Conserva el largo
    (una letra, una letra), así que un lugar en el resultado es el mismo en el original."""
    letras = []
    for letra in texto:
        base = unicodedata.normalize("NFD", letra)[0]
        mayuscula = base.upper()
        letras.append(mayuscula if len(mayuscula) == 1 else base)
    return "".join(letras)


def en_hojas(hojas: list[str]) -> str:
    """Las hojas donde se lee algo; con muchas copias, cuántas."""
    distintas = list(dict.fromkeys(hojas))
    if len(distintas) > 4:
        return f"{len(distintas)} copias"
    return ", ".join(distintas)


def donde_estan(hojas: list[str]) -> str:
    """Dónde está algo: las hojas si son pocas; con muchas, las primeras y cuántas faltan."""
    distintas = sorted(dict.fromkeys(hojas))
    if len(distintas) <= 4:
        return ", ".join(distintas)
    return f"{', '.join(distintas[:3])} y {len(distintas) - 3} hojas más"


@dataclass(frozen=True)
class _Linea:
    """Un renglón de texto con su posición (la de ``ancla_texto``) y su alto."""

    id: str
    texto: str
    x: float
    y: float
    alto: float


@dataclass
class _Instancia:
    """Una nota tal como está en una hoja."""

    seccion: str
    numero: int
    texto: str
    hoja: str
    entidades: list[str]


def _alto(e: NormalizedEntity) -> float:
    alto = e.properties.get("height")
    if not isinstance(alto, int | float) or alto <= 0:
        alto = e.bbox[3] - e.bbox[1]
    return float(alto) if alto > 0 else 1e-6


def _numerada(texto: str) -> tuple[int, str] | None:
    m = _NUMERADA.fullmatch(texto)
    return (int(m.group(1)), m.group(2) or "") if m else None


def _notas_de_la_hoja(lineas: list[_Linea], hoja: str) -> list[_Instancia]:
    """Las notas de una hoja: cada renglón numerado con los que le siguen debajo."""
    lineas = sorted(lineas, key=lambda r: (-r.y, r.x))
    n = len(lineas)
    numeradas = [_numerada(r.texto) for r in lineas]
    consumidas: set[int] = set()
    cadenas: list[tuple[int, list[int]]] = []

    for i in range(n):
        if numeradas[i] is None:
            continue
        referencia = lineas[i].x
        cadena = [i]
        previa = i
        while True:
            siguiente = _siguiente(lineas, previa, referencia, consumidas, numeradas)
            if siguiente is None:
                break
            cadena.append(siguiente)
            previa = siguiente
        consumidas.update(cadena)
        cadenas.append((i, cadena))

    encabezados = [
        i
        for i in range(n)
        if i not in consumidas and _ENCABEZADO.fullmatch(lineas[i].texto) is not None
    ]
    instancias: list[_Instancia] = []
    for primera, cadena in cadenas:
        numero, resto = numeradas[primera] or (0, "")
        partes = [resto, *(lineas[j].texto for j in cadena[1:])]
        seccion = _seccion_de(lineas, primera, encabezados)
        instancias.append(
            _Instancia(
                seccion=seccion,
                numero=numero,
                texto=" ".join(p for p in partes if p),
                hoja=hoja,
                entidades=[lineas[j].id for j in cadena],
            )
        )
    return instancias


def _siguiente(
    lineas: list[_Linea],
    previa: int,
    referencia: float,
    consumidas: set[int],
    numeradas: list[tuple[int, str] | None],
) -> int | None:
    """El renglón que sigue a ``previa`` en la misma nota, o ``None`` si la nota termina.

    Es el más cercano debajo de ``previa`` (con un hueco libre de a lo más 1.5 altos) que cae en
    la columna de la nota, a la izquierda o con sangría; si ése es un renglón numerado o un texto
    bastante más alto, la nota termina ahí."""
    p = lineas[previa]
    tope = (1 + _HUECO_MAXIMO) * _MAS_ALTO * p.alto
    mejor: tuple[float, float, int] | None = None
    for j in range(previa + 1, len(lineas)):
        c = lineas[j]
        bajada = p.y - c.y
        if bajada > tope:
            break
        if j in consumidas or bajada <= _MISMA_LINEA * p.alto:
            continue
        if bajada > (1 + _HUECO_MAXIMO) * max(p.alto, c.alto):
            continue
        if not referencia - _ALINEADO * c.alto <= c.x <= referencia + _SANGRIA * c.alto:
            continue
        llave = (bajada, abs(c.x - referencia), j)
        if mejor is None or llave < mejor:
            mejor = llave
    if mejor is None:
        return None
    j = mejor[2]
    if numeradas[j] is not None:
        return None  # empieza otra nota
    if lineas[j].alto >= _MAS_ALTO * p.alto:
        return None  # un título, no la continuación
    return j


def _seccion_de(lineas: list[_Linea], i: int, encabezados: list[int]) -> str:
    """El encabezado más cercano arriba del renglón, en su misma columna."""
    r = lineas[i]
    mejor: tuple[float, int] | None = None
    for h in encabezados:
        e = lineas[h]
        if e.y <= r.y or abs(e.x - r.x) > _ALCANCE_DEL_ENCABEZADO * r.alto:
            continue
        if mejor is None or e.y - r.y < mejor[0]:
            mejor = (e.y - r.y, h)
    if mejor is None:
        return ""
    return lineas[mejor[1]].texto.rstrip(" :.").strip()


def leer_notas_con_renglones(
    textos: list[NormalizedEntity], hoja_de: Callable[[NormalizedEntity], str]
) -> tuple[list[Nota], list[str], set[str]]:
    """Lo mismo que ``leer_notas``, y además los ``entity_id`` de todos los renglones que son
    parte de una nota (de todas las copias): lo que queda fuera de ellos es texto suelto."""
    por_hoja: dict[str, list[_Linea]] = defaultdict(list)
    for e in textos:
        if not e.is_textual or not e.text or "\n" in e.text.strip():
            continue
        texto = limpiar_texto(e.text)
        if not texto:
            continue
        x, y = ancla_texto(e)
        por_hoja[hoja_de(e)].append(_Linea(e.entity_id, texto, x, y, _alto(e)))

    copias: dict[tuple[str, int, str], list[_Instancia]] = defaultdict(list)
    consumidas: set[str] = set()
    for hoja in sorted(por_hoja):
        for instancia in _notas_de_la_hoja(por_hoja[hoja], hoja):
            copias[(instancia.seccion, instancia.numero, instancia.texto)].append(instancia)
            consumidas.update(instancia.entidades)

    notas: list[Nota] = []
    for (seccion, numero, texto), instancias in copias.items():
        primera = min(instancias, key=lambda i: i.hoja)
        notas.append(
            Nota(
                seccion=seccion,
                numero=numero,
                texto=texto,
                hoja=primera.hoja,
                entidades=primera.entidades,
                copias=len(instancias),
                hojas=sorted({i.hoja for i in instancias}),
            )
        )
    notas.sort(key=lambda nota: (nota.seccion, nota.numero, -nota.copias, nota.hoja))
    return notas, _contradicciones(notas), consumidas


def leer_notas(
    textos: list[NormalizedEntity], hoja_de: Callable[[NormalizedEntity], str]
) -> tuple[list[Nota], list[str]]:
    """Las notas numeradas de ``textos`` y las contradicciones entre sus copias.

    Una nota es un renglón que empieza con su número (``4.``, ``4-``, ``4)``, ``4.-``) y los
    renglones que le siguen debajo en la misma columna: alineados (a lo más un alto de
    diferencia en ``x``) o con sangría (hasta cuatro altos) y con un hueco libre de a lo más 1.5
    altos, hasta el siguiente renglón numerado o un texto bastante más alto. La sección es el
    encabezado (``NOTAS GENERALES DE ESTRUCTURA.``, ``REFUERZO :``) más cercano arriba en su
    columna; sin él, ``""``. Un encabezado es un renglón en mayúsculas que termina en «:» o «.»
    y que no es continuación de una nota (``REFUERZO LONGITUDINAL NI MENOR A:`` bajo una nota
    abierta es de la nota). Los códigos de AutoCAD se leen (``%%%`` es «%»).

    Las copias iguales (misma sección, número y texto) se juntan en una ``Nota`` con ``copias`` y
    ``hojas``. Si la misma nota de un bloque con título dice cosas distintas en distintas hojas
    hay una ``Nota`` por redacción y una frase que cita lo que cambia y dónde; dos textos que no
    se parecen no son redacciones de la misma nota, son dos notas que comparten número, y una
    línea numerada sin título es una nota de su hoja: sus versiones no se comparan."""
    notas, contradicciones, _ = leer_notas_con_renglones(textos, hoja_de)
    return notas, contradicciones


def _contradicciones(notas: list[Nota]) -> list[str]:
    por_numero: dict[tuple[str, int], list[Nota]] = defaultdict(list)
    for nota in notas:
        por_numero[(nota.seccion, nota.numero)].append(nota)
    frases: list[str] = []
    for (seccion, numero), versiones in por_numero.items():
        # Sólo los bloques con título («REFUERZO :») se repiten de hoja en hoja. Una línea
        # numerada sin título es una nota de esa hoja («1. LOSA DE PERALTE TOTAL H=30…»): que
        # otra hoja diga otra cosa no es una contradicción.
        if len(versiones) < 2 or not seccion:
            continue
        versiones = sorted(versiones, key=lambda v: (-v.copias, v.hoja))
        base = versiones[0]
        parecidas = [v for v in versiones[1:] if _parecido(base.texto, v.texto) >= _PARECIDO_MINIMO]
        if not parecidas:
            continue
        cambios = [_cambios(base.texto, v.texto) for v in parecidas]
        lecturas = [(base, cambios[0][0])] + [
            (v, cambio[1]) for v, cambio in zip(parecidas, cambios, strict=True)
        ]
        dice = "; ".join(f"{donde_estan(v.hojas)} dice «{tramo}»" for v, tramo in lecturas)
        frases.append(f"La nota {numero} de {seccion} no dice lo mismo en todas las hojas: {dice}.")
    return frases


def _parecido(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio()


def _cambios(a: str, b: str) -> tuple[str, str]:
    """Lo que cambia de ``a`` a ``b``: los tramos de cada una que no coinciden, en palabras.
    Dos cambios separados por una o dos palabras iguales se citan juntos (``#6, DEL #8``)."""
    pa, pb = a.split(), b.split()
    bloques: list[list[int]] = []  # [i1, i2, j1, j2] de cada tramo que cambia
    for etiqueta, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, pa, pb, autojunk=False
    ).get_opcodes():
        if etiqueta == "equal":
            continue
        if bloques and i1 - bloques[-1][1] <= _PALABRAS_QUE_UNEN:
            bloques[-1][1], bloques[-1][3] = i2, j2
        else:
            bloques.append([i1, i2, j1, j2])
    tramos_a = [" ".join(pa[i1:i2]) or "—" for i1, i2, _, _ in bloques]
    tramos_b = [" ".join(pb[j1:j2]) or "—" for _, _, j1, j2 in bloques]
    return _unir(tramos_a), _unir(tramos_b)


def _unir(tramos: list[str]) -> str:
    if len(tramos) > _TRAMOS_MAXIMOS:
        tramos = [*tramos[:_TRAMOS_MAXIMOS], "…"]
    return " … ".join(tramos)
