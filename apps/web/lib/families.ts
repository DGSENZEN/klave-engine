import type { DetectionOverlay } from "@/lib/api";

/** The 21 canonical element families a detector can assign. Mirrors
 * `klave_engine.detection.taxonomy.Family` — keep the two in sync by hand;
 * nothing generates this list from the Python enum. Used where a human
 * chooses a family explicitly (e.g. counting a family the engine never
 * detected), as opposed to FAMILY_LABELS below, which also carries legacy
 * detection-type keys for rendering old runs. */
export const FAMILIES: string[] = [
  "castillo",
  "columna",
  "trabe",
  "contratrabe",
  "zapata",
  "losa",
  "muro",
  "dala",
  "cerramiento",
  "muro_concreto",
  "pilote",
  "escalera",
  "local",
  "terreno",
  "eje",
  "interseccion_ejes",
  "referencia_detalle",
  "mueble",
  "salida",
  "corrida",
  "vano",
];

// Family-first palette; detection-type keys keep old runs rendering.
// Deliberately desaturated so overlays read as one harmonized system on both
// canvas themes; distinct hues remain because families must stay tellable.
export const FAMILY_COLORS: Record<string, string> = {
  castillo: "#c2703d",
  columna: "#b8504d",
  trabe: "#4a66c9",
  contratrabe: "#6f66b8",
  zapata: "#a07a3a",
  losa: "#4d9077",
  muro: "#8a67ad",
  muro_concreto: "#6b4c9a",
  escalera: "#5b8c5a",
  local: "#2a9d8f",
  cuadro: "#9aa3a8",
  terreno: "#8a6d3b",
  dala: "#c27c2c",
  cerramiento: "#d9a441",
  pilote: "#2f7f8f",
  eje: "#9aa0aa",
  interseccion_ejes: "#767d88",
  referencia_detalle: "#b06084",
  // Instalaciones: la pieza que se instala, la salida que se prepara y los
  // metros de la red. Tres tintes propios para que no se confundan con la
  // estructura sobre la que se dibujan.
  mueble: "#3f8fa6",
  salida: "#5fa8bf",
  corrida: "#7bb8a0",
  vano: "#c98a5e",
  // Legacy detection-type fallbacks (runs without taxonomy).
  grid_line: "#9aa0aa",
  grid_intersection: "#767d88",
  column_tag: "#b8504d",
  beam_tag: "#4a66c9",
  footing: "#a07a3a",
  slab_region: "#4d9077",
  wall: "#8a67ad",
  detail_reference: "#b06084",
  fixture: "#5fa8bf",
  pipe_run: "#7bb8a0",
  opening: "#c98a5e",
};

export const FAMILY_LABELS: Record<string, string> = {
  castillo: "Castillos",
  columna: "Columnas",
  trabe: "Trabes",
  contratrabe: "Contratrabes",
  zapata: "Zapatas",
  losa: "Losas",
  muro: "Muros",
  muro_concreto: "Muros de concreto",
  escalera: "Escaleras",
  local: "Locales",
  cuadro: "Etiquetas de cuadro",
  terreno: "Terreno",
  dala: "Dalas",
  cerramiento: "Cerramientos",
  pilote: "Pilotes",
  pile: "Pilotes",
  eje: "Ejes",
  interseccion_ejes: "Intersecciones",
  referencia_detalle: "Referencias",
  mueble: "Muebles y equipos",
  salida: "Salidas",
  corrida: "Corridas de instalación",
  vano: "Puertas y ventanas",
  // Legacy detection-type fallbacks.
  grid_line: "Ejes",
  grid_intersection: "Intersecciones",
  column_tag: "Columnas/castillos",
  beam_tag: "Trabes",
  footing: "Zapatas/dados",
  slab_region: "Losas",
  wall: "Muros",
  detail_reference: "Referencias",
  fixture: "Muebles y salidas",
  pipe_run: "Corridas de instalación",
  opening: "Puertas y ventanas",
};

/** Grouping key for legend + visibility: family when available, else type. */
export function familyOf(d: DetectionOverlay): string {
  if (d.role === "cuadro") return "cuadro";
  return d.family || d.type;
}

/** Families that start hidden in the visor: cuadro labels are text on the
 * sheet, not elements, and only matter when checking what was read. */
export const HIDDEN_BY_DEFAULT = new Set(["cuadro"]);

export function detectionTitle(d: DetectionOverlay): string {
  const base = d.family_label || FAMILY_LABELS[d.type] || d.type;
  const name = d.mark || d.display_label || d.label;
  return `${base} ${name}`.trim();
}
