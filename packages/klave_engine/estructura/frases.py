"""Las frases con que una nota dice una regla de armado, y la lectura que sólo cree en ellas.

Una regla se lee únicamente de una cláusula (o de unas cláusulas seguidas) que una frase conocida
(``FRASES_CONOCIDAS``) cubre ENTERA, de la primera letra a la última: nunca de un trozo que se
parece a una frase conocida dentro de algo más largo. Cada frase de traslape, soldadura, gancho o
primer estribo lleva su verbo conjugado en positivo («SE PERMITE TRASLAPAR», «SE SOLDARAN»,
«LLEVARAN», «SE COLOCARA»…); un infinitivo suelto («TRASLAPAR VARILLAS…») o una frase sin verbo no
se lee (la única sin verbo, «ESTRIBOS … CON GANCHOS A 135°», vale sólo si es la oración entera). Lo
que puede venir detrás es una lista cerrada: la cola de la varilla («INCLUSIVE», «O MENOR»), el
tramo recto, dónde se dibuja («COMO LO INDICA LA FIG-D», «VER DETALLE 3»). La varilla se escribe
con marca («#6», «No. 6», «NUMERO 6»), en pulgadas con comillas o «PULG», o con un número que el
texto dice que es una varilla («EL 6», «DEL 6», «VARILLA 6», «VARILLA HASTA 6 INCLUSIVE»); un número
pelado en otro lugar («HASTA 6», «HASTA 2 POR SECCION») no es una varilla (``varilla_de``).

Una cláusula que ninguna frase cubre puede ser dos coordinadas con «Y» cuando la de la izquierda,
sin negación, es una frase conocida y la de la derecha empieza con su propio sujeto o verbo («SE
TRASLAPARAN HASTA EL #6 Y NO SE SOLDARA NINGUNA»).

Además, una frase sólo vale si nada de su oración la cambia:
- no trae ninguna negación (``oraciones.NEGACION``);
- cada cláusula de antes es otra frase leída, una neutral («SALVO INDICACION», «SIN EMBARGO»…) o
  una que habla de otra regla con su propio sujeto, sin acotarla a un elemento (la de Marina: «NO
  SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50% …, UNICAMENTE SE PERMITIRA…»); una que no («NO SE
  PERMITIRA,», «PROHIBIDO:», «EN COLUMNAS,», «PARA TRASLAPES EN COLUMNAS,») manda sobre lo que
  sigue y la frase no se lee;
- ninguna cláusula de después la niega o la acota: una negación que no nombra otra regla («…, NO
  ESTA PERMITIDO»), una excepción («…, EXCEPTO EN COLUMNAS»), otro número o un elemento sin regla
  propia o de la misma regla («…, EN COLUMNAS HASTA EL #5», «… Y LOS ESTRIBOS A 90°»);
- la oración que sigue, si no nombra ninguna regla, tampoco la niega ni la acota («… HASTA EL #6.
  NO EN COLUMNAS.»); para el primer estribo, que va por familia, un número de otra familia en esa
  oración no la cambia («… EN TRABES … A 5 CM. EN COLUMNAS A 10 CM.»: se avisa aparte).

Los recubrimientos son una lista cerrada de renglones «N CM EN <elementos>» tras lo que los
presenta («EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE … NI MENOR A:»); un elemento de la lista
es uno conocido o una palabra que no se reconoce (se avisa), nada más («Y LA MITAD EN LOSAS» no
cabe). Hay además frases que se saben leer pero no dan una regla: la proporción por sección de
Marina («NO SE PERMITIRA TRASLAPAR NI SOLDAR MAS DEL 50% …»), «SE COLOCARA PLANTILLA DE CONCRETO
POBRE», «EL TRASLAPE SERA SEGUN TABLA», y lo que acompaña a la otra mitad que sí se leyó («SIN
TRASLAPES» junto a lo que se suelda, «NO SE SOLDARA NINGUNA» junto a lo que se traslapa), si la
nota no lee también lo que eso niega (entonces se desmiente).

Lo que no se lee queda en ``Lectura.resto``. Quien lee decide con la nota entera si sus lecturas
valen (``reglas._lo_que_la_cambia``) y avisa de lo que nombra una regla con un número y no se
entendió (``reglas._vigilar``). Todo trabaja sobre el texto en mayúsculas y sin acentos, que tiene
el mismo largo que el original: un lugar en uno es el mismo en el otro."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from klave_engine.estructura.oraciones import (
    NEGACION,
    Pieza,
    clausulas,
    oraciones,
    sin_referencias,
    tras_un_corte_dudoso,
)

_NUM = r"\d+(?:[.,]\d+)?"
# Un adverbio que no cambia lo que sigue: «SIN EMBARGO SE PERMITE…».
_ADV = r"(?:(?:SIN\s+EMBARGO|NO\s+OBSTANTE|ADEMAS|ASIMISMO|EN\s+GENERAL)\s*,?\s+)?"
_SOLO = r"(?:(?:UNICAMENTE|SOLO|SOLAMENTE)\s+)?"

# Una varilla escrita como el plano la escribe: con su artículo y su nombre si los trae («EL #6»,
# «LA VARILLA No. 8»), con marca («#6», «No. 6», «NUMERO 6», «NUM. 6») o sin ella («EL 6», «DEL
# 6»), en pulgadas («3/4"», «1 1/4"», «5/8 PULG») o en una fracción sin unidad («3/4»), con su
# equivalencia entre paréntesis («No. 6 (3/4")»). Qué es y si vale lo decide ``varilla_de``.
_COMILLAS = '"”″'


def _barra(nombre: str) -> str:
    return (
        rf"(?P<{nombre}>"
        r"(?:(?:EL|LA)\s+)?(?:VARILLAS?\s+)?"
        r"(?:#\s*|(?:NO|N[º°])\.?\s*|NUMERO\s+|NUM\.?\s*)?"
        r"\d+(?:(?:\s+|\s*-\s*)\d+\s*/\s*\d+|\s*/\s*\d+|[.,]\d+)?"
        rf"(?:\s*(?:[{_COMILLAS}]|''|PULG(?:ADAS?)?\b\.?))?"
        r"(?:\s*\(\s*[^()]{1,14}\))?"
        r")"
    )


# La cola que cierra la varilla de un límite: «HASTA EL #6 INCLUSIVE», «… O MENOR», «… Y MENORES».
_COLA = r"(?P<cola>\s*,?\s*INCLUSIVE|\s+(?:O|Y)\s+MENOR(?:ES)?)?"
# Lo que puede ir al final de cualquier frase: dónde se dibuja o se dice más.
_DONDE = (
    r"(?:FIG(?:URA)?S?|DET(?:ALLE)?S?|TABLAS?|PLANOS?|CORTES?|CROQUIS|NOTAS?|ART(?:ICULO)?S?)"
    r"(?:\s*\.)?(?:\s*-\s*|\s+)?(?:(?:NO|N[º°])\.?\s*)?"
    # la clave de la figura o el detalle: una letra o una cifra, no una palabra («D», «4», «A-1»)
    r"(?:\d{1,3}(?:-?[A-Z0-9]{1,3})?|[A-Z](?:-?\d{1,3})?)\b"
)
_CONTEXTO = (
    r"(?:\s*,?\s*(?:COMO\s+(?:LO\s+|SE\s+)?(?:INDICAN?|MUESTRAN?|ILUSTRAN?|ESPECIFICAN?)\s+"
    rf"(?:EN\s+)?(?:LA|EL|LOS|LAS)\s+{_DONDE}|(?:VER|SEGUN)\s+(?:(?:LA|EL)\s+)?{_DONDE}))?"
)

_PERMITE = r"SE\s+PERMIT(?:E|EN|IRA|IRAN)"
_SE_TRASLAPA = (
    r"(?:SE\s+TRASLAPA(?:RA|RAN|N)?|(?:SE\s+)?PODRAN?\s+TRASLAPAR(?:SE)?|SE\s+PUEDEN?\s+TRASLAPAR)"
)
_SE_SUELDA = r"(?:SE\s+SOLDA(?:RA|RAN|N)?|(?:SE\s+)?(?:DEBERAN?|PODRAN?)\s+SOLDAR(?:SE)?)"
_A_TOPE = r"(?:\s+A\s+TOPE)?"
# Un límite: «HASTA EL #6», «VARILLA HASTA 6 INCLUSIVE» (``pre_b`` dice si lo antecede el nombre).
_HASTA = rf"(?P<pre_b>(?:VARILLAS?\s+)?HASTA)\s+{_barra('b')}{_COLA}"
_DESDE_UN = rf"(?P<pre_b>(?:VARILLAS?\s+)?(?:DEL|DE))\s+{_barra('b')}"
_RANGO = rf"(?P<pre_a>DEL|DE)\s+{_barra('a')}\s+(?P<pre_b>AL|A)\s+{_barra('b')}"

_FAMILIA = (
    r"(?:(?:CONTRATRABES?|TRABES?|VIGAS?)(?:\s+DE\s+CIMENTACION)?|COLUMNAS?|CASTILLOS?|DALAS?"
    r"|CADENAS?|CERRAMIENTOS?)"
)
_FAMILIAS = (
    rf"(?:(?:LAS|LOS)\s+)?{_FAMILIA}(?:\s*(?:,|\bY\b|\bE\b)\s*(?:(?:LAS|LOS)\s+)?{_FAMILIA})*"
)
_PANO = (
    r"(?:\s+(?:DEL|DE\s+LOS?|DE\s+LAS?)\s+(?:PANOS?|APOYOS?)"
    r"(?:\s+DE(?:L|\s+LOS?|\s+LAS?)\s+(?:APOYOS?|COLUMNAS?|TRABES?|NUDOS?|MUROS?))?)?"
)
_A_CM = rf"A\s+(?P<n>{_NUM})\s*CMS?\b\.?{_PANO}"
_VERBO_DEL_PRIMER = (
    r"(?:SE\s+(?:COLOCARA|PONDRA|UBICARA|DEJARA)|IRA|ESTARA|QUEDARA"
    r"|DEBERA\s+(?:COLOCARSE|IR|QUEDAR))"
)

_ANGULO = r"\d{2,3})\s*(?:°|º|GRADOS)"
_GANCHO = r"(?:(?:UN|UNOS)\s+)?(?:GANCHOS?|DOBLE(?:Z|CES))\s+(?:A|DE)\s+"
_RECTO = rf"(?P<tq>RECTO\s+DE\s+(?P<recto>{_NUM})\s*(?:Ø|⌀|DIAMETROS?|VECES\s+EL\s+DIAMETRO))"
_TRAMO = rf"(?:\s*,?\s*(?:Y|CON|SEGUIDOS?\s+DE|MAS)\s+(?:UN\s+)?TRAMO\s+{_RECTO})?"
_LLEVAN = (
    r"(?:LLEVARAN|TENDRAN|SE\s+HARAN\s+CON|(?:SE\s+)?TERMINARAN\s+CON|SE\s+ANCLARAN\s+CON"
    r"|DEBERAN\s+(?:LLEVAR|TENER))"
)
# Lo que dice de los estribos antes del verbo: «DEL No. 3», «Ø3/8"», «@ 15 CMS.», «F'Y=4200…».
_DATOS_DEL_ESTRIBO = (
    r"(?:\s+(?:DEL?\s+(?:#\s*|(?:NO|N[º°])\.?\s*|NUM\.?\s*)?\d+(?:\s+EN\s+ADELANTE)?"
    r"|(?:#\s*|(?:NO|N[º°])\.?\s*)\d+"
    rf"|[Ø⌀]\s*\d+(?:\s*/\s*\d+)?\s*[{_COMILLAS}]?"
    r"|(?:@|CADA)\s*\d+(?:[.,]\d+)?\s*CMS?\b\.?"
    r"|F'?Y\s*=\s*\d+\s*(?:KG/CM2)?\.?"
    r"|SEGUN\s+(?:ART|FIG|DET|TABLA)\w*\.?\s*[A-Z0-9-]{1,5}))*"
)


def _quien(nombre: str) -> str:
    return rf"(?:(?:LOS|LAS)\s+)?(?P<{nombre}>ESTRIBOS?|GRAPAS?)"


def _angulo(nombre: str) -> str:
    return rf"(?P<{nombre}>{_ANGULO}"


_UNIDAD = r"(?P<u>CMS?|MTS?|MM|M)\b\.?"
# El material de la plantilla: «DE CONCRETO POBRE», «DE CONCRETO F'C=100 KG/CM2», «F'C=100».
_DE_CONCRETO = (
    r"\s+DE\s+CONCRETO(?:\s+(?:POBRE|SIMPLE|CICLOPEO))?"
    r"(?:\s+(?:DE\s+)?F'?C\s*=\s*\d+(?:[.,]\d+)?\s*(?:KG/CM2)?\.?)?"
    r"|\s+(?:DE\s+)?F'?C\s*=\s*\d+(?:[.,]\d+)?\s*(?:KG/CM2)?\.?"
)
_MATERIAL = rf"(?P<mat>{_DE_CONCRETO})?"
_MATERIAL_DESPUES = (
    r"(?:\s+DE\s+CONCRETO(?:\s+(?:POBRE|SIMPLE|CICLOPEO))?"
    r"(?:\s+(?:DE\s+)?F'?C\s*=\s*\d+(?:[.,]\d+)?\s*(?:KG/CM2)?\.?)?"
    r"|\s+CONCRETO\s+F'?C\s*=\s*\d+(?:[.,]\d+)?\s*(?:KG/CM2)?\.?"
    r"|\s+(?:DE\s+)?F'?C\s*=\s*\d+(?:[.,]\d+)?\s*(?:KG/CM2)?\.?)?"
)
# Dónde va la plantilla, antes o después de ella: «BAJO LA CIMENTACION SE COLOCARA PLANTILLA…»,
# «TODA CIMENTACION SE DESPLANTARA SOBRE UNA PLANTILLA…», «… BAJO ZAPATAS», «… A LAS
# PROFUNDIDADES INDICADAS».
_BAJO = (
    r"(?:\s+BAJO\s+(?:(?:LA|LAS|LOS|TODA\s+LA|TODAS\s+LAS)\s+)?"
    r"(?:CIMENTACION|ZAPATAS?|CONTRATRABES?|LOSAS?\s+DE\s+CIMENTACION)"
    r"|\s+A\s+LAS\s+PROFUNDIDADES\s+INDICADAS)?"
)
_SE_COLOCA_PLANTILLA = (
    r"(?:BAJO\s+(?:(?:LA|LAS|LOS|TODA\s+LA|TODAS\s+LAS)\s+)?"
    r"(?:CIMENTACION|ZAPATAS?|CONTRATRABES?|LOSAS?\s+DE\s+CIMENTACION)\s+)?"
    r"(?:SE\s+COLOCARAN?\s+(?:UNA\s+)?"
    r"|(?:TODA\s+(?:LA\s+)?)?CIMENTACION\s+SE\s+DESPLANTARA\s+SOBRE\s+(?:UNA\s+)?)?"
)
_ESPESOR = r"(?P<esp>\s+(?:DE\s+)?(?:ESPESOR|ESP\b\.?))"


# Los recubrimientos: «5.0 CM EN ELEMENTOS ESTRUCTURALES DE CIMENTACION», «4.0 CM EN TRABES Y
# LOSAS», «3.0 A 5.0 CM EN CASTILLOS, CADENAS, DALAS Y CERRAMIENTOS», «COLUMNAS: 5 CM». Un elemento
# de la lista es uno conocido o una palabra que no se reconoce (se avisa); nada más cabe en ella.
MIEMBRO_CONOCIDO = (
    r"ELEMENTOS\s+(?:ESTRUCTURALES\s+)?DE\s+CIMENTACION|LOSAS?\s+DE\s+CIMENTACION"
    r"|(?:TRABES?|VIGAS?)\s+DE\s+CIMENTACION"
    r"|(?:ZAPATAS?|DADOS?|PILOTES?|CONTRATRABES?)(?:\s+DE\s+CIMENTACION)?|CIMENTACION"
    r"|TRABES?|VIGAS?|COLUMNAS?|LOSAS?|MUROS?\s+DE\s+(?:CONCRETO|CONTENCION)|CASTILLOS?|CADENAS?"
    r"|DALAS?|CERRAMIENTOS?"
)
# (Ni lo que acota o condiciona la regla: «4 CM EN TRABES, OPCIONALMENTE» no nombra un elemento.)
_NO_ES_UN_MIEMBRO = (
    r"(?:EN|DE|DEL|LA|LAS|LOS|EL|Y|E|O|CON|SIN|MAS|MENOS|NO|NI|A|AL|POR|PARA|CMS?|MTS?|LIBRES?"
    r"|SERAN?|QUE|SALVO|EXCEPTO|TAMBIEN|COMO|MITAD|DOBLE|SOLO|SOLAMENTE|UNICAMENTE|EXCLUSIV\w*"
    r"|OPCIONAL\w*|PREFEREN\w*|IGUAL\w*|TODOS?|TODAS?|DEMAS|RESTO|MAYOR(?:ES)?|MENOR(?:ES)?"
    r"|SUPERIORES|INFERIORES|CUANDO|PREVIA|APLICA\w*|VALID\w*|CORRESPONDE\w*|REFERID\w*"
    r"|TRATANDOSE|VICEVERSA|SEGUN|SIEMPRE|MINIMOS?|MAXIMOS?|PROMEDIO|TIPICOS?)\b"
)
_MIEMBRO = (
    rf"(?:(?:LOS|LAS)\s+)?(?:{MIEMBRO_CONOCIDO}"
    rf"|(?!{_NO_ES_UN_MIEMBRO})[A-Z]{{3,}}(?:\s+DE\s+(?!{_NO_ES_UN_MIEMBRO})[A-Z]{{3,}})?)"
)
MIEMBROS = rf"{_MIEMBRO}(?:\s*,\s*{_MIEMBRO}|\s+(?:Y|E)\s+{_MIEMBRO})*"
# Una medida de recubrimiento: «5.0 CM», «3.0 A 5.0 CM», «0.05 M».
MEDIDA = rf"(?P<n>{_NUM})(?:\s*A\s*(?P<m>{_NUM}))?\s*(?P<u>CMS?|MTS?|M)\b\.?"
_MEDIDA_SIN_NOMBRES = rf"{_NUM}(?:\s*A\s*{_NUM})?\s*(?:CMS?|MTS?|M)\b\.?"
# Un renglón de la lista: la medida y luego sus elementos («4.0 CM EN TRABES Y LOSAS»). (El
# elemento antes de la medida, «COLUMNAS 3 CM», no se lee: tras una lista con comas no se sabe de
# qué elementos es cada medida.)
EN_SUS_ELEMENTOS = r"\s+(?:LIBRES?\s+)?EN\s+"
_UN_RECUBRIMIENTO = rf"{_MEDIDA_SIN_NOMBRES}{EN_SUS_ELEMENTOS}{MIEMBROS}"
_RECUBRIMIENTOS = (
    rf"(?P<items>{_UN_RECUBRIMIENTO}"
    rf"(?:(?:\s*,\s*|\s+(?:Y|E)(?:\s+TAMBIEN)?\s+|\s+){_UN_RECUBRIMIENTO})*)"
)
# «EL RECUBRIMIENTO MINIMO LIBRE, NO SERA MENOR QUE EL DIAMETRO DEL REFUERZO LONGITUDINAL NI
# MENOR A:», «RECUBRIMIENTO LIBRE:», «EL RECUBRIMIENTO MINIMO SERA»: lo que va antes de la lista.
# («NO SERA MENOR QUE» dice el mínimo: no niega.)
_ANTES_DEL_RECUBRIMIENTO = (
    r"(?:(?:EL|LOS)\s+)?RECUBRIMIENTOS?(?:\s+MINIMOS?)?(?:\s+LIBRES?)?"
    r"(?:\s+DEL?\s+(?:LAS\s+|LOS\s+)?(?:VARILLAS|REFUERZO))?\s*,?\s*"
    r"(?:SERAN?(?:\s+DE)?|DE|NO\s+SERA\s+MENOR\s+(?:QUE|DE|A)"
    r"(?:\s+EL\s+DIAMETRO\s+DEL\s+REFUERZO(?:\s+LONGITUDINAL)?\s*,?\s*NI\s+MENOR\s+(?:A|DE|QUE))?)?"
    r"\s*[:,]?\s*"
)


@dataclass(frozen=True)
class FraseConocida:
    """Una frase que se sabe leer: la regla que dice y su patrón, que tiene que cubrir el trozo
    entero. ``sola``: no lleva verbo, así que sólo vale si es la oración entera."""

    regla: str
    patron: re.Pattern[str]
    sola: bool = False


def _p(regla: str, patron: str, *, sola: bool = False) -> FraseConocida:
    return FraseConocida(regla, re.compile(patron + _CONTEXTO), sola)


FRASES_CONOCIDAS: tuple[FraseConocida, ...] = (
    # --- traslape: hasta qué varilla se traslapa -------------------------------------------
    _p("traslape", rf"{_ADV}{_SOLO}{_PERMITE}\s+TRASLAPAR\s+(?:(?:LA|LAS)\s+)?{_HASTA}"),
    _p("traslape", rf"{_ADV}{_SOLO}{_SE_TRASLAPA}\s+(?:(?:LA|LAS)\s+)?{_HASTA}"),
    _p("traslape", rf"{_ADV}(?:(?:LA|LAS)\s+)?{_HASTA}\s+{_SE_TRASLAPA}"),
    _p(
        "traslape",
        rf"{_ADV}(?:LOS\s+)?TRASLAPES\s+(?:SE\s+PERMIT(?:EN|IRAN)|SE\s+HARAN|SERAN\s+PERMITIDOS)"
        rf"\s+(?:EN\s+(?:LAS\s+)?VARILLAS\s+)?{_HASTA}",
    ),
    _p(
        "traslape",
        rf"{_ADV}{_SOLO}(?:{_PERMITE}\s+TRASLAPAR|{_SE_TRASLAPA})\s+(?:(?:LA|LAS)\s+)?VARILLAS?\s+"
        rf"{_RANGO}{_COLA}",
    ),
    _p(
        "traslape",
        rf"{_ADV}EL\s+TRASLAPE\s+MAXIMO\s+SERA\s+(?:(?:CON|DE|EN)\s+)?(?:(?:LAS\s+)?VARILLAS?\s+)?"
        rf"(?:(?P<pre_b>DEL|HASTA)\s+)?{_barra('b')}",
    ),
    # --- soldadura: desde qué varilla se suelda --------------------------------------------
    _p(
        "soldar",
        rf"{_ADV}(?:(?:LAS|LOS)\s+)?{_DESDE_UN}\s+(?:Y|O)\s+"
        rf"(?:(?:DIAMETROS|VARILLAS)\s+)?MAYORES\s+{_SE_SUELDA}{_A_TOPE}",
    ),
    _p(
        "soldar",
        rf"{_ADV}(?:(?:LAS|LOS)\s+)?{_DESDE_UN}\s+EN\s+ADELANTE\s+{_SE_SUELDA}"
        rf"{_A_TOPE}",
    ),
    _p(
        "soldar",
        rf"{_ADV}(?P<pre_b>A\s+PARTIR\s+DEL?|DESDE)\s+{_barra('b')}(?:\s*,?\s*INCLUSIVE\s*,?)?\s+"
        rf"{_SE_SUELDA}(?:\s+(?:LAS\s+)?VARILLAS)?{_A_TOPE}",
    ),
    _p(
        "soldar",
        rf"{_ADV}{_SE_SUELDA}\s+(?:(?:LAS|LOS)\s+)?{_DESDE_UN}\s+EN\s+ADELANTE",
    ),
    _p(
        "soldar",
        rf"{_ADV}LA\s+SOLDADURA\s+(?:SE\s+(?:USARA|APLICARA|HARA|EMPLEARA|UTILIZARA|REQUERIRA)"
        rf"|SERA\s+OBLIGATORIA)\s+EN\s+(?:(?:LAS|LOS)\s+)?{_DESDE_UN}\s+EN\s+ADELANTE",
    ),
    # «VARILLAS DEL No. 7 AL No. 12 SE SOLDARAN»: desde el de abajo, si el de arriba es el #12.
    _p(
        "soldar_rango",
        rf"{_ADV}(?:(?:LAS|LOS)\s+)?VARILLAS?\s+{_RANGO}(?:\s+INCLUSIVE)?\s+{_SE_SUELDA}{_A_TOPE}",
    ),
    _p("soldar_rango", rf"{_ADV}{_SE_SUELDA}\s+(?:(?:LAS|LOS)\s+)?VARILLAS?\s+{_RANGO}"),
    # --- el primer estribo, con las familias a las que se aplica ---------------------------
    _p(
        "primer_estribo",
        rf"{_ADV}(?:EN\s+(?P<fam>{_FAMILIAS})\s*,?\s+)?(?:EL\s+)?PRIMER\s+ESTRIBO\s+"
        rf"(?:(?:EN|DE)\s+(?P<fam2>{_FAMILIAS})\s+)?{_VERBO_DEL_PRIMER}\s+{_A_CM}",
    ),
    _p(
        "primer_estribo",
        rf"{_ADV}(?:EN\s+(?P<fam>{_FAMILIAS})\s*,?\s+)?LA\s+SEPARACION\s+DE\s+(?:LOS\s+)?ESTRIBOS\s+"
        r"(?:EMPEZARA|COMENZARA|INICIARA|SE\s+INICIARA|SE\s+MEDIRA|SE\s+CONTARA)\s+A\s+PARTIR\s+"
        r"DEL\s+PANO(?:\s+DE\s+(?:LOS|LAS)\s+(?:APOYOS|COLUMNAS|TRABES|NUDOS))?\s*,?\s+"
        rf"COLOCANDO\s+EL\s+PRIMER\s+ESTRIBO\s+{_A_CM}",
    ),
    # --- ganchos de estribos y grapas -------------------------------------------------------
    _p(
        "gancho_par",
        rf"{_ADV}EL\s+ANCLAJE\s+DE\s+{_quien('q1')}\s+Y\s+{_quien('q2')}\s+SE\s+HARA\s+CON\s+"
        rf"{_GANCHO}{_angulo('a1')}\s*Y\s*{_angulo('a2')}(?:\s*,?\s*RESPECTIVAMENTE)?{_TRAMO}",
    ),
    _p(
        "gancho_par",
        rf"{_ADV}{_quien('q1')}\s+Y\s+{_quien('q2')}\s+{_LLEVAN}\s+{_GANCHO}{_angulo('a1')}\s*Y\s*"
        rf"{_angulo('a2')}(?:\s*,?\s*RESPECTIVAMENTE)?{_TRAMO}",
    ),
    _p(
        "gancho_dos",
        rf"{_ADV}{_quien('q1')}{_DATOS_DEL_ESTRIBO}\s+{_LLEVAN}\s+{_GANCHO}{_angulo('a1')}\s+Y\s+"
        rf"{_quien('q2')}\s+(?:(?:A|DE|CON)\s+)?(?:{_GANCHO})?{_angulo('a2')}{_TRAMO}",
    ),
    _p(
        "gancho",
        rf"{_ADV}{_quien('q1')}{_DATOS_DEL_ESTRIBO}\s+{_LLEVAN}\s+{_GANCHO}{_angulo('a1')}{_TRAMO}",
    ),
    _p(
        "gancho",
        rf"{_ADV}{_quien('q1')}{_DATOS_DEL_ESTRIBO}\s+SE\s+COLOCARAN\s+(?:@|A\s+CADA|CADA)\s*"
        rf"\d+(?:[.,]\d+)?\s*CMS?\b\.?\s+(?:CON|Y\s+(?:TENDRAN|LLEVARAN))\s+{_GANCHO}"
        rf"{_angulo('a1')}{_TRAMO}",
    ),
    _p(
        "gancho",
        rf"{_quien('q1')}{_DATOS_DEL_ESTRIBO}\s+CON\s+{_GANCHO}{_angulo('a1')}{_TRAMO}",
        sola=True,
    ),
    _p("tramo", rf"(?:(?:Y|CON|SEGUIDOS?\s+DE|MAS)\s+)?(?:UN\s+)?TRAMO\s+{_RECTO}"),
    # --- plantilla --------------------------------------------------------------------------
    _p(
        "plantilla",
        rf"{_SE_COLOCA_PLANTILLA}PLANTILLA{_MATERIAL}\s*,?\s+(?:DE\s+|CON\s+)?(?P<n>{_NUM})\s*"
        rf"{_UNIDAD}{_ESPESOR}?"
        rf"(?(esp)(?:\s+Y\s+{_NUM}\s*(?:CMS?|MTS?|M)\b\.?\s+DE\s+(?:VOLADO|ANCHO|LARGO))?|)"
        rf"{_MATERIAL_DESPUES}{_BAJO}",
    ),
    _p(
        "plantilla",
        rf"{_SE_COLOCA_PLANTILLA}PLANTILLA{_MATERIAL}\s*,?\s+(?:CON\s+)?(?:UN\s+)?ESPESOR\s+"
        rf"(?:DE\s+)?(?P<n>{_NUM})\s*{_UNIDAD}{_MATERIAL_DESPUES}{_BAJO}",
    ),
    _p(
        "plantilla",
        rf"{_SE_COLOCA_PLANTILLA}PLANTILLA{_MATERIAL}\s+DE\s+{_NUM}\s*(?:CMS?|MTS?|M)\b\.?\s+DE\s+"
        rf"(?:VOLADO|ANCHO)\s+Y\s+(?P<n>{_NUM})\s*{_UNIDAD}(?P<esp>\s+DE\s+(?:ESPESOR|ESP\b\.?))",
    ),
    # «PLANTILLA DE CONCRETO F'C = 100 KG/CM2 Y 5.0 CM. DE ESPESOR»: tras el material, con «Y».
    _p(
        "plantilla",
        rf"{_SE_COLOCA_PLANTILLA}PLANTILLA(?P<mat>{_DE_CONCRETO})\s+Y\s+"
        rf"(?P<n>{_NUM})\s*{_UNIDAD}(?P<esp>\s+DE\s+(?:ESPESOR|ESP\b\.?)){_BAJO}",
    ),
    # --- recubrimientos: la lista de medidas y elementos, con lo de antes o sin ello ----------
    _p("recubrimiento", rf"{_ANTES_DEL_RECUBRIMIENTO}{_RECUBRIMIENTOS}"),
    _p("recubrimiento_lista", _RECUBRIMIENTOS),
    # --- lo que no da una regla pero se sabe leer -------------------------------------------
    # La proporción de traslapes o soldaduras por sección (la nota 4 de Marina): no da una varilla.
    _p(
        "inerte",
        r"NO\s+SE\s+(?:PERMITIRA|PERMITE|DEBERA)\s+(?:TRASLAPAR|SOLDAR|ACOPLAR)"
        r"(?:\s+(?:NI|O)\s+(?:TRASLAPAR|SOLDAR|ACOPLAR))*\s+MAS\s+DEL?\s+\d+\s*%\s+DEL\s+"
        r"REFUERZO(?:\s+LONGITUDINAL)?\s+EN\s+UNA\s+(?:MISMA|SOLA)\s+SECCION",
    ),
    # La longitud del traslape que da la tabla: no dice hasta qué varilla.
    _p(
        "inerte",
        r"(?:LA\s+LONGITUD\s+DEL?\s+)?(?:EL\s+)?TRASLAPE\s+SERA\s+(?:SEGUN|DE\s+ACUERDO\s+(?:CON|A))\s+"
        r"(?:LA\s+)?TABLA(?:\s+DE\s+VARILLAS|\s+(?:NO|N[º°])\.?\s*\d+)?",
    ),
    # Dónde va la plantilla, sin su espesor: «BAJO LA CIMENTACION SE COLOCARA PLANTILLA DE CONCRETO
    # POBRE» (el espesor lo dice otra cláusula, o no lo dice).
    _p("inerte", rf"{_SE_COLOCA_PLANTILLA}PLANTILLA{_MATERIAL}{_BAJO}"),
    # Lo que repite la otra mitad de una regla que la nota sí da, sin dar una varilla: «SIN
    # TRASLAPES» junto a lo que se suelda, «NO SE SOLDARA NINGUNA» o «LAS DEMAS SE SOLDARAN» junto a
    # lo que se traslapa.
    _p(
        "acompana_soldar",
        r"SIN\s+TRASLAPES?|NO\s+SE\s+TRASLAPARAN|NO\s+SE\s+PERMIT(?:EN|IRAN)\s+TRASLAPES",
    ),
    _p(
        "acompana_traslape",
        r"NO\s+SE\s+SOLDARAN?(?:\s+NINGUNA(?:\s+VARILLA)?)?|SIN\s+SOLDADURA"
        r"|(?:Y\s+)?LAS\s+DEMAS\s+SE\s+SOLDARAN",
    ),
    # --- anclajes que el plano declara ------------------------------------------------------
    _p(
        "anclaje",
        rf"(?P<n>{_NUM})\s*CMS?\.?\s+(?:DE\s+)?ANCLAJE\s+DE\s+(?:(?:LOS|LAS|EL|LA)\s+)?"
        r"(?P<p>[A-Z]+)",
    ),
    _p(
        "anclaje",
        r"ANCLAJE\s+DE\s+(?:(?:LOS|LAS|EL|LA)\s+)?(?P<p>[A-Z]+)\s*[:=]?\s*"
        rf"(?P<n>{_NUM})\s*CMS?\b\.?",
    ),
)


# --- la varilla de una frase ---------------------------------------------------------------


@dataclass(frozen=True)
class Varilla:
    """La varilla que dice el trozo ``escrito`` de una frase. ``tipo``: ``num`` (un número, con
    marca o con artículo), ``pulg`` (pulgadas), ``fraccion`` (una fracción sin unidad: no se sabe
    si son pulgadas), ``pelado`` (un número sin marca ni artículo donde el texto no dice que es una
    varilla: puede ser una cuenta, no se lee) o ``dos`` (la equivalencia entre paréntesis dice
    otra varilla). ``escrito`` va sin artículo ni nombre."""

    escrito: str
    tipo: str
    pulgadas: str = ""  # lo que se pasa a ``numero_de_varilla`` (``num`` y ``pulg``)
    equivalencia: str = ""


_TOKEN = re.compile(
    r"(?P<art>(?:EL|LA)\s+)?(?P<nombre>VARILLAS?\s+)?(?P<cuerpo>.+?)"
    r"(?:\s*\((?P<eq>[^()]*)\))?"
)
_MARCA = re.compile(r"(?:#\s*|(?:NO|N[º°])\.?\s*|NUMERO\s+|NUM\.?\s*)")
_CON_PULGADAS = re.compile(rf"[{_COMILLAS}]|''|PULG")


def varilla_de(m: re.Match[str], nombre: str, *, con_cola: bool = False) -> Varilla:
    """La varilla del grupo ``nombre`` de una frase. Un número sin marca vale si lo dice un
    artículo o el nombre («EL 6», «VARILLA 6», «VARILLAS DE 8»), si lo antecede una contracción
    («DEL 6», «AL 6») o si el límite nombra a la varilla y la cierra («VARILLA HASTA 6
    INCLUSIVE»). «DIAMETRO 12» no es una varilla: puede ser en milímetros."""
    token = " ".join(m.group(nombre).split())
    partes = _TOKEN.fullmatch(token)
    assert partes is not None
    cuerpo = partes["cuerpo"].strip()
    previo = m.groupdict().get(f"pre_{nombre}") or ""
    equivalencia = (partes["eq"] or "").strip()
    if _CON_PULGADAS.search(cuerpo):
        pulgadas = re.sub(r"\s*PULG(?:ADAS?)?\.?", '"', cuerpo).replace("''", '"')
        return Varilla(cuerpo, "pulg", pulgadas, equivalencia)
    if "/" in cuerpo:
        return Varilla(cuerpo, "fraccion", "", equivalencia)
    marca = _MARCA.match(cuerpo)
    if marca is not None:
        return Varilla(cuerpo[marca.end() :].strip(), "num", "", equivalencia)
    pelado_permitido = (
        partes["art"] is not None
        or partes["nombre"] is not None
        or re.search(r"\b(?:DEL|AL)$", previo) is not None
        or (previo.startswith("VARILLA") and (con_cola or previo.endswith("DE")))
    )
    return Varilla(cuerpo, "num" if pelado_permitido else "pelado", "", equivalencia)


# --- lo que una pieza dice, para decidir si cambia una frase -------------------------------

CLAVES = {
    "traslape": re.compile(r"TRASLAP"),
    "soldar": re.compile(r"SOLDA"),
    "estribo": re.compile(r"ESTRIBO"),
    "grapa": re.compile(r"GRAPA"),
    "plantilla": re.compile(r"PLANTILLA"),
    "recubrimiento": re.compile(r"RECUBRIMIENTO"),
    "gancho": re.compile(r"GANCHO|DOBLE[ZC]"),
}
# De qué hablan las frases de cada regla: otra pieza que habla de lo mismo con un número la acota.
TEMAS = {
    "traslape": {"traslape"},
    "soldar": {"soldar"},
    "soldar_rango": {"soldar"},
    "primer_estribo": {"estribo"},
    "gancho": set(),  # de quien la frase nombra: ver ``_temas_de_la_frase``
    "gancho_par": {"estribo", "grapa"},
    "gancho_dos": {"estribo", "grapa"},
    "tramo": set(),
    "plantilla": {"plantilla"},
    "anclaje": set(),
    "recubrimiento": {"recubrimiento"},
    "recubrimiento_lista": {"recubrimiento"},
    "inerte": set(),
    "acompana_soldar": set(),
    "acompana_traslape": set(),
}
# Las reglas que van por familia: otro elemento u otro número no las cambia (es de otra familia).
POR_FAMILIA = frozenset({"primer_estribo", "recubrimiento", "recubrimiento_lista"})
# Lo que no da una regla: vale aunque niegue, si la otra mitad que acompaña se leyó y la nota no
# lee también la regla que niega o recorta («… HASTA EL #6, DEL #8 EN ADELANTE SE SOLDARAN, NO SE
# SOLDARA NINGUNA» se desmiente). (la que acompaña, la suya)
_ACOMPANA = {
    "acompana_soldar": (("soldar", "soldar_rango"), ("traslape",)),
    "acompana_traslape": (("traslape",), ("soldar", "soldar_rango")),
}
# Lo que acompaña diciendo que el resto se suelda («Y LAS DEMAS SE SOLDARAN») contra lo que dice
# que no se suelda ninguna («NO SE SOLDARA NINGUNA», «SIN SOLDADURA»): juntas, la nota se desmiente.
_LAS_DEMAS = re.compile(r"\bDEMAS\b")
# Una excepción a lo que se dice: «SALVO…», «EXCEPTO…», «… PERO…».
EXCEPCION = re.compile(
    r"\b(?:SALVO|EXCEPTO|EXCEPCION|EXCEPTUANDO|EXCLUYENDO|MENOS\s+EN|PERO|AUNQUE)\b"
)
# Un elemento o una parte de la estructura: en una cláusula o un encabezado, acota la regla.
ELEMENTO = re.compile(
    r"\b(?:CONTRATRABES?|TRABES?|VIGAS?|COLUMNAS?|CASTILLOS?|DALAS?|CADENAS?|CERRAMIENTOS?"
    r"|ZAPATAS?|DADOS?|PILOTES?|LOSAS?|MUROS?|NUDOS?|NERVADURAS?|MARCOS?|PILAS?|ENTREPISOS?"
    r"|AZOTEAS?|ELEMENTOS?\s+SECUNDARIOS?|SUPERESTRUCTURAS?)\b"
)
# Una pieza que empieza así acota lo que sigue («EN COLUMNAS,», «PARA TRASLAPES EN…,», «SI…»).
_ACOTA = re.compile(
    r"(?:EN|PARA|POR|SOBRE|CON|DE|DESDE|HASTA|A|AL|DEL|DENTRO|FUERA|CUANDO|SI|SALVO|EXCEPTO"
    r"|MENOS|ENTRE|SEGUN|TRATANDOSE)\b"
)
# Una pieza que no cambia lo que dicen las demás.
_NEUTRA = re.compile(
    r"(?:"
    r"SALVO\s+(?:INDICACION(?:\s+EN\s+CONTRARIO)?|(?:QUE|DONDE)\s+SE\s+INDIQUE\s+(?:OTRA\s+COSA"
    r"|LO\s+CONTRARIO))"
    r"|EXCEPTO\s+(?:DONDE|CUANDO)\s+SE\s+INDIQUE\s+(?:OTRA\s+COSA|LO\s+CONTRARIO)"
    r"|SI\s+NO\s+SE\s+(?:INDICA|HACE|ESPECIFICA)\s+(?:OTRA\s+(?:COSA|INDICACION)|LO\s+CONTRARIO)"
    r"|A\s+MENOS\s+QUE\s+SE\s+INDIQUE\s+(?:OTRA\s+COSA|LO\s+CONTRARIO)"
    r"|SIN\s+EMBARGO|NO\s+OBSTANTE|ADEMAS|ASIMISMO|POR\s+LO\s+TANTO|EN\s+GENERAL"
    r"|EN\s+TODOS\s+LOS\s+CASOS|RESPECTIVAMENTE|NOTA|IMPORTANTE|OBSERVACION(?:ES)?"
    rf"|(?:COMO\s+(?:LO\s+|SE\s+)?(?:INDICAN?|MUESTRAN?|ILUSTRAN?|ESPECIFICAN?)\s+(?:EN\s+)?"
    rf"(?:LA|EL|LOS|LAS)\s+|(?:VER|SEGUN)\s+(?:(?:LA|EL)\s+)?){_DONDE}"
    # la resistencia del concreto o del acero (el «F'C=100 KG/CM2» de la plantilla de Marina): no
    # dice una regla ni acota ninguna
    r"|(?:CONCRETO\s+(?:POBRE\s+)?)?F'?[CY]\s*=\s*\d+(?:[.,]\d+)?"
    r"\s*(?:KGF?\s*/\s*CM\s*(?:2|\^2)|MPA)?"
    r")\.?"
)
# Un número que no puede ser una varilla, un ángulo ni una medida de la regla: un porcentaje,
# veces el diámetro, una resistencia, el número de una tabla o figura, parte de un nombre (LT1).
_NUMERO = re.compile(r"(?<![A-Z0-9',/=-])\d+(?:[.,]\d+)?")
_NO_CUENTA_ANTES = re.compile(
    r"(?:TABLA|NOTA|FIG(?:URA)?|DET(?:ALLE)?|PLANO|HOJA|ART(?:ICULO)?|INCISO|SECCION|NORMA)"
    r"\s*(?:(?:NO|N[º°])\.?\s*)?$|F'?[CY]\s*=\s*$"
)
_NO_CUENTA_DESPUES = re.compile(r"\s*(?:%|POR\s*CIENTO|VECES|[Ø⌀]|DIAMETROS?|KG|\.?-)")


def numeros_libres(texto: str) -> list[re.Match[str]]:
    """Los números de ``texto`` que pueden decir una regla: no un porcentaje, ni las veces del
    diámetro, ni una resistencia, ni el número de una tabla o figura, ni parte de un nombre."""
    libres = []
    for m in _NUMERO.finditer(texto):
        if _NO_CUENTA_ANTES.search(texto[max(0, m.start() - 16) : m.start()]):
            continue
        if _NO_CUENTA_DESPUES.match(texto, m.end()):
            continue
        libres.append(m)
    return libres


def es_neutra(texto: str) -> bool:
    return _NEUTRA.fullmatch(texto.strip(" .")) is not None


def temas_de(texto: str) -> set[str]:
    """De qué reglas habla un texto: traslape, soldar, estribo, grapa, plantilla…"""
    return {tema for tema, clave in CLAVES.items() if clave.search(texto)}


# --- la lectura ----------------------------------------------------------------------------


@dataclass
class Frase:
    """Una frase conocida que cubre las piezas ``desde``…``hasta`` de su oración. ``m`` es el
    patrón sobre ``texto[inicio:fin]``; ``valida`` dice si nada de la oración la cambia."""

    conocida: FraseConocida
    m: re.Match[str]
    inicio: int
    fin: int
    oracion: int
    desde: int
    hasta: int
    valida: bool = True

    @property
    def regla(self) -> str:
        return self.conocida.regla

    def lugar(self, grupo: str) -> tuple[int, int]:
        """Dónde está el grupo ``grupo`` en el texto."""
        a, b = self.m.span(grupo)
        return self.inicio + a, self.inicio + b


@dataclass
class Oracion:
    """Una oración con sus piezas. ``dudosa``: empezó tras el punto de una medida con un conector
    (quizá sigue la anterior); ``colgada``: no nombra ninguna regla (quizá comenta la anterior)."""

    inicio: int
    fin: int
    piezas: list[Pieza]
    dudosa: bool
    colgada: bool = False


@dataclass
class Lectura:
    """Lo que se leyó de un texto: las frases (``valida`` dice cuáles valen), las oraciones con
    sus piezas, el texto que se leyó (sin las referencias metidas) y ese texto con lo leído en
    blanco (``resto``), sobre el que se busca lo que no se entendió."""

    texto: str
    oraciones: list[Oracion]
    frases: list[Frase] = field(default_factory=list)
    resto: str = ""

    def validas(self, *reglas: str) -> list[Frase]:
        return [f for f in self.frases if f.valida and (not reglas or f.regla in reglas)]

    def oracion_de(self, posicion: int) -> int:
        """La oración en la que está ``posicion`` (o la última que empieza antes)."""
        return max((k for k, o in enumerate(self.oraciones) if o.inicio <= posicion), default=0)

    def oracion_extendida(self, k: int) -> tuple[int, int]:
        """La oración ``k`` y, si empezó tras un corte dudoso, la anterior con ella."""
        o = self.oraciones[k]
        inicio = self.oraciones[k - 1].inicio if o.dudosa and k > 0 else o.inicio
        return inicio, o.fin


def _recortar(texto: str, a: int, b: int) -> tuple[int, int]:
    """El trozo sin espacios ni puntos al final, ni un «)» que no abre nada."""
    while b > a and texto[b - 1] in " .":
        b -= 1
    if b > a and texto[b - 1] == ")" and texto[a:b].count("(") < texto[a:b].count(")"):
        b -= 1
        while b > a and texto[b - 1] in " .":
            b -= 1
    return a, b


_ABRE_UNA_PARTE = re.compile(
    r"(?:NO\b(?!\s*\.?\s*[\d#])|NI\b|SE\b|DEL\b|DE\s+LA\b|DESDE\b|A\s+PARTIR\b|HASTA\b|LAS\b|LOS\b"
    r"|LA\b|EL\b|EN\b|PARA\b)"
)
_Y = re.compile(r"\s+(?:Y|E)\s+")


def _admisible(f: Frase) -> bool:
    """Lo que una frase dice tiene la forma de su regla (lo demás no es una frase conocida)."""
    m = f.m
    if f.regla in ("traslape", "soldar", "soldar_rango"):
        for nombre in ("a", "b"):
            if m.groupdict().get(nombre) is None:
                continue
            con_cola = nombre == "b" and m.groupdict().get("cola") is not None
            if varilla_de(m, nombre, con_cola=con_cola).tipo == "pelado":
                return False
    if f.regla in ("gancho_par", "gancho_dos"):
        if m["q1"][:5] == m["q2"][:5]:
            return False
    if f.regla == "plantilla" and m["u"].startswith("M") and m["u"] != "MM":
        # En metros, sólo si la medida va pegada a la palabra o dice que es el espesor.
        if "esp" in m.re.groupindex and m["mat"] and not m["esp"]:
            return False
    return True


def _buscar(texto: str, a: int, b: int, permitidas: frozenset[str], *, sola: bool) -> Frase | None:
    a, b = _recortar(texto, a, b)
    trozo = texto[a:b]
    for conocida in FRASES_CONOCIDAS:
        if conocida.regla not in permitidas or (conocida.sola and not sola):
            continue
        m = conocida.patron.fullmatch(trozo)
        if m is None:
            continue
        frase = Frase(conocida, m, a, b, -1, -1, -1)
        if _admisible(frase):
            return frase
    return None


def _coordinadas(
    texto: str, pieza: Pieza, permitidas: frozenset[str]
) -> list[tuple[Pieza, Frase | None]] | None:
    """Una cláusula que ninguna frase cubre entera puede ser dos coordinadas con «Y»: la de la
    izquierda, sin negación, una frase conocida, y la de la derecha empieza con su propio sujeto o
    verbo («SE TRASLAPARAN HASTA EL #6 Y NO SE SOLDARA NINGUNA»). Devuelve las partes."""
    for y in _Y.finditer(texto, pieza.inicio, pieza.fin):
        if not _ABRE_UNA_PARTE.match(texto, y.end()):
            continue
        izquierda = _buscar(texto, pieza.inicio, y.start(), permitidas, sola=False)
        if izquierda is None or NEGACION.search(texto, pieza.inicio, y.start()):
            continue
        if izquierda.regla.startswith("recubrimiento"):
            continue  # la lista de recubrimientos ya trae sus «Y»: lo que sigue es de la lista
        derecha = Pieza(y.end(), pieza.fin, pieza.separador)
        frase = _buscar(texto, derecha.inicio, derecha.fin, permitidas, sola=False)
        partes: list[tuple[Pieza, Frase | None]] = [
            (Pieza(pieza.inicio, y.start(), " Y "), izquierda)
        ]
        if frase is not None:
            return [*partes, (derecha, frase)]
        resto = _coordinadas(texto, derecha, permitidas)
        return [*partes, *(resto or [(derecha, None)])]
    return None


def _cubrir(texto: str, oracion: Oracion, k: int, permitidas: frozenset[str]) -> list[Frase]:
    """Las frases de la oración, de izquierda a derecha y la más larga primero. Las piezas de la
    oración quedan partidas donde una coordinada se leyó."""
    piezas = oracion.piezas
    finales: list[Pieza] = []
    frases: list[Frase] = []
    i = 0
    while i < len(piezas):
        hallada = None
        for j in range(len(piezas) - 1, i - 1, -1):
            sola = i == 0 and j == len(piezas) - 1
            frase = _buscar(texto, piezas[i].inicio, piezas[j].fin, permitidas, sola=sola)
            if frase is not None:
                hallada = (j, frase)
                break
        if hallada is not None:
            j, frase = hallada
            frase.oracion, frase.desde, frase.hasta = k, len(finales), len(finales) + j - i
            finales.extend(piezas[i : j + 1])
            frases.append(frase)
            i = j + 1
            continue
        partes = _coordinadas(texto, piezas[i], permitidas)
        for pieza, frase in partes or [(piezas[i], None)]:
            if frase is not None:
                frase.oracion, frase.desde, frase.hasta = k, len(finales), len(finales)
                frases.append(frase)
            finales.append(pieza)
        i += 1
    oracion.piezas = finales
    return frases


def _temas_de_la_frase(f: Frase) -> set[str]:
    if f.regla == "gancho":
        return {"estribo" if f.m["q1"].startswith("ESTRIBO") else "grapa"}
    return TEMAS[f.regla]


def _cambia(trozo: str, temas: set[str], *, por_familia: bool = False) -> bool:
    """Si una pieza que sigue a una frase la cambia: la niega sin nombrar otra regla, hace una
    excepción, o da un número o un elemento sin nombrar otra regla (o de la misma). Para una
    regla por familia (``por_familia``), otro número o elemento es de otra familia: no la cambia."""
    suyos = temas_de(trozo) - {"recubrimiento", "gancho"}
    de_lo_mismo = not suyos or bool(suyos & temas)
    return bool(
        (NEGACION.search(trozo) and not suyos)
        or EXCEPCION.search(trozo)
        or (not por_familia and (numeros_libres(trozo) or ELEMENTO.search(trozo)) and de_lo_mismo)
    )


def _colgada(texto: str, oracion: Oracion) -> bool:
    """Una oración que no nombra ninguna regla propia («NO EN COLUMNAS.», «EXCEPTO EN TRABES.»,
    «NO SE ACEPTARAN.»): puede ser un comentario a la oración de antes."""
    return not (temas_de(texto[oracion.inicio : oracion.fin]) - {"recubrimiento"})


def _vale(lectura: Lectura, f: Frase, cubiertas: set[int], siguiente: Oracion | None) -> bool:
    """Si nada de la oración cambia la frase ``f`` (ver el docstring del módulo). ``siguiente``
    es la oración que la sigue cuando no nombra ninguna regla: también puede cambiarla."""
    texto = lectura.texto
    if f.regla == "inerte":
        return True
    if f.regla in _ACOMPANA:
        otra, suya = _ACOMPANA[f.regla]
        demas = _LAS_DEMAS.search(f.m.group(0)) is not None
        contraria = any(
            g.regla == f.regla and (_LAS_DEMAS.search(g.m.group(0)) is not None) != demas
            for g in lectura.frases
        )
        return bool(lectura.validas(*otra)) and not lectura.validas(*suya) and not contraria
    # La de los recubrimientos trae «NO SERA MENOR QUE»: su lista cerrada no puede negar nada.
    if not f.regla.startswith("recubrimiento") and NEGACION.search(texto, f.inicio, f.fin):
        return False
    oracion = lectura.oraciones[f.oracion]
    piezas = oracion.piezas
    temas = _temas_de_la_frase(f)
    # El tramo recto es el complemento del gancho de su oración: lo de antes es del gancho.
    for i in range(0 if f.regla == "tramo" else f.desde):
        if i in cubiertas:
            continue
        pieza = piezas[i]
        trozo = texto[pieza.inicio : pieza.fin]
        if es_neutra(trozo):
            continue
        suyos = temas_de(trozo) - {"recubrimiento"}
        if (
            not suyos
            or _ACOTA.match(trozo)
            or EXCEPCION.search(trozo)
            or (NEGACION.search(trozo) and pieza.separador == ":")
            or ELEMENTO.search(trozo)
            or (numeros_libres(trozo) and suyos & temas)
        ):
            return False
    # Para una regla por familia, otro número o elemento es de otra familia: sólo cuenta si la
    # niega o la exceptúa (lo demás lo mira la nota entera).
    por_familia = f.regla in POR_FAMILIA
    for i in range(f.hasta + 1, len(piezas)):
        trozo = texto[piezas[i].inicio : piezas[i].fin]
        if i not in cubiertas and not es_neutra(trozo):
            if _cambia(trozo, temas, por_familia=por_familia):
                return False
    # Una oración colgada que sigue la cambia igual que una cláusula: «… HASTA EL #6. NO EN
    # COLUMNAS.», «… CON GANCHOS A 90°. NO SE ACEPTARAN.».
    for pieza in siguiente.piezas if siguiente is not None and f.regla != "tramo" else []:
        trozo = texto[pieza.inicio : pieza.fin]
        if not es_neutra(trozo) and _cambia(trozo, temas, por_familia=por_familia):
            return False
    return True


def leer_frases(texto: str, permitidas: Iterable[str]) -> Lectura:
    """Las frases conocidas de ``texto`` (mayúsculas sin acentos) de las reglas ``permitidas``, y
    el resto sin leer."""
    permitidas = frozenset(permitidas)
    preparado = sin_referencias(texto)
    lectura = Lectura(preparado, [])
    for k, (inicio, fin) in enumerate(oraciones(preparado)):
        oracion = Oracion(
            inicio, fin, clausulas(preparado, inicio, fin), tras_un_corte_dudoso(preparado, inicio)
        )
        oracion.colgada = _colgada(preparado, oracion)
        lectura.oraciones.append(oracion)
        lectura.frases.extend(_cubrir(preparado, oracion, k, permitidas))
    validar(lectura)
    return lectura


def validar(lectura: Lectura) -> None:
    """Decide qué frases valen (``_vale``) y deja ``resto`` al día. Una frase que deja de valer
    descubre su pieza, y las demás se miran de nuevo. Quien quita una frase por su cuenta (pone
    ``valida = False``) vuelve a llamar esto."""
    texto = lectura.texto
    cambio = True
    while cambio:
        cambio = False
        for f in lectura.frases:
            if not f.valida:
                continue
            cubiertas = {
                i
                for g in lectura.frases
                if g.valida and g.oracion == f.oracion
                for i in range(g.desde, g.hasta + 1)
            }
            k = f.oracion + 1
            colgada = k < len(lectura.oraciones) and lectura.oraciones[k].colgada
            siguiente = lectura.oraciones[k] if colgada else None
            if not _vale(lectura, f, cubiertas, siguiente):
                f.valida = False
                cambio = True
    lectura.resto = en_blanco(texto, lectura.validas())


def en_blanco(texto: str, frases: Iterable[Frase]) -> str:
    """``texto`` con las ``frases`` en blanco (mismo largo)."""
    letras = list(texto)
    for f in frases:
        letras[f.inicio : f.fin] = " " * (f.fin - f.inicio)
    return "".join(letras)
