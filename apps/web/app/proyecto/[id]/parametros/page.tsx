"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { RotateCcw, Calculator, Loader2, CircleAlert } from "lucide-react";
import {
  ApiError,
  getCostingConfig,
  getCosts,
  recompute,
  money,
  type CostingConfigResponse,
  type CostingConfigFull,
  type CostReport,
  type Insumo,
  type ProjectEvent,
} from "@/lib/api";
import { Button, Card, SectionTitle, Badge, Skeleton } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";
import { actorLabel } from "@/lib/collab";

const LABELS: Record<string, string> = {
  // assumptions
  column_section_m2: "Sección de columna (m²)",
  column_height_m: "Altura de columna (m)",
  beam_section_m2: "Sección de trabe (m²)",
  wall_height_m: "Altura de muro (m)",
  footing_depth_m: "Peralte de zapata (m)",
  excavation_depth_m: "Prof. excavación (m)",
  excavation_swell_factor: "Factor abundamiento",
  // indirects
  field_indirects_pct: "Indirectos de campo (%)",
  office_indirects_pct: "Indirectos de oficina (%)",
  financing_pct: "Financiamiento (%)",
  profit_pct: "Utilidad (%)",
  additional_charges_pct: "Cargos adicionales (%)",
  contingency_pct: "Contingencia (%)",
  // financial
  advance_payment_pct: "Anticipo (%)",
  retention_pct: "Retención (%)",
  annual_operation_pct: "Operación anual (%)",
  annual_maintenance_pct: "Mantenimiento anual (%)",
  operating_horizon_years: "Horizonte O&M (años)",
};

const TYPE_LABELS: Record<string, string> = {
  material: "Material",
  mano_de_obra: "Mano de obra",
  equipo: "Equipo",
};

type ConflictDetail = {
  error_type?: string;
  current_version?: number;
  updated_by?: string | null;
  message?: string;
};

