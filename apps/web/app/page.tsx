"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Archive,
  ArrowCounterClockwise,
  ArrowRight,
  Books,
  Buildings,
  CircleNotch,
  CloudArrowUp,
  FileText,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Stack,
  Trash,
  UserSwitch,
} from "@phosphor-icons/react";
import {
  ApiError,
  listProjects,
  patchProject,
  removeProject,
  uploadProject,
  type ProjectSummary,
} from "@/lib/api";
import { eventsUrl, getBrowserActor, parseProjectEvent, peekBrowserActor } from "@/lib/collab";
import { isProfileComplete } from "@/lib/identity";
import { fetchAuthStatus } from "@/lib/session";
import {
  Avatar,
  Badge,
  Button,
  buttonClasses,
  Callout,
  EmptyState,
  Input,
  Skeleton,
  type BadgeTone,
} from "@/components/ui";
import { KebabMenu, MenuItem } from "@/components/Menu";
import { HowItWorks } from "@/components/HowItWorks";
import { ThemeToggle } from "@/components/ThemeToggle";

const STATUS_TONE: Record<string, BadgeTone> = {
  processed: "success",
  running: "accent",
  queued: "accent",
  failed: "warning",
};

const STATUS_LABELS: Record<string, string> = {
  processed: "Procesado",
  running: "Procesando",
  queued: "En cola",
  failed: "Con errores",
};

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [ready, setReady] = useState(false);
  const [actorName, setActorName] = useState("");
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  // First run goes through /bienvenida to establish the workspace identity.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      if (!isProfileComplete()) {
        router.replace("/bienvenida");
        return;
      }
      setActorName(peekBrowserActor());
      setReady(true);
    }, 0);
    return () => window.clearTimeout(handle);
  }, [router]);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (active) setAvatarSrc(status.user?.picture ?? null);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    function refresh() {
      listProjects()
        .then((items) => {
          if (active) setProjects(items);
        })
        .catch(() => {
          if (active) setProjects([]);
        });
    }
    refresh();
    const source = new EventSource(eventsUrl());
    source.onmessage = (message) => {
      const event = parseProjectEvent(message);
      if (
        event?.type === "project_created" ||
        event?.type === "project_updated" ||
        event?.type === "project_removed" ||
        event?.type === "job_updated" ||
        event?.type === "run_published"
      ) {
        refresh();
      }
    };
    return () => {
      active = false;
      source.close();
    };
  }, []);

  async function handleFiles(list: FileList | File[]) {
    const files = [...list].filter((f) => /\.(dwg|dxf)$/i.test(f.name));
    if (files.length === 0) {
      setError("Formato no soportado. Sube archivos .dwg o .dxf.");
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const { project_id } = await uploadProject(files, getBrowserActor());
      router.push(`/proyecto/${project_id}`);
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      setError(detail || "No se pudo subir el archivo. Revisa que el servidor esté activo.");
      setUploading(false);
    }
  }

  const filtered = useMemo(() => {
    if (!projects) return null;
    const q = query.trim().toLowerCase();
    return projects.filter((p) => {
      if (Boolean(p.archived) !== showArchived) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) || (p.client ?? "").toLowerCase().includes(q)
      );
    });
  }, [projects, query, showArchived]);

  const archivedCount = projects?.filter((p) => p.archived).length ?? 0;

  if (!ready) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-10">
        <Skeleton className="mb-10 h-12 w-64" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  return (
    <div
      className="min-h-screen"
      onDragEnter={(e) => {
        e.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (dragDepth.current === 0) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        if (e.dataTransfer.files?.length) handleFiles(e.dataTransfer.files);
      }}
    >
      {/* Drop overlay: the whole home accepts planos. */}
      {dragging && (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/85 backdrop-blur-sm">
          <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-accent bg-surface px-14 py-12">
            <CloudArrowUp size={40} weight="duotone" className="text-accent" />
            <p className="text-lg font-medium">Suelta tus planos DWG/DXF</p>
            <p className="text-sm text-muted">Varias hojas crean un solo proyecto</p>
          </div>
        </div>
      )}

      <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-5">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-fg">
              <Buildings size={17} weight="duotone" />
            </div>
            <span className="font-display text-[1.05rem] font-semibold tracking-tight">
              Klave
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/catalogo" className={buttonClasses("ghost", "sm")}>
              <Books size={15} weight="duotone" /> Catálogo
            </Link>
            {actorName && (
              <Link
                href="/bienvenida"
                title="Editar perfil"
                className="flex items-center gap-2 rounded-full border border-border bg-surface py-1 pl-1 pr-3 text-sm font-medium transition-colors hover:bg-surface-2"
              >
                <Avatar name={actorName} src={avatarSrc} self size="sm" />
                <span className="hidden max-w-32 truncate sm:inline">{actorName}</span>
              </Link>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-5 pb-16 pt-8">
        <input
          ref={inputRef}
          type="file"
          accept=".dwg,.dxf"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) handleFiles(e.target.files);
            e.target.value = "";
          }}
        />

        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[1.4rem] font-semibold leading-tight">Proyectos</h1>
            <p className="mt-0.5 text-sm text-muted">
              Sube un plano o arrastra varias hojas a esta ventana.
            </p>
          </div>
          <Button variant="primary" onClick={() => inputRef.current?.click()} disabled={uploading}>
            {uploading ? (
              <>
                <CircleNotch size={16} className="animate-spin" /> Subiendo…
              </>
            ) : (
              <>
                <Plus size={16} weight="bold" /> Nuevo proyecto
              </>
            )}
          </Button>
        </div>

        {error && (
          <div className="mb-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}

        {projects !== null && projects.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <MagnifyingGlass
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar por nombre o cliente…"
                className="w-full pl-9"
              />
            </div>
            <div className="flex rounded-lg border border-border bg-surface p-0.5">
              {([false, true] as const).map((archived) => (
                <button
                  key={String(archived)}
                  type="button"
                  onClick={() => setShowArchived(archived)}
                  className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
                    showArchived === archived
                      ? "bg-surface-3 text-foreground"
                      : "text-muted hover:text-foreground"
                  }`}
                >
                  {archived ? `Archivados${archivedCount ? ` (${archivedCount})` : ""}` : "Activos"}
                </button>
              ))}
            </div>
          </div>
        )}

        {projects === null ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="card flex items-center gap-3 p-4">
                <Skeleton className="h-9 w-9 rounded-lg" />
                <div className="flex-1">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="mt-2 h-3 w-32" />
                </div>
                <Skeleton className="h-6 w-20" />
              </div>
            ))}
          </div>
        ) : projects.length === 0 ? (
          <div className="rise-in">
            <EmptyState
              icon={<CloudArrowUp size={22} weight="duotone" />}
              title="Sube tu primer plano"
              hint="Arrastra archivos DWG/DXF a esta ventana o usa el botón para elegirlos. Varias hojas se procesan como un solo proyecto."
              action={
                <Button variant="primary" onClick={() => inputRef.current?.click()}>
                  <Plus size={16} weight="bold" /> Nuevo proyecto
                </Button>
              }
            />
            <div className="mt-10">
              <HowItWorks />
            </div>
          </div>
        ) : filtered && filtered.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted">
            {showArchived
              ? "No hay proyectos archivados que coincidan."
              : "Ningún proyecto coincide con la búsqueda."}
          </p>
        ) : (
          <div className="space-y-2">
            {filtered?.map((project) => (
              <ProjectRow
                key={project.project_id}
                project={project}
                onChanged={() =>
                  listProjects().then(setProjects).catch(() => {})
                }
                onError={setError}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function ProjectRow({
  project,
  onChanged,
  onError,
}: {
  project: ProjectSummary;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState<"name" | "client" | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);

  async function commitEdit() {
    const field = editing;
    setEditing(null);
    const value = draft.trim();
    if (!field) return;
    if (field === "name" && !value) return;
    try {
      await patchProject(project.project_id, { [field]: value }, getBrowserActor());
      onChanged();
    } catch {
      onError("No se pudo guardar el cambio.");
    }
  }

  async function toggleArchived() {
    try {
      await patchProject(
        project.project_id,
        { archived: !project.archived },
        getBrowserActor(),
      );
      onChanged();
    } catch {
      onError("No se pudo archivar el proyecto.");
    }
  }

  async function remove() {
    try {
      await removeProject(project.project_id, getBrowserActor());
      onChanged();
    } catch {
      onError("No se pudo quitar el proyecto.");
    }
  }

  const inner = (
    <>
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2">
        <FileText size={17} weight="duotone" className="text-foreground" />
      </div>
      <div className="min-w-0 flex-1">
        {editing ? (
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setEditing(null);
            }}
            onClick={(e) => e.preventDefault()}
            placeholder={editing === "client" ? "Cliente" : "Nombre del proyecto"}
            className="w-full max-w-sm px-2 py-1 text-sm"
          />
        ) : (
          <>
            <div className="truncate font-medium">{project.name}</div>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
              {project.client && <span className="truncate">{project.client}</span>}
              {project.client && <span className="text-faint">·</span>}
              {(project.sheet_count ?? 0) > 1 && (
                <span className="inline-flex items-center gap-1">
                  <Stack size={12} /> {project.sheet_count} hojas
                </span>
              )}
              {(project.sheet_count ?? 0) > 1 && <span className="text-faint">·</span>}
              {project.created_at && <span>{formatDate(project.created_at)}</span>}
            </div>
          </>
        )}
      </div>
      <Badge tone={STATUS_TONE[project.status ?? ""] ?? "default"}>
        {STATUS_LABELS[project.status ?? ""] ?? project.status ?? "—"}
      </Badge>
      <KebabMenu label={`Opciones de ${project.name}`}>
        {(close) => (
          <>
            <MenuItem
              onSelect={() => {
                setDraft(project.name);
                setEditing("name");
                close();
              }}
            >
              <PencilSimple size={15} /> Renombrar
            </MenuItem>
            <MenuItem
              onSelect={() => {
                setDraft(project.client ?? "");
                setEditing("client");
                close();
              }}
            >
              <UserSwitch size={15} /> Cliente…
            </MenuItem>
            <MenuItem
              onSelect={() => {
                toggleArchived();
                close();
              }}
            >
              {project.archived ? (
                <>
                  <ArrowCounterClockwise size={15} /> Restaurar
                </>
              ) : (
                <>
                  <Archive size={15} /> Archivar
                </>
              )}
            </MenuItem>
            {confirmRemove ? (
              <MenuItem
                danger
                onSelect={() => {
                  remove();
                  close();
                }}
              >
                <Trash size={15} /> Confirmar (archivos permanecen)
              </MenuItem>
            ) : (
              <MenuItem danger onSelect={() => setConfirmRemove(true)}>
                <Trash size={15} /> Quitar de la lista…
              </MenuItem>
            )}
          </>
        )}
      </KebabMenu>
      <ArrowRight
        size={15}
        weight="bold"
        className="text-faint transition group-hover:translate-x-0.5 group-hover:text-foreground"
      />
    </>
  );

  if (editing) {
    return <div className="card flex items-center gap-3 p-3.5">{inner}</div>;
  }
  return (
    <Link
      href={`/proyecto/${project.project_id}`}
      className="card card-hover group flex items-center gap-3 p-3.5"
    >
      {inner}
    </Link>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" }).format(date);
}
