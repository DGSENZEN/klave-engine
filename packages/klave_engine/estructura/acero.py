"""El acero de un elemento desde su armado estructurado, con la fórmula de cada renglón y cada
supuesto dicho.

Las varillas longitudinales son cada grupo (``4#5+2#4`` son dos) por la altura o el claro del
elemento más el anclaje; los estribos, cada juego por cada forma de sus piezas (perimetral, rombo,
interior, grapa, liga), dentro del recubrimiento de la familia como lo dice la hoja del elemento,
más los ganchos de las reglas (2 × ROUNDUP(10Ø), al centímetro: #2 0.14, #3 0.20, #4 0.26), y
acomodados por zona a lo largo del elemento desde el primer estribo (R9: la separación nunca pasa
de la que dice el plano). Lo que se supone (las formas antes de leer el corte, la longitud de los
extremos, el primer estribo, el anclaje) va en ``supuestos``; lo que se usa y alguien tiene que
confirmar (una sección supuesta, un dato en conflicto, uno de la IA) va en ``por_confirmar``; lo
que no se pudo cuantificar (un juego sin separación o sin formas, unos estribos que no se leyeron)
va en ``por_leer``. Nunca se inventa: sin sección, sin longitud o sin varillas longitudinales el
elemento no tiene acero (``acero_elemento`` da ``None`` y ``sin_acero`` dice por qué).

La tabla de varillas del plano no se usa en E0 (anclajes y traslapes por tabla son de E1): sólo se
dice cuándo una varilla que se usa no tiene su fila (``fila_de_varilla``)."""

import math
import re
from typing import Literal

from pydantic import BaseModel, Field

from klave_engine.costing.steel import BAR_KG_PER_M
from klave_engine.estructura.armado import (
    Armado,
    Forma,
    GrupoVarillas,
    JuegoEstribos,
    Zona,
    texto_estribos,
    texto_longitudinal,
)
from klave_engine.estructura.dato import Dato
from klave_engine.estructura.definiciones import asignar_formas
from klave_engine.estructura.elementos import Elemento
from klave_engine.estructura.reglas import (
    RECUBRIMIENTO_SUPUESTO,
    TABLA_ESTANDAR,
    FilaVarilla,
    Reglas,
)

# Las familias que se levantan por planta: su largo es su altura; las demás, su longitud.
_CON_ALTURA = frozenset({"castillo", "columna"})
# Lo que absorbe el ruido de la aritmética de punto flotante al contar (m).
_EPS = 1e-9
_EXTREMOS_MINIMO_M = 0.60
# R212: una sección cuyo lado mayor es al menos este múltiplo del menor es alargada.
_ALARGADA = 2.0


class AceroElemento(BaseModel):
    """El acero de un elemento: kg por número de varilla (sin desperdicio), la fórmula de cada
    renglón, lo supuesto, lo que se usó y hay que confirmar, y lo que no se pudo cuantificar."""

    kg_por_numero: dict[str, float] = Field(default_factory=dict)
    formula: list[str] = Field(default_factory=list)
    supuestos: list[str] = Field(default_factory=list)
    por_confirmar: list[str] = Field(default_factory=list)
    por_leer: list[str] = Field(default_factory=list)
    # R215: el plano no le declara estribos (ni texto sin leer): pesan sólo sus varillas y no es
    # «por leer» (un castillo ahogado).
    sin_estribos_declarados: bool = False

    def total_kg(self) -> float:
        return sum(self.kg_por_numero.values())


def diametro_m(numero: str) -> float:
    """El diámetro nominal de una varilla: su número en octavos de pulgada."""
    return float(numero) / 8 * 0.0254


def _hacia_arriba(valor_m: float) -> float:
    """ROUNDUP al centímetro (como la hoja de la oficina), sin que el ruido de punto flotante
    sume un centímetro (0.10000000001 es 0.10)."""
    return math.ceil(round(valor_m * 100, 6)) / 100


def gancho_m(numero: str, reglas: Reglas, tipo: Literal["estribo", "grapa"]) -> float:
    """Los dos ganchos de una pieza: 2 × ROUNDUP(recto_diametros × Ø) al centímetro, con el tramo
    recto de las reglas (``gancho_estribo`` o ``gancho_grapa``; 10Ø si no lo dicen)."""
    dato = reglas.gancho_estribo if tipo == "estribo" else reglas.gancho_grapa
    valor = dato.valor if isinstance(dato.valor, dict) else {}
    recto = float(valor.get("recto_diametros") or 10)
    return 2 * _hacia_arriba(recto * diametro_m(numero))


