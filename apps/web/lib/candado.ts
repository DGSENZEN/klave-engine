// Quién cerró un nodo, del aviso en vivo que manda el servidor al cerrarlo.
// Sin nombre no se inventa uno: el aviso dice sólo que se cerró.

type EventoCandado = { type: string; data?: Record<string, unknown> } | null | undefined;

export function quienCerro(evento: EventoCandado, nodo: string): string | null {
  if (!evento || evento.type !== "gate_updated") return null;
  const data = evento.data ?? {};
  if (data.node !== nodo || data.approved !== false) return null;
  return typeof data.by === "string" && data.by.trim() ? data.by.trim() : null;
}
