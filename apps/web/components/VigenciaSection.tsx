"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowClockwise, DownloadSimple } from "@phosphor-icons/react";
import {
  apiMessage,
  cotizacionPath,
  downloadFile,
  getIndices,
  getVigencia,
  money2,
  putIndices,
  rollForwardPrices,
  type PriceIndices,
  type RollForwardResult,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { Badge, Button, Callout, Card, Input, SectionTitle, Skeleton, Td, Th } from "@/components/ui";
import { Modal } from "@/components/Modal";

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
  const [preview, setPreview] = useState<RollForwardResult | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [downloading, setDownloading] = useState<"vencido" | "all" | null>(null);

  const reload = useCallback(() => {
    Promise.all([getVigencia(), getIndices()])
      .then(([v, i]) => {
        setCounts(v.counts);
        setIndices(i);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
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

  async function downloadCotizacion(scope: "vencido" | "all") {
    setDownloading(scope);
    try {
      await downloadFile(cotizacionPath(scope), `solicitud_cotizacion_${scope}.xlsx`);
    } catch (e) {
      onError(apiMessage(e, "No se pudo generar la solicitud de cotización."));
    } finally {
      setDownloading(null);
    }
  }

  async function previewRoll(status: "vencido" | "revisar") {
    setBusy(true);
    try {
      setPreview(await rollForwardPrices({ status, dry_run: true }, getBrowserActor()));
    } catch {
      onError("No se pudo calcular la actualización por índice; captura primero la tabla.");
    } finally {
      setBusy(false);
    }
  }

  async function applyRoll() {
    if (!preview) return;
    setBusy(true);
    try {
      // Apply exactly the codes the preview showed, never a fresh selection.
      const result = await rollForwardPrices(
        { codes: preview.updated.map((u) => u.code), to_month: preview.to_month },
        getBrowserActor(),
      );
      const skipped = result.skipped.length ? ` · ${result.skipped.length} sin índice aplicable` : "";
      onNotice(
        `${result.updated.length === 1 ? "1 precio actualizado" : `${result.updated.length} precios actualizados`} por índice a ${result.to_month} (marcado como calculado)${skipped}`,
      );
      setPreview(null);
      reload();
      onChanged();
    } catch {
      onError("No se pudieron actualizar los precios por índice.");
    } finally {
      setBusy(false);
    }
  }

  const vencidos = counts?.vencido ?? 0;
  const revisar = counts?.revisar ?? 0;
  const monthCount = Object.keys(indices?.values ?? {}).length;
  return (
    <Card className="p-5">
      <Modal
        open={preview !== null}
        title="Actualizar precios vencidos por índice"
        sub={
          preview
            ? `${preview.updated.length === 1 ? "1 precio pasa" : `${preview.updated.length} precios pasan`} a ${preview.to_month} con el índice ${indices?.source || "del taller"}; queda marcado como calculado, no como cotización.`
            : undefined
        }
        onClose={() => setPreview(null)}
        busy={busy}
        size="lg"
        footer={
          <>
            <Button onClick={() => setPreview(null)} disabled={busy}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={applyRoll}
              disabled={busy || !preview || preview.updated.length === 0}
            >
              {busy
                ? "Aplicando…"
                : preview?.updated.length === 1
                  ? "Aplicar a 1 precio"
                  : `Aplicar a ${preview?.updated.length ?? 0} precios`}
            </Button>
          </>
        }
      >
        {preview && preview.updated.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2">
                  <Th>Insumo</Th>
                  <Th>Desde</Th>
                  <Th align="right">Actual</Th>
                  <Th align="right">Factor</Th>
                  <Th align="right">Nuevo</Th>
                </tr>
              </thead>
              <tbody>
                {preview.updated.map((u) => (
                  <tr key={u.code} className="border-t border-border">
                    <Td>
                      <div>{u.description || u.code}</div>
                      <div className="font-mono text-xs text-muted">{u.code}</div>
                    </Td>
                    <Td className="whitespace-nowrap text-xs text-muted">{u.vigencia_from}</Td>
                    <Td align="right" className="tabular">{money2(u.from)}</Td>
                    <Td align="right" className="tabular text-muted">×{u.factor.toFixed(4)}</Td>
                    <Td align="right" className="tabular font-medium">{money2(u.to)}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {preview && preview.updated.length === 0 && (
          <p className="text-muted">Ningún precio vencido tiene un índice aplicable para su mes.</p>
        )}
        {preview && preview.skipped.length > 0 && (
          <div className="mt-3 text-xs text-muted">
            <div className="mb-1 font-medium">Sin cambio ({preview.skipped.length})</div>
            <ul className="space-y-0.5 font-mono">
              {preview.skipped.slice(0, 20).map((line) => (
                <li key={line}>{line}</li>
              ))}
              {preview.skipped.length > 20 && <li>… y {preview.skipped.length - 20} más</li>}
            </ul>
          </div>
        )}
      </Modal>
      <SectionTitle sub="Cada precio dice cuántos meses tiene. Pide cotización de los vencidos, importa la respuesta, o tráelos a hoy por el índice que tu taller mantiene (queda marcado como calculado, nunca como cotización).">
        Vigencia de precios
      </SectionTitle>
      {loadError && (
        <div className="mb-3">
          <Callout
            tone="danger"
            action={
              <Button size="sm" onClick={reload}>
                Reintentar
              </Button>
            }
          >
            No se pudo leer la vigencia de los precios.
          </Callout>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {counts === null && !loadError && <Skeleton className="mr-2 h-6 w-64" />}
        {counts && (
          <span className="mr-2 flex items-center gap-1.5 text-sm">
            <Badge tone="success" dot>{counts.vigente} vigentes</Badge>
            <Badge tone="warning" dot>{revisar} por revisar</Badge>
            <Badge tone="danger" dot>{vencidos} vencidos</Badge>
          </span>
        )}
        <Button
          size="sm"
          disabled={vencidos === 0 || downloading !== null}
          onClick={() => downloadCotizacion("vencido")}
        >
          <DownloadSimple size={14} weight="bold" />
          {downloading === "vencido" ? "Generando…" : `Solicitud de cotización: vencidos (${vencidos})`}
        </Button>
        <Button size="sm" disabled={downloading !== null} onClick={() => downloadCotizacion("all")}>
          <DownloadSimple size={14} weight="bold" />
          {downloading === "all" ? "Generando…" : "Solicitud de cotización: todo el catálogo"}
        </Button>
        <Button
          size="sm"
          onClick={() => previewRoll("vencido")}
          disabled={busy || vencidos === 0 || monthCount === 0}
        >
          <ArrowClockwise size={14} weight="bold" /> Actualizar vencidos por índice…
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
