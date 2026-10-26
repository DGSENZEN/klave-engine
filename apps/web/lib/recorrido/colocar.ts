// Dónde va la tarjeta de un paso: junto a su ancla y siempre dentro de la
// vista. Abajo primero, luego arriba, a la derecha y a la izquierda; un ancla
// que no deja lugar (el lienzo del visor) recibe la tarjeta en su esquina.

export type Rect = { top: number; left: number; width: number; height: number };
export type Lado = "abajo" | "arriba" | "derecha" | "izquierda" | "centro";

const acotar = (valor: number, min: number, max: number) => Math.min(Math.max(valor, min), max);

export function colocarTarjeta(
  ancla: Rect | null,
  tarjeta: { w: number; h: number },
  vista: { w: number; h: number },
  margen = 12,
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
  const centroX = acotar(ancla.left + ancla.width / 2 - tarjeta.w / 2, margen, maxLeft);
  const centroY = acotar(ancla.top + ancla.height / 2 - tarjeta.h / 2, margen, maxTop);

  const abajo = ancla.top + ancla.height + margen;
  if (abajo <= maxTop) return { top: abajo, left: centroX, lado: "abajo" };
  const arriba = ancla.top - margen - tarjeta.h;
  if (arriba >= margen) return { top: arriba, left: centroX, lado: "arriba" };
  const derecha = ancla.left + ancla.width + margen;
  if (derecha <= maxLeft) return { top: centroY, left: derecha, lado: "derecha" };
  const izquierda = ancla.left - margen - tarjeta.w;
  if (izquierda >= margen) return { top: centroY, left: izquierda, lado: "izquierda" };
  return { top: maxTop, left: maxLeft, lado: "centro" };
}
