// Los valores de partida sólo cuando el servidor dice que no hay análisis
// guardado. Una falla de carga no los inventa: guardarlos encima reemplazaría
// el análisis real del equipo y el costo del insumo.

export type ResultadoEquipo<T> =
  | { ok: true; data: T | null }
  | { ok: false; status?: number };

export type InicialCostoHorario<T> = {
  params: T | null;
  origen: "guardado" | "partida" | "error";
};

export function inicialCostoHorario<T>(
  r: ResultadoEquipo<T>,
  defaults: T,
): InicialCostoHorario<T> {
  if (r.ok) {
    return r.data ? { params: r.data, origen: "guardado" } : { params: defaults, origen: "partida" };
  }
  if ("status" in r && r.status === 404) return { params: defaults, origen: "partida" };
  return { params: null, origen: "error" };
}
