"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  LayoutDashboard,
  Map,
  Receipt,
  Calculator,
  Coins,
  CalendarDays,
  LineChart,
  TriangleAlert,
  ChevronLeft,
  Building2,
  UserRound,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useProjectLive } from "@/components/ProjectLive";
import { LiveOverlay } from "@/components/LiveOverlay";

type Item = { key: string; label: string; icon: ReactNode; href: string; soon?: boolean };

function nav(id: string): { group: string; items: Item[] }[] {
  const b = `/proyecto/${id}`;
  return [
    {
      group: "Proyecto",
      items: [
        { key: "resumen", label: "Resumen", icon: <LayoutDashboard size={18} />, href: b },
        { key: "plano", label: "Visor del Plano", icon: <Map size={18} />, href: `${b}/plano` },
      ],
    },
    {
      group: "Ingeniería de Costos",
      items: [
        {
          key: "presupuesto",
          label: "Presupuesto",
          icon: <Receipt size={18} />,
          href: `${b}/presupuesto`,
        },
        {
          key: "parametros",
          label: "Parámetros e Insumos",
          icon: <Coins size={18} />,
          href: `${b}/parametros`,
        },
        {
          key: "apu",
          label: "Precios Unitarios",
          icon: <Calculator size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
      ],
    },
    {
      group: "Planeación y Finanzas",
      items: [
        {
          key: "programa",
          label: "Programa de Obra",
          icon: <CalendarDays size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
        {
          key: "finanzas",
          label: "Flujo Financiero",
          icon: <LineChart size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
        {
          key: "riesgos",
          label: "Riesgos",
          icon: <TriangleAlert size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
      ],
    },
  ];
}

export function ProjectShell({
  id,
  name,
  children,
}: {
  id: string;
  name?: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const groups = nav(id);
  const { actorName, setActorName, connected, clientId, viewers, activities } =
    useProjectLive();
  const [nameDraft, setNameDraft] = useState(actorName);
  const otherViewers = useMemo(
    () => viewers.filter((viewer) => viewer.client_id !== clientId),
    [clientId, viewers],
  );

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setNameDraft(actorName);
    }, 0);
    return () => window.clearTimeout(handle);
  }, [actorName]);

  function commitActorName() {
    setActorName(nameDraft);
  }

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--sidebar)]">
        <Link
          href="/"
          className="flex items-center gap-1.5 px-5 pt-4 pb-3 text-xs font-medium text-[var(--muted)] transition hover:text-[var(--foreground)]"
        >
          <ChevronLeft size={15} /> Proyectos
        </Link>
        <div className="flex items-center gap-2 px-5 pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--primary)] to-[#3730a3] text-white shadow-sm">
            <Building2 size={18} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold" title={name}>
              {name ?? id}
            </div>
            <div className="text-xs text-[var(--muted)]">Ingeniería de costos</div>
          </div>
        </div>
        <div className="border-y border-[var(--border)] px-5 py-3">
          <label className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-2 text-sm shadow-[var(--shadow-xs)] transition focus-within:border-[var(--primary)] focus-within:ring-2 focus-within:ring-[var(--ring)]">
            <UserRound size={16} className="shrink-0 text-[var(--muted)]" />
            <input
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={commitActorName}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
              aria-label="Nombre para cambios"
              className="min-w-0 flex-1 bg-transparent font-medium outline-none"
            />
          </label>
          <div className="mt-2 flex items-center gap-1.5 text-xs text-[var(--muted)]">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                connected ? "bg-[var(--success)]" : "bg-[var(--warning)]"
              }`}
            />
            {connected ? <Wifi size={13} /> : <WifiOff size={13} />}
            {connected ? "En vivo" : "Reconectando"}
          </div>
          {viewers.length > 0 && (
            <>
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-xs text-[var(--muted)]">{viewers.length} viendo</span>
                <div className="flex -space-x-1.5">
                  {viewers.slice(0, 5).map((viewer) => (
                    <div
                      key={viewer.client_id}
                      title={`${viewer.actor}${viewer.client_id === clientId ? " (tú)" : ""} · ${
                        viewer.location_label || "Proyecto"
                      }`}
                      className={`flex h-7 w-7 items-center justify-center rounded-full border-2 border-white text-[11px] font-semibold text-white ${
                        viewer.client_id === clientId
                          ? "bg-[var(--primary)]"
                          : "bg-[var(--accent)]"
                      }`}
                    >
                      {initials(viewer.actor)}
                    </div>
                  ))}
                  {viewers.length > 5 && (
                    <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-slate-500 text-[10px] font-semibold text-white">
                      +{viewers.length - 5}
                    </div>
                  )}
                </div>
              </div>
              {otherViewers.length > 0 && (
                <div className="mt-2 space-y-1">
                  {otherViewers.slice(0, 3).map((viewer) => (
                    <div
                      key={viewer.client_id}
                      className="truncate text-xs text-[var(--muted)]"
                      title={`${viewer.actor} · ${viewer.location_label || "Proyecto"}`}
                    >
                      {viewer.actor} · {viewer.location_label || "Proyecto"}
                    </div>
                  ))}
                  {otherViewers.length > 3 && (
                    <div className="text-xs text-[var(--muted)]">
                      +{otherViewers.length - 3} más
                    </div>
                  )}
                </div>
              )}
            </>
          )}
          {activities.length > 0 && (
            <div className="mt-3 border-t border-[var(--border)] pt-2">
              <div className="mb-1 text-xs font-medium text-[var(--foreground)]">
                Actividad reciente
              </div>
              <div className="space-y-1">
                {activities.slice(0, 3).map((activity) => (
                  <div
                    key={activity.id}
                    className="truncate text-xs text-[var(--muted)]"
                    title={`${activity.message} · ${activity.locationLabel || "Proyecto"}`}
                  >
                    {activity.message}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-6">
          {groups.map((g) => (
            <div key={g.group} className="mb-4">
              <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                {g.group}
              </div>
              {g.items.map((it) => {
                const active = it.href === pathname && !it.soon;
                // "Pronto" items reuse the presupuesto href as a placeholder,
                // so presence/activity must not attach to them or it bleeds
                // onto every disabled item when someone opens Presupuesto.
                const itemViewers = it.soon
                  ? []
                  : otherViewers.filter((viewer) => viewer.location_path === it.href);
                const itemActivities = it.soon
                  ? []
                  : activities.filter((activity) => activity.locationPath === it.href);
                return (
                  <Link
                    key={it.key}
                    href={it.soon ? pathname : it.href}
                    aria-disabled={it.soon}
                    className={`relative mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition ${
                      active
                        ? "bg-[var(--primary-soft)] font-medium text-[var(--primary)]"
                        : it.soon
                          ? "cursor-default text-slate-300"
                          : "text-slate-600 hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {active && (
                      <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-[var(--primary)]" />
                    )}
                    {it.icon}
                    <span className="flex-1">{it.label}</span>
                    {itemViewers.length > 0 && (
                      <span className="flex -space-x-1">
                        {itemViewers.slice(0, 3).map((viewer) => (
                          <span
                            key={viewer.client_id}
                            title={`${viewer.actor} · ${viewer.location_label || it.label}`}
                            className="flex h-5 w-5 items-center justify-center rounded-full border border-white bg-[var(--accent)] text-[9px] font-semibold text-white"
                          >
                            {initials(viewer.actor)}
                          </span>
                        ))}
                        {itemViewers.length > 3 && (
                          <span className="flex h-5 w-5 items-center justify-center rounded-full border border-white bg-slate-500 text-[9px] font-semibold text-white">
                            +{itemViewers.length - 3}
                          </span>
                        )}
                      </span>
                    )}
                    {itemActivities.length > 0 && (
                      <span
                        title={itemActivities[0].message}
                        className="h-2 w-2 rounded-full bg-amber-500 shadow-[0_0_0_3px_rgba(245,158,11,0.18)]"
                      />
                    )}
                    {it.soon && (
                      <span className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
                        pronto
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-x-hidden">{children}</main>
      <LiveOverlay />
    </div>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
