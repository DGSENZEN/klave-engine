"use client";

import { useState } from "react";
import { ClockCounterClockwise, X, Check } from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { Avatar, IconButton } from "@/components/ui";

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
    <div className="pointer-events-none fixed right-4 top-[68px] z-50 flex w-[calc(100vw-2rem)] max-w-80 flex-col items-end gap-2 lg:right-5 lg:top-5">
      <div className="pointer-events-auto w-full">
        {open ? (
          <div className="toast-in overflow-hidden rounded-xl border border-border bg-surface shadow-lg">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <ClockCounterClockwise size={15} weight="bold" className="text-accent" />
                Cambios
                {timeline.length > 0 && (
                  <span className="tabular text-xs font-normal text-muted">
                    {timeline.length}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {timeline.length > 0 && (
                  <IconButton aria-label="Limpiar historial" title="Limpiar historial" onClick={clearTimeline}>
                    <Check size={14} />
                  </IconButton>
                )}
                <IconButton aria-label="Ocultar cambios" onClick={close}>
                  <X size={14} />
                </IconButton>
              </div>
            </div>
            <div className="max-h-[50vh] overflow-y-auto">
              {timeline.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-muted">
                  Aún no hay cambios en esta sesión.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {timeline.map((entry) => (
                    <li key={entry.id} className="flex gap-2.5 px-3 py-2.5">
                      <Avatar name={entry.actor} self={entry.isOwn} size="sm" />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm leading-tight">{entry.title}</div>
                        {entry.detail && (
                          <div className="mt-0.5 truncate text-xs tabular text-muted">
                            {entry.detail}
                          </div>
                        )}
                        <div className="mt-0.5 text-[11px] text-faint">
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
              className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-surface-2"
            >
              <ClockCounterClockwise size={14} weight="bold" className="text-muted" />
              Cambios
              {unseen > 0 && (
                <span className="tabular flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-fg">
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
          className="toast-in pointer-events-auto flex w-full items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-sm shadow-lg"
        >
          <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" />
          <div className="min-w-0 flex-1">{toast.message}</div>
          <IconButton aria-label="Cerrar aviso" onClick={() => dismissToast(toast.id)}>
            <X size={14} />
          </IconButton>
        </div>
      ))}
    </div>
  );
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
