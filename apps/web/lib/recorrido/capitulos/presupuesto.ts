import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const presupuesto: Capitulo = {
  id: "presupuesto",
  titulo: "Presupuesto",
  minutos: 6,
  requiereObra: true,
  pasos: pasos("presupuesto", [
    {
      id: "presupuesto.diagnostico",
      tipo: "mirar",
      ruta: "/presupuesto",
      ancla: "diagnostico.niveles",
      titulo: "Lo que hay que atender",
      cuerpo:
        "Tres niveles: bloqueante (entregarlo así estaría mal), dinero (falta un precio o una cantidad) y revisar. Cada hallazgo dice qué hacer y antes de qué momento.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.lineas",
      tipo: "mirar",
      ancla: "presupuesto.lineas",
      titulo: "Las partidas",
      cuerpo:
        "Cada renglón es un concepto con su cantidad medida del plano y su precio unitario. Lo que falta dice «sin precio», nunca $0.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.abrir",
      tipo: "hacer",
      ancla: "presupuesto.renglon",
      titulo: "Abre un renglón",
      cuerpo: "Haz clic en este renglón para ver su detalle y sus variantes.",
      avanza: { con: "clic" },
    },
    {
      id: "presupuesto.variantes",
      tipo: "mirar",
      ancla: "presupuesto.variantes",
      titulo: "Las variantes, con su importe",
      cuerpo:
        "Cada sección con su cantidad y su precio. Las variantes suman exactamente el renglón.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.alplano",
      tipo: "hacer",
      ancla: "presupuesto.alplano",
      titulo: "Del número al dibujo",
      cuerpo:
        "«Verlos en el plano» te lleva a los elementos que sostienen esta cantidad. Así defiendes cada número.",
      avanza: { con: "ruta", ruta: "/plano" },
    },
    {
      id: "presupuesto.apus",
      tipo: "mirar",
      ruta: "/apus",
      ancla: "apus.matriz",
      titulo: "El precio unitario, desarmado",
      cuerpo:
        "Materiales, mano de obra y equipo con su rendimiento: de aquí sale el P.U. de cada concepto.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.captura",
      tipo: "mirar",
      ruta: "/presupuesto",
      ancla: "presupuesto.captura",
      titulo: "Lo que el plano no dio",
      cuerpo:
        "Lo que Klave vio pero no pudo medir, lo que no tiene precio y lo que esperaba y no encontró. Es tu lista de captura.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.convocante",
      tipo: "mirar",
      ruta: "/convocante",
      ancla: "convocante.vista",
      titulo: "El catálogo de la convocante",
      cuerpo:
        "Si la licitación trae su catálogo, impórtalo aquí: Klave le pone al lado la cantidad del plano y no lo modifica.",
      avanza: { con: "siguiente" },
    },
    {
      id: "presupuesto.exportar",
      tipo: "hacer",
      ruta: "/presupuesto",
      ancla: "presupuesto.exportar",
      titulo: "Entrega",
      cuerpo:
        "Exporta en el formato que uses: Klave, OPUS o Neodata. El f'c del plano no coincide con el del catálogo: Klave te detiene y te pide escribir por qué entregas así, y ese motivo queda en el Excel.",
      avanza: { con: "evento", tipo: "export_completed" },
    },
  ]),
  transferencia:
    "En tu obra, resuelve los bloqueantes antes de entregar; si entregas con uno, que sea con un motivo que defenderías.",
};
