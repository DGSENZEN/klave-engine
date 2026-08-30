"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Books,
  CalendarBlank,
  FileMagnifyingGlass,
  ListChecks,
  LockSimple,
  LockSimpleOpen,
  Receipt,
  Scales,
} from "@phosphor-icons/react";
import {
  apiMessage,
  putGate,
  type TableroEstado,
  type TableroFact,
  type TableroNodeKey,
} from "@/lib/api";
import { canApproveGate, GATED_NODES } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { useTablero } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { timeAgo } from "@/lib/time";
import { Avatar, Button, Skeleton } from "@/components/ui";

/**
 * El tablero: el anteproyecto como seis nodos conectados en el orden del
 * proceso, sobre el lienzo punteado. Los nodos son el escenario: cada uno
 * dice sus hechos como renglones etiqueta·valor — minimalismo denso, sin
 * píldoras. Los permisos se ven, no se explican: un nodo que no puedes
 * tocar se ve apagado y no responde; el botón de abrir solo existe para
 * quien puede abrirlo.
 */

type NodeDef = {
  key: TableroNodeKey;
  label: string;
  icon: ReactNode;
  /** Qué es este nodo, en una línea corta que siempre se muestra. */
  detail: string;
  /** Ruta principal al hacer clic; fragmento de proyecto salvo el catálogo. */
  route: string;
  /** Rutas cuya presencia cuenta para este nodo (fragmentos o absolutas). */
  presence: string[];
};

const NODES: NodeDef[] = [
  {
    key: "planos",
    label: "Planos",
    icon: <FileMagnifyingGlass size={18} />,
    detail: "Lo que el motor leyó del dibujo",
    route: "/lectura",
    presence: ["/lectura", "/plano", "/resumen"],
  },
  {
    key: "revision",
    label: "Revisión",
    icon: <ListChecks size={18} />,
    detail: "La firma humana sobre la lectura",
    route: "/revision",
    presence: ["/revision", "/riesgos"],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    icon: <Books size={18} />,
    detail: "Conceptos y precios del taller",
    route: "/catalogo",
    presence: ["/catalogo"],
  },
  {
    key: "presupuesto",
    label: "Presupuesto",
    icon: <Receipt size={18} />,
    detail: "El dinero, con sus huecos a la vista",
    route: "/presupuesto",
    presence: ["/presupuesto", "/apus"],
  },
  {
    key: "programa",
    label: "Programa",
    icon: <CalendarBlank size={18} />,
    detail: "Plazo, fases y flujo de la obra",
    route: "/programa",
    presence: ["/programa", "/flujo", "/parametros"],
  },
  {
    key: "contrato",
    label: "Contrato",
    icon: <Scales size={18} />,
    detail: "La vida legal de la obra",
    route: "/contrato",
    presence: [
      "/contrato",
      "/estimaciones",
      "/convenios",
      "/bitacora",
      "/ajuste-costos",
      "/finiquito",
    ],
  },
];

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