def longitud_pieza_m(
    forma: Forma, b_m: float, h_m: float, r_m: float, numero: str, reglas: Reglas, barras: int
) -> float:
    """La longitud de una pieza de estribo dentro del recubrimiento ``r_m``, con sus ganchos:
    perimetral 2(b−2r)+2(h−2r); rombo 2(b−2r)/√2 + 2(h−2r)/√2; interior 2(h−2r) + 2(b−2r)/3 (el
    supuesto de la hoja de la oficina para 12 varillas, que E3 cambia por el corte dibujado);
    grapa o liga, una rama del lado menor. ``barras`` es el total de varillas longitudinales que la
    pieza amarra (las formas se suponen con él; la longitud no cambia en E0). Una sección que no
    cabe en su recubrimiento es ValueError."""
    del barras  # E0: las formas ya lo usaron; E3 lo usará para la interior por las varillas
    bi, hi = b_m - 2 * r_m, h_m - 2 * r_m
    if bi <= 0 or hi <= 0:
        raise ValueError(
            f"sección {b_m * 100:g}x{h_m * 100:g} cm sin lugar para un recubrimiento de "
            f"{r_m * 100:g} cm"
        )
    if forma == "perimetral":
        return 2 * bi + 2 * hi + gancho_m(numero, reglas, "estribo")
    if forma == "rombo":
        return (2 * bi + 2 * hi) / math.sqrt(2) + gancho_m(numero, reglas, "estribo")
    if forma == "interior":
        return 2 * hi + 2 * bi / 3 + gancho_m(numero, reglas, "estribo")
    if forma in ("grapa", "liga"):
        return min(bi, hi) + gancho_m(numero, reglas, "grapa")
    raise ValueError(f"forma de estribo «{forma}» sin fórmula")


def extremos_supuesto_m(b_m: float, h_m: float, longitud_m: float) -> float:
    """La longitud de los extremos (zona de confinamiento, NTC) cuando el plano no la dice:
    max(b, h, L/6, 0.60 m)."""
    return max(b_m, h_m, longitud_m / 6, _EXTREMOS_MINIMO_M)


def _uniforme(longitud_m: float, separacion_m: float, primero_m: float) -> int:
    """El primero a ``primero_m`` de cada extremo y los demás a no más de ``separacion_m`` (R9:
    ``ceil``), contando los dos de los extremos."""
    libre = longitud_m - 2 * primero_m
    if libre <= _EPS:
        return 1
    return math.ceil(libre / separacion_m - _EPS) + 1


def posiciones(
    longitud_m: float, zonas: list[Zona], primer_m: float | None, extremos_m: float
) -> int:
    """Cuántos estribos lleva un elemento de ``longitud_m`` con estas zonas, acomodados (R9):

    - una zona ``todo``: el primero a ``primer_m`` (o s/2) de cada extremo, y ``ceil((L −
      2·primero)/s) + 1``;
    - ``extremos`` + ``centro``: desde el primero cada ``s_ext`` mientras no pase de la longitud de
      los extremos (la que dice la zona, si no ``extremos_m``), igual desde el otro extremo, y al
      centro, estrictamente entre el último de un extremo y el primero del otro, ``ceil(hueco /
      s_c) − 1``. Si los extremos se tocan, todo el elemento va a ``s_ext``.

    Otras zonas (sólo extremos, sin separación) son ValueError: no se cuentan sin saber cómo."""
    if longitud_m <= 0:
        return 0
    if not zonas:
        raise ValueError("sin separación: el plano no la dice")
    tramos = [z.tramo for z in zonas]
    for z in zonas:
        if z.separacion_m is None or z.separacion_m <= 0:
            raise ValueError(f"zona «{z.tramo}» sin separación")
    if tramos == ["todo"]:
        s = float(zonas[0].separacion_m or 0)
        return _uniforme(longitud_m, s, primer_m if primer_m is not None else s / 2)
    if tramos == ["extremos", "centro"]:
        s_ext = float(zonas[0].separacion_m or 0)
        s_c = float(zonas[1].separacion_m or 0)
        primero = primer_m if primer_m is not None else s_ext / 2
        largo_ext = zonas[0].longitud_m if zonas[0].longitud_m is not None else extremos_m
        en_extremo = max(math.floor((largo_ext - primero) / s_ext + _EPS) + 1, 1)
        ultimo = primero + (en_extremo - 1) * s_ext
        hueco = (longitud_m - ultimo) - ultimo
        if hueco <= _EPS:
            return _uniforme(longitud_m, s_ext, primero)
        return 2 * en_extremo + max(math.ceil(hueco / s_c - _EPS) - 1, 0)
    raise ValueError(f"zonas {tramos}: no se sabe acomodarlas")


