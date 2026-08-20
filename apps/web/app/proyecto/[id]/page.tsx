"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  MapTrifold,
  Receipt,
  Ruler,
  Stack,
  Money,
  TrendUp,
  ShieldCheck,
  CalendarBlank,
} from "@phosphor-icons/react";
import {
  getViews,
  getDimensions,
  money,
  type Views,
  type Dimensions,
} from "@/lib/api";
import { useCostReport } from "@/lib/useProjectReport";
import { phaseColor } from "@/lib/phases";
import {
  buttonClasses,
  Callout,
  Card,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonMetrics,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function Resumen() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [views, setViews] = useState<Views | null>(null);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const { latestEvent, connectionEpoch } = useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getViews(id).then(setViews).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getViews(id).then(setViews).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
  }, [id, latestEvent]);

  const months = costs ? Math.round(costs.schedule.total_duration_days / 24) : 0;

  return (
    <div className="px-6 py-7 lg:px-8">
      <PageHeader
        title="Resumen del proyecto"
        actions={
          <>
            <Link href={`/proyecto/${id}/plano`} className={buttonClasses("secondary")}>
              <MapTrifold size={16} /> Ver plano
            </Link>
            <Link href={`/proyecto/${id}/presupuesto`} className={buttonClasses("primary")}>
              <Receipt size={16} /> Presupuesto
            </Link>
          </>
        }
      />

      {error && (
        <Callout tone="danger">
          No se pudo cargar el resumen de costos. Revisa que el servidor esté activo.
        </Callout>
      )}

      {costs && (
        <div className="rise-in">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Costo directo"
              value={money(costs.integration.direct_cost)}
              icon={<Money size={16} weight="duotone" />}
            />
            <Metric
              label="Precio de venta"
              value={money(costs.integration.sale_price)}
              hint={`factor ${costs.integration.overcost_factor.toFixed(3)}`}
              icon={<TrendUp size={16} weight="duotone" />}
            />
            <Metric
              label="Total c/ contingencia"
              value={money(costs.integration.grand_total)}
              accent="accent"
              icon={<ShieldCheck size={16} weight="duotone" />}
            />
            <Metric
              label="Plazo estimado"
              value={`${costs.schedule.total_duration_days} días`}
              hint={`~${months} meses · ${costs.schedule.phases.length} fases`}
              icon={<CalendarBlank size={16} weight="duotone" />}
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
                    icon={<Stack size={15} />}
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

          <p className="mt-6 text-xs text-muted">
            Precios de insumos de referencia (MXN); sustituir por cotizaciones del proyecto.
            Cantidades deduplicadas por vista; revisar conceptos de baja confianza.
          </p>
        </div>
      )}

      {!costs && !error && (
        <div>
          <SkeletonMetrics count={4} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <Skeleton className="h-4 w-40" />
              <div className="mt-5 space-y-4">
                {Array.from({ length: 3 }, (_, i) => (
                  <div key={i}>
                    <div className="mb-2 flex justify-between">
                      <Skeleton className="h-3.5 w-28" />
                      <Skeleton className="h-3.5 w-20" />
                    </div>
                    <Skeleton className="h-2.5" />
                  </div>
                ))}
              </div>
            </Card>
            <Card className="p-5">
              <Skeleton className="h-4 w-32" />
              <div className="mt-5 space-y-3">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i} className="flex justify-between">
                    <Skeleton className="h-3.5 w-24" />
                    <Skeleton className="h-3.5 w-16" />
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
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
      <dt className="flex items-center gap-2 text-muted">
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
  const sum = entries.reduce((acc, [, v]) => acc + v, 0) || 1;
  return (
    <div className="space-y-4">
      {entries.map(([phase, value], index) => (
        <div key={phase}>
          <div className="mb-1.5 flex items-baseline justify-between text-sm">
            <span className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ background: phaseColor(phase, index) }}
              />
              {phase}
              <span className="text-xs text-muted">
                {((value / sum) * 100).toFixed(0)}%
              </span>
            </span>
            <span className="font-medium tabular">{money(value)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{
                width: `${(value / max) * 100}%`,
                background: phaseColor(phase, index),
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
