// Cuándo la obra de ejemplo «quedó lista» para el recorrido: al terminar de
// procesarse mientras la persona mira, no al abrir una obra que ya estaba
// leída — si no, retomar un paso que espera el procesamiento lo daría por
// hecho sin que nadie lo hiciera.

export function obraRecienLista(antes: string | null, ahora: string | null): boolean {
  return antes !== null && antes !== "processed" && ahora === "processed";
}
