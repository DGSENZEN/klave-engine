"""Financial plan: estimaciones, anticipo y amortización, retenciones,
curva S, and the post-construction operating cost projection."""

from klave_engine.costing.models import (
    CostIntegration,
    FinancialConfig,
    FinancialPlan,
    OperatingYear,
    PeriodCashflow,
    WorkSchedule,
)
from klave_engine.costing.schedule import direct_spend_by_period


def build_financial_plan(
    schedule: WorkSchedule,
    integration: CostIntegration,
    config: FinancialConfig,
    currency: str = "MXN",
) -> FinancialPlan:
    spends = direct_spend_by_period(schedule)
    factor = integration.overcost_factor
    sale_price = integration.sale_price
    advance = round(sale_price * config.advance_payment_pct / 100.0, 2)

    periods: list[PeriodCashflow] = []
    accumulated = 0.0
    total_retention = 0.0
    for i, direct_spend in enumerate(spends):
        billing = round(direct_spend * factor, 2)
        accumulated = round(accumulated + billing, 2)
        amortization = round(billing * config.advance_payment_pct / 100.0, 2)
        retention = round(billing * config.retention_pct / 100.0, 2)
        total_retention = round(total_retention + retention, 2)
        net = round(billing - amortization - retention, 2)
        if i == 0:
            net = round(net + advance, 2)
        periods.append(
            PeriodCashflow(
                period=i + 1,
                label=f"Mes {i + 1}",
                direct_spend=direct_spend,
                billing=billing,
                advance_amortization=amortization,
                retention=retention,
                net_cashflow=net,
                accumulated_billing=accumulated,
                progress_pct=round(100.0 * accumulated / sale_price, 2)
                if sale_price
                else 0.0,
            )
        )

    annual_operating = round(
        integration.grand_total
        * (config.annual_operation_pct + config.annual_maintenance_pct)
        / 100.0,
        2,
    )
    projection: list[OperatingYear] = []
    accumulated_op = 0.0
    for year in range(1, config.operating_horizon_years + 1):
        operation = round(integration.grand_total * config.annual_operation_pct / 100.0, 2)
        maintenance = round(
            integration.grand_total * config.annual_maintenance_pct / 100.0, 2
        )
        accumulated_op = round(accumulated_op + operation + maintenance, 2)
        projection.append(
            OperatingYear(
                year=year,
                operation=operation,
                maintenance=maintenance,
                total=round(operation + maintenance, 2),
                accumulated=accumulated_op,
            )
        )

    return FinancialPlan(
        currency=currency,
        advance_payment_pct=config.advance_payment_pct,
        retention_pct=config.retention_pct,
        advance_payment=advance,
        total_retention=total_retention,
        periods=periods,
        operating_projection=projection,
        annual_operating_cost=annual_operating,
    )
