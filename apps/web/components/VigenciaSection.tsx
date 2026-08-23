"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, DownloadSimple } from "@phosphor-icons/react";
import {
  cotizacionUrl,
  getIndices,
  getVigencia,
  putIndices,
  rollForwardPrices,
  type PriceIndices,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { Badge, Button, Card, Input, SectionTitle } from "@/components/ui";

const FRESH = 6;
const STALE = 12;

function monthsOld(vigencia: string): number | null {
  const m = /^(\d{4})-(\d{2})/.exec(vigencia ?? "");
  if (!m) return null;
  const now = new Date();
  return (now.getFullYear() - Number(m[1])) * 12 + (now.getMonth() + 1 - Number(m[2]));
}

/** Age of a price as a chip: vigente / revisar / vencido. */
export function VigenciaChip({ vigencia }: { vigencia: string }) {
  const months = monthsOld(vigencia);
  const status = months === null || months > STALE ? "vencido" : months > FRESH ? "revisar" : "vigente";
  const tone = status === "vigente" ? "success" : status === "revisar" ? "warning" : "danger";
  return (
    <Badge tone={tone} dot>
      {months === null ? "sin vigencia" : `${months} mes${months === 1 ? "" : "es"}`}
    </Badge>
  );
}

/**
 * Prices that do not rot: how many are stale, the cotización request for
 * them, and the taller's index table to roll old prices forward.
 */
export function VigenciaSection({
  onChanged,
  onError,
  onNotice,
}: {
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [indices, setIndices] = useState<PriceIndices | null>(null);
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    getVigencia()
      .then((v) => setCounts(v.counts))
      .catch(() => {});
    getIndices()
      .then((i) => setIndices(i))
      .catch(() => {});
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function saveIndices() {
    const values: Record<string, number> = {};
    for (const line of text.split(/\n|;/)) {
      const m = /^\s*(\d{4}-\d{2})\s*[\s,:=\t]\s*([\d.,]+)\s*$/.exec(line);
      if (m) values[m[1]] = Number(m[2].replace(",", "."));
    }
    if (Object.keys(values).length === 0) {
      onError("Pega renglones como «2026-06 137.8» (mes y valor del índice).");
      return;
    }
    setBusy(true);
    try {
      const saved = await putIndices(
        { source: source.trim() || indices?.source || "", values: { ...(indices?.values ?? {}), ...values } },
        getBrowserActor(),
      );
      setIndices(saved);
      setText("");
      onNotice(`Índices guardados: ${Object.keys(saved.values).length} meses (${saved.source || "sin fuente"})`);
    } catch {
      onError("No se pudieron guardar los índices.");
    } finally {
      setBusy(false);
    }
  }

  async function roll(status: "vencido" | "revisar") {
    setBusy(true);
    try {
      const result = await rollForwardPrices({ status }, getBrowserActor());
      const skipped = result.skipped.length ? ` · ${result.skipped.length} sin índice aplicable` : "";
      onNotice(
        `${result.updated.length} precios actualizados por índice a ${result.to_month} (marcados como calculado)${skipped}`,
      );
      reload();
      onChanged();
    } catch {
      onError("No se pudieron actualizar los precios por índice; captura primero la tabla.");
    } finally {
      setBusy(false);
    }
  }

  const vencidos = counts?.vencido ?? 0;
  const revisar = counts?.revisar ?? 0;
  const monthCount = Object.keys(indices?.values ?? {}).length;
  return (
    <Card className="p-5">
      <SectionTitle sub="Cada precio dice cuántos meses tiene. Pide cotización de los vencidos, importa la respuesta, o tráelos a hoy por el índice que tu taller mantiene (queda marcado como calculado, nunca como cotización).">
        Vigencia de precios
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-2">
        {counts && (
          <span className="mr-2 flex items-center gap-1.5 text-sm">
            <Badge tone="success" dot>{counts.vigente} vigentes</Badge>
            <Badge tone="warning" dot>{revisar} por revisar</Badge>
            <Badge tone="danger" dot>{vencidos} vencidos</Badge>
          </span>
        )}
        <a href={cotizacionUrl("vencido")} className="inline-flex">
          <Button size="sm" disabled={vencidos === 0}>
            <DownloadSimple size={14} weight="bold" /> Solicitar cotización ({vencidos})
          </Button>
        </a>
        <a href={cotizacionUrl("all")} className="inline-flex">
          <Button size="sm">
            <DownloadSimple size={14} weight="bold" /> Solicitud completa
          </Button>
        </a>
        <Button size="sm" onClick={() => roll("vencido")} disabled={busy || vencidos === 0 || monthCount === 0}>
          <ArrowClockwise size={14} weight="bold" /> Actualizar vencidos por índice
        </Button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-xs font-medium text-muted hover:text-foreground"
        >
          {open ? "Ocultar índices" : `Índices (${monthCount} meses${indices?.source ? ` · ${indices.source}` : ""})`}
        </button>
      </div>
      {open && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div>
            <Input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder={indices?.source || "Fuente (p. ej. INEGI INPP construcción, base jul-2019)"}
              className="mb-2 w-full px-2 py-1.5"
              aria-label="Fuente del índice"
            />
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={"Un mes por renglón: AAAA-MM valor\n2025-06 130.0\n2026-06 137.8"}
              rows={5}
              className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 font-mono text-xs"
              aria-label="Valores del índice"
            />
            <Button size="sm" variant="primary" onClick={saveIndices} disabled={busy} className="mt-2">
              Guardar índices
            </Button>
          </div>
          <div className="text-xs text-muted">
            {monthCount === 0 ? (
              <p>
                Sin índices todavía. Klave no precarga cifras oficiales: pega los valores publicados
                (INEGI INPP construcción u otro) con su fuente; el factor aplicado queda escrito en cada
                precio actualizado.
              </p>
            ) : (
              <ul className="grid grid-cols-2 gap-x-4 font-mono">
                {Object.entries(indices?.values ?? {})
                  .slice(-12)
                  .map(([month, value]) => (
                    <li key={month}>
                      {month} {value}
                    </li>
                  ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
