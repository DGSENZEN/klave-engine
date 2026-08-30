"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
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
  type TableroChip,
  type TableroEstado,
  type TableroNodeKey,
} from "@/lib/api";
import { canApproveGate, GATED_NODES } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { useTablero } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { timeAgo } from "@/lib/time";
import { Avatar, Badge, Button, PageHeader, Skeleton } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

/**
 * El tablero: el anteproyecto como seis nodos conectados en el orden del
 * proceso, sobre el lienzo punteado. Los permisos se ven, no se explican:
 * un nodo que no puedes tocar se ve apagado y no responde; el botón de
 * abrir solo existe para quien puede abrirlo.
 */

type NodeDef = {
  key: TableroNodeKey;
  label: string;
  icon: ReactNode;
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
    route: "/lectura",
    presence: ["/lectura", "/plano", "/resumen"],
  },
  {
    key: "revision",
    label: "Revisión",
    icon: <ListChecks size={18} />,
    route: "/revision",
    presence: ["/revision", "/riesgos"],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    icon: <Books size={18} />,
    route: "/catalogo",
    presence: ["/catalogo"],
  },
  {
    key: "presupuesto",
    label: "Presupuesto",
    icon: <Receipt size={18} />,
    route: "/presupuesto",
    presence: ["/presupuesto", "/apus"],
  },
  {
    key: "programa",
    label: "Programa",
    icon: <CalendarBlank size={18} />,
    route: "/programa",
    presence: ["/programa", "/flujo", "/parametros"],
  },
  {
    key: "contrato",
    label: "Contrato",
    icon: <Scales size={18} />,
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

const CHIP_TONE: Record<TableroChip["tone"], BadgeTone> = {
  ok: "success",
  warn: "warning",
  bad: "danger",
  muted: "default",
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
    <div className="mx-auto max-w-6xl px-4 py-6 lg:px-8">
      <PageHeader
        title="Tablero"
        sub="El anteproyecto, nodo por nodo: qué está leído, qué está firmado y qué sigue con candado."
      />
      {gateError && (
        <div className="mb-4 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger">
          {gateError}
        </div>
      )}
      <div className="flex flex-col gap-6 lg:flex-row">
        <div
          ref={canvasRef}
          className="relative grid flex-1 grid-cols-1 content-start gap-x-10 gap-y-8 rounded-xl border border-border p-6 sm:grid-cols-2 xl:grid-cols-3"
          style={{
            backgroundColor: "var(--canvas-bg)",
            backgroundImage: "radial-gradient(var(--canvas-stroke) 1px, transparent 1px)",
            backgroundSize: "22px 22px",
          }}
        >
          <svg
            aria-hidden
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
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
                className={`relative z-10 flex min-h-32 flex-col gap-2.5 rounded-xl border bg-surface p-4 shadow-sm transition ${
                  untouchable
                    ? "cursor-not-allowed border-border opacity-55 saturate-0"
                    : "cursor-pointer border-border hover:-translate-y-0.5 hover:border-border-strong hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
                    {locked ? <LockSimple size={18} weight="fill" /> : node.icon}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                    {node.label}
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-muted">
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${ESTADO_DOT[estado]}`}
                    />
                    {ESTADO_LABEL[estado]}
                  </span>
                </div>
                {!tablero && !error && <Skeleton className="h-5 w-3/4" />}
                {error && !tablero && (
                  <span className="text-xs text-muted">No se pudo leer el estado.</span>
                )}
                <div className="flex flex-wrap gap-1.5">
                  {(data?.chips ?? []).slice(0, 3).map((chip) => (
                    <Badge key={chip.label} tone={CHIP_TONE[chip.tone] ?? "default"}>
                      {chip.label}
                    </Badge>
                  ))}
                </div>
                {gated && tablero && (gate || (locked && canApprove)) && (
                  <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-2 text-xs text-muted">
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
        <ActivityRail activities={activities} timeline={timeline} />
      </div>
    </div>
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

function ActivityRail({
  activities,
  timeline,
}: {
  activities: { id: number; message: string; locationLabel: string }[];
  timeline: { id: number; ts: string; actor: string; title: string; detail?: string }[];
}) {
  return (
    <aside className="w-full shrink-0 lg:w-72">
      <div className="microlabel mb-2">Actividad</div>
      {activities.length === 0 && timeline.length === 0 && (
        <p className="text-sm text-muted">
          Sin movimientos por ahora. Lo que pase en el proyecto aparece aquí en vivo.
        </p>
      )}
      <div className="space-y-2">
        {activities.slice(0, 4).map((activity) => (
          <div key={`a-${activity.id}`} className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-sm">{activity.message}</div>
            {activity.locationLabel && (
              <div className="text-xs text-muted">{activity.locationLabel}</div>
            )}
          </div>
        ))}
        {timeline.slice(0, 8).map((entry) => (
          <div key={`t-${entry.id}`} className="rounded-lg border border-border bg-surface px-3 py-2">
            <div className="text-sm">{entry.title}</div>
            <div className="text-xs text-muted">
              {entry.actor} · {timeAgo(entry.ts)}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}
