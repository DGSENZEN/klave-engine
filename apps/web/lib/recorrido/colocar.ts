// Dónde va la tarjeta de un paso: junto a su ancla y siempre dentro de la
// vista. Abajo primero, luego arriba, a la derecha y a la izquierda; un ancla
// que no deja lugar (el lienzo del visor) recibe la tarjeta en su esquina.

export type Rect = { top: number; left: number; width: number; height: number };
export type Lado = "abajo" | "arriba" | "derecha" | "izquierda" | "centro" | "esquina";

const acotar = (valor: number, min: number, max: number) => Math.min(Math.max(valor, min), max);

export function colocarTarjeta(
  ancla: Rect | null,
  tarjeta: { w: number; h: number },
  vista: { w: number; h: number },
  margen = 12,
  preferido?: Exclude<Lado, "centro">,
): { top: number; left: number; lado: Lado } {
  if (!ancla) {
    return {
      top: Math.round((vista.h - tarjeta.h) / 2),
      left: Math.round((vista.w - tarjeta.w) / 2),
      lado: "centro",
    };
  }
  const maxLeft = vista.w - tarjeta.w - margen;
  const maxTop = vista.h - tarjeta.h - margen;
  // Abajo a la izquierda: fuera del camino de un menú o un diálogo que el paso abre.
  if (preferido === "esquina") return { top: maxTop, left: margen, lado: "esquina" };
  const centroX = acotar(ancla.left + ancla.width / 2 - tarjeta.w / 2, margen, maxLeft);
  const centroY = acotar(ancla.top + ancla.height / 2 - tarjeta.h / 2, margen, maxTop);

  const abajo = ancla.top + ancla.height + margen;
  const arriba = ancla.top - margen - tarjeta.h;
  const derecha = ancla.left + ancla.width + margen;
  const izquierda = ancla.left - margen - tarjeta.w;
  const lados: Record<Exclude<Lado, "centro" | "esquina">, { cabe: boolean; top: number; left: number }> = {
    abajo: { cabe: abajo <= maxTop, top: abajo, left: centroX },
    arriba: { cabe: arriba >= margen, top: arriba, left: centroX },
    derecha: { cabe: derecha <= maxLeft, top: centroY, left: derecha },
    izquierda: { cabe: izquierda >= margen, top: centroY, left: izquierda },
  };
  // Un paso puede pedir su lado (p. ej. junto a un menú que se abre hacia abajo).
  const orden = [preferido, "abajo", "arriba", "derecha", "izquierda"] as const;
  for (const lado of orden) {
    if (lado && lados[lado].cabe) return { top: lados[lado].top, left: lados[lado].left, lado };
  }
  return { top: maxTop, left: maxLeft, lado: "centro" };
}
