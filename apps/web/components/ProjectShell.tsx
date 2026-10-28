"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import {
  Buildings,
  CaretDown,
  Gauge,
  GearSix,
  LockSimple,
  MagnifyingGlass,
  SquaresFour,
  User,
  WifiHigh,
  WifiSlash,
} from "@phosphor-icons/react";
import { useProjectLive } from "@/components/ProjectLive";
import { CommandPalette, openCommandPalette } from "@/components/CommandPalette";
import { ChangesPanel, ChangesTrigger, LiveToasts } from "@/components/LiveOverlay";
import { ThemeToggle } from "@/components/ThemeToggle";
import { BotonRecorrido } from "@/components/recorrido/MenuRecorrido";
import { Avatar, iconButtonClasses, PRESS } from "@/components/ui";
import { ROUTE_GUARDED_NODES } from "@/lib/gates";
import { useTablero } from "@/lib/useProjectReport";
import { entryHref, nodeForPath, NODE_NAV, type NodeNav } from "@/lib/nodeNav";

/**
 * Sin barra lateral: el proyecto entero vive bajo UNA barra delgada. Su
 * centro es la franja del proceso — los seis nodos en orden, siempre a un
 * clic, con lo que pide atención marcado — y debajo, las entradas del nodo
 * donde estás. El tablero sigue siendo el mapa; la franja, el camino.
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
  const hasNodeBar = (nodeForPath(base, pathname)?.entries.length ?? 0) >= 2;
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
      <NodeWorkspaceBar id={id} />
      <main
        className={`min-w-0 flex-1 ${onTablero ? "flex flex-col" : "overflow-x-clip pb-24"}`}
        // Sticky table headers sit just under the bars above (48 + 40 px).
        style={{ "--chrome-h": hasNodeBar ? "88px" : "48px" } as CSSProperties}
      >
        {children}
      </main>
      {changesOpen && <ChangesPanel onClose={closeChanges} />}
      <CommandPalette projectId={id} />
      <LiveToasts />
    </div>
  );
}

/**
 * La barra del nodo: cuando la pantalla pertenece a un nodo con varias
 * entradas, sus hermanas quedan SIEMPRE visibles como pestañas — moverse
 * dentro de Planos o Revisión es un clic a la vista, nunca un menú.
 */
