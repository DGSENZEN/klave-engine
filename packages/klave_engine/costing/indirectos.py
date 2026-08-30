"""Desglose de indirectos: la aritmética del documento, a mano.

Un documento de desglose es un renglón por renglón; los importes salen de lo que
la obra capturó y los renglones quedan fechados. Un porcentaje desnudo no es un
desglose: es un decreto sin herencia, el juicio lo rechaza en revisión.

**Personal de campo no se captura dos veces.** La plantilla de campo tiene sueldos
capturados renglón por renglón o precio global. Cuando documenta_campo() emite el
desglose, agrega un renglón de "Personal técnico, administrativo y de servicio de
campo" cuyo importe es la suma de esa plantilla multiplicada por los meses del
programa. Ese renglón es la verdad de ley: no sale de lo que alguien tipee en el
formulario de indirectos, sale de la plantilla. Tipear dos veces genera observación.

**El porcentaje de oficina central es derivado, no capturado.** Los rubros de
oficina central —renta, nómina administrativa, servicios— son costos ANUALES de
la empresa. Para saber qué parte de esos costos toca a esta obra, se divide el
costo anual entre el volumen anual de obras en cartera (prorrateo). Ese cociente
es un porcentaje; multiplicado por el costo directo de esta obra, da el importe.
Sin volumen anual no hay cociente, y sin cociente no hay desglose.

**Una tasa sin indicador, fuente y fecha no es una tasa.** El análisis de
financiamiento exige tres datos: cuál es el indicador (TIIE, CPP, etc.), dónde
se publica (Banxico, etc.) y cuándo se consultó. Sin esos tres datos, la tasa es
un invento. El documento queda incompleto y el revisor lo rechaza.

Éste es el **único módulo donde aparecen números de artículos:** RLOPSRM arts.
211 a 220 riegan los indirectos de campo y oficina. Fuera de aquí, el código
silencia las referencias legales y deja que el documento hable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CategoriaRubro = Literal[
    "honorarios_prestaciones",
    "depreciacion_mantenimiento_rentas",
    "servicios",
    "fletes_acarreos",
    "gastos_oficina",
    "capacitacion",
    "seguridad_higiene",
    "seguros_fianzas",
    "trabajos_previos_auxiliares",
]

CATEGORIA_LABEL: dict[str, str] = {
    "honorarios_prestaciones": "Honorarios, sueldos y prestaciones",
    "depreciacion_mantenimiento_rentas": "Depreciación, mantenimiento y rentas",
    "servicios": "Servicios",
    "fletes_acarreos": "Fletes y acarreos",
    "gastos_oficina": "Gastos de oficina",
    "capacitacion": "Capacitación y adiestramiento",
    "seguridad_higiene": "Seguridad e higiene",
    "seguros_fianzas": "Seguros y fianzas",
    "trabajos_previos_auxiliares": "Trabajos previos y auxiliares",
}


class RubroIndirecto(BaseModel):
    concepto: str
    categoria: CategoriaRubro = "servicios"
    # 0 = sin capturar: el renglón se ve vacío y no suma. Nunca es "gratis".
    importe: float = 0.0
    base: Literal["mensual", "unico"] = "mensual"


class DesgloseCampo(BaseModel):
    rubros: list[RubroIndirecto] = Field(default_factory=list)


class DesgloseOficinaCentral(BaseModel):
    # Importes ANUALES; ``base`` se ignora aquí.
    rubros: list[RubroIndirecto] = Field(default_factory=list)
    # 0 = sin capturar: sin volumen no hay prorrateo y no hay análisis.
    volumen_anual_contratado: float = 0.0


class AnalisisFinanciamiento(BaseModel):
    tasa_anual: float = 0.0
    indicador: str = ""       # p. ej. "TIIE 28 días"
    fuente: str = ""          # de dónde salió la tasa
    fecha_publicacion: str = ""  # ISO

    def faltantes(self) -> list[str]:
        missing: list[str] = []
        if self.tasa_anual <= 0:
            missing.append("tasa")
        if not self.indicador.strip():
            missing.append("indicador")
        if not self.fuente.strip():
            missing.append("fuente")
        if not self.fecha_publicacion.strip():
            missing.append("fecha de publicación")
        return missing

    @property
    def completo(self) -> bool:
        return not self.faltantes()


class CargoAdicional(BaseModel):
    concepto: str
    base_legal: str = ""
    pct: float = 0.0


class RenglonDocumento(BaseModel):
    concepto: str
    categoria: str
    base: str
    importe: float
    sin_capturar: bool = False
    fuente: str = "capturado"


class DocumentoDesglose(BaseModel):
    renglones: list[RenglonDocumento] = Field(default_factory=list)
    total: float = 0.0
    notas: list[str] = Field(default_factory=list)


class ComponenteResuelto(BaseModel):
    """Un componente de la integración con su fuente dicha.

    ``amount`` presente = lo respalda un análisis y el importe manda;
    ``amount`` en None = porcentaje declarado, y el reporte lo dice."""

    code: str  # "CI-C" | "CI-O" | "FI" | "UT" | "CA"
    amount: float | None = None
    pct: float = 0.0
    fuente: Literal["analisis", "declarado"] = "declarado"
    documento: dict = Field(default_factory=dict)
    faltantes: list[str] = Field(default_factory=list)


def documenta_campo(
    desglose: DesgloseCampo, meses: int, plantilla_total: float, cargos_sin_sueldo: int
) -> DocumentoDesglose:
    meses = max(1, meses)
    renglones: list[RenglonDocumento] = []
    notas: list[str] = []
    total = 0.0
    if plantilla_total > 0 or cargos_sin_sueldo:
        renglones.append(RenglonDocumento(
            concepto="Personal técnico, administrativo y de servicio de campo",
            categoria="honorarios_prestaciones", base="mensual",
            importe=round(plantilla_total, 2), fuente="plantilla de campo",
        ))
        total += plantilla_total
    for rubro in desglose.rubros:
        if rubro.importe <= 0:
            renglones.append(RenglonDocumento(
                concepto=rubro.concepto, categoria=rubro.categoria,
                base=rubro.base, importe=0.0, sin_capturar=True,
            ))
            continue
        importe = round(rubro.importe * meses, 2) if rubro.base == "mensual" else round(rubro.importe, 2)
        total += importe
        renglones.append(RenglonDocumento(
            concepto=rubro.concepto, categoria=rubro.categoria,
            base=rubro.base, importe=importe,
        ))
    vacios = sum(1 for r in renglones if r.sin_capturar)
    if vacios:
        notas.append(
            f"{vacios} {'renglón' if vacios == 1 else 'renglones'} sin importe "
            "capturado: el total está incompleto en esa medida."
        )
    if cargos_sin_sueldo:
        notas.append(
            f"{cargos_sin_sueldo} {'cargo' if cargos_sin_sueldo == 1 else 'cargos'} "
            "de la plantilla sin sueldo capturado: el rubro de personal está incompleto."
        )
    notas.append(f"Rubros mensuales multiplicados por los {meses} meses del programa.")
    return DocumentoDesglose(renglones=renglones, total=round(total, 2), notas=notas)


def documenta_oficina(
    oficina: DesgloseOficinaCentral, costo_directo: float
) -> DocumentoDesglose | None:
    """None cuando falta el volumen anual o no hay un solo rubro con importe:
    sin esos datos el prorrateo sería un número inventado."""
    if oficina.volumen_anual_contratado <= 0:
        return None
    renglones: list[RenglonDocumento] = []
    anual = 0.0
    for rubro in oficina.rubros:
        if rubro.importe <= 0:
            renglones.append(RenglonDocumento(
                concepto=rubro.concepto, categoria=rubro.categoria,
                base="anual", importe=0.0, sin_capturar=True,
            ))
            continue
        anual += rubro.importe
        renglones.append(RenglonDocumento(
            concepto=rubro.concepto, categoria=rubro.categoria,
            base="anual", importe=round(rubro.importe, 2),
        ))
    if anual <= 0:
        return None
    pct = anual / oficina.volumen_anual_contratado * 100.0
    total = round(costo_directo * pct / 100.0, 2)
    notas = [
        f"Costo anual de oficina central ${anual:,.2f} ÷ volumen anual contratado "
        f"${oficina.volumen_anual_contratado:,.2f} = {pct:.4f} % aplicado al costo "
        "directo de esta obra."
    ]
    vacios = sum(1 for r in renglones if r.sin_capturar)
    if vacios:
        notas.append(
            f"{vacios} {'renglón' if vacios == 1 else 'renglones'} sin importe "
            "capturado: el porcentaje está incompleto en esa medida."
        )
    return DocumentoDesglose(renglones=renglones, total=total, notas=notas)


class PeriodoFinanciamiento(BaseModel):
    """Un mes del flujo de efectivo financiado a tasa.

    ``periodo`` es el ordinal (1, 2, ...). ``saldo`` es lo acumulado que nadie
    ha pagado todavía. ``costo`` es el saldo × tasa del período; negativo cuando
    el anticipo financia la obra."""
    periodo: int
    egresos: float
    ingresos: float
    saldo: float   # acumulado: lo gastado que nadie ha pagado todavía
    costo: float   # saldo × tasa del periodo; negativo cuando el anticipo financia


class DocumentoFinanciamiento(BaseModel):
    """El costo de traer dinero puesto antes de que lo paguen."""
    tasa_anual: float
    indicador: str
    fuente: str
    fecha_publicacion: str
    periodos: list[PeriodoFinanciamiento] = Field(default_factory=list)
    total: float = 0.0


def compute_financiamiento(
    analisis: AnalisisFinanciamiento, egresos: list[float], ingresos: list[float]
) -> DocumentoFinanciamiento:
    """El costo de traer dinero puesto antes de que lo paguen.

    ``egresos`` e ``ingresos`` van por periodo del flujo (meses); la tasa del
    periodo es la anual entre doce. El saldo acumulado por periodo paga (o
    cobra, cuando el anticipo lo vuelve negativo) la tasa. No se interpola,
    no se estima: listas de la misma longitud o nada."""
    tasa_periodo = analisis.tasa_anual / 12.0 / 100.0
    periodos: list[PeriodoFinanciamiento] = []
    saldo = 0.0
    total = 0.0
    for numero, (egreso, ingreso) in enumerate(zip(egresos, ingresos, strict=True), start=1):
        saldo = round(saldo + egreso - ingreso, 2)
        costo = round(saldo * tasa_periodo, 2)
        total = round(total + costo, 2)
        periodos.append(PeriodoFinanciamiento(
            periodo=numero, egresos=round(egreso, 2), ingresos=round(ingreso, 2),
            saldo=saldo, costo=costo,
        ))
    return DocumentoFinanciamiento(
        tasa_anual=analisis.tasa_anual, indicador=analisis.indicador,
        fuente=analisis.fuente, fecha_publicacion=analisis.fecha_publicacion,
        periodos=periodos, total=total,
    )
