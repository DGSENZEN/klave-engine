"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArrowCounterClockwise,
  ArrowsLeftRight,
  BookmarkSimple,
  Trash,
} from "@phosphor-icons/react";
import {
  deleteVersion,
  getVersionDiff,
  getVersions,
  money2,
  num,
  restoreVersion,
  saveVersion,
  type VersionDiff,
  type VersionSummary,
} from "@/lib/api";
import { Badge, Button, Input, Skeleton, Td, Th } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";
import { ConfirmDialog } from "@/components/ConfirmDialog";

/**
 * Versions of the presupuesto: save the current state under a name, compare
 * a version against what is on screen, restore its human decisions. The
 * list reloads on version events from any client and on reconnect.
 */
export function VersionsPanel({ projectId }: { projectId: string }) {
  const { latestEvent, connectionEpoch, actorName, clientId } = useProjectLive();
  const [versions, setVersions] = useState<VersionSummary[] | null>(null);
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparing, setComparing] = useState<string | null>(null);
  // The diff remembers which costing state it was computed against: a
  // costing change after a comparison makes it stale, shown as such.
  const [diffState, setDiffState] = useState<{ diff: VersionDiff; stamp: number | null } | null>(
    null,
  );
  const costingStamp =
    latestEvent && (latestEvent.type === "costing_updated" || latestEvent.type === "run_published")
      ? latestEvent.seq
      : null;
  const diff = diffState?.diff ?? null;
  const diffStale = diffState !== null && diffState.stamp !== costingStamp;
  const [showSame, setShowSame] = useState(false);
  const [confirmRestore, setConfirmRestore] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<VersionSummary | null>(null);

  const reload = useCallback(() => {
    getVersions(projectId)
      .then((r) => {
        setVersions(r.versions);
        setActiveRun(r.active_run_id);
      })
      .catch(() => setVersions([]));
  }, [projectId]);

  useEffect(() => {
    reload();
  }, [reload, connectionEpoch]);

  useEffect(() => {
    if ((latestEvent?.type ?? "").startsWith("version_")) reload();
  }, [latestEvent, reload]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await saveVersion(projectId, { label: label.trim(), note: note.trim() }, actorName, clientId);
      setLabel("");
      setNote("");
      reload();
    } catch {
      setError("No se pudo guardar la versión.");
    } finally {
      setBusy(false);
    }
  }

  async function compare(versionId: string) {
    if (comparing === versionId) {
      setComparing(null);
      setDiffState(null);
      return;
    }
    setComparing(versionId);
    setDiffState(null);
    try {
      const fresh = await getVersionDiff(projectId, versionId);
      setDiffState({ diff: fresh, stamp: costingStamp });
    } catch {
      setError("No se pudo comparar.");
      setComparing(null);
    }
  }

  async function restore(versionId: string) {
    setBusy(true);
    setError(null);
    try {
      await restoreVersion(projectId, versionId, actorName, clientId);
      setConfirmRestore(null);
      setDiffState(null);
      setComparing(null);
      reload();
    } catch {
      setError("No se pudo restaurar la versión.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(versionId: string) {
    try {
      await deleteVersion(projectId, versionId, actorName);
      if (comparing === versionId) {
        setComparing(null);
        setDiffState(null);
      }
      reload();
    } catch {
      setError("No se pudo eliminar la versión.");
    }
  }

  const list = versions ?? [];
  return (
    <div>
      <ConfirmDialog
        open={confirmDelete !== null}
        title={confirmDelete ? `Eliminar la versión v${confirmDelete.number}` : ""}
        description={
          confirmDelete
            ? `«${confirmDelete.label}» (${money2(confirmDelete.grand_total)}) se borra del historial; el presupuesto actual no cambia.`
            : null
        }
        confirmLabel="Eliminar versión"
        onConfirm={() => {
          if (confirmDelete) void remove(confirmDelete.version_id);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Nombre (p. ej. Entrega al cliente)"
          maxLength={80}
          className="w-64 px-2 py-1.5"
          aria-label="Nombre de la versión"
        />
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Nota (qué cambió, para quién)"
          maxLength={500}
          className="min-w-52 flex-1 px-2 py-1.5"
          aria-label="Nota de la versión"
        />
        <Button size="sm" variant="primary" onClick={save} disabled={busy}>
          <BookmarkSimple size={14} weight="bold" /> Guardar versión
        </Button>
      </div>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}

      {versions === null ? (
        <div className="mt-4 space-y-2" aria-busy="true">
          <Skeleton className="h-9" />
          <Skeleton className="h-9 w-3/4" />
        </div>
      ) : list.length === 0 ? (
        <p className="mt-3 text-xs text-faint">
          Aún no hay versiones. Guarda una antes de entregar o antes de un cambio grande: podrás
          comparar línea por línea y volver a ella.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-border">
          {[...list].reverse().map((v) => {
            const open = comparing === v.version_id;
            const stale = activeRun && v.run_id && v.run_id !== activeRun;
            return (
              <li key={v.version_id} className="py-3">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-mono text-xs text-muted">v{v.number}</span>
                  <span className="font-medium">{v.label}</span>
                  <span className="tabular text-sm">{money2(v.grand_total)}</span>
                  <span className="text-xs text-faint">
                    {v.line_count} conceptos
                    {v.adjustments > 0 && ` · ${v.adjustments} ajuste${v.adjustments === 1 ? "" : "s"}`}
                    {v.excluded > 0 && ` · ${v.excluded} excluido${v.excluded === 1 ? "" : "s"}`}
                  </span>
                  {v.actor === "Klave" && (
                    <Badge tone="default" title="Guardada sola al reprocesar: compárala para ver qué cambió entre corridas">
                      automática
                    </Badge>
                  )}
                  {stale && (
                    <Badge tone="warning" dot>
                      otra corrida
                    </Badge>
                  )}
                  <span className="ml-auto text-xs text-faint">
                    {v.actor && `${v.actor} · `}
                    {new Date(v.created_at).toLocaleString("es-MX", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </span>
                  <div className="flex items-center gap-1">
                    <Button size="sm" onClick={() => compare(v.version_id)} disabled={busy}>
                      <ArrowsLeftRight size={13} weight="bold" />
                      {open ? "Cerrar" : "Comparar"}
                    </Button>
                    {confirmRestore === v.version_id ? (
                      <>
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => restore(v.version_id)}
                          disabled={busy}
                        >
                          Sí, restaurar
                        </Button>
                        <Button size="sm" onClick={() => setConfirmRestore(null)} disabled={busy}>
                          No
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => setConfirmRestore(v.version_id)}
                        disabled={busy}
                        title="Reaplica las decisiones de esta versión sobre la lectura actual; el estado de ahora se guarda antes."
                      >
                        <ArrowCounterClockwise size={13} weight="bold" /> Restaurar
                      </Button>
                    )}
                    <button
                      type="button"
                      aria-label={`Eliminar versión ${v.number}`}
                      onClick={() => setConfirmDelete(v)}
                      className="rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash size={14} />
                    </button>
                  </div>
                </div>
                {v.note && <p className="mt-1 text-xs text-muted">{v.note}</p>}
                {open && (
                  <div className="mt-3">
                    {diff ? (
                      <>
                        {diffStale && (
                          <p className="mb-2 text-xs text-warning">
                            El presupuesto cambió después de comparar.{" "}
                            <button
                              type="button"
                              className="underline"
                              onClick={() => {
                                setComparing(null);
                                setDiffState(null);
                                void compare(v.version_id);
                              }}
                            >
                              Comparar de nuevo
                            </button>
                          </p>
                        )}
                        <DiffTable diff={diff} showSame={showSame} onToggleSame={setShowSame} />
                      </>
                    ) : (
                      <div className="space-y-2" aria-busy="true">
                        <Skeleton className="h-8" />
                        <Skeleton className="h-24" />
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function DiffTable({
  diff,
  showSame,
  onToggleSame,
}: {
  diff: VersionDiff;
  showSame: boolean;
  onToggleSame: (v: boolean) => void;
}) {
  const rows = diff.lines.filter((l) => showSame || l.status !== "same");
  const same = diff.lines.length - rows.length;
  const delta = diff.grand_total_after - diff.grand_total_before;
  return (
    <div className="rounded-lg border border-border bg-surface">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border px-3 py-2 text-xs">
        <span className="text-muted">
          {diff.before_label} → {diff.after_label}
        </span>
        <span className="tabular">
          {money2(diff.grand_total_before)} → {money2(diff.grand_total_after)}
        </span>
        <span className={`tabular font-medium ${delta > 0 ? "text-danger" : delta < 0 ? "text-success" : "text-muted"}`}>
          {delta >= 0 ? "+" : ""}
          {money2(delta)}
        </span>
        <span className="text-faint">
          {diff.changed} cambiado{diff.changed === 1 ? "" : "s"} · {diff.added} nuevo
          {diff.added === 1 ? "" : "s"} · {diff.removed} retirado{diff.removed === 1 ? "" : "s"}
        </span>
        {same > 0 && !showSame && (
          <button
            type="button"
            className="ml-auto text-faint underline"
            onClick={() => onToggleSame(true)}
          >
            mostrar {same} sin cambio
          </button>
        )}
        {showSame && (
          <button
            type="button"
            className="ml-auto text-faint underline"
            onClick={() => onToggleSame(false)}
          >
            ocultar sin cambio
          </button>
        )}
      </div>
      {diff.notes.map((n, i) => (
        <p key={i} className="border-b border-border px-3 py-1.5 text-xs text-warning">
          {n}
        </p>
      ))}
      {rows.length === 0 ? (
        <p className="px-3 py-2 text-xs text-muted">Sin movimiento entre las dos.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <Th>Concepto</Th>
                <Th align="right">Cantidad</Th>
                <Th align="right">Importe</Th>
                <Th align="right">Δ importe</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((l) => {
                const d = l.amount_after - l.amount_before;
                return (
                  <tr key={l.concept_code} className="border-b border-border last:border-0">
                    <Td>
                      <span className="font-mono text-xs text-muted">{l.concept_code}</span>{" "}
                      {l.description}{" "}
                      {l.status === "added" && <Badge tone="accent">nuevo</Badge>}
                      {l.status === "removed" && <Badge tone="danger">retirado</Badge>}
                    </Td>
                    <Td align="right" className="tabular">
                      {l.quantity_before == null ? "—" : num(l.quantity_before)}
                      {" → "}
                      {l.quantity_after == null ? "—" : num(l.quantity_after)}{" "}
                      <span className="text-xs text-muted">{l.unit}</span>
                    </Td>
                    <Td align="right" className="tabular text-muted">
                      {money2(l.amount_before)} → {money2(l.amount_after)}
                    </Td>
                    <Td
                      align="right"
                      className={`tabular font-medium ${d > 0 ? "text-danger" : d < 0 ? "text-success" : "text-muted"}`}
                    >
                      {d >= 0 ? "+" : ""}
                      {money2(d)}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
