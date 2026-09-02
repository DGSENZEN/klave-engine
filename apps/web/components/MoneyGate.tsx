"use client";

import { useState } from "react";
import Link from "next/link";
import { Ruler, Warning } from "@phosphor-icons/react";
import {
  setVerification,
  type CostReport,
  type MoneyGateState,
} from "@/lib/api";
import { Button, Callout, Card, Select } from "@/components/ui";

// Re-exported so the existing `import { MoneyGateState } from
// "@/components/MoneyGate"` call sites keep working: the type itself now
// lives in lib/api.ts, because lib/ must not import from components/.
export type { MoneyGateState };

/**
 * The verdict is resolved on the server by costing.presentation, because the
 * rule used to live here, in the exports, and in the project list at three
 * different levels of rigor — and the newest surface always got the weakest
 * one. The client renders the answer; it no longer derives it.
 */
export function moneyState(costs: CostReport | null): MoneyGateState {
  return costs?.money_state ?? "ok";
}

/** Money is shown, but nobody has signed off the reading yet: say so on
 * every money page, with the way to clear it. */
export function UnverifiedBanner({
  id,
  costs,
}: {
  id: string;
  costs: CostReport | null;
}) {
  if (moneyState(costs) !== "unverified") return null;
  const units = costs?.drawing_units;
  return (
    <div className="mb-4">
      <Callout
        tone="warning"
        action={
          <Link href={`/proyecto/${id}/resumen`} className="inline-flex">
            <Button size="sm">Ruta de verificación</Button>
          </Link>
        }
      >
        <span className="font-medium">Sin verificar.</span> Importes calculados con unidades
        leídas del archivo ({units?.unit} · {Math.round((units?.confidence ?? 0) * 100)} %)
        que nadie ha confirmado; el Excel sale marcado SIN VERIFICAR hasta que se confirmen
        unidades y detecciones.
      </Callout>
    </div>
  );
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
        <Select
          value={unit}
          onChange={(e) => setUnit(e.target.value as typeof unit)}
          disabled={busy || done !== null}
        >
          {UNITS.map((u) => (
            <option key={u.value} value={u.value}>
              {u.label}
            </option>
          ))}
        </Select>
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
