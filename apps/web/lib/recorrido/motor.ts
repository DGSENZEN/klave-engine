import type { Capitulo, Entrada, EstadoRecorrido, Paso } from "./tipos";

// El motor del recorrido: una función pura de (estado, entrada) → estado.
// La interfaz sólo despacha entradas; aquí vive cada regla de avance.

export const ESTADO_INICIAL: EstadoRecorrido = {
  activo: false,
  capitulo: null,
  indice: 0,
  projectId: null,
  obraLista: false,
  progreso: {},
  repaso: false,
  anclaPerdida: false,
  fueraDeRuta: false,
};

function capituloDe(estado: EstadoRecorrido, capitulos: Capitulo[]): Capitulo | null {
  return capitulos.find((c) => c.id === estado.capitulo) ?? null;
}

export function pasoActual(estado: EstadoRecorrido, capitulos: Capitulo[]): Paso | null {
  if (!estado.activo) return null;
  return capituloDe(estado, capitulos)?.pasos[estado.indice] ?? null;
}

/** "/x" relativa al proyecto, "~/x" del taller; null si no hay a dónde ir. */
export function resolverRuta(ruta: string, projectId: string | null): string | null {
  if (ruta.startsWith("~/")) return ruta.slice(1);
  if (!projectId) return null;
  const base = `/proyecto/${encodeURIComponent(projectId)}`;
  return ruta === "/" ? base : `${base}${ruta}`;
}

export function rutaDelPaso(paso: Paso, projectId: string | null): string | null {
  return paso.ruta ? resolverRuta(paso.ruta, projectId) : null;
}

function mismaRuta(pathname: string, ruta: string | null): boolean {
  if (ruta === null) return false;
  return decodeURIComponent(pathname) === decodeURIComponent(ruta.split("?")[0]);
}

function iniciar(estado: EstadoRecorrido, id: Capitulo["id"], capitulos: Capitulo[]): EstadoRecorrido {
  let capitulo = capitulos.find((c) => c.id === id) ?? capitulos[0];
  if (capitulo.requiereObra && !estado.obraLista) {
    capitulo = capitulos.find((c) => c.id === "arranque") ?? capitulos[0];
  }
  const hacer = capitulo.pasos.filter((p) => p.tipo === "hacer");
  return {
    ...estado,
    activo: true,
    capitulo: capitulo.id,
    indice: 0,
    repaso: hacer.length > 0 && hacer.every((p) => estado.progreso[p.id] !== undefined),
    anclaPerdida: false,
    fueraDeRuta: false,
  };
}

function completar(
  estado: EstadoRecorrido, paso: Paso, valor: "hecho" | "saltado",
): EstadoRecorrido {
  return {
    ...estado,
    progreso: { ...estado.progreso, [paso.id]: valor },
    indice: estado.indice + 1,
    anclaPerdida: false,
    fueraDeRuta: false,
  };
}

export function avanzar(
  estado: EstadoRecorrido, entrada: Entrada, capitulos: Capitulo[],
): EstadoRecorrido {
  switch (entrada.tipo) {
    case "progreso":
      return { ...estado, progreso: entrada.progreso };
    case "obra":
      return { ...estado, projectId: entrada.projectId, obraLista: entrada.lista };
    case "iniciar":
      return iniciar(estado, entrada.capitulo, capitulos);
    case "pausar":
      return { ...estado, activo: false };
  }
  if (!estado.activo) return estado;
  const capitulo = capituloDe(estado, capitulos);
  if (!capitulo) return estado;
  const paso = capitulo.pasos[estado.indice] ?? null;

  if (paso === null) {
    // La tarjeta de transferencia: Siguiente pasa al capítulo que sigue.
    if (entrada.tipo === "siguiente") {
      const i = capitulos.findIndex((c) => c.id === capitulo.id);
      const despues = capitulos[i + 1];
      return despues ? iniciar(estado, despues.id, capitulos) : { ...estado, activo: false };
    }
    if (entrada.tipo === "atras") return { ...estado, indice: Math.max(0, estado.indice - 1) };
    return estado;
  }

  const avanza = paso.avanza;
  switch (entrada.tipo) {
    case "siguiente":
      return paso.tipo === "mirar" || estado.repaso ? completar(estado, paso, "hecho") : estado;
    case "atras":
      return {
        ...estado, indice: Math.max(0, estado.indice - 1), anclaPerdida: false, fueraDeRuta: false,
      };
    case "saltar":
      return paso.tipo === "hacer" ? completar(estado, paso, "saltado") : estado;
    case "evento": {
      const { type, project_id, data } = entrada.evento;
      if (avanza.con !== "evento" || avanza.tipo !== type) return estado;
      if (!project_id || project_id !== estado.projectId) return estado;
      if (avanza.si && !avanza.si(data ?? {})) return estado;
      return completar(estado, paso, "hecho");
    }
    case "senal":
      return avanza.con === "senal" && avanza.nombre === entrada.nombre
        ? completar(estado, paso, "hecho")
        : estado;
    case "clic":
      return avanza.con === "clic" && paso.ancla === entrada.ancla
        ? completar(estado, paso, "hecho")
        : estado;
    case "ruta": {
      if (avanza.con === "ruta" && mismaRuta(entrada.pathname, resolverRuta(avanza.ruta, estado.projectId))) {
        return completar(estado, paso, "hecho");
      }
      const propia = rutaDelPaso(paso, estado.projectId);
      return { ...estado, fueraDeRuta: propia !== null && !mismaRuta(entrada.pathname, propia) };
    }
    case "ancla_perdida":
      return { ...estado, anclaPerdida: true };
  }
  return estado;
}
