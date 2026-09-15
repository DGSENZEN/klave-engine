"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "@phosphor-icons/react";
import { IconButton } from "@/components/ui";

/**
 * El inspector: el panel derecho que muestra lo que hay que VER de la fila
 * elegida. Tiene la misma anatomía para un insumo, un concepto, un básico o
 * un renglón de la base — secciones con título — para que se aprenda una
 * sola vez. Sustituye a los diálogos modales del catálogo. Esc lo cierra.
 */
export function Inspector({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <aside
      role="complementary"
      aria-label="Inspector"
      className="toast-in fixed inset-y-0 right-0 z-[52] flex w-[min(26rem,100vw)] flex-col border-l border-border bg-surface shadow-2xl"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{title}</div>
          {subtitle && <div className="mt-0.5 text-xs text-muted">{subtitle}</div>}
        </div>
        <IconButton aria-label="Cerrar inspector (Esc)" onClick={onClose}>
          <X size={16} />
        </IconButton>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
    </aside>
  );
}

/** Una sección del inspector: título en versalitas y su contenido. */
export function InspectorSection({
  title,
  children,
  aside,
}: {
  title: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="mb-5">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-faint">{title}</h3>
        {aside}
      </div>
      <div className="text-sm">{children}</div>
    </section>
  );
}