function NodeWorkspaceBar({ id }: { id: string }) {
  const pathname = usePathname();
  const base = `/proyecto/${id}`;
  const node = nodeForPath(base, pathname);
  if (!node || node.entries.length < 2) return null;
  return (
    <nav
      aria-label={`Pantallas de ${node.label}`}
      className="sticky top-12 z-30 flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-sidebar px-3 [scrollbar-width:none] sm:px-4"
    >
      {node.entries.map((item) => {
        const targets = [item.href, ...(item.also ?? [])].map((href) =>
          href === "/catalogo" ? href : `${base}${href}`,
        );
        const active = targets.includes(pathname);
        return (
          <Link
            key={item.key}
            href={entryHref(base, item)}
            aria-current={active ? "page" : undefined}
            className={`relative flex h-full shrink-0 items-center gap-1.5 px-2.5 text-sm transition-colors ${
              active ? "font-medium text-foreground" : "text-muted hover:text-foreground"
            }`}
          >
            <item.glyph size={14} className={active ? "text-foreground" : "text-faint"} />
            {item.label}
            {active && (
              <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-t-full bg-accent" />
            )}
          </Link>
        );
      })}
    </nav>
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
  const pageLabel =
    pathname === `${base}/resumen`
      ? "Resumen"
      : pathname === `${base}/configuracion`
        ? "Configuración"
        : null;
  const [openMenu, setOpenMenu] = useState<"nodo" | "yo" | null>(null);
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

  // El índice completo (tablero, resumen, cada entrada, configuración) cuelga
  // de la flecha junto al nombre. En el teléfono, donde la franja no cabe, la
  // flecha lleva además el nombre del nodo donde estás.
  function screensMenu(menu: ReactNode) {
    const isOpen = openMenu === "nodo";
    const here = onTablero ? null : (node?.label ?? pageLabel);
    return (
      <span className={`relative ${openMenu ? "z-40" : ""}`}>
        <button
          type="button"
          onClick={() => setOpenMenu(isOpen ? null : "nodo")}
          aria-expanded={isOpen}
          aria-label="Todas las pantallas del proyecto"
          data-tip="Todas las pantallas"
          className={`flex h-8 min-w-8 items-center justify-center gap-1 rounded-md px-1.5 text-sm text-muted ${PRESS} hover:bg-surface-2 hover:text-foreground aria-expanded:bg-surface-2 aria-expanded:text-foreground`}
        >
          {here && (
            <span className="max-w-32 truncate text-foreground md:hidden">
              <span className="mr-1 text-faint">/</span>
              {here}
            </span>
          )}
          <CaretDown size={12} className="shrink-0" />
        </button>
        {isOpen && (
          <div className="menu-pop absolute left-0 top-full z-50 mt-1 origin-top-left rounded-xl border border-border-strong bg-surface shadow-xl">
            {menu}
          </div>
        )}
      </span>
    );
  }

  const mapa = (
    <div className="max-h-[70vh] w-64 overflow-y-auto p-1.5">
      <Link
        href={base}
        className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <SquaresFour /> Tablero
      </Link>
      <Link
        href={`${base}/resumen`}
        className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <Gauge /> Resumen
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
              <item.glyph />
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
          <GearSix /> Configuración del proyecto
        </Link>
      </div>
    </div>
  );

  return (
    <header className="sticky top-0 z-40 flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border bg-sidebar px-3 sm:px-4">
      <div className="relative flex min-w-0 items-center gap-1">
        <Link
          href="/"
          aria-label="Todos los proyectos"
          data-tip="Todos los proyectos"
          className={`mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-fg shadow-btn-ink ${PRESS} hover:bg-primary-hover`}
        >
          <Buildings size={14} />
        </Link>
        <Link
          href={base}
          aria-current={onTablero ? "page" : undefined}
          title={name ?? id}
          className={`flex h-8 min-w-0 items-center truncate rounded-md px-2 text-sm font-medium transition-colors hover:bg-surface-2 ${
            onTablero ? "" : "max-w-36 md:max-w-44 xl:max-w-64"
          }`}
        >
          <span className="truncate">{name ?? id}</span>
        </Link>
        {screensMenu(mapa)}
        {openMenu === "nodo" && (
          <button
            type="button"
            aria-label="Cerrar menú"
            onClick={() => setOpenMenu(null)}
            className="fixed inset-0 z-30 cursor-default"
          />
        )}
        <span aria-hidden className="mx-2 hidden h-5 w-px bg-border md:block" />
        <ProcessStrip id={id} active={node?.key} />
      </div>
      <div className="relative flex shrink-0 items-center gap-0.5">
        {otherViewers.length > 0 && (
          <span className="mr-1.5 hidden -space-x-1.5 sm:flex">
            {otherViewers.slice(0, 4).map((viewer) => (
              <Avatar key={viewer.client_id} name={viewer.actor} size="xs" />
            ))}
          </span>
        )}
        <button
          type="button"
          onClick={openCommandPalette}
          data-tour="shell.paleta"
          aria-label="Ir a cualquier pantalla (⌘K)"
          data-tip="Ir a… ⌘K"
          className={iconButtonClasses("md", "max-sm:hidden")}
        >
          <MagnifyingGlass />
        </button>
        <button
          type="button"
          onClick={() => setOpenMenu(openMenu === "yo" ? null : "yo")}
          aria-label="Tu nombre y conexión"
          data-tip={connected ? "Tu nombre · en vivo" : "Tu nombre · reconectando"}
          aria-expanded={openMenu === "yo"}
          className={iconButtonClasses()}
        >
          <User />
          <span
            className={`absolute right-1.5 top-1.5 inline-block h-1.5 w-1.5 rounded-full ring-2 ring-sidebar ${
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
            <div className="menu-pop absolute right-0 top-full z-50 mt-1 w-60 origin-top-right rounded-xl border border-border-strong bg-surface p-3 shadow-xl">
              <label className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-2 text-sm transition focus-within:border-border-strong focus-within:ring-2 focus-within:ring-ring">
                <User className="shrink-0 text-muted" />
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
                {connected ? <WifiHigh size={14} /> : <WifiSlash size={14} />}
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
          data-tip="Configuración"
          aria-current={pathname === `${base}/configuracion` ? "page" : undefined}
          className={iconButtonClasses(
            "md",
            "max-sm:hidden aria-[current=page]:bg-surface-2 aria-[current=page]:text-foreground",
          )}
        >
          <GearSix />
        </Link>
        <span className="contents max-sm:hidden">
          <BotonRecorrido ancla="shell.ayuda" />
        </span>
        <ThemeToggle />
      </div>
    </header>
  );
}

/**
 * La franja del proceso: los seis nodos en el orden del trabajo, cada uno a
 * un clic de su pantalla principal. Solo se marca lo que pide algo — un punto
 * para «atención», un candado para lo cerrado; «en orden» no hace ruido.
 * Debajo de xl los nodos inactivos quedan en su glifo (con su nombre al
 * pasar el cursor); el activo siempre se nombra.
 */
function ProcessStrip({ id, active }: { id: string; active: NodeNav["key"] | undefined }) {
  const base = `/proyecto/${id}`;
  const { tablero } = useTablero(id);
  return (
    <nav aria-label="Proceso del proyecto" className="hidden min-w-0 md:block">
      <ol className="flex items-center">
        {NODE_NAV.map((item, index) => {
          const isActive = item.key === active;
          const estado = tablero?.nodes?.[item.key]?.estado;
          const locked = tablero
            ? ROUTE_GUARDED_NODES.includes(item.key) && !tablero.gates?.[item.key]
            : false;
          const atencion = !locked && estado === "atencion";
          const note = locked ? "con candado" : atencion ? "pide atención" : null;
          return (
            <li key={item.key} className="flex items-center">
              {index > 0 && <span aria-hidden className="h-px w-1.5 bg-border-strong" />}
              <Link
                href={entryHref(base, item.entries[0])}
                aria-current={isActive ? "page" : undefined}
                data-tip={isActive ? undefined : note ? `${item.label} · ${note}` : item.label}
                className={`relative flex h-8 items-center gap-1.5 rounded-md px-2 text-[13px] xl:after:hidden ${PRESS} ${
                  isActive
                    ? "bg-surface-2 font-medium text-foreground"
                    : "text-muted hover:bg-surface-2 hover:text-foreground"
                }`}
              >
                <item.glyph
                  weight={isActive ? "duotone" : "bold"}
                  className={isActive ? "text-accent" : undefined}
                />
                <span className={isActive ? "whitespace-nowrap" : "hidden whitespace-nowrap xl:inline"}>
                  {item.label}
                </span>
                {locked && <LockSimple size={12} weight="fill" className="text-faint" />}
                {atencion && (
                  <span
                    className={`h-1.5 w-1.5 rounded-full bg-warning ${
                      isActive ? "" : "max-xl:absolute max-xl:right-1 max-xl:top-1.5"
                    }`}
                  />
                )}
                {note && <span className="sr-only">({note})</span>}
              </Link>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
