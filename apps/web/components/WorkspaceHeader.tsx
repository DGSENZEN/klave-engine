"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Books, Buildings, FolderOpen, UsersThree } from "@phosphor-icons/react";
import { peekBrowserActor } from "@/lib/collab";
import { fetchAuthStatus } from "@/lib/session";
import { Avatar } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

type Section = "proyectos" | "catalogo" | "equipo" | "cuenta";

/** One header pattern for every workspace-level screen: same places, same
 * order, everywhere — navigation should never need re-learning per page. */
export function WorkspaceHeader({ active }: { active: Section }) {
  const [actorName, setActorName] = useState("");
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let mounted = true;
    fetchAuthStatus().then((status) => {
      if (!mounted) return;
      setActorName(status.user?.name || peekBrowserActor());
      setAvatarSrc(status.user?.picture ?? null);
      setIsAdmin(status.user?.role === "admin");
    });
    return () => {
      mounted = false;
    };
  }, []);

  const linkClass = (section: Section) =>
    `inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium transition-colors ${
      active === section
        ? "bg-surface-2 text-foreground"
        : "text-muted hover:bg-surface-2/70 hover:text-foreground"
    }`;

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-5">
        <div className="flex min-w-0 items-center gap-4">
          <Link href="/" className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-fg">
              <Buildings size={17} weight="duotone" />
            </span>
            <span className="font-display text-[1.05rem] font-semibold tracking-tight">
              Klave
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            <Link href="/" className={linkClass("proyectos")}>
              <FolderOpen size={15} weight="duotone" />
              <span className="hidden sm:inline">Proyectos</span>
            </Link>
            <Link href="/catalogo" className={linkClass("catalogo")}>
              <Books size={15} weight="duotone" />
              <span className="hidden sm:inline">Catálogo</span>
            </Link>
            {isAdmin && (
              <Link href="/equipo" className={linkClass("equipo")}>
                <UsersThree size={15} weight="duotone" />
                <span className="hidden sm:inline">Equipo</span>
              </Link>
            )}
          </nav>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {actorName && (
            <Link
              href="/cuenta"
              title="Tu cuenta"
              className="flex items-center gap-2 rounded-full border border-border bg-surface py-1 pl-1 pr-3 text-sm font-medium transition-colors hover:bg-surface-2"
            >
              <Avatar name={actorName} src={avatarSrc} self size="sm" />
              <span className="hidden max-w-32 truncate md:inline">{actorName}</span>
            </Link>
          )}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
