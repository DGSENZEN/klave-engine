import type { Capitulo } from "../tipos";
import { arranque } from "./arranque";
import { catalogo } from "./catalogo";
import { planos } from "./planos";
import { presupuesto } from "./presupuesto";
import { programa } from "./programa";
import { revision } from "./revision";
import { revisiones } from "./revisiones";
import { tablero } from "./tablero";
import { tuObra } from "./tu-obra";

/** Los capítulos del recorrido, en el orden del flujo de trabajo. Otra
 * revisión va después del programa: cargarla vuelve a leer la obra. */
export const CAPITULOS: Capitulo[] = [
  arranque,
  tablero,
  planos,
  revision,
  catalogo,
  presupuesto,
  programa,
  revisiones,
  tuObra,
];
