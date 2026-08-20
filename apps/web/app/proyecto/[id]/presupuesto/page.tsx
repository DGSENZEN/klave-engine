"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Download, TriangleAlert } from "lucide-react";
import {
  getDimensions,
  money,
  money2,
  num,
  type BoqLine,
  type Dimensions,
} from "@/lib/api";
import { useCostReport } from "@/lib/useProjectReport";
import {
  Badge,
  Button,
  Callout,
  Card,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  TableCard,
  Td,
  Th,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function PresupuestoPage() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const { latestEvent, sendActivity, connectionEpoch } = useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getDimensions(id).then(setDims).catch(() => {});
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getDimensions(id).then(setDims).catch(() => {});
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

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Catálogo de conceptos" />
        <Callout tone="danger">
          No se pudo cargar el presupuesto. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!costs) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <Skeleton className="mb-6 h-14 w-96 max-w-full" />
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
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Catálogo de conceptos"
        sub="Cantidades deducidas del plano · precios de referencia (MXN)"
        actions={
          <Button onClick={downloadCsv}>
            <Download size={16} /> CSV
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric label="Costo directo" value={money(costs.boq.direct_cost_total)} />
        <Metric label="Conceptos" value={costs.boq.lines.length} />
        <Metric
          label="Confianza promedio"
          value={`${(avgConf * 100).toFixed(0)}%`}
          accent={avgConf >= 0.7 ? "success" : undefined}
        />
      </div>

      <TableCard className="mb-6">
        <thead>
          <tr className="border-b border-border bg-surface-2">
            <Th>Clave</Th>
            <Th>Concepto</Th>
            <Th align="right">Cantidad</Th>
            <Th align="right">P.U.</Th>
            <Th align="right">Importe</Th>
            <Th align="center">Conf.</Th>
          </tr>
        </thead>
        <tbody>
          {phases.map((phase) => {
            const lines = costs.boq.lines.filter((l) => l.phase === phase);
            const subtotal = lines.reduce((s, l) => s + l.amount, 0);
            return <PhaseGroup key={phase} phase={phase} lines={lines} subtotal={subtotal} />;
          })}
        </tbody>
        <tfoot>
          <tr className="bg-surface-2 font-semibold">
            <Td colSpan={4}>Costo directo</Td>
            <Td align="right" className="tabular" colSpan={2}>
              {money2(costs.boq.direct_cost_total)}
            </Td>
          </tr>
        </tfoot>
      </TableCard>

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
            <div className="my-2 border-t border-border" />
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
                  dims.typical_wall_thickness_cm ? `${dims.typical_wall_thickness_cm} cm` : "—"
                }
              />
              <Line label="Sistema de losa" value={dims.vigueta_system ?? "—"} />
              <Line label="Cotas (DIMENSION)" value={`${dims.dimension_count}`} />
              {dims.typical_wall_thickness_source && (
                <p className="pt-1 text-xs text-muted">
                  Espesor de muro · fuente: {dims.typical_wall_thickness_source}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted">Sin dimensiones detectadas.</p>
          )}
        </Card>
      </div>

      {costs.boq.warnings.length > 0 && (
        <Card className="mt-6 p-5">
          <SectionTitle sub="Revisar antes de usar el presupuesto como referencia.">
            Advertencias ({costs.boq.warnings.length})
          </SectionTitle>
          <ul className="space-y-1.5 text-sm text-warning">
            {costs.boq.warnings.slice(0, 8).map((w, i) => (
              <li key={i} className="flex items-start gap-2">
                <TriangleAlert size={15} className="mt-0.5 shrink-0" />
                {w}
              </li>
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
      <tr className="border-b border-border bg-surface-2/60">
        <td
          colSpan={4}
          className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted"
        >
          {phase}
        </td>
        <td
          colSpan={2}
          className="px-4 py-2 text-right text-xs font-semibold tabular text-muted"
        >
          {money2(subtotal)}
        </td>
      </tr>
      {lines.map((l) => (
        <tr
          key={l.concept_code}
          className="border-b border-border transition-colors last:border-0 hover:bg-primary-soft/30"
        >
          <Td className="font-mono text-xs text-muted">{l.concept_code}</Td>
          <Td>{l.description}</Td>
          <Td align="right" className="tabular">
            {num(l.quantity)} <span className="text-xs text-muted">{l.unit}</span>
          </Td>
          <Td align="right" className="tabular text-muted">
            {money2(l.unit_price)}
          </Td>
          <Td align="right" className="font-medium tabular">
            {money2(l.amount)}
          </Td>
          <Td align="center">
            <Badge dot tone={l.confidence >= 0.7 ? "success" : "warning"}>
              {(l.confidence * 100).toFixed(0)}%
            </Badge>
          </Td>
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
    <div className="flex items-center justify-between gap-4">
      <span className={muted ? "text-muted" : ""}>{label}</span>
      <span
        className={`tabular ${bold ? "font-semibold" : ""} ${accent ? "text-primary" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
