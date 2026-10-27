// Cuándo una tecla es de quien escribe y no del recorrido. Un botón también
// tiene `value`: preguntar por esa propiedad dejaba las flechas muertas
// justo después de hacer clic en «Siguiente».

const NO_ESCRIBEN = new Set(["button", "checkbox", "radio", "submit", "reset", "range", "color", "file"]);

export function esCampoDeTexto(tag: string, editable: boolean, tipo?: string): boolean {
  if (editable) return true;
  const etiqueta = tag.toUpperCase();
  if (etiqueta === "TEXTAREA" || etiqueta === "SELECT") return true;
  return etiqueta === "INPUT" && !NO_ESCRIBEN.has((tipo ?? "text").toLowerCase());
}

/** Qué hace el recorrido con una tecla. La pantalla manda: si ya la usó
 * (defaultPrevented), si se escribe, o si el paso vive en el visor (que usa
 * ← → para recorrer elementos), el recorrido no la toma. Esc sólo pausa desde
 * la tarjeta: en la pantalla cierra diálogos y deselecciona. */
export function teclaDelRecorrido(evento: {
  key: string;
  defaultPrevented: boolean;
  enTarjeta: boolean;
  escribiendo: boolean;
  tipo: "mirar" | "hacer" | null;
  ancla: string | null | undefined;
}): "pausar" | "siguiente" | "atras" | null {
  if (evento.defaultPrevented || evento.escribiendo) return null;
  if (evento.key === "Escape") return evento.enTarjeta ? "pausar" : null;
  const conFlechas = (evento.tipo === "mirar" || evento.tipo === null) && evento.ancla !== "visor.lienzo";
  if (!conFlechas) return null;
  if (evento.key === "ArrowRight") return "siguiente";
  if (evento.key === "ArrowLeft") return "atras";
  return null;
}
