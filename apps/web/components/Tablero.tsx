"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CaretRight, LockSimple, LockSimpleOpen } from "@phosphor-icons/react";
import {
  apiMessage,
  putGate,
  type TableroEstado,
  type TableroFact,
  type TableroNodeKey,
} from "@/lib/api";
import { canApproveGate, GATED_NODES } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { entryHref, NODE_NAV } from "@/lib/nodeNav";
import { useTablero } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { timeAgo } from "@/lib/time";
import { Avatar, Button, Skeleton } from "@/components/ui";

/**
 * El tablero: el anteproyecto como seis nodos conectados sobre el lienzo
 * que cubre toda la pantalla. Un clic abre el nodo EN SU LUGAR — su menú
 * brota hacia el lienzo, anclado a la tarjeta; navegar es elegir una
 * entrada, nunca un salto sorpresa. Los permisos se ven, no se explican:
 * el nodo que no puedes tocar se ve apagado y no responde.
 */

/** Rutas cuya presencia cuenta para cada nodo, derivadas de sus entradas. */
const PRESENCE: Record<TableroNodeKey, string[]> = Object.fromEntries(
  NODE_NAV.map((node) => [
    node.key,
    [
      ...node.entries.flatMap((entry) => [entry.href, ...(entry.also ?? [])]),
      ...(node.key === "planos" ? ["/resumen"] : []),
    ],
  ]),
) as Record<TableroNodeKey, string[]>;

/** El flujo del proceso: cada arista une un nodo con el que le sigue. */
const EDGES: [TableroNodeKey, TableroNodeKey][] = [
  ["planos", "revision"],
  ["revision", "catalogo"],
  ["catalogo", "presupuesto"],
  ["presupuesto", "programa"],
  ["programa", "contrato"],
];

const ESTADO_LABEL: Record<TableroEstado, string> = {
  ok: "En orden",
  atencion: "Atención",
  bloqueado: "Con candado",
  pendiente: "Pendiente",
};

const ESTADO_DOT: Record<TableroEstado, string> = {
  ok: "bg-success",
  atencion: "bg-warning node-dot-pulse",
  bloqueado: "bg-faint",
  pendiente: "bg-faint",
};

const FACT_DOT: Record<TableroFact["tone"], string> = {
  ok: "bg-success",
  warn: "bg-warning",
  bad: "bg-danger",
  muted: "bg-faint",
};

type EdgePath = { d: string; flowing: boolean };

const MENU_WIDTH = 248;

type MenuPos = {
  node: TableroNodeKey;
  left: number;
  top: number;
  origin: "left" | "right" | "top";
};

