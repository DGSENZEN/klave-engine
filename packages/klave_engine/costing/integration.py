"""Cost integration: costo directo → precio de venta → total con contingencia.

Follows the standard Mexican price integration sequence: indirects on direct
cost, financing on (CD+CI), profit on (CD+CI+F), additional charges on the
accumulated subtotal, then contingency on the sale price.
"""

import math

from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    ComponenteResuelto,
    DesgloseOficinaCentral,
    compute_financiamiento,
    documenta_campo,
    documenta_oficina,
)
from klave_engine.costing.models import (
    CostIntegration,
    CostingConfig,
    FinancialPlan,
    IndirectsConfig,
    IntegrationLine,
    WorkSchedule,
)
from klave_engine.costing.plantilla import build_personal_tecnico


def integrate_costs(direct_cost: float, config: IndirectsConfig) -> CostIntegration:
    lines: list[IntegrationLine] = []
    accumulated = direct_cost

    def add(code: str, description: str, base: float, pct: float) -> float:
        nonlocal accumulated
        amount = round(base * pct / 100.0, 2)
        accumulated = round(accumulated + amount, 2)
        lines.append(
            IntegrationLine(
                code=code,
                description=description,
                base=round(base, 2),
                percentage=pct,
                amount=amount,
                accumulated=accumulated,
            )
        )
        return amount

    # Campo y oficina central van en renglones separados porque se revisan por
    # separado: el de campo es el que tiene que cuadrar contra la plantilla de
    # personal del programa del art. 45-A-XI-d.
    add("CI-C", "Costos indirectos de campo", direct_cost, config.field_indirects_pct)
    add(
        "CI-O",
        "Costos indirectos de oficina central",
        direct_cost,
        config.office_indirects_pct,
    )
    add("FI", "Costo de financiamiento", accumulated, config.financing_pct)
    add("UT", "Utilidad", accumulated, config.profit_pct)
    add("CA", "Cargos adicionales", accumulated, config.additional_charges_pct)

    sale_price = accumulated
    contingency = round(sale_price * config.contingency_pct / 100.0, 2)
    return CostIntegration(
        direct_cost=round(direct_cost, 2),
        lines=lines,
        sale_price=sale_price,
        contingency=contingency,
        grand_total=round(sale_price + contingency, 2),
        overcost_factor=round(sale_price / direct_cost, 4) if direct_cost else 0.0,
    )


