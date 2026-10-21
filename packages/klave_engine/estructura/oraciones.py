"""Las oraciones y las cláusulas de una nota, y lo que niegan.

Una regla de armado se lee sólo de una cláusula que una frase conocida cubre ENTERA
(``estructura.frases``), nunca de un número cualquiera que cae cerca de una palabra clave. Aquí
vive lo que hace falta para eso: partir el texto en oraciones sin cortar donde el punto es de una
abreviatura o de una medida que sigue («15 CM. CON GANCHOS…», «VER FIG. 4», «No. 3»), partir cada
oración en cláusulas (en «,», «;» y «:»), borrar las referencias que se meten entre comas («LOS
ESTRIBOS, VER FIG. 4, TENDRAN…») y saber si un texto niega. Cuando no se sabe si un punto acaba la
oración se corta: un corte de más sólo puede dejar una regla sin leer (y avisada), nunca leerla
mal. Las funciones trabajan sobre texto en mayúsculas y sin acentos
(``notas.mayusculas_sin_acentos``)."""

import re
from dataclasses import dataclass

# El punto de estas abreviaturas nunca acaba la oración: lo que sigue es su clave o su número
# («FIG. B», «VER DET. 3», «ART. 5»). («No.» sí puede acabarla: «… EN PILAS NO.»; sólo es «número»
# si lo sigue una cifra.)
_SIEMPRE_SIGUEN = frozenset("FIG FIGS DET ART VAR VARS".split())
# Un punto detrás de esto es de una abreviatura o de una unidad, y la oración puede seguir.
_ABREVIATURAS = frozenset("NO N° Nº NUM ESP APROX PULG SEC TAB INC VS DIAM EST MIN MAX".split())
_UNIDADES = frozenset("CM CMS CM2 KG/CM2 KG M MT MTS MM M2 M3".split())
_UNIDAD_PEGADA = re.compile(r"\d(?:CMS?|CM2|KG/CM2|MTS?|MM|M2|M3|M)$")
# Tras el punto de una unidad o abreviatura, esto sigue la misma oración: «15 CM. CON GANCHOS»,
# «5 CM DE ESP. DE CONCRETO», «A 5 CMS. DEL PAÑO», «VER FIG. 4».
_SIGUEN = frozenset("CON SEGUN DE DEL".split())
# Esto, en cambio, empieza otra oración —«@ 10 CM. EN LAS ESCUADRAS…», «… CM. A LAS VARILLAS…»—
# salvo «Y», «E» u «O» seguidas de un verbo sin sujeto propio («@ 15CM. Y TENDRAN GANCHOS»).
_CONJUNCIONES = frozenset("Y E O".split())
_VERBO = re.compile(r"(?:SE|\w+(?:RAN|RA|AN|EN))$")
# Lo que, al empezar una oración tras el punto de una unidad, deja la duda de si es la misma.
_CONECTORES = frozenset("CON Y E O EN DE DEL A SEGUN".split())
_FIN = re.compile(r"([.;])\s+")
_PUNTUACION = "(),;:\"'¿¡"


def _palabras_alrededor(texto: str, fin: re.Match[str]) -> tuple[str, list[str]] | None:
    antes = texto[max(0, fin.start() - 40) : fin.start()].split()
    despues = texto[fin.end() : fin.end() + 60].split()
    if not antes or not despues:
        return None
    return antes[-1].strip(_PUNTUACION), despues


def _tras_una_medida(anterior: str) -> bool:
    return bool(
        anterior in _SIEMPRE_SIGUEN
        or anterior in _ABREVIATURAS
        or anterior in _UNIDADES
        or _UNIDAD_PEGADA.search(anterior)
    )


def _sigue_la_oracion(texto: str, fin: re.Match[str]) -> bool:
    """Si el punto de ``fin`` es de una abreviatura o una medida y la oración sigue después."""
    alrededor = _palabras_alrededor(texto, fin)
    if alrededor is None:
        return False
    anterior, despues = alrededor
    if anterior in _SIEMPRE_SIGUEN:
        return True
    if not _tras_una_medida(anterior):
        return False
    siguiente = despues[0].strip(_PUNTUACION)
    if despues[0][:1] in "#(" or siguiente[:1].isdigit() or siguiente in _SIGUEN:
        return True
    if siguiente in _CONJUNCIONES and len(despues) > 1:
        return bool(_VERBO.search(despues[1].strip(_PUNTUACION)))
    return False


