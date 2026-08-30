"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowsInSimple,
  CaretRight,
  LockSimple,
  LockSimpleOpen,
  Minus,
  Plus,
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
import { entryHref, NODE_NAV } from "@/lib/nodeNav";
import { useTablero } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { timeAgo } from "@/lib/time";
import { Avatar, Button, Skeleton } from "@/components/ui";

/**
 * El tablero como lienzo de verdad: los nodos viven en coordenadas, se
 * arrastran, se estiran y el lienzo entero se panea y acerca — y todo se
 * recuerda por persona (localStorage: acomodo tuyo, datos de todos). Un
 * clic (no un arrastre) abre el menú del nodo, que brota hacia el lienzo.
 * Los permisos se ven, no se explican.
 */

const NODE_W = 280;
const MIN_W = 240;
const MAX_W = 520;
const MIN_H = 140;
const MENU_WIDTH = 248;
const COL = 340;
const ROW = 270;

type Box = { x: number; y: number; w: number; h?: number };
type View = { x: number; y: number; z: number };

const DEFAULT_LAYOUT: Record<TableroNodeKey, Box> = {
  planos: { x: 0, y: 0, w: NODE_W },
  revision: { x: COL, y: 0, w: NODE_W },
  catalogo: { x: COL * 2, y: 0, w: NODE_W },
  presupuesto: { x: 0, y: ROW, w: NODE_W },
  programa: { x: COL, y: ROW, w: NODE_W },
  contrato: { x: COL * 2, y: ROW, w: NODE_W },
};

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

function storageKey(id: string): string {
  return `klave-tablero-${id}`;
}

