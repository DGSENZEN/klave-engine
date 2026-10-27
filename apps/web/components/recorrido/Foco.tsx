"use client";

import type { Rect } from "@/lib/recorrido/colocar";

const HOLGURA = 6;

/** Lo que el paso señala. «Mirar» oscurece todo lo demás; «hacer» sólo
 * enmarca el ancla y deja la pantalla viva (teclas, clics, menús). Nunca
 * intercepta el puntero: el recorrido no bloquea el trabajo. */
export function Foco({ rect, tipo }: { rect: Rect | null; tipo: "mirar" | "hacer" }) {
  if (!rect) {
    return tipo === "mirar" ? (
      <div aria-hidden className="pointer-events-none fixed inset-0 z-[70] bg-foreground/35" />
    ) : null;
  }
  const caja = {
    top: rect.top - HOLGURA,
    left: rect.left - HOLGURA,
    width: rect.width + HOLGURA * 2,
    height: rect.height + HOLGURA * 2,
  };
  return (
    <div
      aria-hidden
      className={`pointer-events-none fixed z-[70] rounded-xl ring-2 ring-accent transition-[top,left,width,height] duration-200 motion-reduce:transition-none ${
        tipo === "mirar" ? "recorrido-foco" : ""
      }`}
      style={caja}
    />
  );
}