export function TableroBoard({ id }: { id: string }) {
  const { tablero, error, refetch } = useTablero(id);
  const { viewers, clientId, activities, timeline } = useProjectLive();
  const [menu, setMenu] = useState<MenuPos | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateBusy, setGateBusy] = useState<TableroNodeKey | null>(null);
  const base = `/proyecto/${id}`;

  // Las aristas se dibujan midiendo dónde quedó cada tarjeta en el lienzo.
  // ResizeObserver notifica al observar y en cada cambio de tamaño; el
  // setState ocurre en su callback (asíncrono), nunca en el cuerpo del efecto.
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef(new Map<TableroNodeKey, HTMLDivElement>());
  const [edges, setEdges] = useState<EdgePath[]>([]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const estados: Record<string, TableroEstado> = Object.fromEntries(
      NODE_NAV.map((node) => [node.key, tablero?.nodes?.[node.key]?.estado ?? "pendiente"]),
    );
    const measure = () => {
      const origin = canvas.getBoundingClientRect();
      const boxes = new Map<TableroNodeKey, DOMRect>();
      for (const [key, el] of cardRefs.current) boxes.set(key, el.getBoundingClientRect());
      const next: EdgePath[] = [];
      for (const [from, to] of EDGES) {
        const a = boxes.get(from);
        const b = boxes.get(to);
        if (!a || !b) continue;
        const path = connect(a, b, origin);
        if (path) next.push({ d: path, flowing: estados[from] === "ok" });
      }
      setEdges(next);
    };
    const observer = new ResizeObserver(measure);
    observer.observe(canvas);
    for (const el of cardRefs.current.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [tablero]);

  // Un cambio de tamaño invalida el ancla del menú: se cierra, sin drama.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    window.addEventListener("resize", close);
    return () => window.removeEventListener("resize", close);
  }, [menu]);

  /** Dónde brota el menú: al lado que tenga aire; si no, debajo. */
  function openMenu(node: TableroNodeKey) {
    const canvas = canvasRef.current;
    const card = cardRefs.current.get(node);
    if (!canvas || !card) return;
    const c = canvas.getBoundingClientRect();
    const r = card.getBoundingClientRect();
    if (r.right + 12 + MENU_WIDTH <= c.right - 8) {
      setMenu({ node, left: r.right - c.left + 12, top: r.top - c.top, origin: "left" });
    } else if (r.left - 12 - MENU_WIDTH >= c.left + 8) {
      setMenu({
        node,
        left: r.left - c.left - 12 - MENU_WIDTH,
        top: r.top - c.top,
        origin: "right",
      });
    } else {
      const left = Math.min(r.left - c.left, c.width - MENU_WIDTH - 8);
      setMenu({ node, left: Math.max(8, left), top: r.bottom - c.top + 10, origin: "top" });
    }
  }

  async function toggleGate(node: TableroNodeKey, approved: boolean) {
    setGateBusy(node);
    setGateError(null);
    try {
      await putGate(id, node, approved, getBrowserActor());
      refetch();
    } catch (err) {
      setGateError(apiMessage(err, "No se pudo cambiar el candado."));
    } finally {
      setGateBusy(null);
    }
  }

  const otherViewers = viewers.filter((viewer) => viewer.client_id !== clientId);
  const canApprove = tablero ? canApproveGate(tablero.my_role) : false;
  const menuNode = menu ? NODE_NAV.find((node) => node.key === menu.node) : null;
  const menuGate = menu ? tablero?.gates?.[menu.node] : undefined;
  const menuLocked =
    menu && tablero ? GATED_NODES.includes(menu.node) && !menuGate : false;

  return (
    <div
      ref={canvasRef}
      className="relative flex flex-1"
      style={{
        backgroundColor: "var(--canvas-bg)",
        backgroundImage: "radial-gradient(var(--canvas-stroke) 1px, transparent 1px)",
        backgroundSize: "22px 22px",
      }}
      onClick={() => setMenu(null)}
    >
      <svg aria-hidden className="pointer-events-none absolute inset-0 h-full w-full">
        {edges.map((edge) => (
          <g key={edge.d}>
            <path d={edge.d} fill="none" stroke="var(--canvas-stroke)" strokeWidth="1.5" />
            {edge.flowing && (
              <path
                d={edge.d}
                fill="none"
                stroke="var(--accent)"
                strokeWidth="1.5"
                className="edge-flow"
              />
            )}
          </g>
        ))}
      </svg>
      {gateError && (
        <div className="absolute left-1/2 top-4 z-30 -translate-x-1/2 rounded-lg bg-danger-soft px-4 py-2 text-sm text-danger shadow-sm">
          {gateError}
        </div>
      )}
      <div className="m-auto grid w-full max-w-5xl grid-cols-1 gap-x-16 gap-y-12 px-6 py-10 sm:grid-cols-2 xl:grid-cols-3">
        {NODE_NAV.map((node) => {
          const data = tablero?.nodes?.[node.key];
          const estado: TableroEstado = data?.estado ?? "pendiente";
          const gated = GATED_NODES.includes(node.key);
          const gate = tablero?.gates?.[node.key];
          const locked = gated && tablero ? !gate : false;
          const untouchable = locked && !canApprove;
          const open = menu?.node === node.key;
          const nodeViewers = otherViewers.filter((viewer) =>
            PRESENCE[node.key].some((route) =>
              route === "/catalogo"
                ? viewer.location_path === route
                : viewer.location_path === `${base}${route}`,
            ),
          );
          return (
            <div
              key={node.key}
              ref={(el) => {
                if (el) cardRefs.current.set(node.key, el);
                else cardRefs.current.delete(node.key);
              }}
              role={untouchable ? undefined : "button"}
              tabIndex={untouchable ? undefined : 0}
              aria-disabled={untouchable || undefined}
              aria-expanded={untouchable ? undefined : open}
              onClick={
                untouchable
                  ? undefined
                  : (event) => {
                      event.stopPropagation();
                      if (open) setMenu(null);
                      else openMenu(node.key);
                    }
              }
              onKeyDown={
                untouchable
                  ? undefined
                  : (event) => {
                      if (event.key === "Enter") {
                        if (open) setMenu(null);
                        else openMenu(node.key);
                      }
                      if (event.key === "Escape") setMenu(null);
                    }
              }
              className={`relative flex flex-col gap-3 rounded-xl border bg-surface p-5 transition-all duration-200 ${
                untouchable
                  ? "cursor-not-allowed border-border opacity-55 saturate-0 shadow-sm"
                  : open
                    ? "z-20 -translate-y-0.5 scale-[1.02] cursor-pointer border-border-strong shadow-lg"
                    : "z-10 cursor-pointer border-border shadow-sm hover:-translate-y-0.5 hover:border-border-strong hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
                  {locked ? <LockSimple size={18} weight="fill" /> : node.icon}
                </span>
                <span className="min-w-0 flex-1 pt-1.5 text-[15px] font-semibold leading-none">
                  {node.label}
                </span>
                <span className="flex shrink-0 items-center gap-1.5 pt-2 text-xs text-muted">
                  <span className={`inline-block h-2 w-2 rounded-full ${ESTADO_DOT[estado]}`} />
                  {ESTADO_LABEL[estado]}
                </span>
              </div>
              {!tablero && !error && (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-2/3" />
                </div>
              )}
              {error && !tablero && (
                <span className="text-xs text-muted">No se pudo leer el estado.</span>
              )}
              <div className="flex flex-col gap-1.5">
                {(data?.facts ?? []).slice(0, 5).map((fact, index) => (
                  <FactRow key={`${fact.label}-${index}`} fact={fact} />
                ))}
              </div>
              {gate && (
                <div className="mt-auto flex items-center gap-1.5 truncate border-t border-border pt-2.5 text-xs text-muted">
                  <LockSimpleOpen size={13} className="shrink-0 text-success" />
                  {gate.approved_by || "—"}
                  {gate.approved_at ? ` · ${timeAgo(gate.approved_at)}` : ""}
                </div>
              )}
              {nodeViewers.length > 0 && (
                <div className="absolute -top-2 right-3 flex -space-x-1.5">
                  {nodeViewers.slice(0, 4).map((viewer) => (
                    <Avatar key={viewer.client_id} name={viewer.actor} size="xs" />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {menu && menuNode && (
        <div
          key={menu.node}
          className="menu-pop absolute z-30 rounded-xl border border-border-strong bg-surface p-1.5 shadow-xl"
          style={{
            left: menu.left,
            top: menu.top,
            width: MENU_WIDTH,
            transformOrigin:
              menu.origin === "left"
                ? "left center"
                : menu.origin === "right"
                  ? "right center"
                  : "top center",
          }}
          onClick={(event) => event.stopPropagation()}
        >
          {!menuLocked &&
            menuNode.entries.map((entry) => (
              <Link
                key={entry.key}
                href={entryHref(base, entry)}
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                {entry.icon}
                <span className="flex-1">{entry.label}</span>
                <CaretRight size={12} className="opacity-60" />
              </Link>
            ))}
          {menuLocked && canApprove && (
            <div className="px-2.5 py-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={gateBusy === menu.node}
                className="w-full"
                onClick={() => toggleGate(menu.node, true)}
              >
                Abrir nodo
              </Button>
            </div>
          )}
          {menuGate && canApprove && (
            <div className="mt-1 border-t border-border px-1 pt-1">
              <Button
                size="sm"
                variant="ghost"
                disabled={gateBusy === menu.node}
                className="w-full"
                onClick={() => toggleGate(menu.node, false)}
              >
                Cerrar nodo
              </Button>
            </div>
          )}
        </div>
      )}
      <ActivityDock activities={activities} timeline={timeline} />
    </div>
  );
}

/** Un hecho por renglón: etiqueta a la izquierda, dato tabular a la
 * derecha, tono como punto — nada de píldoras ni saltos de página. */
function FactRow({ fact }: { fact: TableroFact }) {
  return (
    <span className="flex items-baseline justify-between gap-3 text-xs">
      <span className="flex min-w-0 items-center gap-1.5 truncate text-muted">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${FACT_DOT[fact.tone]}`} />
        {fact.label}
      </span>
      {fact.value && (
        <span className="shrink-0 font-medium tabular-nums text-foreground">{fact.value}</span>
      )}
    </span>
  );
}

/**
 * La curva entre dos tarjetas: sale del lado que mira al destino y entra
 * por el lado que mira al origen — horizontal entre vecinos de fila,
 * vertical al saltar de fila (el regreso del acordeón).
 */
function connect(a: DOMRect, b: DOMRect, origin: DOMRect): string | null {
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + b.height / 2 - (a.top + a.height / 2);
  const rel = (x: number, y: number) => `${x - origin.left} ${y - origin.top}`;
  if (Math.abs(dx) >= Math.abs(dy)) {
    const fromRight = dx >= 0;
    const x1 = fromRight ? a.right : a.left;
    const y1 = a.top + a.height / 2;
    const x2 = fromRight ? b.left : b.right;
    const y2 = b.top + b.height / 2;
    if (fromRight ? x2 <= x1 : x2 >= x1) return null;
    const bend = Math.max(24, Math.abs(x2 - x1) / 2) * (fromRight ? 1 : -1);
    return `M ${rel(x1, y1)} C ${rel(x1 + bend, y1)}, ${rel(x2 - bend, y2)}, ${rel(x2, y2)}`;
  }
  const fromBottom = dy >= 0;
  const x1 = a.left + a.width / 2;
  const y1 = fromBottom ? a.bottom : a.top;
  const x2 = b.left + b.width / 2;
  const y2 = fromBottom ? b.top : b.bottom;
  if (fromBottom ? y2 <= y1 : y2 >= y1) return null;
  const bend = Math.max(24, Math.abs(y2 - y1) / 2) * (fromBottom ? 1 : -1);
  return `M ${rel(x1, y1)} C ${rel(x1, y1 + bend)}, ${rel(x2, y2 - bend)}, ${rel(x2, y2)}`;
}

/** La actividad flota discreta en la esquina del lienzo, sin robar espacio
 * al escenario. */
function ActivityDock({
  activities,
  timeline,
}: {
  activities: { id: number; message: string; locationLabel: string }[];
  timeline: { id: number; ts: string; actor: string; title: string; detail?: string }[];
}) {
  const entries = [
    ...activities.slice(0, 2).map((activity) => ({
      key: `a-${activity.id}`,
      main: activity.message,
      sub: activity.locationLabel,
    })),
    ...timeline.slice(0, 3).map((entry) => ({
      key: `t-${entry.id}`,
      main: entry.title,
      sub: `${entry.actor} · ${timeAgo(entry.ts)}`,
    })),
  ];
  if (entries.length === 0) return null;
  return (
    <aside className="pointer-events-none absolute bottom-4 right-4 z-20 hidden w-64 lg:block">
      <div className="pointer-events-auto rounded-xl border border-border bg-surface/90 p-3 shadow-sm backdrop-blur">
        <div className="microlabel mb-2">Actividad</div>
        <div className="space-y-2">
          {entries.slice(0, 4).map((entry) => (
            <div key={entry.key} className="min-w-0">
              <div className="truncate text-xs">{entry.main}</div>
              {entry.sub && <div className="truncate text-[11px] text-faint">{entry.sub}</div>}
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