export default function ParametrosPage() {
  const { id } = useParams<{ id: string }>();
  const [config, setConfig] = useState<CostingConfigFull | null>(null);
  const [insumos, setInsumos] = useState<Insumo[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [report, setReport] = useState<CostReport | null>(null);
  const [baseline, setBaseline] = useState<{ direct: number; total: number } | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [conflict, setConflict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const activityTimer = useRef<number | null>(null);
  const { latestEvent, actorName, clientId, sendActivity } = useProjectLive();

  const applyConfigResponse = useCallback((response: CostingConfigResponse) => {
    setConfig(response.config);
    setInsumos(response.insumos);
    setPrices(response.insumo_prices);
    setVersion(response.version);
  }, []);

  const isRemoteEvent = useCallback(
    (event: ProjectEvent): boolean => {
      const eventClientId = event.data.client_id;
      if (typeof eventClientId === "string" && clientId) return eventClientId !== clientId;
      return event.actor !== actorName;
    },
    [actorName, clientId],
  );

  useEffect(() => {
    let active = true;
    Promise.all([getCostingConfig(id), getCosts(id)])
      .then(([r, c]) => {
        if (!active) return;
        applyConfigResponse(r);
        setReport(c);
        setBaseline({ direct: c.boq.direct_cost_total, total: c.integration.grand_total });
        setDirty(false);
        setConflict(null);
        setError(null);
      })
      .catch(() => {
        if (active) setError("No se pudieron cargar los parámetros.");
      });
    return () => {
      active = false;
    };
  }, [applyConfigResponse, id]);

  useEffect(() => {
    if (!latestEvent) return;
    if (latestEvent.type === "costing_updated" && isRemoteEvent(latestEvent) && dirty) {
      const handle = window.setTimeout(() => {
        setConflict(`${actorLabel(latestEvent.actor)} actualizó los parámetros — recargar`);
      }, 0);
      return () => window.clearTimeout(handle);
    }
    if (latestEvent.type !== "costing_updated" && latestEvent.type !== "run_published") return;

    let active = true;
    Promise.all([getCostingConfig(id), getCosts(id)])
      .then(([r, c]) => {
        if (!active) return;
        applyConfigResponse(r);
        setReport(c);
        setBaseline({ direct: c.boq.direct_cost_total, total: c.integration.grand_total });
        setDirty(false);
        setConflict(null);
        setError(null);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [applyConfigResponse, dirty, id, isRemoteEvent, latestEvent]);

  useEffect(
    () => () => {
      if (activityTimer.current) window.clearTimeout(activityTimer.current);
    },
    [],
  );

  function announceEdit(label: string) {
    if (activityTimer.current) window.clearTimeout(activityTimer.current);
    activityTimer.current = window.setTimeout(() => {
      sendActivity("editing_costing", label);
    }, 350);
  }

  function setField(group: keyof CostingConfigFull, key: string, value: number) {
    setConfig((c) => (c ? { ...c, [group]: { ...(c[group] as object), [key]: value } } : c));
    setDirty(true);
    setConflict(null);
    announceEdit(LABELS[key] ?? key);
  }
  function setPrice(code: string, label: string, value: number) {
    setPrices((p) => ({ ...p, [code]: value }));
    setDirty(true);
    setConflict(null);
    announceEdit(label);
  }

  function conflictMessage(detail: ConflictDetail | undefined) {
    return `${actorLabel(detail?.updated_by)} actualizó los parámetros — recargar`;
  }

  function handleSaveError(err: unknown) {
    if (err instanceof ApiError && err.status === 409) {
      const detail = err.detail as ConflictDetail | undefined;
      if (detail?.error_type === "version_conflict") {
        setConflict(conflictMessage(detail));
        return;
      }
      setError(detail?.message ?? "El proyecto está ocupado; inténtalo de nuevo.");
      return;
    }
    setError("No se pudo recalcular el presupuesto.");
  }

  async function reloadFromServer() {
    setBusy(true);
    try {
      const [r, c] = await Promise.all([getCostingConfig(id), getCosts(id)]);
      applyConfigResponse(r);
      setReport(c);
      setBaseline({ direct: c.boq.direct_cost_total, total: c.integration.grand_total });
      setDirty(false);
      setConflict(null);
      setError(null);
    } finally {
      setBusy(false);
    }
  }

  async function doRecompute() {
    if (!config) return;
    sendActivity("saving_costing", "Recalculando costos");
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      const c = await recompute(
        id,
        { config, insumo_prices: prices, version },
        actorName,
        clientId,
      );
      const r = await getCostingConfig(id);
      applyConfigResponse(r);
      setReport(c);
      setDirty(false);
    } catch (err) {
      handleSaveError(err);
    } finally {
      setBusy(false);
    }
  }

  async function doReset() {
    sendActivity("resetting_costing", "Restableciendo parámetros");
    setBusy(true);
    setError(null);
    setConflict(null);
    try {
      const c = await recompute(
        id,
        {
          config: {
            currency: "MXN",
            assumptions: {},
            indirects: {},
            schedule: {},
            financial: {},
          },
          insumo_prices: {},
          version,
        },
        actorName,
        clientId,
      );
      const r = await getCostingConfig(id);
      applyConfigResponse(r);
      setReport(c);
      setBaseline({ direct: c.boq.direct_cost_total, total: c.integration.grand_total });
      setDirty(false);
    } catch (err) {
      handleSaveError(err);
    } finally {
      setBusy(false);
    }
  }

  const delta = useMemo(() => {
    if (!report || !baseline) return null;
    return {
      direct: report.boq.direct_cost_total - baseline.direct,
      total: report.integration.grand_total - baseline.total,
    };
  }, [report, baseline]);

  if (!config) {
    return (
      <div className="px-8 py-7">
        <Skeleton className="mb-6 h-14 w-96" />
        <div className="grid gap-4 lg:grid-cols-3">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  return (
    <div className="rise-in px-8 py-7 pb-28">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Parámetros e insumos</h1>
        <p className="text-sm text-[var(--muted)]">
          Ajusta supuestos, porcentajes y precios; el presupuesto se recalcula al instante
          (sin volver a detectar).
        </p>
      </div>

      {conflict && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <div className="flex min-w-0 items-center gap-2">
            <CircleAlert size={16} className="shrink-0" />
            <span className="truncate">{conflict}</span>
          </div>
          <button
            onClick={reloadFromServer}
            disabled={busy}
            className="shrink-0 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-amber-900 shadow-sm disabled:opacity-50"
          >
            Recargar
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <CircleAlert size={16} /> {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Group
          title="Supuestos geométricos"
          group="assumptions"
          config={config}
          onChange={setField}
        />
        <Group
          title="Indirectos y sobrecosto"
          group="indirects"
          config={config}
          onChange={setField}
        />
        <Group title="Financiero" group="financial" config={config} onChange={setField} />
      </div>

      <Card className="mt-4 overflow-hidden">
        <div className="border-b border-[var(--border)] px-5 py-4">
          <SectionTitle sub="Precios de referencia (MXN); edítalos con tus cotizaciones">
            Catálogo de insumos
          </SectionTitle>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--surface-2)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="px-5 py-2.5 font-semibold">Insumo</th>
              <th className="px-3 py-2.5 font-semibold">Tipo</th>
              <th className="px-3 py-2.5 font-semibold">Unidad</th>
              <th className="px-5 py-2.5 text-right font-semibold">Costo unitario</th>
            </tr>
          </thead>
          <tbody>
            {insumos.map((ins) => (
              <tr key={ins.code} className="border-t border-[var(--border)]">
                <td className="px-5 py-2.5">
                  <div>{ins.description}</div>
                  <div className="font-mono text-xs text-[var(--muted)]">{ins.code}</div>
                </td>
                <td className="px-3 py-2.5">
                  <Badge>{TYPE_LABELS[ins.resource_type] ?? ins.resource_type}</Badge>
                </td>
                <td className="px-3 py-2.5 text-[var(--muted)]">{ins.unit}</td>
                <td className="px-5 py-2.5 text-right">
                  <input
                    type="number"
                    step="any"
                    value={prices[ins.code] ?? ins.unit_cost}
                    onChange={(e) =>
                      setPrice(ins.code, ins.description, Number(e.target.value))
                    }
                    className="w-32 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-right tabular focus:border-[var(--primary)] focus:outline-none"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Sticky live summary */}
      <div className="fixed bottom-0 left-0 right-0 border-t border-[var(--border)] bg-[var(--surface)]/95 px-8 py-3 shadow-[0_-4px_16px_rgba(16,24,40,0.06)] backdrop-blur lg:left-64">
        <div className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-8 text-sm">
            <Summary
              label="Costo directo"
              value={report?.boq.direct_cost_total}
              delta={delta?.direct}
            />
            <Summary label="Precio de venta" value={report?.integration.sale_price} />
            <Summary
              label="Total c/ contingencia"
              value={report?.integration.grand_total}
              delta={delta?.total}
              accent
            />
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={doReset} disabled={busy || !!conflict}>
              <RotateCcw size={15} /> Restablecer
            </Button>
            <Button
              variant="primary"
              onClick={doRecompute}
              disabled={busy || !dirty || !!conflict}
              className="px-4"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Calculator size={15} />}
              {dirty ? "Recalcular" : "Actualizado"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Group({
  title,
  group,
  config,
  onChange,
}: {
  title: string;
  group: keyof CostingConfigFull;
  config: CostingConfigFull;
  onChange: (g: keyof CostingConfigFull, k: string, v: number) => void;
}) {
  const entries = Object.entries(config[group] as Record<string, number>);
  return (
    <Card className="p-5">
      <SectionTitle>{title}</SectionTitle>
      <div className="space-y-2.5">
        {entries.map(([key, value]) => (
          <label key={key} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-[var(--muted)]">{LABELS[key] ?? key}</span>
            <input
              type="number"
              step="any"
              value={value}
              onChange={(e) => onChange(group, key, Number(e.target.value))}
              className="w-28 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-right tabular focus:border-[var(--primary)] focus:outline-none"
            />
          </label>
        ))}
      </div>
    </Card>
  );
}

function Summary({
  label,
  value,
  delta,
  accent,
}: {
  label: string;
  value?: number;
  delta?: number;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className={`text-lg font-semibold tabular ${accent ? "text-[var(--primary)]" : ""}`}>
        {value != null ? money(value) : "—"}
        {delta != null && Math.abs(delta) > 0.5 && (
          <span
            className={`ml-2 text-xs font-medium ${
              delta > 0 ? "text-[var(--danger)]" : "text-[var(--success)]"
            }`}
          >
            {delta > 0 ? "▲" : "▼"} {money(Math.abs(delta))}
          </span>
        )}
      </div>
    </div>
  );
}
