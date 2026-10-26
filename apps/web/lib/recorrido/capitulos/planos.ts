import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const planos: Capitulo = {
  id: "planos",
  titulo: "Planos",
  minutos: 5,
  requiereObra: true,
  pasos: pasos("planos", [
    {
      id: "planos.metricas",
      tipo: "mirar",
      ruta: "/lectura",
      ancla: "lectura.metricas",
      titulo: "Lo primero: las unidades",
      cuerpo:
        "Klave leyó centímetros del encabezado del archivo y encontró dos hojas. Si las unidades están mal, todas las cantidades lo están: revísalas antes que nada.",
      avanza: { con: "siguiente" },
    },
    {
      id: "planos.pestanas",
      tipo: "mirar",
      ancla: "lectura.pestanas",
      titulo: "Qué leyó, hoja por hoja",
      cuerpo:
        "Hojas, capas y familias, el levantamiento y, en Avisos, lo que no pudo leer. Nada se omite en silencio.",
      avanza: { con: "siguiente" },
    },
    {
      id: "planos.mover",
      tipo: "hacer",
      ruta: "/plano",
      ancla: "visor.lienzo",
      titulo: "El visor del plano",
      cuerpo:
        "Arrastra para moverte y usa la rueda para acercarte. Cada color es una familia de elementos que Klave leyó.",
      avanza: { con: "senal", nombre: "visor.mover" },
    },
    {
      id: "planos.seleccion",
      tipo: "hacer",
      ancla: "visor.lienzo",
      titulo: "Toca un elemento",
      cuerpo:
        "Haz clic sobre una columna o una zapata. Klave te muestra qué leyó, de dónde y con qué medida.",
      avanza: { con: "senal", nombre: "visor.seleccion" },
    },
    {
      id: "planos.inspector",
      tipo: "mirar",
      ancla: "visor.inspector",
      titulo: "La evidencia de cada lectura",
      cuerpo:
        "Marca, hoja, medida y supuestos de este elemento. Cada cantidad del presupuesto apunta a elementos como éste.",
      avanza: { con: "siguiente" },
    },
    {
      id: "planos.decidir",
      tipo: "hacer",
      ancla: "visor.lienzo",
      titulo: "Decide una duda",
      cuerpo:
        "Junto al cuadro de columnas, Klave leyó las marcas «C-1» y «C-2» del cuadro como si fueran columnas, y duda. Selecciona una y presiona X para excluirla (C confirma, ← → recorren).",
      avanza: {
        con: "evento",
        tipo: "review_updated",
        si: (data) => String(data.action ?? "").startsWith("detection_"),
      },
    },
  ]),
  transferencia:
    "En tu obra, recorre el visor hoja por hoja antes de mirar el dinero: excluir aquí cuesta segundos; descubrirlo en obra cuesta caro.",
};