def resolve_integration(
    config: CostingConfig,
    integracion_taller: dict | None,
    direct_cost: float,
    schedule: WorkSchedule | None,
    flujo: FinancialPlan | None,
) -> list[ComponenteResuelto]:
    """Cada componente con su fuente dicha: análisis cuando los datos alcanzan,
    porcentaje declarado cuando no — y en ese caso, qué falta exactamente.

    Los faltantes se reclaman sólo cuando alguien capturó a medias: un taller
    que no ha capturado nada trabaja en modo declarado sin regaños, igual que
    la plantilla no alarma cuando no existe."""
    taller = integracion_taller or {}
    ind = config.indirects
    out: list[ComponenteResuelto] = []

    # ---- CI de campo -------------------------------------------------
    if config.desglose_campo is not None and schedule is not None:
        period_days = schedule.workdays_per_month or 24
        meses = (
            max(1, math.ceil(schedule.total_duration_days / period_days))
            if schedule.total_duration_days else 1
        )
        programa = build_personal_tecnico(config.plantilla_campo, meses, period_days, "mes")
        doc = documenta_campo(
            config.desglose_campo, meses, programa.total, programa.cargos_sin_sueldo
        )
        mensual_mes = sum(
            r.importe for r in config.desglose_campo.rubros
            if r.base == "mensual" and r.importe > 0
        )
        unicos = sum(
            r.importe for r in config.desglose_campo.rubros
            if r.base == "unico" and r.importe > 0
        )
        por_periodo = []
        for i in range(meses):
            plantilla_i = (
                programa.total_por_periodo[i]
                if i < len(programa.total_por_periodo) else 0.0
            )
            por_periodo.append(round(
                mensual_mes + plantilla_i + (unicos if i == 0 else 0.0), 2
            ))
        documento = doc.model_dump()
        documento["por_periodo"] = por_periodo
        faltantes = [n for n in doc.notas if "sin importe" in n or "sin sueldo" in n]
        out.append(ComponenteResuelto(
            code="CI-C", amount=doc.total, fuente="analisis",
            documento=documento, faltantes=faltantes,
        ))
    else:
        out.append(ComponenteResuelto(code="CI-C", pct=ind.field_indirects_pct))

    # ---- CI de oficina central ---------------------------------------
    oficina = DesgloseOficinaCentral.model_validate(taller.get("oficina") or {})
    doc_oficina = documenta_oficina(oficina, direct_cost)
    if doc_oficina is not None:
        documento_oficina = doc_oficina.model_dump()
        importe_oficina = doc_oficina.total
        faltantes_oficina: list[str] = []
        if config.oficina_share_pct is not None:
            if len(config.oficina_share_motivo.strip()) >= 15:
                importe_oficina = round(direct_cost * config.oficina_share_pct / 100.0, 2)
                documento_oficina["override"] = config.oficina_share_pct
                documento_oficina["motivo"] = config.oficina_share_motivo.strip()
                documento_oficina.setdefault("notas", []).append(
                    f"Share fijado a mano en {config.oficina_share_pct:g} % — "
                    f"{config.oficina_share_motivo.strip()}"
                )
            else:
                faltantes_oficina = [
                    "share de oficina fijado sin motivo escrito (≥15 caracteres): "
                    "se usa el prorrateo derivado"
                ]
        out.append(ComponenteResuelto(
            code="CI-O", amount=importe_oficina, fuente="analisis",
            documento=documento_oficina, faltantes=faltantes_oficina,
        ))
    else:
        faltantes = []
        if oficina.rubros:  # capturó rubros pero no el volumen: eso sí se reclama
            faltantes = ["sin volumen anual contratado: el prorrateo de oficina "
                         "central no puede calcularse"]
        out.append(ComponenteResuelto(
            code="CI-O", pct=ind.office_indirects_pct, faltantes=faltantes,
        ))

    # ---- Financiamiento ----------------------------------------------
    analisis = config.financiamiento
    if analisis is None and taller.get("financiamiento"):
        analisis = AnalisisFinanciamiento.model_validate(taller["financiamiento"])
    if analisis is not None and analisis.completo and flujo is not None and flujo.periods:
        n = len(flujo.periods)
        campo = out[0]
        campo_total = (
            campo.amount if campo.amount is not None
            else round(direct_cost * campo.pct / 100.0, 2)
        )
        oficina_total = (
            out[1].amount if out[1].amount is not None
            else round(direct_cost * out[1].pct / 100.0, 2)
        )
        campo_pp = list(campo.documento.get("por_periodo") or [])
        if not campo_pp:
            campo_pp = [round(campo_total / n, 2)] * n
        if len(campo_pp) < n:
            campo_pp += [0.0] * (n - len(campo_pp))
        total_spend = sum(p.direct_spend for p in flujo.periods) or 1.0
        egresos = [
            p.direct_spend + campo_pp[i] + oficina_total * (p.direct_spend / total_spend)
            for i, p in enumerate(flujo.periods)
        ]
        ingresos = [p.net_cashflow for p in flujo.periods]
        doc_fi = compute_financiamiento(analisis, egresos, ingresos)
        out.append(ComponenteResuelto(
            code="FI", amount=doc_fi.total, fuente="analisis",
            documento=doc_fi.model_dump(),
        ))
    else:
        faltantes = []
        if analisis is not None and analisis.faltantes():
            faltantes = [f"sin {f} capturada" if f == "tasa" else f"sin {f}"
                         for f in analisis.faltantes()]
        out.append(ComponenteResuelto(
            code="FI", pct=ind.financing_pct, faltantes=faltantes,
        ))

    # ---- Utilidad: declarada por diseño ------------------------------
    out.append(ComponenteResuelto(code="UT", pct=ind.profit_pct))

    # ---- Cargos adicionales ------------------------------------------
    if config.cargos_adicionales:
        out.append(ComponenteResuelto(
            code="CA", fuente="analisis",
            pct=round(sum(c.pct for c in config.cargos_adicionales), 6),
            documento={"items": [c.model_dump() for c in config.cargos_adicionales]},
        ))
    else:
        out.append(ComponenteResuelto(code="CA", pct=ind.additional_charges_pct))

    return out
