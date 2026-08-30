import type { ReactNode } from "react";
import {
  Books,
  Calculator,
  CalendarBlank,
  ChartLineUp,
  Coins,
  FileMagnifyingGlass,
  Flag,
  ListChecks,
  MapTrifold,
  Notebook,
  NotePencil,
  Receipt,
  Scales,
  Warning,
} from "@phosphor-icons/react";
import type { TableroNodeKey } from "@/lib/api";

/**
 * La navegación vive en los nodos: cada nodo del tablero carga sus propias
 * entradas (lo que antes era la barra lateral completa). El tablero las
 * muestra dentro de cada tarjeta y la barra lateral de las subpantallas se
 * vuelve contextual — solo el nodo donde estás parado.
 */

export type NodeEntry = {
  key: string;
  label: string;
  icon: ReactNode;
  /** Fragmento de ruta del proyecto, o ruta absoluta (catálogo del taller). */
  href: string;
  /** Rutas hermanas que también cuentan como esta entrada (p.ej. /flujo). */
  also?: string[];
};

export type NodeNav = {
  key: TableroNodeKey;
  label: string;
  icon: ReactNode;
  entries: NodeEntry[];
};

export const NODE_NAV: NodeNav[] = [
  {
    key: "planos",
    label: "Planos",
    icon: <FileMagnifyingGlass size={18} />,
    entries: [
      {
        key: "lectura",
        label: "Lectura del plano",
        icon: <FileMagnifyingGlass size={16} />,
        href: "/lectura",
      },
      { key: "plano", label: "Visor del plano", icon: <MapTrifold size={16} />, href: "/plano" },
    ],
  },
  {
    key: "revision",
    label: "Revisión",
    icon: <ListChecks size={18} />,
    entries: [
      { key: "revision", label: "Revisión", icon: <ListChecks size={16} />, href: "/revision" },
      { key: "riesgos", label: "Riesgos", icon: <Warning size={16} />, href: "/riesgos" },
    ],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    icon: <Books size={18} />,
    entries: [
      {
        key: "catalogo",
        label: "Catálogo del taller",
        icon: <Books size={16} />,
        href: "/catalogo",
      },
    ],
  },
  {
    key: "presupuesto",
    label: "Presupuesto",
    icon: <Receipt size={18} />,
    entries: [
      { key: "presupuesto", label: "Presupuesto", icon: <Receipt size={16} />, href: "/presupuesto" },
      { key: "apu", label: "Precios unitarios", icon: <Calculator size={16} />, href: "/apus" },
    ],
  },
  {
    key: "programa",
    label: "Programa",
    icon: <CalendarBlank size={18} />,
    entries: [
      {
        key: "programa",
        label: "Programa y flujo",
        icon: <CalendarBlank size={16} />,
        href: "/programa",
        also: ["/flujo"],
      },
      {
        key: "parametros",
        label: "Parámetros e insumos",
        icon: <Coins size={16} />,
        href: "/parametros",
      },
    ],
  },
  {
    key: "contrato",
    label: "Contrato",
    icon: <Scales size={18} />,
    entries: [
      {
        key: "contrato",
        label: "Catálogo del contrato",
        icon: <Scales size={16} />,
        href: "/contrato",
      },
      {
        key: "estimaciones",
        label: "Estimaciones",
        icon: <Receipt size={16} />,
        href: "/estimaciones",
      },
      { key: "convenios", label: "Convenios", icon: <NotePencil size={16} />, href: "/convenios" },
      { key: "bitacora", label: "Bitácora", icon: <Notebook size={16} />, href: "/bitacora" },
      {
        key: "ajuste-costos",
        label: "Ajuste de costos",
        icon: <ChartLineUp size={16} />,
        href: "/ajuste-costos",
      },
      { key: "finiquito", label: "Finiquito", icon: <Flag size={16} />, href: "/finiquito" },
    ],
  },
];

/** Resuelve un href de entrada a ruta real (el catálogo es del taller). */
export function entryHref(base: string, entry: NodeEntry): string {
  return entry.href === "/catalogo" ? entry.href : `${base}${entry.href}`;
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
