"use client";

import { useState } from "react";
import { Ruler, Warning } from "@phosphor-icons/react";
import { setVerification, type CostReport, type ProjectReviews } from "@/lib/api";
import { Button, Callout, Card } from "@/components/ui";

export type MoneyGateState = "ok" | "unverified" | "blocked";

/**
 * The one rule every money surface obeys: no MXN until the unit everything
 * multiplies by is either detected with confidence or confirmed by a person.
 * "unverified" shows money with the SIN VERIFICAR banner; "blocked" shows
 * the gate instead of amounts.
 */
export function moneyGate(
  costs: CostReport | null,
  reviews: ProjectReviews | null,
): MoneyGateState {
  if (!costs) return "ok";
  const units = costs.drawing_units;
  const confirmed = Boolean(reviews?.verification.units_confirmed_at);
  if (confirmed) return "ok";
  const trustworthy = units.unit !== "drawing_units" && units.confidence >= 0.7;
  return trustworthy ? "unverified" : "blocked";
}

const UNITS: { value: "m" | "cm" | "mm" | "ft" | "in"; label: string }[] = [
  { value: "m", label: "metros (m)" },
  { value: "cm", label: "centímetros (cm)" },
  { value: "mm", label: "milímetros (mm)" },
  { value: "ft", label: "pies (ft)" },
  { value: "in", label: "pulgadas (in)" },
];

export function UnitsGate({
  id,
  costs,
  actorName,
  onConfirmed,
}: {
  id: string;
  costs: CostReport;
  actorName: string;
  onConfirmed?: (reprocessing: boolean) => void;
}) {
  const detected = costs.drawing_units;
  const [unit, setUnit] = useState<"m" | "cm" | "mm" | "ft" | "in">(
    (UNITS.find((u) => u.value === detected.unit)?.value ?? "m"),
  );
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      const result = await setVerification(id, "units", true, actorName, unit);
      const reprocessing = Boolean(result.reprocessing);
      setDone(
        reprocessing
          ? `Unidades confirmadas en ${unit}. Releyendo el plano con esa escala…`
          : `Unidades confirmadas en ${unit}.`,
      );
      onConfirmed?.(reprocessing);
    } catch {
      setError("No se pudieron confirmar las unidades.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="rise-in mx-auto max-w-xl p-6">
      <div className="mb-3 flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-warning-soft text-warning">
          <Ruler size={20} weight="duotone" />
        </span>
        <div>
          <h2 className="text-[0.95rem] font-semibold">Primero, las unidades</h2>
          <p className="text-sm text-muted">
            Todo el dinero se multiplica por esta escala. El plano no la declara con
            certeza, así que no mostramos importes hasta que la confirmes.
          </p>
        </div>
      </div>
      <Callout tone="warning">
        Lectura actual: <span className="font-medium">{detected.unit}</span> ·{" "}
        {Math.round(detected.confidence * 100)} % de confianza ({detected.source}).
        {detected.notes?.[0] ? ` ${detected.notes[0]}` : ""}
      </Callout>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value as typeof unit)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
          disabled={busy || done !== null}
        >
          {UNITS.map((u) => (
            <option key={u.value} value={u.value}>
              {u.label}
            </option>
          ))}
        </select>
        <Button variant="primary" onClick={confirm} disabled={busy || done !== null}>
          {busy ? "Confirmando…" : "Confirmar unidades y calcular"}
        </Button>
      </div>
      <p className="mt-3 flex items-start gap-1.5 text-xs text-muted">
        <Warning size={13} className="mt-0.5 shrink-0" />
        Mide una cota conocida en el visor si dudas: una puerta de 0.90 debe medir 0.90 en
        metros, 90 en centímetros.
      </p>
      {done && <p className="mt-3 text-sm text-success">{done}</p>}
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
    </Card>
  );
}