# --------------------------------------------------------------------------- la tabla de varillas

_COMPLETADAS = re.compile(r";\s*([^;]*?)\s+de la tabla estándar \(supuesto\)")


def fila_de_varilla(numero: str, reglas: Reglas) -> tuple[FilaVarilla | None, str | None]:
    """La fila de la tabla de varillas para ``numero`` y, si no es la del plano, por qué: la de la
    tabla estándar como supuesto (el plano no trae tabla, o su tabla no trae esa varilla) o
    ninguna (ni el plano ni la estándar la traen: #2 y #7). Nunca revienta."""
    tabla = reglas.tabla_varillas
    filas = tabla.valor if isinstance(tabla.valor, dict) else {}
    fila = filas.get(numero)
    if fila is not None:
        fila = fila if isinstance(fila, FilaVarilla) else FilaVarilla.model_validate(fila)
        if tabla.fuente != "cuadro":
            return fila, (
                f"el plano no trae tabla de varillas: la fila del #{numero} es la de la tabla "
                "estándar (supuesto)"
            )
        completadas = {n for m in _COMPLETADAS.finditer(tabla.texto) for n in _numeros(m[1])}
        if numero in completadas:
            return fila, (
                f"la tabla de varillas del plano no trae el #{numero}: se usa la fila de la "
                "tabla estándar (supuesto)"
            )
        return fila, None
    estandar = TABLA_ESTANDAR.get(numero)
    if estandar is not None:
        return estandar.model_copy(), (
            f"la tabla de varillas del plano no trae el #{numero}: se usa la fila de la tabla "
            "estándar (supuesto)"
        )
    donde = "ni la del plano" if tabla.fuente == "cuadro" else "el plano no trae tabla"
    return None, (
        f"la tabla de varillas no trae el #{numero} ({donde}, ni la estándar): en E0 su acero "
        "sólo usa su diámetro y su peso por metro (NMX-B-506), ninguna fila de la tabla"
    )


def _numeros(texto: str) -> list[str]:
    return re.findall(r"#(\d+(?:\.5)?)", texto)


# ------------------------------------------------------------------------------- el elemento


def _largo(e: Elemento) -> Dato | None:
    return e.altura_m if e.familia in _CON_ALTURA else e.longitud_m


def _aviso(e: Elemento, campo: str) -> str | None:
    """El aviso del elemento sobre ``campo`` («longitudinales: el plano lo escribe y no se leyó
    …»), o ``None``."""
    return next((a for a in e.avisos if a.startswith(f"{campo}:")), None)


def _numero(valor: object) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, int | float):
        return None
    return float(valor)


def _lados(dato: Dato | None) -> tuple[float, float] | None:
    """La sección b×h (cm) de un dato, o ``None`` si no es un rectángulo con dos lados."""
    if dato is None or not isinstance(dato.valor, list | tuple) or len(dato.valor) != 2:
        return None
    b, h = (_numero(v) for v in dato.valor)
    if b is None or h is None or b <= 0 or h <= 0:
        return None
    return b, h


def _grupos(dato: Dato | None) -> list[GrupoVarillas]:
    if dato is None or not isinstance(dato.valor, list):
        return []
    return [GrupoVarillas.model_validate(g) for g in dato.valor]


def _juegos(dato: Dato | None) -> list[JuegoEstribos]:
    if dato is None or not isinstance(dato.valor, list):
        return []
    return [JuegoEstribos.model_validate(j) for j in dato.valor]


def sin_acero(e: Elemento) -> list[str]:
    """Por qué un elemento no tiene acero (vacío si lo tiene): sin sección, sin altura o claro, sin
    varillas longitudinales; cada motivo con el aviso del elemento que lo explica, si lo hay."""
    motivos: list[str] = []
    if e.seccion_cm is None or e.seccion_cm.valor is None:
        motivos.append(_aviso(e, "sección") or "sección: el plano no la declara; sin sección")
    largo = _largo(e)
    if largo is None or (_numero(largo.valor) or 0.0) <= 0:
        campo = "altura" if e.familia in _CON_ALTURA else "longitud"
        motivos.append(
            _aviso(e, campo)
            or (largo is not None and largo.ilegible and f"{campo}: ilegible «{largo.texto}»")
            or f"{campo}: sin {campo}"
        )
    if not _grupos(e.longitudinales):
        motivos.append(
            _aviso(e, "longitudinales")
            or (
                f"longitudinales: ilegibles («{e.longitudinales.texto}»)"
                if e.longitudinales is not None and e.longitudinales.ilegible
                else "longitudinales: el plano no las declara"
            )
        )
    return motivos


