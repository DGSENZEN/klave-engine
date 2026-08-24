"use client";

import { useParams } from "next/navigation";
import { CalendarBlank, Stack, ListChecks } from "@phosphor-icons/react";
import { useState } from "react";
import {
  getCostingConfig,
  money,
  num,
  recompute,
  type ScheduleActivity,
} from "@/lib/api";
import { phaseColor } from "@/lib/phases";
import { useCostReport, useProjectReviews } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { ProgramaFlujoTabs } from "@/components/ProgramaFlujoTabs";
import { moneyGate, UnitsGate, UnverifiedBanner } from "@/components/MoneyGate";
import { PlantillaCampo } from "@/components/PlantillaCampo";
import {
  Callout,
  Card,
  EmptyState,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonHeader,
  SkeletonMetrics,
} from "@/components/ui";

export default function ProgramaPage() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const reviews = useProjectReviews(id);
  const { actorName, clientId } = useProjectLive();
  const [dateBusy, setDateBusy] = useState(false);
  const [dateError, setDateError] = useState<string | null>(null);

  async function setStartDate(value: string) {
    setDateBusy(true);
    setDateError(null);
    try {
      const current = await getCostingConfig(id);
      current.config.schedule.start_date = value || null;
      await recompute(
        id,
        { config: current.config, insumo_prices: current.insumo_prices, version: current.version },
        actorName,
        clientId,
      );
    } catch {
      setDateError("No se pudo guardar la fecha de arranque; inténtalo de nuevo.");
    } finally {
      setDateBusy(false);
    }
  }

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Programa de obra" />
        <Callout tone="danger">
          No se pudo cargar el programa de obra. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!costs) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <SkeletonMetrics count={3} />
        <Card className="p-5">
          <Skeleton className="h-4 w-40" />
          <div className="mt-6 space-y-3">
            {Array.from({ length: 6 }, (_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Skeleton className="h-3.5 w-56 shrink-0" />
                <div className="relative h-5 flex-1">
                  <Skeleton
                    className="absolute top-0.5 h-4"
                    style={{ left: `${(i * 13) % 55}%`, width: `${12 + ((i * 9) % 28)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  if (moneyGate(costs, reviews) === "blocked") {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Programa de obra" />
        <UnitsGate id={id} costs={costs} actorName={actorName} />
      </div>
    );
  }

  const activities = costs.schedule.activities ?? [];
  const criticalCount = activities.filter((a) => a.critical).length;
  const totalDays = Math.max(
    costs.schedule.total_duration_days,
    ...activities.map((a) => a.end_day),
    1,
  );
  const months = Math.max(1, Math.round(totalDays / 24));
  const phases = costs.schedule.phases.filter((phase) =>
    activities.some((a) => a.phase === phase),
  );

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Programa y flujo"
        sub="Red de actividades derivada de las cantidades y del rendimiento de cada matriz; holguras y ruta crítica conforme al RLOPSRM art. 224."
      />
      <ProgramaFlujoTabs id={id} />
      <UnverifiedBanner id={id} costs={costs} reviews={reviews} />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric
          label="Plazo contractual"
          value={`${costs.schedule.calendar_days ?? totalDays} días naturales`}
          hint={`${totalDays} días hábiles en semana de seis días · ≈ ${months} ${
            months === 1 ? "mes" : "meses"
          }. El contrato se cuenta en naturales (LOPSRM art. 31 fr. V).`}
          icon={<CalendarBlank size={16} weight="duotone" />}
          accent="accent"
        />
        <Metric
          label={costs.schedule.end_date ? "Termina" : "Actividades"}
          value={
            costs.schedule.end_date
              ? formatDate(costs.schedule.end_date)
              : activities.length
          }
          hint={costs.schedule.end_date ? `${activities.length} actividades` : undefined}
          icon={<ListChecks size={16} weight="duotone" />}
        />
        <Metric
          label="En ruta crítica"
          value={`${criticalCount} de ${activities.length}`}
          hint={
            criticalCount >= activities.length * 0.8
              ? "Casi todo es crítico: con una cuadrilla por actividad y un solo frente, el programa es una cadena sin holgura. Sube cuadrillas o abre frentes para ganar margen."
              : `${activities.length - criticalCount} actividades tienen holgura`
          }
          icon={<Stack size={16} weight="duotone" />}
          accent={criticalCount >= activities.length * 0.8 ? "danger" : undefined}
        />
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted">Fecha de arranque</span>
          <Input
            type="date"
            defaultValue={costs.schedule.start_date ?? ""}
            onChange={(e) => void setStartDate(e.target.value)}
            disabled={dateBusy}
            className="px-2 py-1.5"
            aria-label="Fecha de arranque de la obra"
          />
        </label>
        <span className="text-xs text-muted">
          {dateBusy
            ? "Recalculando el calendario…"
            : costs.schedule.start_date
              ? "Semana de seis días (domingos no laborables); los días se vuelven fechas."
              : "Sin fecha, el programa queda en días laborables relativos."}
        </span>
        {dateError && <span className="text-xs text-danger">{dateError}</span>}
      </div>

      {activities.length === 0 ? (
        <EmptyState
          icon={<CalendarBlank size={22} weight="duotone" />}
          title="Este procesamiento no incluye programa"
          hint="Vuelve a procesar el proyecto para generar el programa de obra."
        />
      ) : (
        <Card className="p-5">
          <SectionTitle sub="Cada barra abarca del día de inicio al de término de la actividad.">
            Diagrama de barras
          </SectionTitle>
          <div className="overflow-x-auto">
            <div className="min-w-[720px]">
              <DayScale totalDays={totalDays} />
              {phases.map((phase, phaseIndex) => {
                const phaseActivities = activities.filter((a) => a.phase === phase);
                const phaseCost = phaseActivities.reduce((s, a) => s + a.direct_cost, 0);
                return (
                  <div key={phase} className="mt-4 first:mt-2">
                    <div className="mb-1.5 flex items-baseline justify-between gap-3">
                      <span className="microlabel flex items-center gap-2">
                        <span
                          className="h-2.5 w-2.5 rounded-sm"
                          style={{ background: phaseColor(phase, phaseIndex) }}
                        />
                        {phase}
                      </span>
                      <span className="tabular text-xs text-muted">{money(phaseCost)}</span>
                    </div>
                    {phaseActivities.map((activity) => (
                      <GanttRow
                        key={activity.concept_code}
                        activity={activity}
                        totalDays={totalDays}
                        color={phaseColor(phase, phaseIndex)}
                      />
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      )}

      {/* El quinto programa del art. 45-A: el único que no sale del
          presupuesto, porque el personal de campo es costo indirecto. */}
      <div className="mt-6">
        <PlantillaCampo id={id} />
      </div>
    </div>
  );
}

function DayScale({ totalDays }: { totalDays: number }) {
  // ~6 ticks, snapped to multiples of 5 days for readability.
  const rawStep = totalDays / 6;
  const step = Math.max(5, Math.round(rawStep / 5) * 5);
  const ticks: number[] = [];
  for (let day = 0; day <= totalDays; day += step) ticks.push(day);
  return (
    <div className="relative ml-[240px] h-5 border-b border-border">
      {ticks.map((day) => (
        <span
          key={day}
          className="absolute top-0 -translate-x-1/2 text-[10px] tabular text-faint"
          style={{ left: `${(day / totalDays) * 100}%` }}
        >
          {day === 0 ? "día 0" : day}
        </span>
      ))}
    </div>
  );
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T12:00:00`);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "2-digit" });
}

function GanttRow({
  activity,
  totalDays,
  color,
}: {
  activity: ScheduleActivity;
  totalDays: number;
  color: string;
}) {
  const left = (activity.start_day / totalDays) * 100;
  const width = Math.max(((activity.end_day - activity.start_day) / totalDays) * 100, 0.8);
  // Holgura drawn as the bar's shadow: how far this activity could slide
  // before it pushes the obra's end. RLOPSRM art. 224 asks for it, and it is
  // the difference between a bar chart and a programa you can defend.
  const float = activity.total_float_days ?? 0;
  const floatWidth = (float / totalDays) * 100;
  return (
    <div className="group flex items-center gap-0 py-1">
      <div className="w-[240px] shrink-0 pr-4">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm" title={activity.description}>
            {activity.description}
          </span>
          {activity.critical && (
            <span
              className="shrink-0 rounded bg-danger-soft px-1 text-[10px] font-semibold text-danger"
              title="En la ruta crítica: retrasarla retrasa toda la obra"
            >
              CRÍTICA
            </span>
          )}
        </div>
        <div className="text-[11px] tabular text-faint">
          {num(activity.quantity)} {activity.unit} · {activity.duration_days} días
          {float > 0 && ` · ${float} d de holgura`}
          {activity.start_date && ` · ${formatDate(activity.start_date)}`}
        </div>
      </div>
      <div className="relative h-6 flex-1 rounded bg-surface-2/60">
        {float > 0 && (
          <div
            className="absolute top-[9px] h-1 rounded-full opacity-45"
            title={`Holgura total ${float} días: puede recorrerse ese tanto sin mover la fecha final`}
            style={{
              left: `${left + width}%`,
              width: `${Math.max(floatWidth, 0.4)}%`,
              background: color,
            }}
          />
        )}
        <div
          className={`absolute top-1 h-4 rounded-[4px] opacity-90 transition group-hover:opacity-100 ${
            activity.critical ? "ring-1 ring-danger/60" : ""
          }`}
          title={
            activity.start_date && activity.end_date
              ? `${activity.description} · ${formatDate(activity.start_date)} → ${formatDate(activity.end_date)} · ${money(activity.direct_cost)}`
              : `${activity.description} · día ${activity.start_day} → ${activity.end_day} · ${money(activity.direct_cost)}`
          }
          style={{ left: `${left}%`, width: `${width}%`, background: color }}
        />
      </div>
    </div>
  );
}
