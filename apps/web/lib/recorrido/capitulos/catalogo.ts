import type { Capitulo } from "../tipos";
import { pasos } from "./paso";

export const catalogo: Capitulo = {
  id: "catalogo",
  titulo: "Catálogo",
  minutos: 4,
  requiereObra: true,
  pasos: pasos("catalogo", [
    {
      id: "catalogo.lista",
      tipo: "mirar",
      ruta: "/revision?tab=catalogo",
      ancla: "variantes.lista",
      titulo: "Variantes del plano",
      cuerpo:
        "El plano distingue columnas C-1 de 30×40 y C-2 de 40×40, y tu catálogo las cobra distinto. Cada fila es una variante que necesita su concepto.",
      avanza: { con: "siguiente" },
    },
    {
      id: "catalogo.mapear",
      tipo: "hacer",
      ancla: "variantes.mapear",
      titulo: "Mapea una variante",
      cuerpo:
        "Con «Elegir…» asigna el concepto de tu catálogo que le corresponde, o márcala sin equivalente. Así el presupuesto usa tus claves.",
      avanza: {
        con: "evento",
        tipo: "costing_updated",
        si: (data) => data.review_action === "mapeo",
      },
    },
    {
      id: "catalogo.memoria",
      tipo: "mirar",
      ancla: "variantes.resumen",
      titulo: "Klave lo recuerda",
      cuerpo: "Lo que mapeas se aplica solo en tus siguientes obras: decides una vez.",
      avanza: { con: "siguiente" },
    },
    {
      id: "catalogo.origen",
      tipo: "mirar",
      ruta: "~/catalogo?tab=insumos",
      ancla: "catalogo.origen",
      titulo: "El catálogo de tu taller",
      cuerpo:
        "Insumos, matrices y rendimientos con los que se calcula todo. Cada fila dice de dónde viene: oficial, importada, generada o tuya.",
      avanza: { con: "siguiente" },
    },
    {
      id: "catalogo.procedencia",
      tipo: "mirar",
      ancla: "catalogo.procedencia",
      titulo: "Fuente y vigencia de cada precio",
      cuerpo:
        "Referencia, cotización, publicación oficial o calculado, con su mes. Un precio viejo se marca para que lo revises.",
      avanza: { con: "siguiente" },
    },
  ]),
  transferencia:
    "En tu obra, importa tus precios (o tu base de OPUS) antes de cotizar. Los precios de referencia sirven para empezar y no son precios de mercado.",
};