def oraciones(texto: str) -> list[tuple[int, int]]:
    """Dónde empieza y dónde acaba cada oración de ``texto`` (el punto va dentro; el espacio que
    lo sigue, no). Se corta en «. » y en «; », salvo el punto de «FIG.», «DET.», «ART.» (nunca) y
    el de una unidad o abreviatura («CM.», «No.») seguido de una cifra, de «CON», «SEGUN», «DE» o
    «DEL», o de «Y» con un verbo sin sujeto propio («@ 15 CM. CON GANCHOS» y «@ 15CM. Y TENDRAN
    GANCHOS» son una sola oración; «@ 10 CM. TODAS LAS ESCUADRAS» y «@ 10 CM. EN LAS ESCUADRAS»
    son dos)."""
    inicios = [0]
    fines: list[int] = []
    for m in _FIN.finditer(texto):
        if m.group(1) == "." and _sigue_la_oracion(texto, m):
            continue
        fines.append(m.start() + 1)
        inicios.append(m.end())
    fines.append(len(texto.rstrip()))
    return [(i, max(f, i)) for i, f in zip(inicios, fines, strict=True)]


def tras_un_corte_dudoso(texto: str, inicio: int) -> bool:
    """Si la oración que empieza en ``inicio`` sigue al punto de una unidad o abreviatura y
    empieza con un conector («… @ 10 CM. EN LAS ESCUADRAS…»): se cortó, pero puede ser la misma."""
    antes = texto[max(0, inicio - 40) : inicio].rstrip()
    if not antes.endswith("."):
        return False
    palabras = antes[:-1].split()
    despues = texto[inicio : inicio + 30].split()
    if not palabras or not despues:
        return False
    return _tras_una_medida(palabras[-1].strip(_PUNTUACION)) and (
        despues[0].strip(_PUNTUACION) in _CONECTORES
    )


@dataclass(frozen=True)
class Pieza:
    """Un trozo de una oración que se lee entero: una cláusula (entre «,», «;» y «:») o una parte
    de una cláusula coordinada con «Y». ``separador`` es lo que la termina (``""`` al final)."""

    inicio: int
    fin: int
    separador: str


# Una cláusula acaba en «,» (no la de «2,5»), «;» o «:».
_CORTE_DE_CLAUSULA = re.compile(r"[;:]|(?<!\d),|,(?!\d)")


def clausulas(texto: str, inicio: int, fin: int) -> list[Pieza]:
    """Las cláusulas de ``texto[inicio:fin]``, sin los espacios de las orillas."""
    piezas: list[Pieza] = []
    desde = inicio
    cortes = [(c.start(), c.group(0)) for c in _CORTE_DE_CLAUSULA.finditer(texto, inicio, fin)]
    for posicion, separador in [*cortes, (fin, "")]:
        a, b = desde, posicion
        while a < b and texto[a].isspace():
            a += 1
        while b > a and texto[b - 1].isspace():
            b -= 1
        if a < b:
            piezas.append(Pieza(a, b, separador))
        desde = posicion + len(separador)
    return piezas


# Una referencia metida entre comas o entre paréntesis («, VER FIG. 4,», «(VER TABLA No. 1)») no
# es parte de la frase: se borra (con espacios, para que los lugares del texto no cambien).
_REFERENCIA = (
    r"(?:VER|SEGUN|CONFORME\s+A|DE\s+ACUERDO\s+(?:CON|A))\s+(?:(?:LA|EL|LOS|LAS)\s+)?"
    r"(?:FIG(?:URA)?S?|DET(?:ALLE)?S?|TABLAS?|ART(?:ICULO)?S?|NOTAS?|PLANOS?|CORTES?|CROQUIS)"
    r"(?:\s*\.)?(?:\s*-\s*|\s+)?(?:(?:NO|N[º°])\.?\s*)?"
    r"(?:\d{1,3}(?:-?[A-Z0-9]{1,3})?|[A-Z](?:-?\d{1,3})?)\b"
)
_REFERENCIA_METIDA = re.compile(rf",\s*{_REFERENCIA}\s*,|\(\s*{_REFERENCIA}\s*\)")


def sin_referencias(texto: str) -> str:
    """``texto`` con las referencias metidas («, VER FIG. 4,», «(VER TABLA No. 1)») en blanco."""
    return _REFERENCIA_METIDA.sub(lambda m: " " * len(m.group(0)), texto)


# «NO», «NI», «SIN», «NUNCA», «PROHIBIDO», «EVITAR»…; no el «No.» de «No. 6» ni el «NO 6», ni
# «NO OBSTANTE» o «SIN EMBARGO». Un «NO.» al final («… EN PILAS NO.») sí niega.
NEGACION = re.compile(
    r"\b(?:NO(?!\s*\.?\s*[\d#])(?![°º])(?!\s+OBSTANTE\b)|NI|SIN(?!\s+EMBARGO\b)|NUNCA|JAMAS|TAMPOCO"
    r"|NINGUN[OA]?S?|PROHIB\w*|EVIT\w*)\b"
)


def niega(frase: str, inicio: int, fin: int) -> bool:
    """Si una negación de la cláusula anula la frase que va de ``inicio`` a ``fin`` de ``frase``:
    un «NO», «NI», «SIN»… desde el principio de su cláusula hasta el final de la frase."""
    cortes = [c.end() for c in _CORTE_DE_CLAUSULA.finditer(frase, 0, inicio)]
    desde = cortes[-1] if cortes else 0
    return NEGACION.search(frase, desde, fin) is not None
