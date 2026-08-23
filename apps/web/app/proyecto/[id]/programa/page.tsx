"use client";

import { useParams } from "next/navigation";
import { CalendarBlank, Stack, ListChecks } from "@phosphor-icons/react";
import { money, num, type ScheduleActivity } from "@/lib/api";
import { phaseColor } from "@/lib/phases";
import { useCostReport, useProjectReviews } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { moneyGate, UnitsGate, UnverifiedBanner } from "@/components/MoneyGate";
import {
  Callout,
  Card,
  EmptyState,
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
  const { actorName } = useProjectLive();

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
        title="Programa de obra"
        sub="Secuencia de actividades derivada de las cantidades y rendimientos; duraciones en días laborables."
      />
      <UnverifiedBanner id={id} costs={costs} reviews={reviews} />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric
          label="Duración total"
          value={`${totalDays} días`}
          hint={`≈ ${months} ${months === 1 ? "mes" : "meses"} (24 días/mes)`}
          icon={<CalendarBlank size={16} weight="duotone" />}
          accent="accent"
        />
        <Metric
          label="Actividades"
          value={activities.length}
          icon={<ListChecks size={16} weight="duotone" />}
        />
        <Metric label="Fases" value={phases.length} icon={<Stack size={16} weight="duotone" />} />
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
  return (
    <div className="group flex items-center gap-0 py-1">
      <div className="w-[240px] shrink-0 pr-4">
        <div className="truncate text-sm" title={activity.description}>
          {activity.description}
        </div>
        <div className="text-[11px] tabular text-faint">
          {num(activity.quantity)} {activity.unit} · {activity.duration_days} días
        </div>
      </div>
      <div className="relative h-6 flex-1 rounded bg-surface-2/60">
        <div
          className="absolute top-1 h-4 rounded-[4px] opacity-90 transition group-hover:opacity-100"
          title={`${activity.description} · día ${activity.start_day} → ${activity.end_day} · ${money(activity.direct_cost)}`}
          style={{ left: `${left}%`, width: `${width}%`, background: color }}
        />
      </div>
    </div>
  );
}
