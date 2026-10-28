import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const arranque: Capitulo = {
  id: "arranque",
  titulo: "Arranque",
  minutos: 2,
  requiereObra: false,
  pasos: pasos("arranque", [
    {
      id: "arranque.hola",
      tipo: "mirar",
      ruta: "~/",
      ancla: "inicio.recorrido",
      titulo: "Del plano a tu presupuesto",
      cuerpo:
        "Klave lee los planos de una obra, mide cada elemento y arma generadores ligados al dibujo, en tu catálogo y listos para OPUS o Neodata. Lo vas a hacer tú, en una obra de ejemplo que es sólo tuya.",
      avanza: { con: "siguiente" },
    },
    {
      id: "arranque.crear",
      tipo: "hacer",
      accion: "crear_obra",
      libre: true,
      titulo: "Crea tu obra de ejemplo",
      cuerpo:
        "Son dos hojas en centímetros (cimentación y estructura) y Klave las lee como cualquier plano tuyo. Mientras se procesa verás en qué etapa va.",
      avanza: { con: "senal", nombre: "obra.lista" },
    },
  ]),
  transferencia:
    "En tu obra empiezas igual: Nuevo proyecto, con todas las hojas juntas. Si un DWG no se convierte, expórtalo a DXF desde tu programa de dibujo.",
};
