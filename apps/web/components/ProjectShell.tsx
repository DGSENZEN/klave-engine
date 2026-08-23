"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Books,
  Buildings,
  Calculator,
  CalendarBlank,
  CaretLeft,
  Coins,
  FileMagnifyingGlass,
  GearSix,
  List,
  ListChecks,
  MapTrifold,
  Receipt,
  SquaresFour,
  User,
  Warning,
  WifiHigh,
  WifiSlash,
  X,
} from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { ChangesPanel, ChangesTrigger, LiveToasts } from "@/components/LiveOverlay";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Avatar, IconButton } from "@/components/ui";

type Item = { key: string; label: string; icon: ReactNode; href: string };

/**
 * Three jobs, in the order they happen: read the plano, review what was
 * read, deliver the numbers. Settings sit apart, as settings do.
 */
function nav(id: string): { group: string; items: Item[] }[] {
  const b = `/proyecto/${id}`;
  return [
    {
      group: "Leer",
      items: [
        { key: "resumen", label: "Resumen", icon: <SquaresFour size={18} />, href: b },
        {
          key: "lectura",
          label: "Lectura del plano",
          icon: <FileMagnifyingGlass size={18} />,
          href: `${b}/lectura`,
        },
        {
          key: "plano",
          label: "Visor del plano",
          icon: <MapTrifold size={18} />,
          href: `${b}/plano`,
        },
      ],
    },
    {
      group: "Revisar",
      items: [
        {
          key: "revision",
          label: "Revisión",
          icon: <ListChecks size={18} />,
          href: `${b}/revision`,
        },
        {
          key: "riesgos",
          label: "Riesgos",
          icon: <Warning size={18} />,
          href: `${b}/riesgos`,
        },
      ],
    },
    {
      group: "Entregar",
      items: [
        {
          key: "presupuesto",
          label: "Presupuesto",
          icon: <Receipt size={18} />,
          href: `${b}/presupuesto`,
        },
        {
          key: "apu",
          label: "Precios unitarios",
          icon: <Calculator size={18} />,
          href: `${b}/apus`,
        },
        {
          key: "programa",
          label: "Programa y flujo",
          icon: <CalendarBlank size={18} />,
          href: `${b}/programa`,
        },
        {
          key: "parametros",
          label: "Parámetros e insumos",
          icon: <Coins size={18} />,
          href: `${b}/parametros`,
        },
      ],
    },
    {
      group: "Ajustes",
      items: [
        {
          key: "configuracion",
          label: "Configuración del proyecto",
          icon: <GearSix size={18} />,
          href: `${b}/configuracion`,
        },
        {
          key: "catalogo",
          label: "Catálogo del taller",
          icon: <Books size={18} />,
          href: "/catalogo",
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
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { timeline } = useProjectLive();

  // Change-history panel: trigger lives in the chrome; "unseen" counts the
  // entries that arrived since the panel was last closed.
  const [changesOpen, setChangesOpen] = useState(false);
  const [seenId, setSeenId] = useState(0);
  const topId = timeline[0]?.id ?? 0;
  const unseen = changesOpen ? 0 : timeline.filter((entry) => entry.id > seenId).length;
  const closeChanges = () => {
    setSeenId(topId);
    setChangesOpen(false);
  };

  // Close the mobile drawer after navigating (state adjustment during render).
  const [lastPathname, setLastPathname] = useState(pathname);
  if (lastPathname !== pathname) {
    setLastPathname(pathname);
    if (drawerOpen) setDrawerOpen(false);
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto border-r border-border bg-sidebar lg:flex">
        <SidebarContent
          id={id}
          name={name}
          unseenChanges={unseen}
          onOpenChanges={() => setChangesOpen(true)}
        />
      </aside>

      {/* Mobile top bar */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center justify-between border-b border-border bg-sidebar px-3 lg:hidden">
        <div className="flex min-w-0 items-center gap-2">
          <IconButton
            aria-label="Abrir menú de navegación"
            onClick={() => setDrawerOpen(true)}
            className="p-2"
          >
            <List size={20} weight="bold" />
          </IconButton>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-fg">
            <Buildings size={16} weight="duotone" />
          </div>
          <span className="truncate text-sm font-semibold" title={name}>
            {name ?? id}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <ChangesTrigger
            variant="topbar"
            unseen={unseen}
            onClick={() => setChangesOpen(true)}
          />
          <ThemeToggle />
        </div>
      </header>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-foreground/30"
          />
          <aside className="toast-in absolute inset-y-0 left-0 flex w-72 flex-col overflow-y-auto border-r border-border bg-sidebar shadow-lg">
            <div className="flex justify-end px-3 pt-3">
              <IconButton aria-label="Cerrar menú" onClick={() => setDrawerOpen(false)}>
                <X size={18} />
              </IconButton>
            </div>
            <SidebarContent
              id={id}
              name={name}
              unseenChanges={unseen}
              onOpenChanges={() => {
                setDrawerOpen(false);
                setChangesOpen(true);
              }}
            />
          </aside>
        </div>
      )}

      <main className="min-w-0 flex-1 overflow-x-hidden pt-14 lg:pt-0">{children}</main>
      {changesOpen && <ChangesPanel onClose={closeChanges} />}
      <LiveToasts />
    </div>
  );
}

function SidebarContent({
  id,
  name,
  unseenChanges,
  onOpenChanges,
}: {
  id: string;
  name?: string;
  unseenChanges: number;
  onOpenChanges: () => void;
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
    <>
      <Link
        href="/"
        className="flex items-center gap-1.5 px-5 pt-4 pb-3 text-xs font-medium text-muted transition hover:text-foreground"
      >
        <CaretLeft size={13} weight="bold" /> Proyectos
      </Link>
      <div className="flex items-center gap-2 px-5 pb-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-fg">
          <Buildings size={18} weight="duotone" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" title={name}>
            {name ?? id}
          </div>
          <div className="text-xs text-muted">Ingeniería de costos</div>
        </div>
      </div>
      <div className="border-y border-border px-5 py-3">
        <label className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm transition focus-within:border-border-strong focus-within:ring-2 focus-within:ring-ring">
          <User size={16} className="shrink-0 text-muted" />
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
        <div className="mt-2 flex items-center gap-1.5 text-xs text-muted">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              connected ? "bg-success" : "bg-warning"
            }`}
          />
          {connected ? <WifiHigh size={13} weight="bold" /> : <WifiSlash size={13} weight="bold" />}
          {connected ? "En vivo" : "Reconectando"}
        </div>
        {viewers.length > 0 && (
          <>
            <div className="mt-3 flex items-center justify-between gap-2">
              <span className="text-xs text-muted">{viewers.length} viendo</span>
              <div className="flex -space-x-1.5">
                {viewers.slice(0, 5).map((viewer) => (
                  <Avatar
                    key={viewer.client_id}
                    name={viewer.actor}
                    self={viewer.client_id === clientId}
                    title={`${viewer.actor}${viewer.client_id === clientId ? " (tú)" : ""} · ${
                      viewer.location_label || "Proyecto"
                    }`}
                  />
                ))}
                {viewers.length > 5 && (
                  <span className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-surface bg-faint text-[10px] font-semibold text-primary-fg">
                    +{viewers.length - 5}
                  </span>
                )}
              </div>
            </div>
            {otherViewers.length > 0 && (
              <div className="mt-2 space-y-1">
                {otherViewers.slice(0, 3).map((viewer) => (
                  <div
                    key={viewer.client_id}
                    className="truncate text-xs text-muted"
                    title={`${viewer.actor} · ${viewer.location_label || "Proyecto"}`}
                  >
                    {viewer.actor} · {viewer.location_label || "Proyecto"}
                  </div>
                ))}
                {otherViewers.length > 3 && (
                  <div className="text-xs text-muted">+{otherViewers.length - 3} más</div>
                )}
              </div>
            )}
          </>
        )}
        {activities.length > 0 && (
          <div className="mt-3 border-t border-border pt-2">
            <div className="mb-1 text-xs font-medium text-foreground">Actividad reciente</div>
            <div className="space-y-1">
              {activities.slice(0, 3).map((activity) => (
                <div
                  key={activity.id}
                  className="truncate text-xs text-muted"
                  title={`${activity.message} · ${activity.locationLabel || "Proyecto"}`}
                >
                  {activity.message}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <nav className="flex-1 px-3 pb-4 pt-2">
        {groups.map((g) => (
          <div key={g.group} className="mb-4">
            <div className="microlabel px-2 pb-1.5">{g.group}</div>
            {g.items.map((it) => {
              const active =
                it.href === pathname ||
                (it.key === "programa" && pathname === it.href.replace(/\/programa$/, "/flujo"));
              const itemViewers = otherViewers.filter(
                (viewer) => viewer.location_path === it.href,
              );
              const itemActivities = activities.filter(
                (activity) => activity.locationPath === it.href,
              );
              return (
                <Link
                  key={it.key}
                  href={it.href}
                  className={`relative mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                    active
                      ? "bg-surface-2 font-medium text-foreground"
                      : "text-muted hover:bg-surface-2/70 hover:text-foreground"
                  }`}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-4.5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent" />
                  )}
                  {it.icon}
                  <span className="flex-1">{it.label}</span>
                  {itemViewers.length > 0 && (
                    <span className="flex -space-x-1">
                      {itemViewers.slice(0, 3).map((viewer) => (
                        <Avatar
                          key={viewer.client_id}
                          name={viewer.actor}
                          size="xs"
                          title={`${viewer.actor} · ${viewer.location_label || it.label}`}
                        />
                      ))}
                      {itemViewers.length > 3 && (
                        <span className="flex h-5 w-5 items-center justify-center rounded-full border border-surface bg-faint text-[9px] font-semibold text-primary-fg">
                          +{itemViewers.length - 3}
                        </span>
                      )}
                    </span>
                  )}
                  {itemActivities.length > 0 && (
                    <span
                      title={itemActivities[0].message}
                      className="h-2 w-2 rounded-full bg-warning shadow-[0_0_0_3px_var(--warning-soft)]"
                    />
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="flex items-center justify-between border-t border-border px-3 py-2.5">
        <ChangesTrigger variant="sidebar" unseen={unseenChanges} onClick={onOpenChanges} />
        <ThemeToggle />
      </div>
    </>
  );
}
