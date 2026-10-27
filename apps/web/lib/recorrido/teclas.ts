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
