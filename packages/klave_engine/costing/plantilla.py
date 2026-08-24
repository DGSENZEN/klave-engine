"""La plantilla de personal técnico, administrativo y de servicio de campo.

RLOPSRM art. 45-A-XI-d pide un «programa de utilización del personal
profesional técnico, administrativo y de servicio», calendarizado igual que
los otros tres. Los otros tres salen solos de la explosión de insumos, porque
la mano de obra, la maquinaria y los materiales están dentro de las matrices.
Éste no: el superintendente, el residente, el velador y la secretaria son
**costo indirecto de campo**. No aparecen en ninguna matriz, así que no hay
de dónde derivarlos.

Antes este programa salía vacío, con una nota diciendo de dónde tendría que
venir. Vacío no se entrega: una propuesta a la que le falta uno de los cinco
programas del art. 45-A se desecha, y el licitante se entera cuando ya no
puede corregirla.

Lo que se hace aquí, entonces, es partir la pregunta en dos:

* **Qué puestos necesita una obra de esta duración y con estos frentes** es
  conocimiento del oficio, no dinero. Un residente por frente, un velador
  siempre, un topógrafo mientras se traza. Eso el motor lo puede proponer, y
  lo propone con la razón escrita al lado.
* **Cuánto gana cada uno** es dinero, y el motor no lo inventa. Un cargo sin
  sueldo capturado sale en el programa con su participación en el calendario
  y sin importe, marcado «sin sueldo capturado». Es una casilla vacía que se
  ve, no un cero que se confunde con gratis.

La otra mitad del trabajo es la congruencia. Un revisor bajo el art. 64-A-I
compara el importe de esta plantilla contra los indirectos de campo que
declara la integración del precio: si la plantilla suma más de lo que los
indirectos pagan, la propuesta se contradice a sí misma. Esa comparación se
hace aquí y se dice en el programa, tanto si cuadra como si no.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipoCargo = Literal["tecnico", "administrativo", "servicio"]

TIPO_LABEL: dict[str, str] = {
    "tecnico": "Técnico",
    "administrativo": "Administrativo",
    "servicio": "Servicio",
}

# Cuando la plantilla y los indirectos de campo difieren más que esto, la
# diferencia deja de ser redondeo y se dice.
TOLERANCIA_PCT = 10.0


class CargoCampo(BaseModel):
    """Un puesto de la plantilla de campo, con su participación en el tiempo.

    ``desde_periodo`` y ``hasta_periodo`` son 1-based e inclusivos sobre el
    calendario del programa; ``hasta_periodo`` en None significa hasta el
    final de la obra."""

    puesto: str
    tipo: TipoCargo = "tecnico"
    cantidad: float = 1.0
    # Sueldo nominal mensual en MXN. 0 = no capturado: el renglón sale sin
    # importe, nunca en cero.
    salario_mensual: float = 0.0
    # Factor de salario real (IMSS, INFONAVIT, prestaciones, días no
    # laborados). El del taller manda; 1.60 es el que trae la casilla vacía.
    fsr: float = 1.60
    desde_periodo: int = 1
    hasta_periodo: int | None = None
    dedicacion_pct: float = 100.0
    # Por qué está en la lista, cuando la propuso el motor.
    razon: str = ""

    def participa_en(self, periodo: int) -> float:
        """Personas-equivalente en ese periodo (1-based); 0 si no participa."""
        if periodo < self.desde_periodo:
            return 0.0
        if self.hasta_periodo is not None and periodo > self.hasta_periodo:
            return 0.0
        return self.cantidad * max(self.dedicacion_pct, 0.0) / 100.0


def plantilla_sugerida(
    duracion_meses: float, frentes: int = 1
) -> list[CargoCampo]:
    """Los puestos que una obra de este tamaño necesita, sin sueldos.

    Es una propuesta para editar, no una plantilla. El motor sabe que una obra
    con dos frentes lleva dos residentes; no sabe, ni pretende saber, cuánto
    gana el residente de este taller."""
    meses = max(1, round(duracion_meses))
    frentes = max(1, frentes)
    hasta_trazo = max(1, round(meses * 0.6))
    cargos: list[CargoCampo] = [
        CargoCampo(
            puesto="Superintendente de obra",
            tipo="tecnico",
            razon="Responsable único de la obra ante la contratante, toda la obra",
        ),
        CargoCampo(
            puesto="Residente de obra",
            tipo="tecnico",
            cantidad=float(frentes),
            razon=(
                f"Un residente por frente de trabajo ({frentes} "
                f"{'frente' if frentes == 1 else 'frentes'} en el programa)"
            ),
        ),
        CargoCampo(
            puesto="Cabo de obra / sobrestante",
            tipo="tecnico",
            cantidad=float(frentes),
            razon="Un cabo por frente, coordinando cuadrillas en sitio",
        ),
        CargoCampo(
            puesto="Topógrafo con cadenero",
            tipo="tecnico",
            hasta_periodo=hasta_trazo,
            dedicacion_pct=50.0,
            razon="Trazo, niveles y control durante la etapa de estructura",
        ),
        CargoCampo(
            puesto="Almacenista",
            tipo="administrativo",
            razon="Control de entradas y salidas de material en obra",
        ),
        CargoCampo(
            puesto="Velador",
            tipo="servicio",
            razon="Vigilancia del sitio, toda la obra",
        ),
    ]
    if meses >= 4:
        cargos.append(
            CargoCampo(
                puesto="Ingeniero de costos y estimaciones",
                tipo="tecnico",
                razon=f"Obra de {meses} meses: generadores y estimaciones periódicas",
            )
        )
        cargos.append(
            CargoCampo(
                puesto="Auxiliar administrativo",
                tipo="administrativo",
                dedicacion_pct=50.0,
                razon=f"Obra de {meses} meses: control documental y nóminas de campo",
            )
        )
    return cargos


class RenglonPlantilla(BaseModel):
    """Un cargo puesto sobre el calendario, listo para el formato."""

    puesto: str
    tipo: TipoCargo
    unidad: str  # "mes-hombre" | "quincena-hombre" | "semana-hombre"
    cantidad: float  # total de periodos-hombre
    importe: float
    sin_sueldo: bool
    por_periodo: list[float] = Field(default_factory=list)
    importe_por_periodo: list[float] = Field(default_factory=list)
    razon: str = ""


class ProgramaPersonal(BaseModel):
    renglones: list[RenglonPlantilla]
    total: float
    total_por_periodo: list[float] = Field(default_factory=list)
    # Cuántos cargos quedaron sin sueldo capturado: el importe de arriba está
    # incompleto en esa medida, y hay que decirlo antes de que alguien lo sume.
    cargos_sin_sueldo: int = 0
    notas: list[str] = Field(default_factory=list)


def desajuste_de_indirectos(
    total_plantilla: float, indirectos_campo: float, cargos_sin_sueldo: int
) -> float | None:
    """Cuánto se pasa (o le falta) la plantilla frente a los indirectos de
    campo, en por ciento. None cuando no hay nada que comparar todavía.

    Con un solo sueldo sin capturar la suma está incompleta, y comparar una
    suma incompleta produce una alarma falsa. Una alarma falsa gasta la
    atención que hace falta para la verdadera, así que no se levanta."""
    if cargos_sin_sueldo or indirectos_campo <= 0 or total_plantilla <= 0:
        return None
    diferencia = (total_plantilla - indirectos_campo) / indirectos_campo * 100.0
    return diferencia if abs(diferencia) > TOLERANCIA_PCT else None


def build_personal_tecnico(
    cargos: list[CargoCampo],
    periods: int,
    period_days: int,
    period_label: str,
    indirectos_campo: float = 0.0,
) -> ProgramaPersonal:
    """El programa del art. 45-A-XI-d, calendarizado y reconciliado.

    ``indirectos_campo`` es el importe que la integración del precio destina a
    indirectos de campo. Cuando viene, se compara contra lo que suma la
    plantilla: son los dos números que un revisor pone lado a lado."""
    unidad = f"{period_label}-hombre"
    # El sueldo del periodo sale del mensual: una quincena es media mensualidad.
    factor_periodo = period_days / 24.0
    renglones: list[RenglonPlantilla] = []
    totales = [0.0] * periods
    sin_sueldo = 0

    for cargo in cargos:
        por_periodo = [cargo.participa_en(i + 1) for i in range(periods)]
        if not any(por_periodo):
            continue  # su participación queda fuera del calendario de la obra
        costo_periodo = cargo.salario_mensual * cargo.fsr * factor_periodo
        importes = [round(v * costo_periodo, 2) for v in por_periodo]
        if cargo.salario_mensual <= 0:
            sin_sueldo += 1
        for index, value in enumerate(importes):
            totales[index] += value
        renglones.append(
            RenglonPlantilla(
                puesto=cargo.puesto,
                tipo=cargo.tipo,
                unidad=unidad,
                cantidad=round(sum(por_periodo), 4),
                importe=round(sum(importes), 2),
                sin_sueldo=cargo.salario_mensual <= 0,
                por_periodo=[round(v, 4) for v in por_periodo],
                importe_por_periodo=importes,
                razon=cargo.razon,
            )
        )

    # Técnico antes que administrativo antes que servicio, y dentro de cada
    # tipo el de mayor peso primero: es el orden en que se lee un formato.
    orden = {"tecnico": 0, "administrativo": 1, "servicio": 2}
    renglones.sort(key=lambda r: (orden.get(r.tipo, 3), -r.cantidad, r.puesto))
    total = round(sum(r.importe for r in renglones), 2)

    notas: list[str] = []
    if not renglones:
        notas.append(
            "Sin plantilla de campo capturada. Este programa es obligatorio "
            "(RLOPSRM art. 45-A-XI-d) y no se puede derivar del presupuesto: el "
            "personal técnico y administrativo es costo indirecto, no está en "
            "ninguna matriz. Captura la plantilla o parte de la sugerida."
        )
        return ProgramaPersonal(renglones=[], total=0.0, total_por_periodo=[], notas=notas)

    notas.append(
        f"Cantidades en {unidad}: personal en obra durante cada {period_label}. "
        f"Importes a sueldo nominal por factor de salario real."
    )
    if sin_sueldo:
        notas.append(
            f"{sin_sueldo} "
            f"{'cargo' if sin_sueldo == 1 else 'cargos'} sin sueldo capturado: "
            "aparecen con su participación en el calendario y sin importe. El total "
            "de abajo está incompleto en esa medida — no es que ese personal salga gratis."
        )
    if indirectos_campo > 0 and total > 0 and not sin_sueldo:
        diferencia = desajuste_de_indirectos(total, indirectos_campo, sin_sueldo)
        if diferencia is None:
            cerca = (total - indirectos_campo) / indirectos_campo * 100.0
            notas.append(
                f"Congruente con la integración: la plantilla suma "
                f"${total:,.2f} y los indirectos de campo del presupuesto son "
                f"${indirectos_campo:,.2f} ({cerca:+.1f} %)."
            )
        else:
            direccion = "más" if diferencia > 0 else "menos"
            notas.append(
                f"La plantilla suma ${total:,.2f}, {abs(diferencia):.1f} % {direccion} "
                f"que los ${indirectos_campo:,.2f} de indirectos de campo que declara "
                "la integración del precio. Un revisor compara estos dos números "
                "(RLOPSRM art. 64-A-I): ajusta el porcentaje de indirectos de campo o "
                "la plantilla, para que la propuesta no se contradiga."
            )
    elif indirectos_campo > 0 and sin_sueldo:
        notas.append(
            f"No se puede comparar contra los ${indirectos_campo:,.2f} de indirectos de "
            "campo mientras haya cargos sin sueldo: la suma de la plantilla todavía "
            "no está completa."
        )

    return ProgramaPersonal(
        renglones=renglones,
        total=total,
        total_por_periodo=[round(v, 2) for v in totales],
        cargos_sin_sueldo=sin_sueldo,
        notas=notas,
    )
