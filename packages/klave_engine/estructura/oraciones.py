"""Las oraciones de una nota y lo que niegan.

Una regla de armado se lee de UNA oración que dice una frase conocida («SE PERMITE TRASLAPAR
VARILLA HASTA EL #6», «LOS ESTRIBOS LLEVARAN GANCHOS A 135°»), nunca de un número cualquiera que
cae cerca de una palabra clave. Aquí vive lo que hace falta para eso: partir el texto en oraciones
sin cortar donde el punto es de una unidad o de una abreviatura («15 CM. CON GANCHOS…», «VER FIG.
4», «No. 3»), y saber si una oración niega lo que viene (una negación en la cláusula, antes de la
frase, la anula: «NO SE PERMITE TRASLAPAR…», «SIN SOLDADURA EN…»). Las funciones trabajan sobre
texto en mayúsculas y sin acentos (``notas.mayusculas_sin_acentos``)."""

import re

# Un punto detrás de esto es de una abreviatura o de una unidad, no el fin de una oración —cuando
# lo que sigue es un conector o una cifra—: «15 CM. CON GANCHOS», «KG/CM2. CON», «FIG. 4».
_ABREVIATURAS = frozenset("NO N° Nº NUM FIG ART DET ESP APROX PULG SEC TAB INC VS".split())
_UNIDADES = frozenset("CM CMS CM2 KG/CM2 KG M MT MTS MM M2 M3".split())
_UNIDAD_PEGADA = re.compile(r"\d(?:CMS?|CM2|KG/CM2|MTS?|MM|M2|M3|M)$")
_CONECTORES = frozenset("CON Y E O EN DE A SEGUN".split())
_FIN = re.compile(r"([.;])\s+")
_PUNTUACION = "(),;:\"'¿¡"


def _es_abreviatura(texto: str, fin: re.Match[str]) -> bool:
    """Si el punto de ``fin`` es de una abreviatura o una unidad que sigue en la misma oración."""
    antes = texto[max(0, fin.start() - 40) : fin.start()].split()
    despues = texto[fin.end() : fin.end() + 40].split(None, 1)
    if not antes or not despues:
        return False
    anterior = antes[-1].strip(_PUNTUACION)
    siguiente = despues[0].strip(_PUNTUACION)
    es_abreviatura = (
        anterior in _ABREVIATURAS or anterior in _UNIDADES or _UNIDAD_PEGADA.search(anterior)
    )
    sigue = siguiente in _CONECTORES or siguiente[:1].isdigit() or despues[0][:1] in "#("
    return bool(es_abreviatura and sigue)


def oraciones(texto: str) -> list[tuple[int, int]]:
    """Dónde empieza y dónde acaba cada oración de ``texto`` (el punto va dentro; el espacio que
    lo sigue, no). Se corta en «. » y en «; », salvo el punto de una unidad o abreviatura seguido
    de un conector o una cifra («@ 15 CM. CON GANCHOS» es una sola oración; «@ 10 CM. TODAS LAS
    ESCUADRAS» son dos)."""
    inicios = [0]
    fines: list[int] = []
    for m in _FIN.finditer(texto):
        if m.group(1) == "." and _es_abreviatura(texto, m):
            continue
        fines.append(m.start() + 1)
        inicios.append(m.end())
    fines.append(len(texto.rstrip()))
    return [(i, max(f, i)) for i, f in zip(inicios, fines, strict=True)]


def oracion_de(texto: str, posicion: int) -> tuple[int, int]:
    """La oración que contiene ``posicion``."""
    for inicio, fin in oraciones(texto):
        if posicion < fin or fin == len(texto.rstrip()):
            return inicio, fin
    return 0, len(texto)


# «NO», «NI», «SIN», «NUNCA», «PROHIBIDO»…; no el «No.» de «No. 6» ni el «NO 6».
_NEGACION = re.compile(r"\b(?:NO(?!\s*[.\d#°º])|NI|SIN|NUNCA|JAMAS|NINGUN[OA]S?|PROHIB\w*)\b")
# Una cláusula acaba en «,» (no la de «2,5»), «;» o «:».
_CORTE_DE_CLAUSULA = re.compile(r"[;:]|(?<!\d),|,(?!\d)")


def clausula(frase: str, posicion: int) -> tuple[int, int]:
    """La cláusula (entre comas, «;» o «:») de ``frase`` que contiene ``posicion``."""
    cortes = list(_CORTE_DE_CLAUSULA.finditer(frase))
    inicio = max((c.end() for c in cortes if c.end() <= posicion), default=0)
    fin = min((c.start() for c in cortes if c.start() >= posicion), default=len(frase))
    return inicio, fin


def niega(frase: str, inicio: int, fin: int) -> bool:
    """Si una negación de la cláusula anula la frase que va de ``inicio`` a ``fin`` de ``frase``:
    un «NO», «NI», «SIN»… desde el principio de su cláusula hasta el final de la frase. («NO SE
    PERMITIRA TRASLAPAR NI SOLDAR…, UNICAMENTE SE PERMITIRA TRASLAPAR VARILLA HASTA EL #6» niega la
    primera cláusula, no la segunda.)"""
    cortes = [c.end() for c in _CORTE_DE_CLAUSULA.finditer(frase, 0, inicio)]
    desde = cortes[-1] if cortes else 0
    return _NEGACION.search(frase, desde, fin) is not None
