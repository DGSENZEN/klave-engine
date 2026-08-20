"use client";

import { useParams } from "next/navigation";
import { Banknote, CalendarRange, PiggyBank, Wrench } from "lucide-react";
import { money, money2, type PeriodCashflow } from "@/lib/api";
import { useCostReport } from "@/lib/useProjectReport";
import {
  Callout,
  Card,
  EmptyState,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

export default function FlujoPage() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Flujo financiero" />
        <Callout tone="danger">
          No se pudo cargar el flujo financiero. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!costs) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <Skeleton className="mb-6 h-14 w-80" />
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
        </div>
        <Skeleton className="mb-6 h-64" />
        <Skeleton className="h-80" />
      </div>
    );
  }

  const fin = costs.financial;
  const periods = fin.periods ?? [];
  const operating = fin.operating_projection ?? [];

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Flujo financiero"
        sub="Estimaciones por periodo a precio de venta: anticipo, amortización, retenciones y flujo neto."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Anticipo"
          value={money(fin.advance_payment)}
          hint={fin.advance_payment_pct != null ? `${fin.advance_payment_pct}% del monto` : undefined}
          icon={<Banknote size={16} />}
          accent="primary"
        />
        <Metric
          label="Retención total"
          value={money(fin.total_retention)}
          hint={fin.retention_pct != null ? `${fin.retention_pct}% por estimación` : undefined}
          icon={<PiggyBank size={16} />}
        />
        <Metric
          label="Periodos"
          value={periods.length}
          hint="estimaciones mensuales"
          icon={<CalendarRange size={16} />}
        />
        <Metric
          label="O&M anual"
          value={money(fin.annual_operating_cost)}
          hint="operación y mantenimiento"
          icon={<Wrench size={16} />}
        />
      </div>

      {periods.length === 0 ? (
        <EmptyState
          icon={<CalendarRange size={22} />}
          title="Este procesamiento no incluye flujo por periodos"
          hint="Vuelve a procesar el proyecto para generar el flujo financiero."
        />
      ) : (
        <>
          <Card className="mb-6 p-5">
            <SectionTitle sub="Flujo neto por periodo; la primera barra suele reflejar el anticipo.">
              Flujo neto
            </SectionTitle>
            <CashflowChart periods={periods} />
          </Card>

          <Card className="mb-6 overflow-hidden">
            <div className="border-b border-border px-5 py-4">
              <SectionTitle sub="Cifras a precio de venta, MXN.">
                Estimaciones por periodo
              </SectionTitle>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface-2">
                    <Th>Periodo</Th>
                    <Th align="right">Avance</Th>
                    <Th align="right">Gasto directo</Th>
                    <Th align="right">Estimación</Th>
                    <Th align="right">Amort. anticipo</Th>
                    <Th align="right">Retención</Th>
                    <Th align="right">Flujo neto</Th>
                    <Th align="right">Fact. acumulada</Th>
                  </tr>
                </thead>
                <tbody>
                  {periods.map((p) => (
                    <tr key={p.period} className="border-b border-border last:border-0">
                      <Td className="font-medium">{p.label}</Td>
                      <Td align="right" className="tabular text-muted">
                        {p.progress_pct.toFixed(1)}%
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {money2(p.direct_spend)}
                      </Td>
                      <Td align="right" className="tabular">
                        {money2(p.billing)}
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {money2(p.advance_amortization)}
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {money2(p.retention)}
                      </Td>
                      <Td
                        align="right"
                        className={`font-medium tabular ${
                          p.net_cashflow < 0 ? "text-danger" : "text-foreground"
                        }`}
                      >
                        {money2(p.net_cashflow)}
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {money2(p.accumulated_billing)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}

      {operating.length > 0 && (
        <Card className="overflow-hidden">
          <div className="border-b border-border px-5 py-4">
            <SectionTitle sub="Proyección anual de operación y mantenimiento.">
              Operación y mantenimiento
            </SectionTitle>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <Th>Año</Th>
                  <Th align="right">Operación</Th>
                  <Th align="right">Mantenimiento</Th>
                  <Th align="right">Total</Th>
                  <Th align="right">Acumulado</Th>
                </tr>
              </thead>
              <tbody>
                {operating.map((year) => (
                  <tr key={year.year} className="border-b border-border last:border-0">
                    <Td className="font-medium">Año {year.year}</Td>
                    <Td align="right" className="tabular text-muted">
                      {money2(year.operation)}
                    </Td>
                    <Td align="right" className="tabular text-muted">
                      {money2(year.maintenance)}
                    </Td>
                    <Td align="right" className="tabular">
                      {money2(year.total)}
                    </Td>
                    <Td align="right" className="tabular text-muted">
                      {money2(year.accumulated)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function CashflowChart({ periods }: { periods: PeriodCashflow[] }) {
  const width = 720;
  const height = 200;
  const padTop = 12;
  const padBottom = 26;
  const values = periods.map((p) => p.net_cashflow);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const chartH = height - padTop - padBottom;
  const zeroY = padTop + (max / span) * chartH;
  const slot = width / periods.length;
  const barW = Math.min(slot * 0.55, 48);
  const labelEvery = Math.ceil(periods.length / 12);

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-w-[560px]"
        role="img"
        aria-label="Flujo neto por periodo"
      >
        <line
          x1={0}
          x2={width}
          y1={zeroY}
          y2={zeroY}
          stroke="var(--border-strong)"
          strokeWidth={1}
        />
        {periods.map((p, i) => {
          const x = i * slot + (slot - barW) / 2;
          const h = (Math.abs(p.net_cashflow) / span) * chartH;
          const y = p.net_cashflow >= 0 ? zeroY - h : zeroY;
          return (
            <g key={p.period}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(h, 1)}
                rx={3}
                fill={p.net_cashflow >= 0 ? "var(--chart-1)" : "var(--danger)"}
                opacity={0.9}
              >
                <title>{`${p.label}: ${money(p.net_cashflow)}`}</title>
              </rect>
              {i % labelEvery === 0 && (
                <text
                  x={i * slot + slot / 2}
                  y={height - 8}
                  textAnchor="middle"
                  className="tabular"
                  fill="var(--faint)"
                  fontSize={10}
                >
                  {p.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
