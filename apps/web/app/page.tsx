"use client";

import { useCapabilities } from "@/components/Capabilities";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Archive,
  ArrowCounterClockwise,
  ArrowRight,
  CaretRight,
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
  apiMessage,
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
import { uploadErrorMessage, validateDrawingFiles } from "@/lib/uploads";
import {
  Badge,
  Button,
  Callout,
  Input,
  Skeleton,
  type BadgeTone,
} from "@/components/ui";
import { KebabMenu, MenuItem } from "@/components/Menu";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { COMPOSER_PICK_ID, NewProjectComposer } from "@/components/NewProjectComposer";
import { ReprocesarDialog } from "@/components/ReprocesarDialog";
import { Modal } from "@/components/Modal";
import { InicioRecorrido } from "@/components/recorrido/InicioRecorrido";
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const uploadInFlight = useRef(false);
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [focus, setFocus] = useState<Focus>("all");
  const [ready, setReady] = useState(false);
  /** Sheets chosen for a new project; null while the composer is closed. */
  const [draft, setDraft] = useState<File[] | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: string; text: string; href: string; tone: "success" | "warning" }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const overviewRef = useRef<WorkspaceOverview | null>(null);
  useEffect(() => {
    overviewRef.current = overview;
  }, [overview]);

  // The gate: protected workspaces require an active session; open mode only
  // needs the local first-run profile. A visitor with no account at all gets
  // the public portada; an account still waiting for approval, or an open
  // workspace without a profile, lands on /bienvenida.
  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      if (status.mode === "protected" && !status.user) {
        router.replace("/portada");
        return;
      }
      if (status.mode === "protected" && status.user?.status !== "active") {
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

  const refreshNow = useCallback(async () => {
    setRefreshing(true);
    try {
      setOverview(await getWorkspaceOverview());
      setLoadError(null);
    } catch (error) {
      setLoadError(apiMessage(error, "No se pudo cargar el taller. Revisa tu conexión e inténtalo de nuevo."));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    let active = true;
    let timer: number | null = null;
    function refresh() {
      getWorkspaceOverview()
        .then((data) => {
          if (active) {
            setOverview(data);
            setLoadError(null);
          }
        })
        .catch(() => {
          if (active) setLoadError("No se pudo cargar el taller. Revisa tu conexión e inténtalo de nuevo.");
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

  function addFiles(list: FileList | File[]) {
    if (uploadInFlight.current) return;
    const current = draft ?? [];
    const seen = new Set(current.map((f) => `${f.name}:${f.size}`));
    const files = [...current, ...[...list].filter((f) => !seen.has(`${f.name}:${f.size}`))];
    setUploadError(null);
    const validation = validateDrawingFiles(files, overview?.upload_limits);
    setDraftError(validation);
    setDraft(validation ? current : files);
  }

  function removeFile(index: number) {
    setDraft((current) => (current ?? []).filter((_, i) => i !== index));
    setDraftError(null);
    setUploadError(null);
  }

  function openComposer() {
    setDraft((current) => current ?? []);
    // After it renders: bring it into view and put the keyboard on "choose sheets".
    window.setTimeout(() => {
      const pick = document.getElementById(COMPOSER_PICK_ID);
      pick?.scrollIntoView({ block: "center", behavior: "smooth" });
      pick?.focus({ preventScroll: true });
    }, 0);
  }

  function closeComposer() {
    setDraft(null);
    setDraftError(null);
    setUploadError(null);
  }

  async function createProject(files: File[], name: string, client: string) {
    if (uploadInFlight.current) return;
    uploadInFlight.current = true;
    setUploading(true);
    setUploadError(null);
    try {
      const { project_id, warnings } = await uploadProject(files, getBrowserActor(), {
        project_name: name,
        client,
      });
      if (warnings.length) {
        try { sessionStorage.setItem("klave.upload.warning." + project_id, warnings.join(" ")); } catch {}
      }
      setDraft(null);
      router.push(`/proyecto/${encodeURIComponent(project_id)}`);
    } catch (e) {
      setUploadError(uploadErrorMessage(e, "No se pudo confirmar la subida. Revisa la lista de proyectos antes de volver a subirlos; conservamos tu selección."));
      uploadInFlight.current = false;
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

  if (!ready) {
    return (
      <div className="mx-auto max-w-6xl px-5 py-10 sm:px-6">
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
        if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
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
                <SealCheck className="text-success" />
              ) : (
                <Warning className="text-warning" />
              )}
              <span className="max-w-72 truncate">{toast.text}</span>
              <ArrowRight size={14} className="text-faint" />
            </Link>
          ))}
        </div>
      )}

      <main className="mx-auto max-w-6xl px-5 pb-16 pt-8 sm:px-6">
        <input
          ref={inputRef}
          type="file"
          accept=".dwg,.dxf"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
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
          <Button
            variant="primary"
            onClick={openComposer}
            disabled={uploading}
            data-tour="inicio.subir"
          >
            {uploading ? (
              <>
                <CircleNotch className="animate-spin" /> Subiendo…
              </>
            ) : (
              <>
                <Plus /> Nuevo proyecto
              </>
            )}
          </Button>
        </div>

        {error && (
          <div className="mb-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        {loadError && (
          <div className="mb-4" role="alert">
            <Callout tone="danger">
              <p>{loadError}</p>
              <Button className="mt-2" onClick={refreshNow} disabled={refreshing}>
                <ArrowCounterClockwise /> {refreshing ? "Cargando…" : "Volver a intentar"}
              </Button>
            </Callout>
          </div>
        )}

        {overview && <AttentionStrip overview={overview} focus={focus} onFocus={setFocus} />}

        {projects !== null && <InicioRecorrido />}

        {projects !== null && (draft !== null || projects.length === 0) && (
          <NewProjectComposer
            title={projects.length === 0 ? "Sube tu primera obra" : "Nuevo proyecto"}
            files={draft ?? []}
            limits={overview?.upload_limits}
            busy={uploading}
            error={draftError ?? uploadError}
            onPick={() => inputRef.current?.click()}
            onRemove={removeFile}
            onCreate={(name, client) => createProject(draft ?? [], name, client)}
            onClose={projects.length > 0 ? closeComposer : undefined}
          />
        )}

        {projects !== null && projects.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <MagnifyingGlass
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

        {projects === null ? (loadError ? null : (
          <div className="card divide-y divide-border overflow-clip">
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <Skeleton className="h-8 w-8 rounded-md" />
                <div className="flex-1">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="mt-2 h-3 w-32" />
                </div>
                <Skeleton className="h-6 w-20" />
              </div>
            ))}
          </div>
        )) : projects.length === 0 ? null : filtered && filtered.length === 0 ? (
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
          // One list, divided rows: projects are entries in a register, not
          // separate objects to admire.
          // No overflow clip: each row's options menu hangs below it, and on
          // the last row it must reach past the card. The rows round the
          // corners instead.
          <ul className="card divide-y divide-border [&>li:first-child>*]:rounded-t-[11px] [&>li:last-child>*]:rounded-b-[11px]">
            {filtered?.map((project) => (
              <li key={project.project_id}>
                <ProjectRow project={project} onChanged={refreshNow} onError={setError} />
              </li>
            ))}
          </ul>
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
      icon: <Warning size={14} />,
      tone: "warning",
    });
  }
  if (attention.unverified > 0) {
    chips.push({
      key: "unverified",
      label:
        attention.unverified === 1 ? "1 sin verificar" : `${attention.unverified} sin verificar`,
      icon: <SealCheck size={14} />,
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
      icon: <ArrowsClockwise size={14} />,
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
      icon: <UsersThree size={14} />,
      tone: "warning",
      href: "/equipo",
    });
  }
  if (attention.stale_insumos > 0 && overview.is_admin) {
    chips.push({
      key: "catalog",
      label: `${attention.stale_insumos} precios con más de ${attention.stale_threshold_months} meses`,
      icon: <Books size={14} />,
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
      <span className="mr-1 text-xs text-muted">Atención</span>
      {chips.map((chip) =>
        chip.href ? (
          <Link key={chip.key} href={chip.href} className={classes(chip.tone, false)}>
            {chip.icon} {chip.label} <ArrowRight size={14} />
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
  // An overview from an API without role enforcement has no my_role.
  const caps = useCapabilities(project.my_role === undefined ? "legacy" : project.my_role);
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
  const [confirmReprocess, setConfirmReprocess] = useState(false);
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
                    <SealCheck size={14} /> Verificado
                  </Badge>
                ) : (
                  <span title="Unidades, elementos y supuestos por confirmar">
                    <Badge tone="default">{doneSteps}/3 verificado</Badge>
                  </span>
                ))}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
              {project.client && <span className="truncate">{project.client}</span>}
              {project.client && <span className="text-faint">·</span>}
              {(project.sheet_count ?? 0) > 1 && (
                <span className="inline-flex items-center gap-1">
                  <Stack size={14} /> {project.sheet_count} hojas
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
                  <span className="inline-flex items-center gap-1" title="Procesado con una versión anterior de Klave">
                    <ArrowsClockwise size={14} /> lectura anterior
                  </span>
                </>
              )}
            </div>
          </>
        )}
      </div>
      {project.money_state === "blocked" ? (
        <div className="hidden text-right sm:block">
          <div className="text-[13px] text-muted">sin unidades</div>
          <div className="text-xs text-warning">confirma la escala</div>
        </div>
      ) : (
        project.grand_total != null && (
          <div className="hidden text-right sm:block">
            <div className="font-display text-[15px] font-medium tabular">
              {money(project.grand_total, project.currency)}
            </div>
            <div className="text-xs text-muted">total</div>
          </div>
        )
      )}
      {/* «Procesado» es el estado normal: sólo se anuncia lo que no lo es. */}
      {project.status !== "processed" && (
        <Badge tone={STATUS_TONE[project.status ?? ""] ?? "default"}>
          {STATUS_LABELS[project.status ?? ""] ?? project.status ?? "—"}
        </Badge>
      )}
      {(caps.editProject || caps.manageProject) && (
      <KebabMenu label={`Opciones de ${project.name}`}>
        {(close) => (
          <>
            {caps.manageProject && (
              <>
                <MenuItem
                  onSelect={() => {
                    setDraft(project.name);
                    setEditing("name");
                    close();
                  }}
                >
                  <PencilSimple /> Renombrar
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    setDraft(project.client ?? "");
                    setEditing("client");
                    close();
                  }}
                >
                  <UserSwitch /> Cliente…
                </MenuItem>
              </>
            )}
            {caps.editProject && (
              <MenuItem
                onSelect={() => {
                  setConfirmReprocess(true);
                  close();
                }}
              >
                <ArrowsClockwise className={reprocessing ? "animate-spin" : ""} />{" "}
                {reprocessing ? "Encolando…" : "Reprocesar"}
              </MenuItem>
            )}
            {caps.manageProject && (
            <>
            <MenuItem
              onSelect={() => {
                toggleArchived();
                close();
              }}
            >
              {project.archived ? (
                <>
                  <ArrowCounterClockwise /> Restaurar
                </>
              ) : (
                <>
                  <Archive /> Archivar
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
              <Trash /> Quitar de la lista…
            </MenuItem>
            </>
            )}
          </>
        )}
      </KebabMenu>
      )}
      <CaretRight
        size={14}
        aria-hidden
        className="shrink-0 text-faint transition-transform duration-150 ease-out group-hover:translate-x-0.5 group-hover:text-foreground"
      />
    </>
  );

  const dialog = (
    <>
    <ReprocesarDialog
      open={confirmReprocess}
      onConfirm={() => {
        setConfirmReprocess(false);
        void reprocess();
      }}
      onCancel={() => setConfirmReprocess(false)}
    />
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
    </>
  );

  if (editing) {
    return (
      <>
        <div className="flex items-center gap-3 px-4 py-2.5">{inner}</div>
        {dialog}
      </>
    );
  }
  return (
    <>
      <Link
        href={`/proyecto/${project.project_id}`}
        className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-surface-2/60"
      >
        {inner}
      </Link>
      {dialog}
    </>
  );
}
