"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Buildings,
  CaretDown,
  CaretLeft,
  Gauge,
  GearSix,
  List,
  SquaresFour,
  User,
  WifiHigh,
  WifiSlash,
  X,
} from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { ChangesPanel, ChangesTrigger, LiveToasts } from "@/components/LiveOverlay";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Avatar, IconButton } from "@/components/ui";
import { entryHref, nodeForPath, NODE_NAV, type NodeNav } from "@/lib/nodeNav";

/**
 * La navegación vive en los nodos. En el tablero (la raíz del proyecto) no
 * hay barra lateral: el lienzo cubre todo y arriba queda una barra delgada.
 * En las subpantallas la barra lateral es contextual — el nodo donde estás
 * parado, con sus entradas, más Tablero/Resumen y Ajustes. El mapa completo
 * vive en el propio tablero (y en el cajón móvil).
 */
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
  const base = `/proyecto/${id}`;
  const onTablero = pathname === base;
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
    <div className={`flex min-h-screen ${onTablero ? "flex-col" : ""}`}>
      {onTablero ? (
        <TableroTopBar
          id={id}
          name={name}
          unseenChanges={unseen}
          onOpenChanges={() => setChangesOpen(true)}
        />
      ) : (
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col overflow-y-auto border-r border-border bg-sidebar lg:flex">
          <SidebarContent
            id={id}
            name={name}
            unseenChanges={unseen}
            onOpenChanges={() => setChangesOpen(true)}
          />
        </aside>
      )}

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
          <span className="truncate text-sm font-semibold">{name ?? id}</span>
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

      {/* Mobile drawer: el mapa completo, nodo por nodo */}
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
              allNodes
              unseenChanges={unseen}
              onOpenChanges={() => {
                setDrawerOpen(false);
                setChangesOpen(true);
              }}
            />
          </aside>
        </div>
      )}

      <main
        className={`min-w-0 flex-1 overflow-x-hidden pt-14 lg:pt-0 ${
          onTablero ? "flex flex-col" : ""
        }`}
      >
        {!onTablero && <Crumbs id={id} name={name} />}
        {children}
      </main>
      {changesOpen && <ChangesPanel onClose={closeChanges} />}
      <LiveToasts />
    </div>
  );
}

/**
 * La miga de pan de las subpantallas: proyecto / nodo / entrada. El nombre
 * regresa al tablero (nunca más el viaje hasta la lista de proyectos), el
 * nodo abre el mapa completo y la entrada salta entre hermanas — moverse
 * entre menús es un clic, no una expedición.
 */