export function TableroBoard({ id }: { id: string }) {
  const { tablero, error, refetch } = useTablero(id);
  const { viewers, clientId, activities, timeline } = useProjectLive();
  const router = useRouter();
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateBusy, setGateBusy] = useState<TableroNodeKey | null>(null);
  const base = `/proyecto/${id}`;
  // El catálogo vive a nivel taller; todo lo demás es una ruta del proyecto.
  const resolve = (route: string) => (route === "/catalogo" ? route : `${base}${route}`);

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
      NODES.map((node) => [node.key, tablero?.nodes?.[node.key]?.estado ?? "pendiente"]),
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

  return (
    <div className="px-4 py-5 lg:px-8">
      <div className="mb-4 flex items-baseline justify-between">
        <h1 className="font-display text-xl font-semibold tracking-tight">Tablero</h1>
        {gateError && <span className="text-sm text-danger">{gateError}</span>}
      </div>
      <div
        ref={canvasRef}
        className="relative grid min-h-[70vh] grid-cols-1 content-center gap-x-14 gap-y-12 rounded-xl border border-border p-6 sm:grid-cols-2 lg:p-10 xl:grid-cols-3"
        style={{
          backgroundColor: "var(--canvas-bg)",
          backgroundImage: "radial-gradient(var(--canvas-stroke) 1px, transparent 1px)",
          backgroundSize: "22px 22px",
        }}
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
        {NODES.map((node) => {
          const data = tablero?.nodes?.[node.key];
          const estado: TableroEstado = data?.estado ?? "pendiente";
          const gated = GATED_NODES.includes(node.key);
          const gate = tablero?.gates?.[node.key];
          const locked = gated && tablero ? !gate : false;
          const untouchable = locked && !canApprove;
          const nodeViewers = otherViewers.filter((viewer) =>
            node.presence.some((route) =>
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
              role={untouchable ? undefined : "link"}
              tabIndex={untouchable ? undefined : 0}
              aria-disabled={untouchable || undefined}
              onClick={untouchable ? undefined : () => router.push(resolve(node.route))}
              onKeyDown={
                untouchable
                  ? undefined
                  : (event) => {
                      if (event.key === "Enter") router.push(resolve(node.route));
                    }
              }
              className={`relative z-10 flex min-h-44 flex-col gap-3 rounded-xl border bg-surface p-5 shadow-sm transition ${
                untouchable
                  ? "cursor-not-allowed border-border opacity-55 saturate-0"
                  : "cursor-pointer border-border hover:-translate-y-0.5 hover:border-border-strong hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              }`}
            >
              <div className="flex items-start gap-2.5">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
                  {locked ? <LockSimple size={18} weight="fill" /> : node.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] font-semibold">
                    {node.label}
                  </span>
                  <span className="block truncate text-xs text-muted">{node.detail}</span>
                </span>
                <span className="flex shrink-0 items-center gap-1.5 pt-0.5 text-xs text-muted">
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
                  <FactRow
                    key={`${fact.label}-${index}`}
                    fact={fact}
                    href={fact.href ? resolve(fact.href) : undefined}
                  />
                ))}
              </div>
              {gated && tablero && (gate || (locked && canApprove)) && (
                <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-2.5 text-xs text-muted">
                  {gate ? (
                    <>
                      <span
                        className="flex min-w-0 items-center gap-1.5 truncate"
                        title={gate.approved_at ?? undefined}
                      >
                        <LockSimpleOpen size={13} className="shrink-0 text-success" />
                        {gate.approved_by || "—"}
                        {gate.approved_at ? ` · ${timeAgo(gate.approved_at)}` : ""}
                      </span>
                      {canApprove && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={gateBusy === node.key}
                          onClick={(event) => {
                            event.stopPropagation();
                            toggleGate(node.key, false);
                          }}
                        >
                          Cerrar
                        </Button>
                      )}
                    </>
                  ) : (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={gateBusy === node.key}
                      className="ml-auto"
                      onClick={(event) => {
                        event.stopPropagation();
                        toggleGate(node.key, true);
                      }}
                    >
                      Abrir nodo
                    </Button>
                  )}
                </div>
              )}
              {nodeViewers.length > 0 && (
                <div className="absolute -top-2 right-3 flex -space-x-1.5">
                  {nodeViewers.slice(0, 4).map((viewer) => (
                    <Avatar
                      key={viewer.client_id}
                      name={viewer.actor}
                      size="xs"
                      title={`${viewer.actor} · ${viewer.location_label || node.label}`}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <ActivityStrip activities={activities} timeline={timeline} />
    </div>
  );
}

/** Un hecho por renglón: etiqueta a la izquierda, dato tabular a la
 * derecha, tono como punto — nada de píldoras. */
function FactRow({ fact, href }: { fact: TableroFact; href?: string }) {
  const row = (
    <span className="flex items-baseline justify-between gap-3">
      <span className="flex min-w-0 items-center gap-1.5 truncate text-muted">
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${FACT_DOT[fact.tone]}`} />
        {fact.label}
      </span>
      {fact.value && (
        <span className="shrink-0 font-medium tabular-nums text-foreground">
          {fact.value}
        </span>
      )}
    </span>
  );
  if (!href) return <span className="block text-xs">{row}</span>;
  return (
    <Link
      href={href}
      onClick={(event) => event.stopPropagation()}
      className="block rounded text-xs transition hover:bg-surface-2/70"
    >
      {row}
    </Link>
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

/** La actividad va debajo del escenario, en una tira discreta. */
function ActivityStrip({
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
    ...timeline.slice(0, 6).map((entry) => ({
      key: `t-${entry.id}`,
      main: entry.title,
      sub: `${entry.actor} · ${timeAgo(entry.ts)}`,
    })),
  ];
  if (entries.length === 0) return null;
  return (
    <div className="mt-5">
      <div className="microlabel mb-2">Actividad</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        {entries.slice(0, 8).map((entry) => (
          <div key={entry.key} className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="truncate text-sm" title={entry.main}>
              {entry.main}
            </div>
            {entry.sub && <div className="truncate text-xs text-muted">{entry.sub}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
