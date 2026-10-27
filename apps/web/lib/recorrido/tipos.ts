// El recorrido guiado como datos: capítulos de pasos que señalan la interfaz
// real. Puro TS (sin React, sin DOM, sin alias «@/»): las pruebas de node lo
// compilan con tsc tal cual.

export type CapituloId =
  | "arranque"
  | "tablero"
  | "planos"
  | "revision"
  | "catalogo"
  | "presupuesto"
  | "programa"
  | "revisiones"
  | "tu-obra";

/** Lo que hace avanzar un paso: el botón Siguiente (sólo «mirar»), un clic
 * en el ancla, llegar a una ruta, un evento del servidor o una señal de la
 * interfaz. Un paso «hacer» sólo avanza cuando la app ve que ocurrió. */
export type Avance =
  | { con: "siguiente" }
  | { con: "clic" }
  | { con: "ruta"; ruta: string }
  | { con: "evento"; tipo: string; si?: (data: Record<string, unknown>) => boolean }
  | { con: "senal"; nombre: string };

export type AccionPaso = "crear_obra" | "cargar_rev_b";

export type Paso = {
  id: string;
  capitulo: CapituloId;
  tipo: "mirar" | "hacer";
  /** "/x" es relativa a /proyecto/{id}; "~/x" es una ruta del taller ("/x"). */
  ruta?: string;
  /** El valor de un atributo data-tour="…" en la pantalla. */
  ancla?: string;
  titulo: string;
  cuerpo: string;
  avanza: Avance;
  accion?: AccionPaso;
  /** Dónde prefiere su tarjeta, si el ancla abre algo hacia abajo (un menú). */
  lado?: "abajo" | "arriba" | "derecha" | "izquierda" | "esquina";
};

export type Capitulo = {
  id: CapituloId;
  titulo: string;
  minutos: number;
  pasos: Paso[];
  /** «En tu obra, …»: la última tarjeta del capítulo. */
  transferencia: string;
  /** Necesita la obra de ejemplo ya procesada; si no, el recorrido va al arranque. */
  requiereObra: boolean;
};

export type EventoBus = {
  type: string;
  project_id?: string | null;
  data?: Record<string, unknown>;
};

export type Progreso = Record<string, "hecho" | "saltado">;

export type EstadoRecorrido = {
  activo: boolean;
  capitulo: CapituloId | null;
  /** Índice del paso; igual a pasos.length en la tarjeta de transferencia. */
  indice: number;
  projectId: string | null;
  obraLista: boolean;
  progreso: Progreso;
  /** Capítulo ya hecho: sus pasos «hacer» se recorren con Siguiente. */
  repaso: boolean;
  anclaPerdida: boolean;
  fueraDeRuta: boolean;
};

export type Entrada =
  | { tipo: "iniciar"; capitulo: CapituloId }
  | { tipo: "siguiente" }
  | { tipo: "atras" }
  | { tipo: "saltar" }
  | { tipo: "pausar" }
  | { tipo: "evento"; evento: EventoBus }
  | { tipo: "senal"; nombre: string }
  | { tipo: "clic"; ancla: string }
  | { tipo: "ruta"; pathname: string }
  | { tipo: "ancla_perdida" }
  | { tipo: "obra"; projectId: string; lista: boolean }
  | { tipo: "progreso"; progreso: Progreso };
