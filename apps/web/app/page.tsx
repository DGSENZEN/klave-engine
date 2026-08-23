"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Archive,
  ArrowCounterClockwise,
  ArrowRight,
  ArrowsClockwise,
  Books,
  CircleNotch,
  CloudArrowUp,
  FileText,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  SealCheck,
  Stack,
  Trash,
  UserSwitch,
  UsersThree,
  Warning,
} from "@phosphor-icons/react";
import {
  ApiError,
  getWorkspaceOverview,
  money,
  patchProject,
  processProject,
  removeProject,
  uploadProject,
  type ProjectOverview,
  type WorkspaceOverview,
} from "@/lib/api";
import { eventsUrl, getBrowserActor, parseProjectEvent } from "@/lib/collab";
import { isProfileComplete } from "@/lib/identity";
import { fetchAuthStatus } from "@/lib/session";
import { timeAgo } from "@/lib/time";
import {
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
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { HowItWorks } from "@/components/HowItWorks";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

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
  created: "Sin procesar",
};

/** Events that change what the home shows. */
const REFRESH_EVENTS = new Set([
  "project_created",
  "project_updated",
  "project_removed",
  "job_updated",
  "run_published",
  "review_updated",
  "costing_updated",
  "user_pending",
  "user_status_changed",
  "catalog_updated",
]);

type Focus = "all" | "processing" | "failed" | "unverified" | "stale";

