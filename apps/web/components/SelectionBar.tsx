"use client";

import { useEffect, type ReactNode } from "react";
import { X } from "@phosphor-icons/react";
import { IconButton } from "@/components/ui";

/**
 * La barra de selección: aparece sólo cuando hay filas marcadas y trae las
 * acciones que actúan sobre varias a la vez. Cuando no hay selección no
 * existe — así las acciones en lote nunca se vuelven botones permanentes.
 * Esc la vacía.
 */
export function SelectionBar({
  count,
  noun,
  onClear,
  children,
}: {
  count: number;
  noun: string;
  onClear: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (count === 0) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClear();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [count, onClear]);
  if (count === 0) return null;
  return (
    <div
      role="toolbar"
      aria-label="Acciones sobre la selección"
      className="toast-in fixed bottom-5 left-1/2 z-[55] flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border-strong bg-surface px-4 py-2.5 shadow-2xl"
    >
      <span className="tabular text-sm font-medium">
        {count.toLocaleString("es-MX")} {noun}
      </span>
      <span className="h-5 w-px bg-border" />
      <div className="flex items-center gap-2">{children}</div>
      <IconButton aria-label="Quitar selección (Esc)" onClick={onClear}>
        <X size={16} />
      </IconButton>
    </div>
  );
}
