"use client";

import { Badge, Card, SectionTitle } from "@/components/ui";
import { num, type Indicators } from "@/lib/api";

const TONE: Record<string, "success" | "warning" | "danger" | "default"> = {
  ok: "success",
  alto: "warning",
  bajo: "warning",
  falta: "danger",
  sin_dato: "default",
  sin_referencia: "default",
};
const LABEL: Record<string, string> = {
  ok: "en rango",
  alto: "alto",
  bajo: "bajo",
  falta: "falta",
  sin_dato: "sin dato",
  sin_referencia: "sin referencia",
};

/** The ratios a senior estimator checks before a presupuesto leaves the
 * office, and the partidas the taller's plantilla has that this one lacks. */
export function IndicatorsCard({ indicators }: { indicators: Partial<Indicators> }) {
  const ratios = indicators.indicators ?? [];
  const shares = indicators.phase_shares ?? [];
  if (ratios.length === 0 && shares.length === 0) return null;
  const flagged = ratios.filter((i) => i.status === "alto" || i.status === "bajo").length;
  const missing = indicators.missing_phases ?? [];
  return (
    <Card className="mt-6 p-5">
      <SectionTitle
        sub={`Razones típicas de la tipología y participación por partida contra ${indicators.reference ?? "rangos típicos"}. Fuera de rango es una señal para revisar, no una corrección.`}
      >
        Indicadores de sanidad
        {flagged > 0 && (
          <span className="ml-2 align-middle">
            <Badge tone="warning">{flagged} fuera de rango</Badge>
          </span>
        )}
        {missing.length > 0 && (
          <span className="ml-2 align-middle">
            <Badge tone="danger">
              {missing.length} partida{missing.length === 1 ? "" : "s"} faltante{missing.length === 1 ? "" : "s"}
            </Badge>
          </span>
        )}
      </SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {ratios.map((i) => (
          <div key={i.key} className="rounded-lg border border-border bg-surface p-3">
            <div className="text-xs text-muted">{i.label}</div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-lg font-semibold tabular">
                {i.value == null ? "—" : num(i.value)}
              </span>
              <span className="text-xs text-muted">{i.unit}</span>
              <Badge tone={TONE[i.status]} dot>
                {LABEL[i.status]}
              </Badge>
            </div>
            <div className="mt-1 text-[11px] text-faint">
              {i.low != null && i.high != null && `típico ${num(i.low)}–${num(i.high)} · `}
              {i.detail}
            </div>
          </div>
        ))}
      </div>
      {shares.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {shares.map((s) => (
            <span
              key={s.phase}
              className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-xs"
              title={
                s.typical_pct != null
                  ? `${s.phase}: ${s.share_pct}% aquí · ${s.typical_pct}% en la plantilla`
                  : `${s.phase}: ${s.share_pct}% del costo directo`
              }
            >
              <span className="font-medium">{s.phase}</span>
              <span className="tabular text-muted">{s.share_pct}%</span>
              {s.typical_pct != null && (
                <span className="tabular text-faint">/ {s.typical_pct}%</span>
              )}
              <Badge tone={TONE[s.status]}>{LABEL[s.status]}</Badge>
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}
