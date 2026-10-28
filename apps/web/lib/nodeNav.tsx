import type { Icon } from "@phosphor-icons/react";
import {
  Blueprint,
  Books,
  Calculator,
  ChartBarHorizontal,
  ChartLineUp,
  ClipboardText,
  Coins,
  FileMagnifyingGlass,
  Flag,
  GitDiff,
  Handshake,
  Invoice,
  MapTrifold,
  Notebook,
  SealCheck,
  Signature,
  Tag,
  Timer,
  Wallet,
  Warning,
} from "@phosphor-icons/react";
import type { TableroNodeKey } from "@/lib/api";

/**
 * La navegación vive en los nodos: cada nodo del tablero carga sus propias
 * entradas. La franja del proceso (ProjectShell) muestra los seis nodos
 * siempre; la barra del nodo, sus entradas.
 *
 * Cada nodo tiene UN glifo y es suyo: el mismo en el tablero, la franja y la
 * paleta, y ninguna otra entrada lo usa salvo la principal de ese nodo.
 */

export type NodeEntry = {
  key: string;
  label: string;
  glyph: Icon;
  /** Fragmento de ruta del proyecto, o ruta absoluta (catálogo del taller). */
  href: string;
  /** Rutas hermanas que también cuentan como esta entrada (p.ej. /flujo). */
  also?: string[];
  /** La pantalla no espera al candado de su nodo (GateGuard): el tablero la
   * sigue ofreciendo aunque el nodo esté cerrado. */
  sinCandado?: boolean;
};

export type NodeNav = {
  key: TableroNodeKey;
  label: string;
  glyph: Icon;
  entries: NodeEntry[];
};

export const NODE_NAV: NodeNav[] = [
  {
    key: "planos",
    label: "Planos",
    glyph: Blueprint,
    entries: [
      { key: "lectura", label: "Lectura del plano", glyph: FileMagnifyingGlass, href: "/lectura" },
      { key: "plano", label: "Visor del plano", glyph: MapTrifold, href: "/plano" },
      { key: "cambios", label: "Cambios entre revisiones", glyph: GitDiff, href: "/cambios" },
    ],
  },
  {
    key: "revision",
    label: "Revisión",
    glyph: SealCheck,
    entries: [
      { key: "revision", label: "Revisión", glyph: SealCheck, href: "/revision" },
      { key: "riesgos", label: "Riesgos", glyph: Warning, href: "/riesgos" },
    ],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    glyph: Books,
    entries: [{ key: "catalogo", label: "Catálogo del taller", glyph: Books, href: "/catalogo" }],
  },
  {
    key: "presupuesto",
    label: "Presupuesto",
    glyph: Calculator,
    entries: [
      { key: "presupuesto", label: "Presupuesto", glyph: Calculator, href: "/presupuesto" },
      {
        key: "convocante",
        label: "Catálogo de la convocante",
        glyph: ClipboardText,
        href: "/convocante",
      },
      { key: "apu", label: "Precios unitarios", glyph: Tag, href: "/apus" },
      { key: "piloto", label: "Medición del piloto", glyph: Timer, href: "/piloto" },
    ],
  },
  {
    key: "programa",
    label: "Programa",
    glyph: ChartBarHorizontal,
    entries: [
      {
        key: "programa",
        label: "Programa de obra",
        glyph: ChartBarHorizontal,
        href: "/programa",
      },
      { key: "flujo", label: "Flujo financiero", glyph: Wallet, href: "/flujo" },
      {
        key: "parametros",
        label: "Parámetros e insumos",
        glyph: Coins,
        href: "/parametros",
        // Los supuestos alimentan al presupuesto y son el paso 3 de la ruta
        // de verificación: no pueden esperar a que se abra el programa.
        sinCandado: true,
      },
    ],
  },
  {
    key: "contrato",
    label: "Contrato",
    glyph: Signature,
    entries: [
      { key: "contrato", label: "Catálogo del contrato", glyph: Signature, href: "/contrato" },
      { key: "estimaciones", label: "Estimaciones", glyph: Invoice, href: "/estimaciones" },
      { key: "convenios", label: "Convenios", glyph: Handshake, href: "/convenios" },
      { key: "bitacora", label: "Bitácora", glyph: Notebook, href: "/bitacora" },
      { key: "ajuste-costos", label: "Ajuste de costos", glyph: ChartLineUp, href: "/ajuste-costos" },
      { key: "finiquito", label: "Finiquito", glyph: Flag, href: "/finiquito" },
    ],
  },
];

/** Un id de proyecto tal como lo emite el motor (`proj_1a2b3c4d`): nada que
 * pueda volverse otra ruta u otro origen al armar un enlace. */
export function isProjectSlug(value: string | null | undefined): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(value);
}

/**
 * Resuelve un href de entrada a ruta real. El catálogo es del taller y vive
 * fuera de la obra; lleva `?desde=` para que desde ahí se pueda volver.
 */
export function entryHref(base: string, entry: NodeEntry): string {
  if (entry.href !== "/catalogo") return `${base}${entry.href}`;
  const id = base.replace(/^\/proyecto\//, "");
  return isProjectSlug(id) ? `/catalogo?desde=${id}` : entry.href;
}

/** En qué nodo está parada esta ruta, para la barra lateral contextual. */
export function nodeForPath(base: string, pathname: string): NodeNav | null {
  for (const node of NODE_NAV) {
    for (const entry of node.entries) {
      const targets = [entry.href, ...(entry.also ?? [])].map((href) =>
        href === "/catalogo" ? href : `${base}${href}`,
      );
      if (targets.includes(pathname)) return node;
    }
  }
  return null;
}