def motivos_por_leer(e: Elemento) -> list[str]:
    """Todo lo que falta para pesar un elemento sin acero: lo que lo deja sin acero
    (``sin_acero``) y, si tampoco tiene estribos, por qué (para que la oficina vea de una vez
    todo lo que hay que leer)."""
    motivos = sin_acero(e)
    if motivos and not _juegos(e.estribos):
        motivos.append(
            _aviso(e, "estribos")
            or (
                f"estribos: ilegibles («{e.estribos.texto}»)"
                if e.estribos is not None and e.estribos.ilegible
                else "estribos: el plano no los declara"
            )
        )
    return motivos


def _de_la_fuente(campo: str, dato: Dato | None, por_confirmar: list[str]) -> None:
    """Lo que hay que confirmar de un dato que se usa: supuesto, de la IA o en conflicto."""
    if dato is None:
        return
    if dato.fuente == "supuesto":
        adjetivo = "supuesta" if campo in ("sección", "altura", "longitud") else "supuestos"
        por_confirmar.append(f"{campo} {adjetivo}: {dato.texto}" if dato.texto else campo)
    elif dato.fuente == "ia":
        por_confirmar.append(f"{campo} de la IA, por confirmar: {dato.texto}")
    if dato.en_conflicto:
        otros = sorted(
            {
                repr(a.valor)
                for a in dato.alternativas
                if a.valor is not None and a.valor != dato.valor
            }
        )
        por_confirmar.append(
            f"{campo} en conflicto (el plano dice otra cosa en otra hoja o variante"
            + (f": {', '.join(otros)}" if otros else "")
            + f"); se usa {dato.valor!r}"
        )


def _nombre_juego(j: JuegoEstribos) -> str:
    try:
        return texto_estribos(Armado(estribos=[j]))
    except ValueError:
        return f"{j.cantidad} {j.tipo} #{j.numero}"


def acero_elemento(e: Elemento, reglas: Reglas, anclaje_m: float) -> AceroElemento | None:
    """El acero de ``e`` con las reglas de SU hoja (``Reglas.para(e.hoja)``, que el llamador
    guarda por hoja). ``None`` sin sección, sin altura o claro, o sin varillas longitudinales
    (``sin_acero`` dice por qué). Los estribos que no se pueden cuantificar no tumban el
    elemento: quedan en ``por_leer`` y el acero de lo demás cuenta."""
    if sin_acero(e):
        return None
    largo_dato = _largo(e)
    assert largo_dato is not None
    largo = float(largo_dato.valor)
    salida = AceroElemento()
    kg = salida.kg_por_numero
    _de_la_fuente("sección", e.seccion_cm, salida.por_confirmar)
    _de_la_fuente("altura" if e.familia in _CON_ALTURA else "longitud", largo_dato,
                  salida.por_confirmar)  # fmt: skip
    _de_la_fuente("varillas longitudinales", e.longitudinales, salida.por_confirmar)
    _de_la_fuente("estribos", e.estribos, salida.por_confirmar)

    grupos = _grupos(e.longitudinales)
    numeros: list[str] = []
    for g in grupos:
        if g.numero not in BAR_KG_PER_M:
            salida.por_leer.append(f"{g.cantidad}#{g.numero}: varilla sin peso por metro")
            continue
        kgm = BAR_KG_PER_M[g.numero]
        pesa = g.cantidad * (largo + anclaje_m) * kgm
        kg[g.numero] = kg.get(g.numero, 0.0) + pesa
        numeros.append(g.numero)
        salida.formula.append(
            f"{g.cantidad}#{g.numero}: {g.cantidad} × ({largo:.2f} + {anclaje_m:.2f}) m × "
            f"{kgm} kg/m = {pesa:.2f} kg"
        )
    salida.supuestos.append(
        f"supuesto: anclaje de {anclaje_m:.2f} m por varilla longitudinal (el de la tabla de "
        "varillas es de E1)" + _anclaje_declarado(e.familia, reglas)
    )

    _estribos(e, reglas, largo, grupos, salida, numeros)

    for numero in dict.fromkeys(numeros):
        fila, aviso = fila_de_varilla(numero, reglas)
        if aviso is not None and (fila is None or reglas.tabla_varillas.fuente == "cuadro"):
            salida.supuestos.append(f"tabla de varillas: {aviso}")
    return salida


