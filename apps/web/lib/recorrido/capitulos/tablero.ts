import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const tablero: Capitulo = {
  id: "tablero",
  titulo: "El tablero",
  minutos: 3,
  requiereObra: true,
  pasos: pasos("tablero", [
    {
      id: "tablero.nodos",
      tipo: "mirar",
      ruta: "/",
      ancla: "tablero.nodos",
      titulo: "El tablero de tu obra",
      cuerpo:
        "Seis nodos en el orden del trabajo: planos, revisión, catálogo, presupuesto, programa y contrato. Un clic en un nodo abre sus pantallas.",
      avanza: { con: "siguiente" },
    },
    {
      id: "tablero.sigue",
      tipo: "mirar",
      ancla: "tablero.sigue",
      titulo: "Lo que sigue",
      cuerpo:
        "Klave te dice el siguiente paso según cómo va la obra. Si no sabes por dónde seguir, empieza aquí.",
      avanza: { con: "siguiente" },
    },
    {
      id: "tablero.candado",
      tipo: "mirar",
      ancla: "tablero.candado",
      titulo: "Un nodo con candado",
      cuerpo:
        "Algunos nodos se abren sólo cuando lo anterior está en orden, y los abre quien tiene la autoridad. Abrirás uno más adelante, después de revisar.",
      avanza: { con: "siguiente" },
    },
    {
      id: "tablero.paleta",
      tipo: "mirar",
      ancla: "shell.paleta",
      titulo: "Ir a cualquier pantalla",
      cuerpo:
        "⌘K (Ctrl+K) abre un buscador de pantallas: tres letras y Enter. Ahí también están los capítulos de este recorrido.",
      avanza: { con: "siguiente" },
    },
  ]),
  transferencia:
    "En tu obra, vuelve al tablero cuando te pierdas: el nodo en «Atención» es el que pide tu mano.",
};
