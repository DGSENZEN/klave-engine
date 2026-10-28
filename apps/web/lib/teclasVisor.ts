// El circuito de revisión del visor vive en el teclado: flechas recorren,
// C confirma, Q quita. Excluir saca dinero del presupuesto, así que X no
// excluye: abre el motivo, igual que en Revisión. Mientras se escribe —en un
// campo o en el motivo— ninguna tecla actúa.

export type AccionTecla =
  | "confirmar"
  | "pedir-motivo"
  | "quitar"
  | "siguiente"
  | "anterior"
  | "cancelar";

export type ContextoTecla = {
  enCampo: boolean;
  seleccionado: boolean;
  motivoAbierto: boolean;
  midiendo: boolean;
};

export function accionDeTecla(key: string, ctx: ContextoTecla): AccionTecla | null {
  if (ctx.enCampo || ctx.motivoAbierto) return null;
  if (key === "Escape") return "cancelar";
  if (ctx.midiendo) return null;
  if (key === "ArrowRight") return "siguiente";
  if (key === "ArrowLeft") return "anterior";
  if (!ctx.seleccionado) return null;
  const k = key.toLowerCase();
  if (k === "c") return "confirmar";
  if (k === "x") return "pedir-motivo";
  if (k === "q") return "quitar";
  return null;
}