function Crumbs({ id, name }: { id: string; name?: string }) {
  const pathname = usePathname();
  const base = `/proyecto/${id}`;
  const node = nodeForPath(base, pathname);
  const entry = node?.entries.find((candidate) => {
    const targets = [candidate.href, ...(candidate.also ?? [])].map((href) =>
      href === "/catalogo" ? href : `${base}${href}`,
    );
    return targets.includes(pathname);
  });
  const pageLabel =
    pathname === `${base}/resumen`
      ? "Resumen"
      : pathname === `${base}/configuracion`
        ? "Configuración"
        : null;
  const [openMenu, setOpenMenu] = useState<"nodo" | "entrada" | null>(null);
  const { connected } = useProjectLive();

  // Navegar cierra el menú (ajuste de estado durante el render, como el cajón).
  const [lastPathname, setLastPathname] = useState(pathname);
  if (lastPathname !== pathname) {
    setLastPathname(pathname);
    if (openMenu) setOpenMenu(null);
  }

  function crumbButton(label: ReactNode, which: "nodo" | "entrada") {
    return (
      <button
        type="button"
        onClick={() => setOpenMenu(openMenu === which ? null : which)}
        aria-expanded={openMenu === which}
        className="flex items-center gap-1 rounded-lg px-2 py-1 text-sm transition-colors hover:bg-surface-2"
      >
        {label}
        <CaretDown size={11} className="text-faint" />
      </button>
    );
  }

  const mapa = (
    <div className="max-h-[70vh] w-64 overflow-y-auto p-1.5">
      <Link
        href={base}
        className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <SquaresFour size={16} /> Tablero
      </Link>
      <Link
        href={`${base}/resumen`}
        className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <Gauge size={16} /> Resumen
      </Link>
      {NODE_NAV.map((group) => (
        <div key={group.key} className="mt-1.5">
          <div className="microlabel px-2.5 pb-1">{group.label}</div>
          {group.entries.map((item) => (
            <Link
              key={item.key}
              href={entryHref(base, item)}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              {item.icon}
              {item.label}
            </Link>
          ))}
        </div>
      ))}
      <div className="mt-1.5 border-t border-border pt-1.5">
        <Link
          href={`${base}/configuracion`}
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <GearSix size={16} /> Configuración del proyecto
        </Link>
      </div>
    </div>
  );

  return (
    <div className="sticky top-0 z-30 hidden h-11 items-center justify-between border-b border-border bg-background/85 px-4 backdrop-blur lg:flex">
      <div className="relative flex min-w-0 items-center gap-0.5">
        <Link
          href={base}
          className="flex items-center gap-1.5 truncate rounded-lg px-2 py-1 text-sm font-medium transition-colors hover:bg-surface-2"
        >
          <SquaresFour size={14} className="text-muted" />
          {name ?? id}
        </Link>
        <span className="text-faint">/</span>
        {crumbButton(node?.label ?? pageLabel ?? "…", "nodo")}
        {node && entry && (
          <>
            <span className="text-faint">/</span>
            {crumbButton(<span className="font-medium">{entry.label}</span>, "entrada")}
          </>
        )}
        {openMenu && (
          <>
            <button
              type="button"
              aria-label="Cerrar menú"
              onClick={() => setOpenMenu(null)}
              className="fixed inset-0 z-40 cursor-default"
            />
            <div className="menu-pop absolute left-0 top-full z-50 mt-1 origin-top rounded-xl border border-border-strong bg-surface shadow-xl">
              {openMenu === "nodo" || !node ? (
                mapa
              ) : (
                <div className="w-56 p-1.5">
                  {node.entries.map((item) => (
                    <Link
                      key={item.key}
                      href={entryHref(base, item)}
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
                    >
                      {item.icon}
                      {item.label}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          connected ? "bg-success" : "bg-warning"
        }`}
        aria-label={connected ? "En vivo" : "Reconectando"}
      />
    </div>
  );
}

/** La barra delgada sobre el lienzo: identidad a la izquierda, en vivo y
 * ajustes a la derecha. */
function TableroTopBar({
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
  const { connected, clientId, viewers } = useProjectLive();
  const otherViewers = viewers.filter((viewer) => viewer.client_id !== clientId);
  return (
    <header className="sticky top-0 z-30 hidden h-12 shrink-0 items-center justify-between border-b border-border bg-sidebar px-4 lg:flex">
      <div className="flex min-w-0 items-center gap-3">
        <Link
          href="/"
          className="flex items-center gap-1 text-xs font-medium text-muted transition hover:text-foreground"
        >
          <CaretLeft size={13} weight="bold" /> Proyectos
        </Link>
        <span className="h-4 w-px bg-border" />
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-fg">
          <Buildings size={14} weight="duotone" />
        </div>
        <span className="truncate text-sm font-semibold">{name ?? id}</span>
        <Link
          href={`/proyecto/${id}/resumen`}
          className="ml-2 flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted transition hover:bg-surface-2 hover:text-foreground"
        >
          <Gauge size={14} /> Resumen
        </Link>
      </div>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs text-muted">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              connected ? "bg-success" : "bg-warning"
            }`}
          />
          {connected ? (
            <WifiHigh size={13} weight="bold" />
          ) : (
            <WifiSlash size={13} weight="bold" />
          )}
        </span>
        {otherViewers.length > 0 && (
          <span className="flex -space-x-1.5">
            {otherViewers.slice(0, 4).map((viewer) => (
              <Avatar key={viewer.client_id} name={viewer.actor} size="xs" />
            ))}
          </span>
        )}
        <ChangesTrigger variant="topbar" unseen={unseenChanges} onClick={onOpenChanges} />
        <Link
          href={`/proyecto/${id}/configuracion`}
          aria-label="Configuración del proyecto"
          className="rounded-lg p-1.5 text-muted transition hover:bg-surface-2 hover:text-foreground"
        >
          <GearSix size={16} />
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}

function SidebarContent({
  id,
  name,
  allNodes = false,
  unseenChanges,
  onOpenChanges,
}: {
  id: string;
  name?: string;
  /** true en el cajón móvil: el mapa completo, no solo el nodo actual. */
  allNodes?: boolean;
  unseenChanges: number;
  onOpenChanges: () => void;
}) {
  const pathname = usePathname();
  const base = `/proyecto/${id}`;
  const currentNode = nodeForPath(base, pathname);
  const nodes: NodeNav[] = allNodes ? NODE_NAV : currentNode ? [currentNode] : [];
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

  const pinned = [
    { key: "tablero", label: "Tablero", icon: <SquaresFour size={18} />, href: base },
    { key: "resumen", label: "Resumen", icon: <Gauge size={18} />, href: `${base}/resumen` },
  ];

  function itemLink(item: {
    key: string;
    label: string;
    icon: ReactNode;
    href: string;
    also?: string[];
  }) {
    const active = item.href === pathname || (item.also ?? []).includes(pathname);
    const itemViewers = otherViewers.filter((viewer) => viewer.location_path === item.href);
    const itemActivities = activities.filter(
      (activity) => activity.locationPath === item.href,
    );
    return (
      <Link
        key={item.key}
        href={item.href}
        className={`relative mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors ${
          active
            ? "bg-surface-2 font-medium text-foreground"
            : "text-muted hover:bg-surface-2/70 hover:text-foreground"
        }`}
      >
        {active && (
          <span className="absolute left-0 top-1/2 h-4.5 w-[3px] -translate-y-1/2 rounded-r-full bg-accent" />
        )}
        {item.icon}
        <span className="flex-1">{item.label}</span>
        {itemViewers.length > 0 && (
          <span className="flex -space-x-1">
            {itemViewers.slice(0, 3).map((viewer) => (
              <Avatar key={viewer.client_id} name={viewer.actor} size="xs" />
            ))}
          </span>
        )}
        {itemActivities.length > 0 && (
          <span className="h-2 w-2 rounded-full bg-warning shadow-[0_0_0_3px_var(--warning-soft)]" />
        )}
      </Link>
    );
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
          <div className="truncate text-sm font-semibold">{name ?? id}</div>
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
        {otherViewers.length > 0 && (
          <div className="mt-3 flex items-center justify-between gap-2">
            <span className="text-xs text-muted">{viewers.length} viendo</span>
            <div className="flex -space-x-1.5">
              {otherViewers.slice(0, 5).map((viewer) => (
                <Avatar key={viewer.client_id} name={viewer.actor} />
              ))}
            </div>
          </div>
        )}
      </div>
      <nav className="flex-1 px-3 pb-4 pt-2">
        <div className="mb-4">{pinned.map((item) => itemLink(item))}</div>
        {nodes.map((node) => (
          <div key={node.key} className="mb-4">
            <div className="microlabel px-2 pb-1.5">{node.label}</div>
            {node.entries.map((entry) =>
              itemLink({
                key: entry.key,
                label: entry.label,
                icon: entry.icon,
                href: entryHref(base, entry),
                also: (entry.also ?? []).map((href) => `${base}${href}`),
              }),
            )}
          </div>
        ))}
        <div className="mb-4">
          <div className="microlabel px-2 pb-1.5">Ajustes</div>
          {itemLink({
            key: "configuracion",
            label: "Configuración del proyecto",
            icon: <GearSix size={18} />,
            href: `${base}/configuracion`,
          })}
        </div>
      </nav>
      <div className="flex items-center justify-between border-t border-border px-3 py-2.5">
        <ChangesTrigger variant="sidebar" unseen={unseenChanges} onClick={onOpenChanges} />
        <ThemeToggle />
      </div>
    </>
  );
}
