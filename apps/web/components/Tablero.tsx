"use client";

import { useState, type ReactNode } from "react";
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
  type TableroNodeKey,
} from "@/lib/api";
import { canApproveGate, GATED_NODES, quienPuedeAbrir } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { useTablero } from "@/lib/useProjectReport";
import { useProjectLive } from "@/components/ProjectLive";
import { timeAgo } from "@/lib/time";
import { Avatar, Badge, Button, Card, PageHeader, Skeleton } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

/**
 * El tablero: el anteproyecto como seis nodos en el orden del proceso.
 * Cada nodo dice sus hechos en chips (un hecho por chip, con denominador),
 * y los nodos con candado dicen qué falta y quién puede abrirlos — visibles
 * siempre, ocultos nunca.
 */

type NodeDef = {
  key: TableroNodeKey;
  label: string;
  icon: ReactNode;
  /** Ruta principal al hacer clic; fragmento de proyecto salvo que empiece absoluta. */
  route: string;
  /** Rutas cuya presencia cuenta para este nodo (fragmentos o absolutas). */
  presence: string[];
};

const NODES: NodeDef[] = [
  {
    key: "planos",
    label: "Planos",
    icon: <FileMagnifyingGlass size={20} />,
    route: "/lectura",
    presence: ["/lectura", "/plano", "/resumen"],
  },
  {
    key: "revision",
    label: "Revisión",
    icon: <ListChecks size={20} />,
    route: "/revision",
    presence: ["/revision", "/riesgos"],
  },
  {
    key: "catalogo",
    label: "Catálogo",
    icon: <Books size={20} />,
    route: "/catalogo",
    presence: ["/catalogo"],
  },
  {
    key: "presupuesto",
    label: "Presupuesto",
    icon: <Receipt size={20} />,
    route: "/presupuesto",
    presence: ["/presupuesto", "/apus"],
  },
  {
    key: "programa",
    label: "Programa",
    icon: <CalendarBlank size={20} />,
    route: "/programa",
    presence: ["/programa", "/flujo", "/parametros"],
  },
  {
    key: "contrato",
    label: "Contrato",
    icon: <Scales size={20} />,
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

const ESTADO_BADGE: Record<string, { tone: BadgeTone; label: string }> = {
  ok: { tone: "success", label: "En orden" },
  atencion: { tone: "warning", label: "Atención" },
  bloqueado: { tone: "default", label: "Con candado" },
  pendiente: { tone: "default", label: "Pendiente" },
};

const CHIP_TONE: Record<TableroChip["tone"], BadgeTone> = {
  ok: "success",
  warn: "warning",
  bad: "danger",
  muted: "default",
};

export function TableroBoard({ id }: { id: string }) {
  const { tablero, error, refetch } = useTablero(id);
  const { viewers, clientId, activities, timeline } = useProjectLive();
  const router = useRouter();
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateBusy, setGateBusy] = useState<TableroNodeKey | null>(null);
  const base = `/proyecto/${id}`;
  // El catálogo vive a nivel taller; todo lo demás es una ruta del proyecto.
  const resolve = (route: string) => (route === "/catalogo" ? route : `${base}${route}`);

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
          className="grid flex-1 grid-cols-1 gap-4 rounded-xl border border-border p-4 sm:grid-cols-2 xl:grid-cols-3"
          style={{
            backgroundColor: "var(--canvas-bg)",
            backgroundImage: "radial-gradient(var(--canvas-stroke) 1px, transparent 1px)",
            backgroundSize: "22px 22px",
          }}
        >
          {NODES.map((node) => {
            const data = tablero?.nodes?.[node.key];
            const estado = data?.estado ?? "pendiente";
            const badge = ESTADO_BADGE[estado] ?? ESTADO_BADGE.pendiente;
            const gated = GATED_NODES.includes(node.key);
            const gate = tablero?.gates?.[node.key];
            const canApprove = canApproveGate(tablero?.my_role ?? null);
            const nodeViewers = otherViewers.filter((viewer) =>
              node.presence.some((route) =>
                route === "/catalogo"
                  ? viewer.location_path === route
                  : viewer.location_path === `${base}${route}`,
              ),
            );
            return (
              <Card
                key={node.key}
                className={`flex cursor-pointer flex-col gap-3 p-4 transition hover:border-border-strong ${
                  estado === "bloqueado" ? "opacity-80" : ""
                }`}
              >
                <button
                  type="button"
                  onClick={() => router.push(resolve(node.route))}
                  className="flex items-start justify-between gap-2 text-left"
                >
                  <span className="flex items-center gap-2 font-medium">
                    <span className="text-muted">{node.icon}</span>
                    {node.label}
                    {gated &&
                      (gate ? (
                        <LockSimpleOpen size={14} className="text-success" />
                      ) : (
                        <LockSimple size={14} className="text-muted" />
                      ))}
                  </span>
                  <Badge tone={badge.tone} dot>
                    {badge.label}
                  </Badge>
                </button>
                {!tablero && !error && <Skeleton className="h-6 w-full" />}
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
                {gated && (
                  <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-2.5 text-xs text-muted">
                    {gate ? (
                      <>
                        <span className="truncate" title={gate.approved_at ?? undefined}>
                          Abierto por {gate.approved_by || "—"}
                          {gate.approved_at ? ` · ${timeAgo(gate.approved_at)}` : ""}
                        </span>
                        {canApprove && (
                          <Button
                            size="sm"
                            variant="ghost"
                            disabled={gateBusy === node.key}
                            onClick={() => toggleGate(node.key, false)}
                          >
                            Cerrar
                          </Button>
                        )}
                      </>
                    ) : (
                      <>
                        <span className="truncate">{quienPuedeAbrir(tablero?.my_role ?? null)}</span>
                        {canApprove && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={gateBusy === node.key || !tablero}
                            onClick={() => toggleGate(node.key, true)}
                          >
                            Abrir nodo
                          </Button>
                        )}
                      </>
                    )}
                  </div>
                )}
                {nodeViewers.length > 0 && (
                  <div className="flex -space-x-1.5">
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
              </Card>
            );
          })}
        </div>
        <ActivityRail activities={activities} timeline={timeline} />
      </div>
    </div>
  );
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