function loadStored(id: string): { layout?: Record<string, Box>; view?: View } | null {
  try {
    const raw = window.localStorage.getItem(storageKey(id));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function persist(id: string, layout: Record<TableroNodeKey, Box>, view: View | null) {
  try {
    window.localStorage.setItem(storageKey(id), JSON.stringify({ layout, view }));
  } catch {
    // sin almacenamiento no pasa nada: el acomodo vive esta sesión
  }
}

type Rect = { left: number; right: number; top: number; bottom: number; width: number; height: number };

function boxRect(box: Box, height: number): Rect {
  return {
    left: box.x,
    right: box.x + box.w,
    top: box.y,
    bottom: box.y + height,
    width: box.w,
    height,
  };
}

export function TableroBoard({ id }: { id: string }) {
  const { tablero, error, refetch } = useTablero(id);
  const { viewers, clientId, activities, timeline } = useProjectLive();
  const [layout, setLayout] = useState<Record<TableroNodeKey, Box>>(DEFAULT_LAYOUT);
  const [view, setView] = useState<View | null>(null);
  const [heights, setHeights] = useState<Partial<Record<TableroNodeKey, number>>>({});
  const [menuFor, setMenuFor] = useState<TableroNodeKey | null>(null);
  const [dragging, setDragging] = useState<TableroNodeKey | "pan" | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateBusy, setGateBusy] = useState<TableroNodeKey | null>(null);
  const base = `/proyecto/${id}`;

  const canvasRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef(new Map<TableroNodeKey, HTMLDivElement>());
  const stateRef = useRef<{ layout: Record<TableroNodeKey, Box>; view: View | null }>({
    layout,
    view,
  });
  useEffect(() => {
    stateRef.current = { layout, view };
  }, [layout, view]);

  // Acomodo guardado + vista inicial centrada: se cargan tras el montaje
  // (timeout-0) para no pelear con la hidratación ni con el lint de efectos.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      const stored = loadStored(id);
      if (stored?.layout) {
        setLayout((current) => {
          const next = { ...current };
          for (const key of Object.keys(next) as TableroNodeKey[]) {
            if (stored.layout?.[key]) next[key] = { ...next[key], ...stored.layout[key] };
          }
          return next;
        });
      }
      if (stored?.view) {
        setView(stored.view);
      } else {
        const canvas = canvasRef.current;
        if (canvas) {
          const rect = canvas.getBoundingClientRect();
          const contentW = COL * 2 + NODE_W;
          const contentH = ROW + 340;
          const z = Math.min(1, (rect.width - 48) / contentW);
          setView({
            x: (rect.width - contentW * z) / 2,
            y: Math.max(24, (rect.height - contentH * z) / 2),
            z,
          });
        } else {
          setView({ x: 40, y: 40, z: 1 });
        }
      }
    }, 0);
    return () => window.clearTimeout(handle);
  }, [id]);

  // Alturas reales de cada tarjeta (ResizeObserver reporta tamaño de layout,
  // inmune al scale del lienzo): de ahí salen las aristas.
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      setHeights((current) => {
        let changed = false;
        const next = { ...current };
        for (const item of entries) {
          for (const [key, el] of cardRefs.current) {
            if (el === item.target) {
              const h = el.offsetHeight;
              if (next[key] !== h) {
                next[key] = h;
                changed = true;
              }
            }
          }
        }
        return changed ? next : current;
      });
    });
    for (const el of cardRefs.current.values()) observer.observe(el);
    return () => observer.disconnect();
  }, [tablero]);

  // Zoom con rueda (ctrl/cmd ancla al puntero) y paneo con rueda libre.
  // Listener manual porque React registra wheel pasivo y aquí hay preventDefault.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const { view: current } = stateRef.current;
      if (!current) return;
      const rect = canvas.getBoundingClientRect();
      if (event.ctrlKey || event.metaKey) {
        const px = event.clientX - rect.left;
        const py = event.clientY - rect.top;
        const z = Math.min(1.6, Math.max(0.4, current.z * Math.exp(-event.deltaY * 0.0022)));
        const next = {
          x: px - ((px - current.x) * z) / current.z,
          y: py - ((py - current.y) * z) / current.z,
          z,
        };
        setView(next);
        persist(id, stateRef.current.layout, next);
      } else {
        const next = { ...current, x: current.x - event.deltaX, y: current.y - event.deltaY };
        setView(next);
        persist(id, stateRef.current.layout, next);
      }
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [id]);

  /** Arrastres con umbral: menos de 4 px es un clic (abre el menú). */
  function startPointer(
    event: React.PointerEvent,
    mode:
      | { type: "node"; key: TableroNodeKey }
      | { type: "resize"; key: TableroNodeKey }
      | { type: "pan" },
  ) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startY = event.clientY;
    const snapshot = stateRef.current;
    const startView = snapshot.view ?? { x: 0, y: 0, z: 1 };
    const startBox =
      mode.type === "pan" ? null : { ...snapshot.layout[mode.key] };
    const startH =
      mode.type === "resize"
        ? (snapshot.layout[mode.key].h ?? cardRefs.current.get(mode.key)?.offsetHeight ?? MIN_H)
        : 0;
    let moved = false;

    const onMove = (move: PointerEvent) => {
      const dx = move.clientX - startX;
      const dy = move.clientY - startY;
      if (!moved && Math.hypot(dx, dy) > 4) {
        moved = true;
        setMenuFor(null);
        setDragging(mode.type === "pan" ? "pan" : mode.key);
      }
      if (!moved) return;
      if (mode.type === "pan") {
        setView({ ...startView, x: startView.x + dx, y: startView.y + dy });
      } else if (mode.type === "node" && startBox) {
        setLayout((current) => ({
          ...current,
          [mode.key]: {
            ...current[mode.key],
            x: startBox.x + dx / startView.z,
            y: startBox.y + dy / startView.z,
          },
        }));
      } else if (mode.type === "resize" && startBox) {
        setLayout((current) => ({
          ...current,
          [mode.key]: {
            ...current[mode.key],
            w: Math.min(MAX_W, Math.max(MIN_W, startBox.w + dx / startView.z)),
            h: Math.max(MIN_H, startH + dy / startView.z),
          },
        }));
      }
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      setDragging(null);
      const latest = stateRef.current;
      if (moved) {
        persist(id, latest.layout, latest.view);
      } else if (mode.type === "node") {
        setMenuFor((current) => (current === mode.key ? null : mode.key));
      } else if (mode.type === "pan") {
        setMenuFor(null);
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function setZoom(factor: number | null) {
    const canvas = canvasRef.current;
    const current = stateRef.current.view;
    if (!canvas || !current) return;
    const rect = canvas.getBoundingClientRect();
    let next: View;
    if (factor === null) {
      const contentW = COL * 2 + NODE_W;
      const contentH = ROW + 340;
      const z = Math.min(1, (rect.width - 48) / contentW);
      next = {
        x: (rect.width - contentW * z) / 2,
        y: Math.max(24, (rect.height - contentH * z) / 2),
        z,
      };
    } else {
      const z = Math.min(1.6, Math.max(0.4, current.z * factor));
      const px = rect.width / 2;
      const py = rect.height / 2;
      next = {
        x: px - ((px - current.x) * z) / current.z,
        y: py - ((py - current.y) * z) / current.z,
        z,
      };
    }
    setView(next);
    persist(id, stateRef.current.layout, next);
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
  const menuNode = menuFor ? NODE_NAV.find((node) => node.key === menuFor) : null;
  const menuGate = menuFor ? tablero?.gates?.[menuFor] : undefined;
  const menuLocked =
    menuFor && tablero ? GATED_NODES.includes(menuFor) && !menuGate : false;
  const menuBox = menuFor ? layout[menuFor] : null;

  const edges = EDGES.flatMap(([from, to]) => {
    const a = boxRect(layout[from], layout[from].h ?? heights[from] ?? 180);
    const b = boxRect(layout[to], layout[to].h ?? heights[to] ?? 180);
    const d = connect(a, b);
    if (!d) return [];
    const estado = tablero?.nodes?.[from]?.estado ?? "pendiente";
    return [{ d, flowing: estado === "ok" }];
  });

  return (
    <div
      ref={canvasRef}
      className={`relative flex-1 touch-none overflow-hidden ${
        dragging === "pan" ? "cursor-grabbing" : "cursor-grab"
      }`}
      style={{
        backgroundColor: "var(--canvas-bg)",
        backgroundImage: "radial-gradient(var(--canvas-stroke) 1px, transparent 1px)",
        backgroundSize: `${22 * (view?.z ?? 1)}px ${22 * (view?.z ?? 1)}px`,
        backgroundPosition: `${view?.x ?? 0}px ${view?.y ?? 0}px`,
      }}
      onPointerDown={(event) => startPointer(event, { type: "pan" })}
    >
      {gateError && (
        <div className="absolute left-1/2 top-4 z-30 -translate-x-1/2 rounded-lg bg-danger-soft px-4 py-2 text-sm text-danger shadow-sm">
          {gateError}
        </div>
      )}
      <div
        className="absolute left-0 top-0"
        style={{
          transform: view
            ? `translate(${view.x}px, ${view.y}px) scale(${view.z})`
            : undefined,
          transformOrigin: "0 0",
          visibility: view ? "visible" : "hidden",
        }}
      >
        <svg
          aria-hidden
          width={1}
          height={1}
          className="pointer-events-none absolute left-0 top-0"
          style={{ overflow: "visible" }}
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
        {NODE_NAV.map((node) => {
          const data = tablero?.nodes?.[node.key];
          const estado: TableroEstado = data?.estado ?? "pendiente";
          const gated = GATED_NODES.includes(node.key);
          const gate = tablero?.gates?.[node.key];
          const locked = gated && tablero ? !gate : false;
          const untouchable = locked && !canApprove;
          const open = menuFor === node.key;
          const box = layout[node.key];
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
              onPointerDown={
                untouchable
                  ? (event) => event.stopPropagation()
                  : (event) => startPointer(event, { type: "node", key: node.key })
              }
              onKeyDown={
                untouchable
                  ? undefined
                  : (event) => {
                      if (event.key === "Enter")
                        setMenuFor((current) => (current === node.key ? null : node.key));
                      if (event.key === "Escape") setMenuFor(null);
                    }
              }
              className={`group absolute flex flex-col gap-3 rounded-xl border bg-surface p-5 transition-shadow ${
                dragging === node.key ? "" : "duration-200"
              } ${
                untouchable
                  ? "cursor-not-allowed border-border opacity-55 saturate-0 shadow-sm"
                  : open || dragging === node.key
                    ? "z-20 cursor-grab border-border-strong shadow-lg active:cursor-grabbing"
                    : "z-10 cursor-grab border-border shadow-sm hover:border-border-strong hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none active:cursor-grabbing"
              }`}
              style={{
                left: box.x,
                top: box.y,
                width: box.w,
                minHeight: box.h,
              }}
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
              {!untouchable && (
                <span
                  aria-hidden
                  onPointerDown={(event) =>
                    startPointer(event, { type: "resize", key: node.key })
                  }
                  className="absolute -bottom-1 -right-1 h-4 w-4 cursor-nwse-resize rounded-sm opacity-0 transition group-hover:opacity-100"
                  style={{
                    background:
                      "linear-gradient(135deg, transparent 50%, var(--border-strong, var(--faint)) 50%)",
                  }}
                />
              )}
            </div>
          );
        })}
        {menuFor && menuNode && menuBox && (
          <div
            key={menuFor}
            className="menu-pop absolute z-30 rounded-xl border border-border-strong bg-surface p-1.5 shadow-xl"
            style={{
              left: menuBox.x + menuBox.w + 12,
              top: menuBox.y,
              width: MENU_WIDTH,
              transformOrigin: "left center",
            }}
            onPointerDown={(event) => event.stopPropagation()}
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
                  disabled={gateBusy === menuFor}
                  className="w-full"
                  onClick={() => toggleGate(menuFor, true)}
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
                  disabled={gateBusy === menuFor}
                  className="w-full"
                  onClick={() => toggleGate(menuFor, false)}
                >
                  Cerrar nodo
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
      <div
        className="absolute bottom-4 left-4 z-20 flex items-center gap-0.5 rounded-lg border border-border bg-surface/90 p-0.5 shadow-sm backdrop-blur"
        onPointerDown={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          aria-label="Alejar"
          onClick={() => setZoom(1 / 1.2)}
          className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <Minus size={14} weight="bold" />
        </button>
        <span className="tabular min-w-10 text-center text-xs text-muted">
          {Math.round((view?.z ?? 1) * 100)} %
        </span>
        <button
          type="button"
          aria-label="Acercar"
          onClick={() => setZoom(1.2)}
          className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <Plus size={14} weight="bold" />
        </button>
        <button
          type="button"
          aria-label="Ajustar a la pantalla"
          onClick={() => setZoom(null)}
          className="rounded-md p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <ArrowsInSimple size={14} weight="bold" />
        </button>
      </div>
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
 * La curva entre dos tarjetas en coordenadas del lienzo: sale del lado que
 * mira al destino y entra por el que mira al origen.
 */
function connect(a: Rect, b: Rect): string | null {
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + b.height / 2 - (a.top + a.height / 2);
  if (Math.abs(dx) >= Math.abs(dy)) {
    const fromRight = dx >= 0;
    const x1 = fromRight ? a.right : a.left;
    const y1 = a.top + a.height / 2;
    const x2 = fromRight ? b.left : b.right;
    const y2 = b.top + b.height / 2;
    if (fromRight ? x2 <= x1 : x2 >= x1) return null;
    const bend = Math.max(24, Math.abs(x2 - x1) / 2) * (fromRight ? 1 : -1);
    return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
  }
  const fromBottom = dy >= 0;
  const x1 = a.left + a.width / 2;
  const y1 = fromBottom ? a.bottom : a.top;
  const x2 = b.left + b.width / 2;
  const y2 = fromBottom ? b.top : b.bottom;
  if (fromBottom ? y2 <= y1 : y2 >= y1) return null;
  const bend = Math.max(24, Math.abs(y2 - y1) / 2) * (fromBottom ? 1 : -1);
  return `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
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
