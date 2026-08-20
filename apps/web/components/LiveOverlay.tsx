"use client";

import { ClockCounterClockwise, X, Check } from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { Avatar, IconButton } from "@/components/ui";

/*
 * Live-change surfaces. The old implementation floated a "Cambios" pill over
 * the top-right of every page, where it covered page headers and intercepted
 * their clicks. The trigger now lives in the shell chrome (sidebar footer on
 * desktop, top bar on mobile) and the panel anchors to it; transient toasts
 * stack at the bottom-right, clear of headers and the parametros action bar.
 */

export function ChangesTrigger({
  unseen,
  onClick,
  variant,
}: {
  unseen: number;
  onClick: () => void;
  variant: "sidebar" | "topbar";
}) {
  if (variant === "topbar") {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-label="Ver cambios recientes"
        className="relative rounded-md p-2 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <ClockCounterClockwise size={18} weight="bold" />
        {unseen > 0 && (
          <span className="absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold tabular text-white">
            {unseen}
          </span>
        )}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
    >
      <ClockCounterClockwise size={16} weight="bold" />
      Cambios
      {unseen > 0 && (
        <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold tabular text-white">
          {unseen}
        </span>
      )}
    </button>
  );
}

export function ChangesPanel({ onClose }: { onClose: () => void }) {
  const { timeline, clearTimeline } = useProjectLive();
  return (
    <div className="toast-in fixed right-3 top-16 z-50 w-[calc(100vw-1.5rem)] max-w-80 overflow-hidden rounded-xl border border-border bg-surface shadow-lg lg:bottom-14 lg:left-3 lg:right-auto lg:top-auto">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ClockCounterClockwise size={15} weight="bold" className="text-accent" />
          Cambios
          {timeline.length > 0 && (
            <span className="tabular text-xs font-normal text-muted">{timeline.length}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {timeline.length > 0 && (
            <IconButton
              aria-label="Limpiar historial"
              title="Limpiar historial"
              onClick={clearTimeline}
            >
              <Check size={14} weight="bold" />
            </IconButton>
          )}
          <IconButton aria-label="Ocultar cambios" onClick={onClose}>
            <X size={14} weight="bold" />
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
                  <div className="mt-0.5 text-[11px] text-faint">{timeAgo(entry.ts)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/** Transient toasts, bottom-right: clear of page headers and action bars. */
export function LiveToasts() {
  const { toasts, dismissToast } = useProjectLive();
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-20 right-4 z-40 flex w-[calc(100vw-2rem)] max-w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="toast-in pointer-events-auto flex items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-sm shadow-lg"
        >
          <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-accent" />
          <div className="min-w-0 flex-1">{toast.message}</div>
          <IconButton aria-label="Cerrar aviso" onClick={() => dismissToast(toast.id)}>
            <X size={14} weight="bold" />
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