def _anclaje_declarado(familia: str, reglas: Reglas) -> str:
    dato = reglas.anclajes_declarados_m.get(familia)
    if dato is None or _numero(dato.valor) is None:
        return ""
    return (
        f"; el plano declara {float(dato.valor):.2f} m de anclaje de {familia} («{dato.texto}»"
        + (f", {dato.hoja}" if dato.hoja else "")
        + "), que se aplica en E1 con la continuidad de cada varilla"
    )


_RANGO = re.compile(r"(\d+(?:[.,]\d+)?)\s*A\s*(\d+(?:[.,]\d+)?)\s*CMS?\b", re.IGNORECASE)


def _recubrimiento(e: Elemento, reglas: Reglas, salida: AceroElemento) -> float | None:
    """El recubrimiento del elemento (el de su sección dibujada, R212, o el de su familia en su
    hoja); el mínimo de un rango de la nota («3.0 A 5.0 CM») es un supuesto y se dice."""
    dato = e.recubrimiento_m or reglas.recubrimiento_m.get(e.familia)
    if dato is not None and _numero(dato.valor) is not None:
        valor = float(dato.valor)
        if dato.fuente == "supuesto":
            salida.supuestos.append(
                f"supuesto: recubrimiento {valor:.3f} m"
                + (f" ({dato.texto})" if dato.texto else "")
            )
        rango = _RANGO.search(dato.texto or "") if dato.fuente in ("nota", "regla") else None
        if rango is not None and rango[1].replace(",", ".") != rango[2].replace(",", "."):
            salida.supuestos.append(
                f"supuesto: recubrimiento {valor * 100:.1f} cm, el mínimo de «{rango[0].upper()}»"
                " (la nota da un rango; no se tomó un recubrimiento dibujado de su hoja)"
            )
        # R216: lo que el plano acota y no se tomó (una sola esquina, otra hoja, fuera de la nota)
        # queda por confirmar, con el valor que se usa.
        for aviso in e.avisos:
            if aviso.startswith("recubrimiento"):
                salida.por_confirmar.append(f"{aviso} ({valor * 100:g} cm), por confirmar")
        if dato.en_conflicto:
            otros = sorted({f"{float(a.valor) * 100:g}" for a in dato.alternativas
                            if _numero(a.valor) is not None and a.valor != dato.valor})  # fmt: skip
            salida.por_confirmar.append(
                f"recubrimiento en conflicto (el plano dice también {', '.join(otros)} cm); se "
                f"usa {valor * 100:g} cm"
            )
        return valor
    estandar = RECUBRIMIENTO_SUPUESTO.get(e.familia)
    if estandar is not None:
        salida.supuestos.append(
            f"supuesto: recubrimiento {estandar:.3f} m, el estándar de {e.familia}: el plano no "
            "lo dice"
        )
    return estandar


