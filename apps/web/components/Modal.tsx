"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  type RefObject,
} from "react";
import { X } from "@phosphor-icons/react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]), [contenteditable="true"]';

function focusables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (element) => element.getClientRects().length > 0,
  );
}

/**
 * El foco de un diálogo: entra al abrir, no se escapa con Tab y vuelve a
 * donde estaba al cerrar. Sin esto, quien navega con teclado sigue
 * tabulando por la página de atrás con el diálogo encima.
 *
 * `initial` decide dónde cae el foco; si no hay, el primer control del
 * cuerpo (`[data-dialog-body]`) y, si tampoco, el diálogo mismo. Un hijo con
 * autoFocus gana: si el foco ya está adentro, no se mueve. Devuelve el
 * manejador de teclado que va en el elemento del diálogo; así, con un
 * diálogo dentro de otro, atrapa el de más adentro.
 */
export function useDialogFocus(
  open: boolean,
  dialogRef: RefObject<HTMLElement | null>,
  initial?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handle = window.setTimeout(() => {
      const dialog = dialogRef.current;
      if (!dialog || dialog.contains(document.activeElement)) return;
      const body = dialog.querySelector<HTMLElement>("[data-dialog-body]");
      const target = initial?.current ?? (body ? focusables(body)[0] : undefined) ?? dialog;
      target.focus();
    }, 0);
    return () => {
      window.clearTimeout(handle);
      if (previous?.isConnected) previous.focus();
    };
  }, [open, dialogRef, initial]);

  return useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      const dialog = dialogRef.current;
      if (event.key !== "Tab" || event.defaultPrevented || !dialog) return;
      const items = focusables(dialog);
      const active = document.activeElement;
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    },
    [dialogRef],
  );
}

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
  const dialogRef = useRef<HTMLDivElement>(null);
  const onDialogKeyDown = useDialogFocus(open, dialogRef);

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
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        onKeyDown={onDialogKeyDown}
        className={`toast-in relative flex outline-none max-h-[90vh] w-full ${width} flex-col rounded-xl border border-border bg-surface shadow-lg`}
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
        <div data-dialog-body className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm">
          {children}
        </div>
        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
