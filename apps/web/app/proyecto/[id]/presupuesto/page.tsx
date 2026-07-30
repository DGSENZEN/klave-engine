"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Download } from "lucide-react";
import {
  getCosts,
  getDimensions,
  money,
  money2,
  num,
  type BoqLine,
  type CostReport,
  type Dimensions,
} from "@/lib/api";
import { Button, Card, Metric, SectionTitle, Badge, Skeleton } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function PresupuestoPage() {
  const { id } = useParams<{ id: string }>();
  const [costs, setCosts] = useState<CostReport | null>(null);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const { latestEvent, sendActivity, connectionEpoch } = useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getCosts(id).then(setCosts).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (!latestEvent) return;
    if (latestEvent.type === "costing_updated" || latestEvent.type === "run_published") {
      getCosts(id).then(setCosts).catch(() => {});
    }
    if (latestEvent.type === "run_published") {
      getDimensions(id).then(setDims).catch(() => {});
    }
  }, [id, latestEvent]);

  function downloadCsv() {
    if (!costs) return;
    sendActivity("exporting_budget", "Presupuesto CSV");
    const rows = [
      ["clave", "concepto", "unidad", "cantidad", "p_unitario", "importe", "fase", "confianza"],
      ...costs.boq.lines.map((l) => [
        l.concept_code,
        `"${l.description}"`,
        l.unit,
        l.quantity,
        l.unit_price,
        l.amount,
        l.phase,
        l.confidence,
      ]),
      [],
      ["", "COSTO DIRECTO", "", "", "", costs.boq.direct_cost_total],
      ["", "PRECIO DE VENTA", "", "", "", costs.integration.sale_price],
      ["", "TOTAL", "", "", "", costs.integration.grand_total],
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "presupuesto.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!costs) {
    return (
      <div className="px-8 py-7">
        <Skeleton className="mb-6 h-14 w-96" />
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
        </div>
        <Skeleton className="h-80" />
      </div>
    );
  }

  const avgConf =
    costs.boq.lines.reduce((s, l) => s + l.confidence, 0) / (costs.boq.lines.length || 1);
  const phases = [...new Set(costs.boq.lines.map((l) => l.phase))];

  return (
    <div className="rise-in px-8 py-7">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Catálogo de conceptos</h1>
          <p className="text-sm text-[var(--muted)]">
            Cantidades deducidas del plano · precios de referencia (MXN)
          </p>
        </div>
        <Button onClick={downloadCsv}>
          <Download size={16} /> CSV
        </Button>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric label="Costo directo" value={money(costs.boq.direct_cost_total)} />
        <Metric label="Conceptos" value={costs.boq.lines.length} />
        <Metric
          label="Confianza promedio"
          value={`${(avgConf * 100).toFixed(0)}%`}
          accent={avgConf >= 0.7 ? "success" : undefined}
        />
      </div>

      <Card className="mb-6 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--surface-2)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="px-4 py-3 font-semibold">Clave</th>
              <th className="px-4 py-3 font-semibold">Concepto</th>
              <th className="px-4 py-3 text-right font-semibold">Cantidad</th>
              <th className="px-4 py-3 text-right font-semibold">P.U.</th>
              <th className="px-4 py-3 text-right font-semibold">Importe</th>
              <th className="px-4 py-3 text-center font-semibold">Conf.</th>
            </tr>
          </thead>
          <tbody>
            {phases.map((phase) => {
              const lines = costs.boq.lines.filter((l) => l.phase === phase);
              const subtotal = lines.reduce((s, l) => s + l.amount, 0);
              return (
                <PhaseGroup
                  key={phase}
                  phase={phase}
                  lines={lines}
                  subtotal={subtotal}
                />
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-[var(--surface-2)] font-semibold">
              <td className="px-4 py-3" colSpan={4}>
                Costo directo
              </td>
              <td className="px-4 py-3 text-right tabular" colSpan={2}>
                {money2(costs.boq.direct_cost_total)}
              </td>
            </tr>
          </tfoot>
        </table>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle>Integración del precio</SectionTitle>
          <div className="space-y-2 text-sm">
            <Line label="Costo directo" value={money2(costs.integration.direct_cost)} bold />
            {costs.integration.lines.map((l) => (
              <Line
                key={l.description}
                label={`${l.description} (${l.percentage}%)`}
                value={money2(l.amount)}
                muted
              />
            ))}
            <div className="my-2 border-t border-[var(--border)]" />
            <Line
              label={`Precio de venta · factor ${costs.integration.overcost_factor.toFixed(3)}`}
              value={money2(costs.integration.sale_price)}
              bold
            />
            <Line label="Contingencia" value={money2(costs.integration.contingency)} muted />
            <Line
              label="Total con contingencia"
              value={money2(costs.integration.grand_total)}
              bold
              accent
            />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle sub="Fuente de verdad leída del archivo">
            Dimensiones detectadas
          </SectionTitle>
          {dims ? (
            <div className="space-y-2.5 text-sm">
              <Line
                label="Sección típica"
                value={
                  dims.typical_section_cm
                    ? `${dims.typical_section_cm[0]}×${dims.typical_section_cm[1]} cm`
                    : "—"
                }
              />
              <Line
                label="Espesor de muro"
                value={
                  dims.typical_wall_thickness_cm
                    ? `${dims.typical_wall_thickness_cm} cm`
                    : "—"
                }
              />
              <Line label="Sistema de losa" value={dims.vigueta_system ?? "—"} />
              <Line label="Cotas (DIMENSION)" value={`${dims.dimension_count}`} />
              {dims.typical_wall_thickness_source && (
                <p className="pt-1 text-xs text-[var(--muted)]">
                  Espesor de muro · fuente: {dims.typical_wall_thickness_source}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-[var(--muted)]">Sin dimensiones detectadas.</p>
          )}
        </Card>
      </div>

      {costs.boq.warnings.length > 0 && (
        <Card className="mt-6 p-5">
          <SectionTitle>Advertencias ({costs.boq.warnings.length})</SectionTitle>
          <ul className="space-y-1.5 text-sm text-[var(--warning)]">
            {costs.boq.warnings.slice(0, 8).map((w, i) => (
              <li key={i}>• {w}</li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function PhaseGroup({
  phase,
  lines,
  subtotal,
}: {
  phase: string;
  lines: BoqLine[];
  subtotal: number;
}) {
  return (
    <>
      <tr className="border-b border-[var(--border)] bg-[var(--surface-2)]/60">
        <td colSpan={4} className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
          {phase}
        </td>
        <td colSpan={2} className="px-4 py-2 text-right text-xs font-semibold tabular text-[var(--muted)]">
          {money2(subtotal)}
        </td>
      </tr>
      {lines.map((l) => (
        <tr
          key={l.concept_code}
          className="border-b border-[var(--border)] transition-colors last:border-0 hover:bg-[var(--primary-soft)]/30"
        >
          <td className="px-4 py-3 font-mono text-xs text-[var(--muted)]">{l.concept_code}</td>
          <td className="px-4 py-3">{l.description}</td>
          <td className="px-4 py-3 text-right tabular">
            {num(l.quantity)} <span className="text-xs text-[var(--muted)]">{l.unit}</span>
          </td>
          <td className="px-4 py-3 text-right tabular text-[var(--muted)]">
            {money2(l.unit_price)}
          </td>
          <td className="px-4 py-3 text-right font-medium tabular">{money2(l.amount)}</td>
          <td className="px-4 py-3 text-center">
            <Badge dot tone={l.confidence >= 0.7 ? "success" : "warning"}>
              {(l.confidence * 100).toFixed(0)}%
            </Badge>
          </td>
        </tr>
      ))}
    </>
  );
}

function Line({
  label,
  value,
  bold,
  muted,
  accent,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className={muted ? "text-[var(--muted)]" : ""}>{label}</span>
      <span
        className={`tabular ${bold ? "font-semibold" : ""} ${
          accent ? "text-[var(--primary)]" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}
