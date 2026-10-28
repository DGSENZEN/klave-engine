// Quitar la revisión en lote deshace decisiones de otros: arriba de un lote
// chico se pregunta antes, nombrando cuántas.
export const UMBRAL_LOTE = 50;

export function pideConfirmarQuitarEnLote(n: number): boolean {
  return n > UMBRAL_LOTE;
}