def _estribos(
    e: Elemento,
    reglas: Reglas,
    largo: float,
    grupos: list[GrupoVarillas],
    salida: AceroElemento,
    numeros: list[str],
) -> None:
    """Cada juego por cada forma de sus piezas, acomodado por zona; lo que no se puede cuantificar
    va a ``por_leer`` con su motivo."""
    juegos = _juegos(e.estribos)
    if not juegos:
        motivo = _aviso(e, "estribos") or (
            f"estribos: ilegibles («{e.estribos.texto}»)"
            if e.estribos is not None and e.estribos.ilegible
            else None
        )
        if motivo is None and e.estribos is None and sum(g.cantidad for g in grupos) == 1:
            # R215, R219: una sola varilla sin estribos ni texto suyo sin leer (la forma de un
            # castillo ahogado): el plano no los declara. Cualquier otro sigue «por leer».
            salida.sin_estribos_declarados = True
            return
        salida.por_leer.append(motivo or "estribos: el plano no los declara")
        return
    lados = _lados(e.seccion_cm)
    if lados is None:
        valor = e.seccion_cm.valor if e.seccion_cm is not None else None
        forma = (
            f"no rectangular de {round(float(valor['area_cm2'])):g} cm²"
            if isinstance(valor, dict) and _numero(valor.get("area_cm2")) is not None
            else f"no es un rectángulo b×h ({valor!r})"
        )
        salida.por_leer.append(f"estribos: la sección {forma}; su forma la dirá el corte dibujado")
        return
    b, h = lados[0] / 100, lados[1] / 100
    r = _recubrimiento(e, reglas, salida)
    if r is None:
        salida.por_leer.append(f"estribos: sin recubrimiento para {e.familia}")
        return
    barras = sum(g.cantidad for g in grupos)
    primer_dato = reglas.primer_estribo_m.get(e.familia)
    primer = _numero(primer_dato.valor) if primer_dato is not None else None
    extremos_dichos = False
    por_que = e.seccion_cm.texto if e.seccion_cm is not None else ""
    supuesta = e.seccion_cm is not None and e.seccion_cm.fuente == "supuesto"
    for juego in juegos:
        nombre = _nombre_juego(juego)
        if supuesta and (juego.cantidad > 1 or any(z.tramo != "todo" for z in juego.zonas)):
            # R214, R217: un juego de varias piezas o por zonas no se pesa sobre una sección que
            # el plano no da (sus piezas y sus extremos dependen de ella).
            salida.por_leer.append(
                f"estribos {nombre}: no se pesan sobre una sección supuesta "
                f"({lados[0]:g}x{lados[1]:g} cm: {por_que})"
            )
            continue
        (j,), avisos = asignar_formas([juego], grupos)
        if not j.formas:
            salida.por_leer.append(f"estribos {nombre}: " + (avisos[0] if avisos else "sin formas"))
            continue
        if j.formas_fuente == "supuesto":
            salida.supuestos.append(
                f"supuesto: {nombre} con formas {', '.join(j.formas)} (la práctica del taller; "
                "las dirá el corte dibujado)"
            )
            if j.cantidad in (2, 3) and max(b, h) >= _ALARGADA * min(b, h):
                # R212: en una sección alargada el corte suele dibujar amarres interiores donde
                # la práctica supone un rombo.
                salida.por_confirmar.append(
                    "formas de estribos supuestas en una sección alargada (h/b ≥ 2), por "
                    "confirmar con el corte dibujado (E3): el corte puede traer amarres "
                    "interiores donde se supuso un rombo"
                )
        extremos = extremos_supuesto_m(b, h, largo)
        try:
            n = posiciones(largo, j.zonas, primer, extremos)
        except ValueError as error:
            salida.por_leer.append(f"estribos {nombre}: {error}; no se cuentan")
            continue
        if j.zonas and j.zonas[0].tramo == "extremos" and j.zonas[0].longitud_m is None:
            if not extremos_dichos:
                salida.supuestos.append(
                    f"supuesto: extremos {extremos:.2f} m = max(b, h, L/6, 0.60 m) (NTC): el "
                    "plano no dice su longitud"
                )
                extremos_dichos = True
        s = j.zonas[0].separacion_m or 0.0
        primero = primer if primer is not None else s / 2
        if primer is None:
            salida.supuestos.append(
                f"supuesto: primer estribo a s/2 ({primero * 100:g} cm) del paño: el plano no lo "
                f"dice para {e.familia}"
            )
        kgm = BAR_KG_PER_M.get(j.numero)
        if kgm is None:
            salida.por_leer.append(f"estribos {nombre}: varilla #{j.numero} sin peso por metro")
            continue
        for forma in j.formas:
            try:
                pieza = longitud_pieza_m(forma, b, h, r, j.numero, reglas, barras)
            except ValueError as error:
                salida.por_leer.append(f"estribos {nombre} {forma}: {error}")
                continue
            pesa = n * pieza * kgm
            salida.kg_por_numero[j.numero] = salida.kg_por_numero.get(j.numero, 0.0) + pesa
            numeros.append(j.numero)
            salida.formula.append(
                f"{nombre} {forma}: {n} pzas (primero a {primero:.2f} m) × {pieza:.3f} m × "
                f"{kgm} kg/m = {pesa:.2f} kg"
            )
    salida.supuestos[:] = list(dict.fromkeys(salida.supuestos))


def texto_del_armado(e: Elemento) -> str:
    """El armado del elemento como texto canónico («8#8+4#6 2E#3 EXT@10 CENTRO@20»)."""
    armado = Armado(longitudinales=_grupos(e.longitudinales), estribos=_juegos(e.estribos))
    try:
        return " ".join(p for p in (texto_longitudinal(armado), texto_estribos(armado)) if p)
    except ValueError:
        return " ".join(f"{g.cantidad}#{g.numero}" for g in armado.longitudinales)
