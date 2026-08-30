import type { Tablero, TableroEstado, TableroNodeKey } from "@/lib/api";

/**
 * The board's one rule, as a pure function (the moneyGate style): a node's
 * estado comes from the server's cheap read, and a missing node degrades to
 * "pendiente" — the board never invents progress.
 */
export function nodeGate(tablero: Tablero | null, node: TableroNodeKey): TableroEstado {
  return tablero?.nodes?.[node]?.estado ?? "pendiente";
}

/** Los nodos que llevan candado, en el orden del proceso. */
export const GATED_NODES: TableroNodeKey[] = ["presupuesto", "programa", "contrato"];

/**
 * Quién puede abrir un candado: el admin del taller o el owner del proyecto.
 * En modo abierto (my_role null, sin cuentas) todos pueden — la misma
 * libertad local-first del resto de la app.
 */
export function canApproveGate(myRole: Tablero["my_role"]): boolean {
  return myRole === null || myRole === "admin" || myRole === "owner";
}
