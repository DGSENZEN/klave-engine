"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Warning } from "@phosphor-icons/react";
import { Button, buttonClasses, Input } from "@/components/ui";

/**
 * Deliberate friction for destructive or authority-changing actions.
 *
 * Cancel gets initial focus so Enter never destroys anything by reflex, and
 * `typeToConfirm` demands the exact name be typed before the button arms.
 * Everyday actions must never go through this — the point is that dangerous
 * buttons feel different from the rest of the app.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  typeToConfirm,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  /** Exact string the user must type before the action arms. */
  typeToConfirm?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [typed, setTyped] = useState("");
  const cancelRef = useRef<HTMLButtonElement>(null);

  // Reset the typed confirmation each time the dialog opens (render-time
  // state adjustment keeps the strict effect lint honest).
  const [lastOpen, setLastOpen] = useState(open);
  if (lastOpen !== open) {
    setLastOpen(open);
    if (open) setTyped("");
  }

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => cancelRef.current?.focus(), 0);
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(handle);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onCancel]);

  if (!open) return null;
  const armed = !typeToConfirm || typed.trim() === typeToConfirm;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Cancelar"
        onClick={onCancel}
        className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]"
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        className="toast-in relative w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-lg"
      >
        <div className="mb-2 flex items-center gap-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-danger-soft text-danger">
            <Warning size={16} weight="bold" />
          </span>
          <h2 className="text-[0.95rem] font-semibold">{title}</h2>
        </div>
        <div className="text-sm leading-relaxed text-muted">{description}</div>
        {typeToConfirm && (
          <div className="mt-3">
            <p className="mb-1.5 text-xs text-muted">
              Escribe <span className="font-mono font-medium text-foreground">{typeToConfirm}</span>{" "}
              para confirmar:
            </p>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="w-full font-mono text-sm"
              autoFocus={false}
            />
          </div>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className={buttonClasses("secondary")}
          >
            Cancelar
          </button>
          <Button variant="danger" onClick={onConfirm} disabled={!armed}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
