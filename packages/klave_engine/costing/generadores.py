"""Números generadores de estimación: de dónde salió cada cantidad que se cobra.

El generador del presupuesto ya existe y sale del plano: cada cantidad apunta a
las detecciones que la produjeron. Este es el otro, el de obra, y responde a
otra pregunta. No dice qué dibujó el proyectista sino **qué midió el residente
en el campo**, y es lo que una contratante revisa antes de autorizar el pago:
sin generador, una estimación se regresa.

La regla que ordena todo el módulo es de dirección: **la cantidad sale del
generador, no al revés**. Cuando alguien teclea 320 m² y luego anota unas
medidas que suman 297, lo que está mal no es el generador, es la cantidad. Por
eso la diferencia se dice fuerte y con las dos cifras, en vez de ajustarse sola
a la que ya estaba escrita.

Lo segundo es qué se puede multiplicar. Un concepto en m² no tiene altura y uno
en metro lineal no tiene ancho: la unidad decide qué dimensiones participan, y
las que no participan se ignoran aunque vengan capturadas. Lo que **no** se hace
es rellenar con 1.00 la dimensión que falta. Un dato faltante que se vuelve uno
neutro produce un número plausible y equivocado, y ese es peor que un hueco: el
hueco se ve, el número se cobra.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

# Qué dimensiones multiplica cada unidad. Las siete primeras son las que
# aparecen en los catálogos ya importados; las demás son abreviaturas de uso
# corriente que van a llegar. Fuera de esta tabla la línea se captura con su
# medida directa: quedarse fuera no rompe nada, sólo pide el número a mano.
DIMENSIONES: dict[str, tuple[str, ...]] = {
    "m": ("largo",),
    "ml": ("largo",),
    "m2": ("largo", "ancho"),
    "m²": ("largo", "ancho"),
    "m3": ("largo", "ancho", "alto"),
    "m³": ("largo", "ancho", "alto"),
    "kg": (),
    "ton": (),
    "pza": (),
    "pieza": (),
    "pz": (),
    "lote": (),
    "jgo": (),
    "sal": (),
    "jor": (),
}

# Debajo de esto la diferencia es redondeo de cinta métrica, no un error.
TOLERANCIA = 0.005


def dimensiones_de(unit: str) -> tuple[str, ...] | None:
    """Qué dimensiones multiplica esta unidad, o None si no se reconoce."""
    return DIMENSIONES.get(unit.strip().lower())


class LineaGenerador(BaseModel):
    """Una medición de campo: dónde, cuántas veces y de qué tamaño.

    ``medida_directa`` es para lo que no se calcula multiplicando —kilos de
    acero de una lista de habilitado, piezas contadas—: se captura el número y
    se acabó. Si viene, manda sobre las dimensiones."""

    ubicacion: str = ""
    # Elementos iguales en esa ubicación: 4 zapatas del mismo tipo, un tramo.
    veces: float = 1.0
    largo: float | None = None
    ancho: float | None = None
    alto: float | None = None
    medida_directa: float | None = None
    nota: str = ""


@dataclass
class LineaCalculada:
    """Una línea con su resultado y, si no lo tiene, con la razón."""

    linea: LineaGenerador
    unidad: str
    medida: float | None = None
    formula: str = ""
    falta: tuple[str, ...] = ()

    @property
    def completa(self) -> bool:
        return self.medida is not None


@dataclass
class ResumenGenerador:
    """Lo que suma el generador contra lo que dice cobrarse."""

    unidad: str
    lineas: list[LineaCalculada] = field(default_factory=list)
    total: float = 0.0
    cantidad_capturada: float = 0.0
    avisos: list[str] = field(default_factory=list)

    @property
    def incompletas(self) -> int:
        return sum(1 for ln in self.lineas if not ln.completa)

    @property
    def diferencia(self) -> float:
        return round(self.total - self.cantidad_capturada, 4)

    @property
    def cuadra(self) -> bool:
        """Cuadra sólo si todo se pudo calcular y la suma coincide.

        Un generador con líneas incompletas no cuadra aunque las que sí se
        calcularon den el número: el faltante podría ser justo lo que sobra."""
        return self.incompletas == 0 and abs(self.diferencia) <= TOLERANCIA


def _calcular_linea(linea: LineaGenerador, unidad: str) -> LineaCalculada:
    dims = dimensiones_de(unidad)
    calc = LineaCalculada(linea=linea, unidad=unidad)

    if linea.medida_directa is not None:
        calc.medida = round(linea.medida_directa * linea.veces, 4)
        calc.formula = (
            f"{linea.veces:g} × {linea.medida_directa:g}"
            if linea.veces != 1
            else f"{linea.medida_directa:g}"
        )
        return calc

    if dims is None:
        calc.falta = ("medida_directa",)
        return calc

    if not dims:
        # Unidad sin dimensiones (pza, kg, lote): la medida es la cuenta.
        calc.medida = round(linea.veces, 4)
        calc.formula = f"{linea.veces:g}"
        return calc

    valores = {d: getattr(linea, d) for d in dims}
    faltantes = tuple(d for d, v in valores.items() if v is None)
    if faltantes:
        # Aquí es donde estaría la tentación de poner 1.00 y seguir.
        calc.falta = faltantes
        return calc

    producto = linea.veces
    for d in dims:
        producto *= float(valores[d] or 0)
    calc.medida = round(producto, 4)
    partes = [f"{float(valores[d] or 0):g}" for d in dims]
    if linea.veces != 1:
        partes.insert(0, f"{linea.veces:g}")
    calc.formula = " × ".join(partes)
    return calc


def calcular(
    lineas: list[LineaGenerador], unidad: str, cantidad_capturada: float
) -> ResumenGenerador:
    """El generador calculado y confrontado contra la cantidad que se cobra."""
    res = ResumenGenerador(unidad=unidad, cantidad_capturada=cantidad_capturada)
    res.lineas = [_calcular_linea(ln, unidad) for ln in lineas]
    res.total = round(sum(ln.medida or 0.0 for ln in res.lineas), 4)

    if dimensiones_de(unidad) is None and lineas:
        res.avisos.append(
            f"La unidad «{unidad}» no tiene una fórmula conocida, así que cada línea se "
            "captura con su medida directa. El motor no va a suponer cómo se multiplica."
        )

    if res.incompletas:
        sin_dato = sorted({d for ln in res.lineas for d in ln.falta})
        res.avisos.append(
            f"{res.incompletas} de {len(res.lineas)} línea"
            f"{'s' if len(res.lineas) > 1 else ''} no se "
            f"{'pueden' if res.incompletas > 1 else 'puede'} calcular: falta "
            f"{', '.join(sin_dato)}. Esas líneas no suman, y no se rellenan con 1.00 "
            "porque un hueco se ve y un número inventado se cobra."
        )

    if lineas and abs(res.diferencia) > TOLERANCIA:
        res.avisos.append(
            f"El generador suma {res.total:,.4g} {unidad} y la estimación cobra "
            f"{cantidad_capturada:,.4g} {unidad}: sobran "
            f"{abs(res.diferencia):,.4g}"
            f"{' en el generador' if res.diferencia > 0 else ' en la cantidad cobrada'}. "
            "La cantidad sale del generador, no al revés."
        )
    elif not lineas and cantidad_capturada > 0:
        res.avisos.append(
            f"Se cobran {cantidad_capturada:,.4g} {unidad} sin una sola línea de "
            "generador. Una estimación sin respaldo de medición se regresa."
        )
    return res