export default function Home() {
  const router = useRouter();
  const [overview, setOverview] = useState<WorkspaceOverview | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [focus, setFocus] = useState<Focus>("all");
  const [ready, setReady] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[] | null>(null);
  const [toasts, setToasts] = useState<{ id: string; text: string; href: string; tone: "success" | "warning" }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const overviewRef = useRef<WorkspaceOverview | null>(null);
  useEffect(() => {
    overviewRef.current = overview;
  }, [overview]);

  // The gate: protected workspaces require an active session; open mode only
  // needs the local first-run profile. Both land on /bienvenida otherwise.
  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      if (status.mode === "protected" && (!status.user || status.user.status !== "active")) {
        router.replace("/bienvenida");
        return;
      }
      if (status.mode !== "protected" && !isProfileComplete()) {
        router.replace("/bienvenida");
        return;
      }
      setReady(true);
    });
    return () => {
      active = false;
    };
  }, [router]);

  // "/" jumps to search from anywhere on the page (never while typing).
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && ("value" in target || target.isContentEditable)) return;
      event.preventDefault();
      searchRef.current?.focus();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!ready) return;
    let active = true;
    let timer: number | null = null;
    function refresh() {
      getWorkspaceOverview()
        .then((data) => {
          if (active) setOverview(data);
        })
        .catch(() => {
          if (active) setError("No se pudo cargar el taller. ¿Está activo el servidor?");
        });
    }
    refresh();
    const source = new EventSource(eventsUrl(), { withCredentials: true });
    source.onmessage = (message) => {
      const event = parseProjectEvent(message);
      if (event?.type === "job_updated") {
        const data = event.data as { state?: string; error?: string | null };
        if (data.state === "processed" || data.state === "failed") {
          const name =
            overviewRef.current?.projects.find((p) => p.project_id === event.project_id)?.name ??
            event.project_id ?? "Proyecto";
          const id = `${event.project_id}-${event.seq}`;
          setToasts((list) => [
            ...list.slice(-3),
            {
              id,
              text: data.state === "processed" ? `${name} terminó de procesar` : `${name}: ${data.error || "el procesamiento falló"}`,
              href: `/proyecto/${event.project_id}`,
              tone: data.state === "processed" ? "success" : "warning",
            },
          ]);
          window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 9000);
        }
      }
      if (event && REFRESH_EVENTS.has(event.type)) {
        // Coalesce bursts (a processing run emits several events per second).
        if (timer) window.clearTimeout(timer);
        timer = window.setTimeout(refresh, 250);
      }
    };
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
      source.close();
    };
  }, [ready]);

  function handleFiles(list: FileList | File[]) {
    const files = [...list].filter((f) => /\.(dwg|dxf)$/i.test(f.name));
    if (files.length === 0) {
      setError("Formato no soportado. Sube archivos .dwg o .dxf.");
      return;
    }
    setError(null);
    setPendingFiles(files);
  }

  async function createProject(files: File[], name: string, client: string) {
    setUploading(true);
    try {
      const { project_id } = await uploadProject(files, getBrowserActor(), {
        project_name: name,
        client,
      });
      setPendingFiles(null);
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

  const projects = overview?.projects ?? null;

  const filtered = useMemo(() => {
    if (!projects) return null;
    const q = query.trim().toLowerCase();
    return projects.filter((p) => {
      if (Boolean(p.archived) !== showArchived) return false;
      if (focus === "processing" && !(p.status === "queued" || p.status === "running")) return false;
      if (focus === "failed" && p.status !== "failed") return false;
      if (focus === "unverified" && !(p.status === "processed" && !p.verified)) return false;
      if (focus === "stale" && !p.engine_stale) return false;
      if (!q) return true;
      return (
        p.name.toLowerCase().includes(q) || (p.client ?? "").toLowerCase().includes(q)
      );
    });
  }, [projects, query, showArchived, focus]);

  const archivedCount = projects?.filter((p) => p.archived).length ?? 0;

  function refreshNow() {
    getWorkspaceOverview().then(setOverview).catch(() => {});
  }

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

      <WorkspaceHeader active="proyectos" />

      {pendingFiles && (
        <NewProjectDialog
          files={pendingFiles}
          busy={uploading}
          onCancel={() => setPendingFiles(null)}
          onCreate={(name, client) => createProject(pendingFiles, name, client)}
        />
      )}

      {toasts.length > 0 && (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
          {toasts.map((toast) => (
            <Link
              key={toast.id}
              href={toast.href}
              className={`toast-in flex items-center gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg ${
                toast.tone === "success"
                  ? "border-success/30 bg-surface text-foreground"
                  : "border-warning/40 bg-surface text-foreground"
              }`}
            >
              {toast.tone === "success" ? (
                <SealCheck size={15} weight="bold" className="text-success" />
              ) : (
                <Warning size={15} weight="bold" className="text-warning" />
              )}
              <span className="max-w-72 truncate">{toast.text}</span>
              <ArrowRight size={13} weight="bold" className="text-faint" />
            </Link>
          ))}
        </div>
      )}

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
            <h1 className="text-[1.4rem] font-semibold leading-tight">
              {overview?.workspace.name && overview.mode === "protected"
                ? overview.workspace.name
                : "Proyectos"}
            </h1>
            <p className="mt-0.5 text-sm text-muted">
              Sube un plano o arrastra varias hojas a esta ventana: un proyecto por obra.
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

        {overview && <AttentionStrip overview={overview} focus={focus} onFocus={setFocus} />}

        {projects !== null && projects.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <MagnifyingGlass
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <Input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar por nombre o cliente…  ( / )"
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
            {focus !== "all"
              ? "Nada pendiente en este filtro."
              : showArchived
                ? "No hay proyectos archivados que coincidan."
                : "Ningún proyecto coincide con la búsqueda."}
            {focus !== "all" && (
              <>
                {" "}
                <button
                  type="button"
                  onClick={() => setFocus("all")}
                  className="font-medium text-foreground hover:underline"
                >
                  Ver todos
                </button>
              </>
            )}
          </p>
        ) : (
          <div className="space-y-2">
            {filtered?.map((project) => (
              <ProjectRow
                key={project.project_id}
                project={project}
                onChanged={refreshNow}
                onError={setError}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

/* --------------------------------------------------------------- attention -- */

function AttentionStrip({
  overview,
  focus,
  onFocus,
}: {
  overview: WorkspaceOverview;
  focus: Focus;
  onFocus: (focus: Focus) => void;
}) {
  const { attention } = overview;
  const chips: {
    key: Focus | "users" | "catalog";
    label: string;
    icon: React.ReactNode;
    tone: "accent" | "warning" | "default";
    href?: string;
  }[] = [];
  if (attention.processing > 0) {
    chips.push({
      key: "processing",
      label: attention.processing === 1 ? "1 procesando" : `${attention.processing} procesando`,
      icon: <CircleNotch size={14} className="animate-spin" />,
      tone: "accent",
    });
  }
  if (attention.failed > 0) {
    chips.push({
      key: "failed",
      label: attention.failed === 1 ? "1 con errores" : `${attention.failed} con errores`,
      icon: <Warning size={14} weight="bold" />,
      tone: "warning",
    });
  }
  if (attention.unverified > 0) {
    chips.push({
      key: "unverified",
      label:
        attention.unverified === 1 ? "1 sin verificar" : `${attention.unverified} sin verificar`,
      icon: <SealCheck size={14} weight="bold" />,
      tone: "default",
    });
  }
  if (attention.stale_runs > 0) {
    chips.push({
      key: "stale",
      label:
        attention.stale_runs === 1
          ? "1 con lectura anterior"
          : `${attention.stale_runs} con lectura anterior`,
      icon: <ArrowsClockwise size={14} weight="bold" />,
      tone: "default",
    });
  }
  if (attention.pending_users) {
    chips.push({
      key: "users",
      label:
        attention.pending_users === 1
          ? "1 cuenta por aprobar"
          : `${attention.pending_users} cuentas por aprobar`,
      icon: <UsersThree size={14} weight="bold" />,
      tone: "warning",
      href: "/equipo",
    });
  }
  if (attention.stale_insumos > 0 && overview.is_admin) {
    chips.push({
      key: "catalog",
      label: `${attention.stale_insumos} precios con más de ${attention.stale_threshold_months} meses`,
      icon: <Books size={14} weight="bold" />,
      tone: "default",
      href: "/catalogo",
    });
  }
  if (chips.length === 0) return null;

  const classes = (tone: "accent" | "warning" | "default", active: boolean) =>
    `inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors ${
      active
        ? "border-foreground bg-foreground text-background"
        : tone === "accent"
          ? "border-accent/30 bg-accent-soft text-accent hover:border-accent/60"
          : tone === "warning"
            ? "border-warning/30 bg-warning-soft text-warning hover:border-warning/60"
            : "border-border bg-surface text-foreground hover:bg-surface-2"
    }`;

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <span className="microlabel mr-1">Atención</span>
      {chips.map((chip) =>
        chip.href ? (
          <Link key={chip.key} href={chip.href} className={classes(chip.tone, false)}>
            {chip.icon} {chip.label} <ArrowRight size={12} weight="bold" />
          </Link>
        ) : (
          <button
            key={chip.key}
            type="button"
            onClick={() => onFocus(focus === chip.key ? "all" : (chip.key as Focus))}
            className={classes(chip.tone, focus === chip.key)}
          >
            {chip.icon} {chip.label}
          </button>
        ),
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- row -- */

function ProjectRow({
  project,
  onChanged,
  onError,
}: {
  project: ProjectOverview;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState<"name" | "client" | null>(null);
  const [draft, setDraft] = useState("");
  const [removeOpen, setRemoveOpen] = useState(false);

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

  const [reprocessing, setReprocessing] = useState(false);
  async function reprocess() {
    setReprocessing(true);
    try {
      await processProject(project.project_id);
      onChanged();
    } catch {
      onError("No se pudo reprocesar el proyecto.");
    } finally {
      setReprocessing(false);
    }
  }

  const processed = project.status === "processed";
  const steps = project.verification;
  const doneSteps = [steps.units, steps.detections, steps.assumptions].filter(Boolean).length;

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
            <div className="flex items-center gap-2">
              <span className="truncate font-medium">{project.name}</span>
              {processed &&
                (project.verified ? (
                  <Badge tone="success">
                    <SealCheck size={12} weight="bold" /> Verificado
                  </Badge>
                ) : (
                  <span title="Unidades, detecciones y supuestos por confirmar">
                    <Badge tone="default">{doneSteps}/3 verificado</Badge>
                  </span>
                ))}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              {project.client && <span className="truncate">{project.client}</span>}
              {project.client && <span className="text-faint">·</span>}
              {(project.sheet_count ?? 0) > 1 && (
                <span className="inline-flex items-center gap-1">
                  <Stack size={12} /> {project.sheet_count} hojas
                </span>
              )}
              {(project.sheet_count ?? 0) > 1 && <span className="text-faint">·</span>}
              {project.last_activity && <span>{timeAgo(project.last_activity)}</span>}
              {project.job_error && (
                <>
                  <span className="text-faint">·</span>
                  <span className="truncate text-warning">{project.job_error}</span>
                </>
              )}
              {project.engine_stale && (
                <>
                  <span className="text-faint">·</span>
                  <span className="inline-flex items-center gap-1" title="Procesado con una versión anterior del motor">
                    <ArrowsClockwise size={12} /> lectura anterior
                  </span>
                </>
              )}
            </div>
          </>
        )}
      </div>
      {project.grand_total != null && (
        <div className="hidden text-right sm:block">
          <div className="font-display text-sm font-semibold tabular">
            {money(project.grand_total, project.currency)}
          </div>
          <div className="microlabel">total</div>
        </div>
      )}
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
                reprocess();
                close();
              }}
            >
              <ArrowsClockwise size={15} className={reprocessing ? "animate-spin" : ""} />{" "}
              {reprocessing ? "Encolando…" : "Reprocesar"}
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
            <MenuItem
              danger
              onSelect={() => {
                close();
                setRemoveOpen(true);
              }}
            >
              <Trash size={15} /> Quitar de la lista…
            </MenuItem>
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

  const dialog = (
    <ConfirmDialog
      open={removeOpen}
      title="Quitar proyecto de la lista"
      description={
        <>
          <span className="font-medium text-foreground">{project.name}</span> dejará de
          aparecer en el taller. Los archivos y reportes permanecen en el disco.
        </>
      }
      confirmLabel="Quitar de la lista"
      typeToConfirm={project.name}
      onCancel={() => setRemoveOpen(false)}
      onConfirm={() => {
        setRemoveOpen(false);
        remove();
      }}
    />
  );

  if (editing) {
    return (
      <>
        <div className="card flex items-center gap-3 p-3.5">{inner}</div>
        {dialog}
      </>
    );
  }
  return (
    <>
      <Link
        href={`/proyecto/${project.project_id}`}
        className="card card-hover group flex items-center gap-3 p-3.5"
      >
        {inner}
      </Link>
      {dialog}
    </>
  );
}


/* ------------------------------------------------------------ new project -- */

function suggestName(file: File): string {
  const stem = file.name.replace(/\.(dwg|dxf)$/i, "").replace(/[_\-]+/g, " ").trim();
  return stem.replace(/\s+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()).slice(0, 80);
}

function NewProjectDialog({
  files,
  busy,
  onCancel,
  onCreate,
}: {
  files: File[];
  busy: boolean;
  onCancel: () => void;
  onCreate: (name: string, client: string) => void;
}) {
  const [name, setName] = useState(() => suggestName(files[0]));
  const [client, setClient] = useState("");

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, onCancel]);

  const totalMb = files.reduce((sum, f) => sum + f.size, 0) / 1e6;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button type="button" aria-label="Cancelar" onClick={() => !busy && onCancel()} className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]" />
      <form
        role="dialog"
        aria-modal="true"
        aria-label="Nuevo proyecto"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim().length >= 2) onCreate(name.trim(), client.trim());
        }}
        className="toast-in relative w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-lg"
      >
        <h2 className="text-[0.95rem] font-semibold">Nuevo proyecto</h2>
        <p className="mb-4 text-sm text-muted">
          {files.length === 1 ? "1 hoja" : `${files.length} hojas`} · {totalMb.toFixed(1)} MB.
          Las hojas se procesan juntas como una sola obra.
        </p>
        <label className="mb-1 block text-xs font-medium text-muted">Nombre del proyecto</label>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          maxLength={120}
          required
          className="mb-3 w-full"
        />
        <label className="mb-1 block text-xs font-medium text-muted">Cliente (opcional)</label>
        <Input
          value={client}
          onChange={(e) => setClient(e.target.value)}
          placeholder="Constructora, dependencia, particular…"
          maxLength={120}
          className="mb-3 w-full"
        />
        <ul className="mb-4 max-h-32 space-y-1 overflow-y-auto text-xs text-muted">
          {files.map((file) => (
            <li key={file.name} className="flex items-center gap-1.5">
              <FileText size={12} /> <span className="truncate">{file.name}</span>
            </li>
          ))}
        </ul>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} disabled={busy} className={buttonClasses("secondary")}>
            Cancelar
          </button>
          <Button type="submit" variant="primary" disabled={busy || name.trim().length < 2}>
            {busy ? (
              <>
                <CircleNotch size={15} className="animate-spin" /> Subiendo…
              </>
            ) : (
              <>
                <Plus size={15} weight="bold" /> Crear y procesar
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
