"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Gauge, GearSix, MagnifyingGlass, SquaresFour } from "@phosphor-icons/react";
import { entryHref, NODE_NAV } from "@/lib/nodeNav";

/**
 * El salto directo: ⌘K (o Ctrl+K) abre la paleta, se teclean tres letras y
 * Enter lleva a cualquier pantalla del proyecto — cero clics de entrada y
 * salida. La lista es el mismo mapa de nodos de la navegación: una sola
 * fuente, ninguna deriva.
 */

type Destino = {
  key: string;
  label: string;
  grupo: string;
  icon: React.ReactNode;
  href: string;
};

function destinos(base: string): Destino[] {
  return [
    { key: "tablero", label: "Tablero", grupo: "Proyecto", icon: <SquaresFour size={16} />, href: base },
    { key: "resumen", label: "Resumen", grupo: "Proyecto", icon: <Gauge size={16} />, href: `${base}/resumen` },
    ...NODE_NAV.flatMap((node) =>
      node.entries.map((entry) => ({
        key: `${node.key}-${entry.key}`,
        label: entry.label,
        grupo: node.label,
        icon: entry.icon,
        href: entryHref(base, entry),
      })),
    ),
    {
      key: "configuracion",
      label: "Configuración del proyecto",
      grupo: "Ajustes",
      icon: <GearSix size={16} />,
      href: `${base}/configuracion`,
    },
  ];
}

/** Coincidencia simple y predecible: subcadenas por palabra, sin magia. */
function matches(destino: Destino, term: string): boolean {
  const text = `${destino.grupo} ${destino.label}`.toLowerCase();
  return term
    .toLowerCase()
    .split(/\s+/)
    .every((word) => !word || text.includes(word));
}

/** Abre la paleta desde cualquier control (el atajo sigue siendo ⌘K). */
export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent("klave:palette"));
}

export function CommandPalette({ projectId }: { projectId: string }) {
  const router = useRouter();
  const base = `/proyecto/${projectId}`;
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const visibles = useMemo(() => {
    const all = destinos(base);
    return term.trim() ? all.filter((d) => matches(d, term)) : all;
  }, [base, term]);
  const seleccion = Math.min(index, Math.max(visibles.length - 1, 0));

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => {
          if (!value) {
            setTerm("");
            setIndex(0);
          }
          return !value;
        });
      }
    }
    function onOpen() {
      setTerm("");
      setIndex(0);
      setOpen(true);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("klave:palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("klave:palette", onOpen);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const handle = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(handle);
  }, [open]);

  if (!open) return null;

  function go(destino: Destino | undefined) {
    if (!destino) return;
    setOpen(false);
    router.push(destino.href);
  }

  return (
    <div className="fixed inset-0 z-[70]">
      <button
        type="button"
        aria-label="Cerrar"
        onClick={() => setOpen(false)}
        className="absolute inset-0 bg-foreground/25"
      />
      <div className="menu-pop absolute left-1/2 top-24 w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border border-border-strong bg-surface shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-3.5 py-2.5">
          <MagnifyingGlass size={16} className="shrink-0 text-faint" />
          <input
            ref={inputRef}
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") setOpen(false);
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIndex((i) => Math.min(i + 1, visibles.length - 1));
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((i) => Math.max(i - 1, 0));
              }
              if (e.key === "Enter") {
                e.preventDefault();
                go(visibles[seleccion]);
              }
            }}
            placeholder="Ir a…"
            aria-label="Buscar pantalla"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
          <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 text-[10px] text-faint">
            esc
          </kbd>
        </div>
        <div className="max-h-80 overflow-y-auto p-1.5">
          {visibles.length === 0 && (
            <p className="px-2.5 py-3 text-sm text-muted">Nada coincide con «{term.trim()}».</p>
          )}
          {visibles.map((destino, i) => (
            <button
              key={destino.key}
              type="button"
              onClick={() => go(destino)}
              onPointerEnter={() => setIndex(i)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
                i === seleccion ? "bg-surface-2 text-foreground" : "text-muted"
              }`}
            >
              {destino.icon}
              <span className="flex-1">{destino.label}</span>
              <span className="text-xs text-faint">{destino.grupo}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
