// Qué muestra un proyecto según su trabajo de procesamiento. Reprocesar no
// desmonta lo que alguien ya tiene abierto: con una lectura legible (o la
// pantalla ya abierta en esta pestaña) el proyecto sigue a la vista con un
// aviso, y se actualiza al terminar.

export type Vista = "shell" | "shell-reprocesando" | "procesando" | "fallo";

export function vista(
  estado: string | undefined,
  artefactos: boolean,
  yaAbierta: boolean,
): Vista {
  if (estado === "processed") return "shell";
  if (estado === "failed") return artefactos ? "shell" : "fallo";
  return artefactos || yaAbierta ? "shell-reprocesando" : "procesando";
}
