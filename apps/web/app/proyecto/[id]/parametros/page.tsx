"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { RotateCcw, Calculator, Loader2 } from "lucide-react";
import {
  getCostingConfig,
  recompute,
  money,
  type CostingConfigFull,
  type CostReport,
  type Insumo,
} from "@/lib/api";
import { Card, SectionTitle, Spinner, Badge } from "@/components/ui";

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

export default function ParametrosPage() {
  const { id } = useParams<{ id: string }>();
  const [config, setConfig] = useState<CostingConfigFull | null>(null);
  const [insumos, setInsumos] = useState<Insumo[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [report, setReport] = useState<CostReport | null>(null);
  const [baseline, setBaseline] = useState<{ direct: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    getCostingConfig(id).then((r) => {
      setConfig(r.config);
      setInsumos(r.insumos);
    });
  }, [id]);

  // Establish a baseline (current saved report) to diff against.
  useEffect(() => {
    import("@/lib/api").then(({ getCosts }) =>
      getCosts(id)
        .then((c) => {
          setReport(c);
          setBaseline({
            direct: c.boq.direct_cost_total,
            total: c.integration.grand_total,
          });
        })
        .catch(() => {}),
    );
  }, [id]);

  function setField(group: keyof CostingConfigFull, key: string, value: number) {
    setConfig((c) => (c ? { ...c, [group]: { ...(c[group] as object), [key]: value } } : c));
    setDirty(true);
  }
  function setPrice(code: string, value: number) {
    setPrices((p) => ({ ...p, [code]: value }));
    setDirty(true);
  }

  async function doRecompute() {
    if (!config) return;
    setBusy(true);
    try {
      const c = await recompute(id, { config, insumo_prices: prices });
      setReport(c);
      setDirty(false);
    } finally {
      setBusy(false);
    }
  }

  async function doReset() {
    setBusy(true);
    try {
      const c = await recompute(id, {
        config: { currency: "MXN", assumptions: {}, indirects: {}, schedule: {}, financial: {} },
        insumo_prices: {},
      });
      const r = await getCostingConfig(id);
      setConfig(r.config);
      setInsumos(r.insumos);
      setPrices({});
      setReport(c);
      setBaseline({ direct: c.boq.direct_cost_total, total: c.integration.grand_total });
      setDirty(false);
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
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-[var(--muted)]">
        <Spinner className="h-5 w-5" /> Cargando parámetros…
      </div>
    );
  }

  return (
    <div className="px-8 py-7 pb-28">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Parámetros e insumos</h1>
        <p className="text-sm text-[var(--muted)]">
          Ajusta supuestos, porcentajes y precios; el presupuesto se recalcula al instante
          (sin volver a detectar).
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Group title="Supuestos geométricos" group="assumptions" config={config} onChange={setField} />
        <Group title="Indirectos y sobrecosto" group="indirects" config={config} onChange={setField} />
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
                    defaultValue={ins.unit_cost}
                    onChange={(e) => setPrice(ins.code, Number(e.target.value))}
                    className="w-32 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-right tabular focus:border-[var(--primary)] focus:outline-none"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Sticky live summary */}
      <div className="fixed bottom-0 left-64 right-0 border-t border-[var(--border)] bg-[var(--surface)]/95 px-8 py-3 backdrop-blur">
        <div className="flex items-center justify-between gap-6">
          <div className="flex items-center gap-8 text-sm">
            <Summary label="Costo directo" value={report?.boq.direct_cost_total} delta={delta?.direct} />
            <Summary label="Precio de venta" value={report?.integration.sale_price} />
            <Summary
              label="Total c/ contingencia"
              value={report?.integration.grand_total}
              delta={delta?.total}
              accent
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={doReset}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm font-medium hover:bg-[var(--surface-2)] disabled:opacity-50"
            >
              <RotateCcw size={15} /> Restablecer
            </button>
            <button
              onClick={doRecompute}
              disabled={busy || !dirty}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Calculator size={15} />}
              {dirty ? "Recalcular" : "Actualizado"}
            </button>
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
              defaultValue={value}
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
