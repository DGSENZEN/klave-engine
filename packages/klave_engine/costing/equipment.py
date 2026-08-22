"""Costo horario de maquinaria per RLOPSRM art. 194–206, line by line.

    Phm = cargos fijos (D + Im + Sm + Mn) + consumos (Co + Lb + N + Ae) + Po

    D  = (Vm − Vr) / Ve                 depreciación lineal
    Im = ((Vm + Vr) / (2·Hea)) · i      inversión
    Sm = ((Vm + Vr) / (2·Hea)) · s      seguros
    Mn = Ko · D                         mantenimiento mayor y menor
    Co = Gh · Pc                        combustible
    Lb = (Ah + Ga) · Pa                 lubricantes
    N  = Pn / Vn                        llantas
    Ae = Pa_e / Va                      piezas especiales
    Po = Sr / Ht                        operación (salario real por turno)

Every symbol is an editable input; the result keeps each line so the APU
shows the machine's hour the way the reglamento defines it.
"""

from pydantic import BaseModel, Field


class EquipmentParameters(BaseModel):
    vm: float = Field(gt=0, description="Valor de la máquina nueva (sin llantas ni piezas)")
    vr: float = Field(ge=0, description="Valor de rescate")
    ve: float = Field(gt=0, description="Vida económica en horas")
    hea: float = Field(gt=0, default=2000.0, description="Horas efectivas por año")
    i: float = Field(ge=0, default=0.12, description="Tasa de interés anual (fracción)")
    s: float = Field(ge=0, default=0.03, description="Prima anual de seguros (fracción)")
    ko: float = Field(ge=0, default=0.80, description="Coeficiente de mantenimiento")
    gh: float = Field(ge=0, default=0.0, description="Combustible por hora (l/h)")
    pc: float = Field(ge=0, default=0.0, description="Precio del combustible ($/l)")
    ah: float = Field(ge=0, default=0.0, description="Aceite consumido por hora (l/h)")
    ga: float = Field(ge=0, default=0.0, description="Aceite por cambios periódicos (l/h)")
    pa: float = Field(ge=0, default=0.0, description="Precio del aceite ($/l)")
    pn: float = Field(ge=0, default=0.0, description="Valor de las llantas nuevas")
    vn: float = Field(ge=0, default=0.0, description="Vida de las llantas en horas")
    pa_e: float = Field(ge=0, default=0.0, description="Valor de piezas especiales")
    va: float = Field(ge=0, default=0.0, description="Vida de piezas especiales en horas")
    sr: float = Field(ge=0, default=0.0, description="Salario real del operador por turno")
    ht: float = Field(gt=0, default=8.0, description="Horas efectivas por turno")
    other_energy: float = Field(ge=0, default=0.0, description="Otras fuentes de energía ($/h)")


class EquipmentBreakdown(BaseModel):
    depreciacion: float
    inversion: float
    seguros: float
    mantenimiento: float
    cargos_fijos: float
    combustible: float
    otras_energias: float
    lubricantes: float
    llantas: float
    piezas_especiales: float
    consumos: float
    operacion: float
    costo_horario: float
    notes: list[str]


def compute_costo_horario(p: EquipmentParameters) -> EquipmentBreakdown:
    d = (p.vm - p.vr) / p.ve
    base = (p.vm + p.vr) / (2.0 * p.hea)
    im = base * p.i
    sm = base * p.s
    mn = p.ko * d
    co = p.gh * p.pc
    lb = (p.ah + p.ga) * p.pa
    n = p.pn / p.vn if p.vn > 0 else 0.0
    ae = p.pa_e / p.va if p.va > 0 else 0.0
    po = p.sr / p.ht
    fijos = d + im + sm + mn
    consumos = co + p.other_energy + lb + n + ae
    total = fijos + consumos + po
    notes = [
        f"D = (Vm − Vr) / Ve = ({p.vm:,.2f} − {p.vr:,.2f}) / {p.ve:,.0f} = {d:,.2f}",
        f"Im = ((Vm + Vr) / 2·Hea) · i = {base:,.2f} × {p.i:.4f} = {im:,.2f}",
        f"Sm = ((Vm + Vr) / 2·Hea) · s = {base:,.2f} × {p.s:.4f} = {sm:,.2f}",
        f"Mn = Ko · D = {p.ko:.2f} × {d:,.2f} = {mn:,.2f}",
        f"Co = Gh · Pc = {p.gh:.2f} × {p.pc:.2f} = {co:,.2f}",
        f"Lb = (Ah + Ga) · Pa = ({p.ah:.3f} + {p.ga:.3f}) × {p.pa:.2f} = {lb:,.2f}",
        f"N = Pn / Vn = {n:,.2f}; Ae = Pa / Va = {ae:,.2f}",
        f"Po = Sr / Ht = {p.sr:,.2f} / {p.ht:g} = {po:,.2f}",
        "RLOPSRM art. 194–206 (cargos fijos + consumos + operación)",
    ]
    return EquipmentBreakdown(
        depreciacion=round(d, 4), inversion=round(im, 4), seguros=round(sm, 4),
        mantenimiento=round(mn, 4), cargos_fijos=round(fijos, 4), combustible=round(co, 4),
        otras_energias=round(p.other_energy, 4), lubricantes=round(lb, 4), llantas=round(n, 4),
        piezas_especiales=round(ae, 4), consumos=round(consumos, 4), operacion=round(po, 4),
        costo_horario=round(total, 2), notes=notes,
    )
