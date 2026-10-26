import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const revisiones: Capitulo = {
  id: "revisiones",
  titulo: "Otra revisión",
  minutos: 3,
  requiereObra: true,
  pasos: pasos("revisiones", [
    {
      id: "revisiones.revb",
      tipo: "hacer",
      ruta: "/cambios",
      accion: "cargar_rev_b",
      titulo: "Llega la Rev B",
      cuerpo:
        "Cuando llega otra revisión del plano, se sube al mismo proyecto. Carga la Rev B de ejemplo: agranda una zapata, cambia una columna y quita un muro.",
      avanza: { con: "senal", nombre: "obra.lista" },
    },
    {
      id: "revisiones.resumen",
      tipo: "mirar",
      ruta: "/cambios",
      ancla: "cambios.resumen",
      titulo: "Qué cambió, en pesos",
      cuerpo:
        "Elementos agregados, eliminados, movidos y modificados, y la diferencia a precio de hoy: tu libro de aditivas y deductivas.",
      avanza: { con: "siguiente" },
    },
    {
      id: "revisiones.alplano",
      tipo: "hacer",
      ancla: "cambios.alplano",
      titulo: "Míralo en el plano",
      cuerpo:
        "«Ver en el plano» marca lo que cambió sobre el dibujo nuevo, con la huella del anterior.",
      avanza: { con: "ruta", ruta: "/plano" },
    },
  ]),
  transferencia:
    "En tu obra, sube cada revisión al mismo proyecto: Klave compara lectura contra lectura y te da las aditivas y deductivas en Excel.",
};
