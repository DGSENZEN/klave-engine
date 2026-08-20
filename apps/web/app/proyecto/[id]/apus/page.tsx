"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { Calculator, ChevronDown } from "lucide-react";
import { money2, num, type Apu } from "@/lib/api";
import { useCostReport } from "@/lib/useProjectReport";
import {
  Badge,
  Callout,
  Card,
  EmptyState,
  Metric,
  PageHeader,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

const RESOURCE_LABELS: Record<string, string> = {
  material: "Material",
  mano_de_obra: "Mano de obra",
  equipo: "Equipo",
};

const RESOURCE_COLORS: Record<string, string> = {
  material: "var(--chart-1)",
  mano_de_obra: "var(--chart-2)",
  equipo: "var(--chart-3)",
};

export default function ApusPage() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [open, setOpen] = useState<string | null>(null);

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Precios unitarios" />
        <Callout tone="danger">
          No se pudo cargar el análisis de precios unitarios. Revisa que el servidor esté
          activo.
        </Callout>
      </div>
    );
  }

  if (!costs) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <Skeleton className="mb-6 h-14 w-80" />
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      </div>
    );
  }

  const apus = costs.apus ?? [];
  const openCode = open ?? apus[0]?.concept_code ?? null;
  const resourceTotals: Record<string, number> = {};
  for (const apu of apus) {
    for (const [type, amount] of Object.entries(apu.breakdown)) {
      resourceTotals[type] = (resourceTotals[type] ?? 0) + amount;
    }
  }
  const dominant = Object.entries(resourceTotals).sort((a, b) => b[1] - a[1])[0];

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Precios unitarios"
        sub="Análisis de precio unitario (APU) por concepto: recursos, rendimientos e importes por unidad de obra."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric label="Conceptos analizados" value={apus.length} icon={<Calculator size={16} />} />
        <Metric
          label="Moneda"
          value={costs.currency}
          hint="Costo directo por unidad, sin indirectos"
        />
        <Metric
          label="Componente dominante"
          value={dominant ? (RESOURCE_LABELS[dominant[0]] ?? dominant[0]) : "—"}
          hint={dominant ? `${money2(dominant[1])} en el costo unitario agregado` : undefined}
        />
      </div>

      {apus.length === 0 ? (
        <EmptyState
          icon={<Calculator size={22} />}
          title="Este procesamiento no incluye APUs"
          hint="Vuelve a procesar el proyecto para generar el análisis de precios unitarios."
        />
      ) : (
        <div className="space-y-3">
          {apus.map((apu) => (
            <ApuCard
              key={apu.concept_code}
              apu={apu}
              open={openCode === apu.concept_code}
              onToggle={() =>
                setOpen(openCode === apu.concept_code ? "" : apu.concept_code)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ApuCard({
  apu,
  open,
  onToggle,
}: {
  apu: Apu;
  open: boolean;
  onToggle: () => void;
}) {
  const breakdown = Object.entries(apu.breakdown).filter(([, v]) => v > 0);
  const total = breakdown.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-4 px-5 py-4 text-left transition hover:bg-surface-2/50"
      >
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="font-mono text-xs text-muted">{apu.concept_code}</span>
            <span className="font-medium">{apu.concept_description}</span>
          </div>
          <div className="mt-2 flex h-1.5 max-w-md overflow-hidden rounded-full bg-surface-2">
            {breakdown.map(([type, amount]) => (
              <div
                key={type}
                title={`${RESOURCE_LABELS[type] ?? type}: ${money2(amount)}`}
                style={{
                  width: `${(amount / total) * 100}%`,
                  background: RESOURCE_COLORS[type] ?? "var(--chart-5)",
                }}
              />
            ))}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-lg font-semibold tabular">{money2(apu.direct_unit_cost)}</div>
          <div className="text-xs text-muted">por {apu.unit}</div>
        </div>
        <ChevronDown
          size={18}
          className={`shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="border-t border-border">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <Th>Recurso</Th>
                  <Th>Tipo</Th>
                  <Th>Unidad</Th>
                  <Th align="right">Cantidad</Th>
                  <Th align="right">Costo unitario</Th>
                  <Th align="right">Importe</Th>
                </tr>
              </thead>
              <tbody>
                {apu.lines.map((line) => (
                  <tr
                    key={line.resource_code}
                    className="border-b border-border last:border-0"
                  >
                    <Td>
                      <div>{line.description}</div>
                      <div className="font-mono text-xs text-muted">{line.resource_code}</div>
                    </Td>
                    <Td>
                      <Badge>{RESOURCE_LABELS[line.resource_type] ?? line.resource_type}</Badge>
                    </Td>
                    <Td className="text-muted">{line.unit}</Td>
                    <Td align="right" className="tabular">
                      {num(line.quantity, 4)}
                    </Td>
                    <Td align="right" className="tabular text-muted">
                      {money2(line.unit_cost)}
                    </Td>
                    <Td align="right" className="font-medium tabular">
                      {money2(line.amount)}
                    </Td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-surface-2 font-semibold">
                  <Td colSpan={5}>Costo directo unitario</Td>
                  <Td align="right" className="tabular">
                    {money2(apu.direct_unit_cost)}
                  </Td>
                </tr>
              </tfoot>
            </table>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1.5 border-t border-border px-5 py-3">
            {breakdown.map(([type, amount]) => (
              <span key={type} className="inline-flex items-center gap-1.5 text-xs text-muted">
                <span
                  className="h-2 w-2 rounded-sm"
                  style={{ background: RESOURCE_COLORS[type] ?? "var(--chart-5)" }}
                />
                {RESOURCE_LABELS[type] ?? type}
                <span className="tabular font-medium text-foreground">{money2(amount)}</span>
                <span className="tabular">({((amount / total) * 100).toFixed(0)}%)</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
