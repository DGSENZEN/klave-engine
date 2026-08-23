"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "@phosphor-icons/react";

/**
 * One modal for the app: backdrop, Escape, a title, and a footer for the
 * buttons. Destructive confirmations use ConfirmDialog instead; this is
 * for forms and previews ("esto es lo que va a cambiar") that need room.
 */
export function Modal({
  open,
  title,
  sub,
  onClose,
  busy = false,
  size = "md",
  footer,
  children,
}: {
  open: boolean;
  title: string;
  sub?: string;
  onClose: () => void;
  /** While true, Escape and the backdrop do not close it. */
  busy?: boolean;
  size?: "md" | "lg";
  footer?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onClose]);

  if (!open) return null;
  const width = size === "lg" ? "max-w-2xl" : "max-w-md";
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Cerrar"
        onClick={() => !busy && onClose()}
        className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`toast-in relative flex max-h-[90vh] w-full ${width} flex-col rounded-xl border border-border bg-surface shadow-lg`}
      >
        <div className="flex items-start gap-3 border-b border-border px-5 py-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-[0.95rem] font-semibold">{title}</h2>
            {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
          </div>
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => !busy && onClose()}
            className="rounded-md p-1 text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            <X size={16} weight="bold" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">{children}</div>
        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
