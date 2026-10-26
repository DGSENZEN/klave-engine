import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const tuObra: Capitulo = {
  id: "tu-obra",
  titulo: "Tu obra",
  minutos: 2,
  requiereObra: false,
  pasos: pasos("tu-obra", [
    {
      id: "tu-obra.ayuda",
      tipo: "mirar",
      ruta: "~/",
      ancla: "workspace.ayuda",
      titulo: "El recorrido sigue aquí",
      cuerpo:
        "En Ayuda está este recorrido: repasa cualquier capítulo cuando lo necesites, o empieza de cero con la obra.",
      avanza: { con: "siguiente" },
    },
    {
      id: "tu-obra.subir",
      tipo: "mirar",
      ancla: "inicio.subir",
      titulo: "Tu primera obra",
      cuerpo:
        "Nuevo proyecto, con todas las hojas juntas (DWG o DXF). Lo que hiciste en la obra de ejemplo es lo mismo que harás con ella; con un juego grande, el procesamiento tarda más.",
      avanza: { con: "siguiente" },
    },
  ]),
  transferencia:
    "Ése es el camino completo: plano, revisión, catálogo, presupuesto, programa y entrega. Cuando quieras, sube tu obra.",
};
