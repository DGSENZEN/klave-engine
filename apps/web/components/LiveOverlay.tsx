"use client";

import { useState } from "react";
import { History, X, Check } from "lucide-react";
import { useProjectLive } from "@/components/ProjectLive";

/** Top-right live layer: a hideable change timeline stacked above transient
 * toasts, so a burst of edits accumulates in the panel instead of piling up
 * as a tall wall of toasts. */
export function LiveOverlay() {
  const { toasts, dismissToast, timeline, clearTimeline } = useProjectLive();
  const [open, setOpen] = useState(false);
  const [seenId, setSeenId] = useState(0);
  const topId = timeline[0]?.id ?? 0;
  const unseen = open ? 0 : timeline.filter((entry) => entry.id > seenId).length;

  // Everything currently in the panel is "seen" once it's closed again.
  const close = () => {
    setSeenId(topId);
    setOpen(false);
  };

  return (
    <div className="pointer-events-none fixed right-5 top-5 z-50 flex w-80 flex-col items-end gap-2">
      <div className="pointer-events-auto w-full">
        {open ? (
          <div className="toast-in overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
            <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <History size={15} className="text-[var(--primary)]" />
                Cambios
                {timeline.length > 0 && (
                  <span className="tabular text-xs font-normal text-[var(--muted)]">
                    {timeline.length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {timeline.length > 0 && (
                  <button
                    onClick={clearTimeline}
                    className="rounded p-1 text-xs text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    title="Limpiar historial"
                  >
                    <Check size={14} />
                  </button>
                )}
                <button
                  onClick={close}
                  aria-label="Ocultar cambios"
                  className="rounded p-1 text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                >
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="max-h-[50vh] overflow-y-auto">
              {timeline.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-[var(--muted)]">
                  Aún no hay cambios en esta sesión.
                </p>
              ) : (
                <ul className="divide-y divide-[var(--border)]">
                  {timeline.map((entry) => (
                    <li key={entry.id} className="flex gap-2.5 px-3 py-2.5">
                      <span
                        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-semibold text-white ${
                          entry.isOwn ? "bg-[var(--primary)]" : "bg-[var(--accent)]"
                        }`}
                      >
                        {initials(entry.actor)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm leading-tight">{entry.title}</div>
                        {entry.detail && (
                          <div className="mt-0.5 truncate text-xs tabular text-[var(--muted)]">
                            {entry.detail}
                          </div>
                        )}
                        <div className="mt-0.5 text-[11px] text-[var(--muted)]">
                          {timeAgo(entry.ts)}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ) : (
          <div className="flex justify-end">
            <button
              onClick={() => setOpen(true)}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-[var(--surface-2)]"
            >
              <History size={14} className="text-[var(--muted)]" />
              Cambios
              {unseen > 0 && (
                <span className="tabular flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--primary)] px-1 text-[10px] font-semibold text-white">
                  {unseen}
                </span>
              )}
            </button>
          </div>
        )}
      </div>

      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="toast-in pointer-events-auto flex w-full items-start gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm shadow-[var(--shadow-lg)]"
        >
          <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[var(--primary)]" />
          <div className="min-w-0 flex-1">{toast.message}</div>
          <button
            onClick={() => dismissToast(toast.id)}
            aria-label="Cerrar aviso"
            className="rounded p-0.5 text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function timeAgo(ts: string): string {
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return "";
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 10) return "ahora";
  if (secs < 60) return `hace ${secs} s`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.round(mins / 60);
  return `hace ${hours} h`;
}
