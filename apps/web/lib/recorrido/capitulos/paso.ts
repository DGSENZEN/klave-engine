import type { CapituloId, Paso } from "../tipos";

/** Los pasos de un capítulo, sin repetir a qué capítulo pertenecen. */
export function pasos(capitulo: CapituloId, lista: Omit<Paso, "capitulo">[]): Paso[] {
  return lista.map((paso) => ({ ...paso, capitulo }));
}
