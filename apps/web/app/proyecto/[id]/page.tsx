"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Map, Receipt, Ruler, Layers } from "lucide-react";
import {
  getCosts,
  getViews,
  getDimensions,
  money,
  type CostReport,
  type Views,
  type Dimensions,
} from "@/lib/api";
import { Card, Metric, SectionTitle, Badge } from "@/components/ui";

export default function Resumen() {
  const { id } = useParams<{ id: string }>();
  const [costs, setCosts] = useState<CostReport | null>(null);
  const [views, setViews] = useState<Views | null>(null);
  const [dims, setDims] = useState<Dimensions | null>(null);

  useEffect(() => {
    getCosts(id).then(setCosts).catch(() => {});
    getViews(id).then(setViews).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
  }, [id]);

  const months = costs ? Math.round(costs.schedule.total_duration_days / 24) : 0;

  return (
    <div className="px-8 py-7">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Resumen del proyecto</h1>
        <div className="flex gap-2">
          <Link
            href={`/proyecto/${id}/plano`}
            className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm font-medium hover:bg-[var(--surface-2)]"
          >
            <Map size={16} /> Ver plano
          </Link>
          <Link
            href={`/proyecto/${id}/presupuesto`}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--primary)] px-3 py-2 text-sm font-medium text-white"
          >
            <Receipt size={16} /> Presupuesto
          </Link>
        </div>
      </div>

      {costs && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Costo directo" value={money(costs.integration.direct_cost)} />
            <Metric
              label="Precio de venta"
              value={money(costs.integration.sale_price)}
              hint={`factor ${costs.integration.overcost_factor.toFixed(3)}`}
            />
            <Metric
              label="Total c/ contingencia"
              value={money(costs.integration.grand_total)}
              accent="primary"
            />
            <Metric
              label="Plazo estimado"
              value={`${costs.schedule.total_duration_days} días`}
              hint={`~${months} meses · ${costs.schedule.phases.length} fases`}
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <SectionTitle sub="Importe del costo directo por fase de obra">
                Costo directo por fase
              </SectionTitle>
              <PhaseBars totals={costs.boq.totals_by_phase} />
            </Card>

            <Card className="p-5">
              <SectionTitle>Lectura del plano</SectionTitle>
              <dl className="space-y-3 text-sm">
                <Row
                  icon={<Ruler size={15} />}
                  label="Unidades"
                  value={`${costs.drawing_units.unit} · ${Math.round(
                    costs.drawing_units.confidence * 100,
                  )}%`}
                />
                {views?.is_segmented && (
                  <Row
                    icon={<Layers size={15} />}
                    label="Vistas de planta"
                    value={`${views.views.filter((v) => v.kind === "plan").length} · NPT ${
                      views.npt_levels.length
                    }`}
                  />
                )}
                {dims && (
                  <>
                    <Row
                      icon={<Ruler size={15} />}
                      label="Cotas leídas"
                      value={`${dims.dimension_count}`}
                    />
                    {dims.typical_wall_thickness_cm && (
                      <Row
                        label="Espesor de muro"
                        value={`${dims.typical_wall_thickness_cm} cm`}
                      />
                    )}
                    {dims.vigueta_system && (
                      <Row label="Sistema de losa" value={`vigueta ${dims.vigueta_system}`} />
                    )}
                  </>
                )}
              </dl>
            </Card>
          </div>

          <p className="mt-6 text-xs text-[var(--muted)]">
            Precios de insumos de referencia (MXN); sustituir por cotizaciones del proyecto.
            Cantidades deduplicadas por vista; revisar conceptos de baja confianza.
          </p>
        </>
      )}

      {!costs && (
        <div className="text-sm text-[var(--muted)]">Cargando indicadores…</div>
      )}
    </div>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <dt className="flex items-center gap-2 text-[var(--muted)]">
        {icon}
        {label}
      </dt>
      <dd className="font-medium tabular">{value}</dd>
    </div>
  );
}

function PhaseBars({ totals }: { totals: Record<string, number> }) {
  const entries = Object.entries(totals);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  const colors: Record<string, string> = {
    Preliminares: "#0d9488",
    Cimentación: "#d97706",
    Estructura: "#1d4ed8",
  };
  return (
    <div className="space-y-3">
      {entries.map(([phase, value]) => (
        <div key={phase}>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span>{phase}</span>
            <span className="font-medium tabular">{money(value)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-[var(--surface-2)]">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(value / max) * 100}%`,
                background: colors[phase] ?? "#64748b",
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
