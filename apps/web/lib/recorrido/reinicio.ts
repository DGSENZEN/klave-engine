// «Empezar de cero»: primero la obra, después el progreso. Si el servidor no
// pudo reiniciar la obra (se está procesando), el progreso se queda tal cual:
// borrarlo dejaría pasos prácticos imposibles de repetir sobre una obra que
// no volvió a la Rev A.

type Detalle = { detail?: { message?: string } | string; message?: string };

const AVISO = "La obra de ejemplo se está procesando; espera a que termine e inténtalo otra vez.";

function mensajeDe(error: unknown): string {
  const e = error as Detalle | null;
  const detalle = e?.detail;
  if (detalle && typeof detalle === "object" && detalle.message) return detalle.message;
  return AVISO;
}

export async function empezarDeCero(
  projectId: string | null,
  deps: { reiniciar(projectId: string): Promise<unknown>; borrar(): Promise<void> },
): Promise<{ ok: true } | { ok: false; mensaje: string }> {
  if (projectId) {
    try {
      await deps.reiniciar(projectId);
    } catch (error) {
      return { ok: false, mensaje: mensajeDe(error) };
    }
  }
  await deps.borrar();
  return { ok: true };
}
