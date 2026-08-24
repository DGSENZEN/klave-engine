"""Cost integration: costo directo → precio de venta → total con contingencia.

Follows the standard Mexican price integration sequence: indirects on direct
cost, financing on (CD+CI), profit on (CD+CI+F), additional charges on the
accumulated subtotal, then contingency on the sale price.
"""

from klave_engine.costing.models import CostIntegration, IndirectsConfig, IntegrationLine


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
