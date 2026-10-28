import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const programa: Capitulo = {
  id: "programa",
  titulo: "Programa",
  minutos: 3,
  requiereObra: true,
  pasos: pasos("programa", [
    {
      id: "programa.abrir",
      tipo: "hacer",
      ruta: "/programa",
      ancla: "gate.abrir",
      titulo: "Abre el programa",
      cuerpo:
        "El programa tiene candado: se abre cuando lo anterior está revisado. Ya revisaste y verificaste; ábrelo.",
      avanza: {
        con: "evento",
        tipo: "gate_updated",
        si: (data) => data.node === "programa",
      },
    },
    {
      id: "programa.plazo",
      tipo: "mirar",
      ancla: "programa.plazo",
      titulo: "El plazo, en días naturales",
      cuerpo:
        "Así lo cuenta el contrato. A su lado: cuándo termina la obra y cuántas actividades son críticas.",
      avanza: { con: "siguiente" },
    },
    {
      id: "programa.barras",
      tipo: "mirar",
      ancla: "programa.barras",
      titulo: "Barras y ruta crítica",
      cuerpo:
        "Cada barra va del inicio al término de su actividad. Las críticas retrasan toda la obra; las demás muestran su holgura.",
      avanza: { con: "siguiente" },
    },
    {
      id: "programa.flujo",
      tipo: "mirar",
      ruta: "/flujo",
      ancla: "flujo.curva",
      titulo: "El flujo de dinero",
      cuerpo: "Lo que la obra cobra y gasta por periodo, con el anticipo al inicio.",
      avanza: { con: "siguiente" },
    },
  ]),
  transferencia:
    "En tu obra, ajusta frentes de trabajo y fecha de arranque antes de comprometer un plazo: más cuadrillas o frentes abren margen.",
};
