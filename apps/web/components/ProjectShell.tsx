"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import {
  Buildings,
  CaretDown,
  Gauge,
  GearSix,
  SquaresFour,
  User,
  WifiHigh,
  WifiSlash,
} from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { ChangesPanel, ChangesTrigger, LiveToasts } from "@/components/LiveOverlay";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Avatar } from "@/components/ui";
import { entryHref, nodeForPath, NODE_NAV } from "@/lib/nodeNav";

/**
 * Sin barra lateral: el proyecto entero vive bajo UNA barra delgada. La
 * miga de pan (proyecto / nodo / entrada) es la navegación — el nombre
 * regresa al tablero, el nodo abre el mapa completo y la entrada salta
 * entre hermanas. El tablero es el mapa; la barra solo el camino de vuelta.
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

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar
        id={id}
        name={name}
        unseenChanges={unseen}
        onOpenChanges={() => setChangesOpen(true)}
      />
      <main className={`min-w-0 flex-1 ${onTablero ? "flex flex-col" : "overflow-x-hidden"}`}>
        {children}
      </main>
      {changesOpen && <ChangesPanel onClose={closeChanges} />}
      <LiveToasts />
    </div>
  );
}

/**
 * La única barra: identidad y miga a la izquierda; presencia, nombre,
 * cambios, configuración y tema a la derecha. En el tablero la miga es
 * solo el nombre; adentro crece a proyecto / nodo / entrada.
 */
function TopBar({
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
  const base = `/proyecto/${id}`;
  const onTablero = pathname === base;
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
  const [openMenu, setOpenMenu] = useState<"nodo" | "entrada" | "yo" | null>(null);
  const { connected, clientId, viewers, actorName, setActorName } = useProjectLive();
  const [nameDraft, setNameDraft] = useState(actorName);
  const otherViewers = viewers.filter((viewer) => viewer.client_id !== clientId);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setNameDraft(actorName);
    }, 0);
    return () => window.clearTimeout(handle);
  }, [actorName]);

  // Navegar cierra los menús (ajuste de estado durante el render).
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
        className="flex max-w-40 items-center gap-1 truncate rounded-lg px-2 py-1 text-sm transition-colors hover:bg-surface-2 sm:max-w-none"
      >
        {label}
        <CaretDown size={11} className="shrink-0 text-faint" />
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
    <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center justify-between border-b border-border bg-sidebar px-3 sm:px-4">
      <div className="relative flex min-w-0 items-center gap-0.5">
        <Link
          href="/"
          aria-label="Todos los proyectos"
          className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-fg transition hover:brightness-110"
        >
          <Buildings size={14} weight="duotone" />
        </Link>
        <Link
          href={base}
          className={`flex min-w-0 items-center gap-1.5 truncate rounded-lg px-2 py-1 text-sm font-medium transition-colors hover:bg-surface-2 ${
            onTablero ? "" : "max-w-36 sm:max-w-none"
          }`}
        >
          {name ?? id}
        </Link>
        {!onTablero && (
          <>
            <span className="text-faint">/</span>
            {crumbButton(node?.label ?? pageLabel ?? "…", "nodo")}
            {node && entry && (
              <>
                <span className="hidden text-faint sm:inline">/</span>
                <span className="hidden sm:contents">
                  {crumbButton(<span className="font-medium">{entry.label}</span>, "entrada")}
                </span>
              </>
            )}
          </>
        )}
        {(openMenu === "nodo" || openMenu === "entrada") && (
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
      <div className="relative flex shrink-0 items-center gap-1">
        {otherViewers.length > 0 && (
          <span className="mr-1 hidden -space-x-1.5 sm:flex">
            {otherViewers.slice(0, 4).map((viewer) => (
              <Avatar key={viewer.client_id} name={viewer.actor} size="xs" />
            ))}
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpenMenu(openMenu === "yo" ? null : "yo")}
          aria-label="Tu nombre y conexión"
          aria-expanded={openMenu === "yo"}
          className="relative rounded-md p-2 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <User size={18} weight="bold" />
          <span
            className={`absolute right-1 top-1 inline-block h-1.5 w-1.5 rounded-full ${
              connected ? "bg-success" : "bg-warning"
            }`}
          />
        </button>
        {openMenu === "yo" && (
          <>
            <button
              type="button"
              aria-label="Cerrar"
              onClick={() => setOpenMenu(null)}
              className="fixed inset-0 z-40 cursor-default"
            />
            <div className="menu-pop absolute right-0 top-full z-50 mt-1 w-60 origin-top rounded-xl border border-border-strong bg-surface p-3 shadow-xl">
              <label className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm transition focus-within:border-border-strong focus-within:ring-2 focus-within:ring-ring">
                <User size={16} className="shrink-0 text-muted" />
                <input
                  value={nameDraft}
                  onChange={(e) => setNameDraft(e.target.value)}
                  onBlur={() => setActorName(nameDraft)}
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
                {connected ? (
                  <WifiHigh size={13} weight="bold" />
                ) : (
                  <WifiSlash size={13} weight="bold" />
                )}
                {connected ? "En vivo" : "Reconectando"}
                {viewers.length > 1 && <span>· {viewers.length} viendo</span>}
              </div>
            </div>
          </>
        )}
        <ChangesTrigger variant="topbar" unseen={unseenChanges} onClick={onOpenChanges} />
        <Link
          href={`${base}/configuracion`}
          aria-label="Configuración del proyecto"
          className="rounded-md p-2 text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <GearSix size={18} />
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}
