import type { ConteosDeProyecto } from "./api";

// Los conteos se guardan como un documento entero: guardar sobre una base que
// nunca cargó reemplazaría lo de todos con un solo renglón. Por eso un fallo
// conserva lo que ya estaba en pantalla y, sin base, no se puede guardar.

export type CargaConteos = { base: ConteosDeProyecto | null; error: boolean };

export type ResultadoCarga =
  | { ok: true; data: ConteosDeProyecto }
  | { ok: false };

export function alCargar(prev: CargaConteos, r: ResultadoCarga): CargaConteos {
  if (r.ok) return { base: r.data, error: false };
  return { base: prev.base, error: true };
}

export function puedeGuardar(c: CargaConteos): boolean {
  return c.base !== null;
}
