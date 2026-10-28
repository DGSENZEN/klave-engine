import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

const verificacion = (paso: string) => (data: Record<string, unknown>) =>
  data.action === `verification_${paso}`;

export const revision: Capitulo = {
  id: "revision",
  titulo: "Revisión",
  minutos: 4,
  requiereObra: true,
  pasos: pasos("revision", [
    {
      id: "revision.tabla",
      tipo: "mirar",
      ruta: "/revision",
      ancla: "revision.tabla",
      titulo: "Todos los elementos, en una tabla",
      cuerpo:
        "Lo mismo que el visor, en filas: filtra por familia o por confianza y revisa de corrido. En obras grandes, Klave te propone primero un lote con las dudas.",
      avanza: { con: "siguiente" },
    },
    {
      id: "revision.masivo",
      tipo: "mirar",
      ancla: "revision.masivo",
      titulo: "Decidir muchos a la vez",
      cuerpo:
        "Selecciona filas (Shift+clic para un rango) y confírmalas o exclúyelas juntas. Cada decisión queda con tu nombre.",
      avanza: { con: "siguiente" },
    },
    {
      id: "revision.unidades",
      tipo: "hacer",
      ruta: "/resumen",
      ancla: "resumen.verificacion",
      titulo: "Verifica las unidades",
      cuerpo:
        "Tres pasos y el presupuesto deja de estar SIN VERIFICAR. El primero: confirma que el plano está en centímetros.",
      avanza: { con: "evento", tipo: "review_updated", si: verificacion("units") },
    },
    {
      id: "revision.elementos",
      tipo: "hacer",
      ancla: "resumen.verificacion",
      titulo: "Verifica los elementos",
      cuerpo: "Ya revisaste el plano: confírmalo. Lo que excluiste queda registrado.",
      avanza: { con: "evento", tipo: "review_updated", si: verificacion("detections") },
    },
    {
      id: "revision.supuestos",
      tipo: "hacer",
      ancla: "resumen.verificacion",
      titulo: "Verifica los supuestos",
      cuerpo:
        "Alturas, secciones y porcentajes que convierten elementos en dinero. Confírmalos cuando estés de acuerdo; se ajustan en Parámetros.",
      avanza: { con: "evento", tipo: "review_updated", si: verificacion("assumptions") },
    },
    {
      id: "revision.sello",
      tipo: "mirar",
      ancla: "resumen.sello",
      titulo: "Verificado",
      cuerpo:
        "Pantallas y Excel ya no llevan el sello SIN VERIFICAR. La app propone; tú firmas.",
      avanza: { con: "siguiente" },
    },
  ]),
  transferencia:
    "En tu obra, haz siempre estos tres pasos: un presupuesto sin verificar sale con el sello SIN VERIFICAR.",
};
