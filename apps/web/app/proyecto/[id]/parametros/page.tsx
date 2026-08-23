"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowCounterClockwise, Calculator, CircleNotch } from "@phosphor-icons/react";
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
import {
  Badge,
  Button,
  Callout,
  Card,
  Input,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonHeader,
  Td,
  Th,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";
import { CONFIG_LABELS, ConfigGroup } from "@/components/CostingConfigForm";
import { actorLabel } from "@/lib/collab";

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
  const [catalogChanged, setCatalogChanged] = useState(false);
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
    if (latestEvent?.type !== "catalog_updated") return;
    const handle = window.setTimeout(() => setCatalogChanged(true), 0);
    return () => window.clearTimeout(handle);
  }, [latestEvent]);

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

  function setField(group: keyof CostingConfigFull, key: string, value: number | null) {
    setConfig((c) => (c ? { ...c, [group]: { ...(c[group] as object), [key]: value } } : c));
    setDirty(true);
    setConflict(null);
    announceEdit(CONFIG_LABELS[key] ?? key);
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

  if (!config && error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Parámetros e insumos" />
        <Callout tone="danger">{error}</Callout>
      </div>
    );
  }
  if (!config) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <div className="grid gap-4 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, card) => (
            <Card key={card} className="p-5">
              <Skeleton className="h-4 w-40" />
              <div className="mt-5 space-y-3">
                {Array.from({ length: 5 }, (_, row) => (
                  <div key={row} className="flex items-center justify-between gap-3">
                    <Skeleton className="h-3.5 w-32" />
                    <Skeleton className="h-7 w-24" />
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="rise-in px-6 py-7 pb-32 lg:px-8">
      <PageHeader
        title="Parámetros e insumos"
        sub="Ajusta supuestos, porcentajes y precios; el presupuesto se recalcula al instante (sin volver a detectar)."
      />

      {conflict && (
        <div className="mb-4">
          <Callout
            tone="warning"
            action={
              <Button size="sm" onClick={reloadFromServer} disabled={busy}>
                Recargar
              </Button>
            }
          >
            <span className="truncate">{conflict}</span>
          </Callout>
        </div>
      )}

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {catalogChanged && !conflict && (
        <div className="mb-4">
          <Callout
            tone="info"
            action={
              <Button
                size="sm"
                onClick={() => {
                  setCatalogChanged(false);
                  void doRecompute();
                }}
                disabled={busy}
              >
                Recalcular
              </Button>
            }
          >
            El catálogo del taller cambió; recalcula para aplicar los nuevos precios.
          </Callout>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <ConfigGroup
          title="Supuestos geométricos"
          group="assumptions"
          config={config}
          onChange={setField}
        />
        <ConfigGroup
          title="Indirectos y sobrecosto"
          group="indirects"
          config={config}
          onChange={setField}
        />
        <ConfigGroup title="Financiero" group="financial" config={config} onChange={setField} />
      </div>

      <Card className="mt-4 overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <SectionTitle sub="Precios de referencia (MXN); edítalos con tus cotizaciones">
            Catálogo de insumos
          </SectionTitle>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2">
                <Th className="px-5">Insumo</Th>
                <Th className="px-3">Tipo</Th>
                <Th className="px-3">Unidad</Th>
                <Th align="right" className="px-5">
                  Costo unitario
                </Th>
              </tr>
            </thead>
            <tbody>
              {insumos.map((ins) => (
                <tr key={ins.code} className="border-t border-border">
                  <Td className="px-5 py-2.5">
                    <div>{ins.description}</div>
                    <div className="font-mono text-xs text-muted">{ins.code}</div>
                  </Td>
                  <Td className="px-3 py-2.5">
                    <Badge>{TYPE_LABELS[ins.resource_type] ?? ins.resource_type}</Badge>
                  </Td>
                  <Td className="px-3 py-2.5 text-muted">{ins.unit}</Td>
                  <Td align="right" className="px-5 py-2.5">
                    <Input
                      type="number"
                      step="any"
                      value={prices[ins.code] ?? ins.unit_cost}
                      onChange={(e) =>
                        setPrice(ins.code, ins.description, Number(e.target.value))
                      }
                      className="w-32 px-2 py-1 text-right tabular"
                    />
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Sticky live summary */}
      <div className="fixed bottom-0 left-0 right-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur lg:left-64 lg:px-8">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-5 text-sm lg:gap-8">
            <Summary
              label="Costo directo"
              value={report?.boq.direct_cost_total}
              delta={delta?.direct}
            />
            <div className="hidden sm:block">
              <Summary label="Precio de venta" value={report?.integration.sale_price} />
            </div>
            <div className="hidden md:block">
              <Summary
                label="Total c/ contingencia"
                value={report?.integration.grand_total}
                delta={delta?.total}
                accent
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={doReset} disabled={busy || !!conflict}>
              <ArrowCounterClockwise size={15} weight="bold" /> Restablecer
            </Button>
            <Button
              variant="primary"
              onClick={doRecompute}
              disabled={busy || !dirty || !!conflict}
              className="px-4"
            >
              {busy ? (
                <CircleNotch size={15} className="animate-spin" />
              ) : (
                <Calculator size={15} weight="bold" />
              )}
              {dirty ? "Recalcular" : "Actualizado"}
            </Button>
          </div>
        </div>
      </div>
    </div>
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
      <div className="microlabel">{label}</div>
      <div className={`text-lg font-semibold tabular ${accent ? "text-accent" : ""}`}>
        {value != null ? money(value) : "—"}
        {delta != null && Math.abs(delta) > 0.5 && (
          <span
            className={`ml-2 text-xs font-medium ${
              delta > 0 ? "text-danger" : "text-success"
            }`}
          >
            {delta > 0 ? "▲" : "▼"} {money(Math.abs(delta))}
          </span>
        )}
      </div>
    </div>
  );
}
