"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Buildings,
  CloudArrowUp,
  FileText,
  ArrowRight,
  CircleNotch,
} from "@phosphor-icons/react";
import { ApiError, listProjects, uploadProject, type ProjectSummary } from "@/lib/api";
import { eventsUrl, getBrowserActor, parseProjectEvent, peekBrowserActor } from "@/lib/collab";
import { isProfileComplete } from "@/lib/identity";
import { fetchAuthStatus } from "@/lib/session";
import { Avatar, Badge, Callout, Skeleton, type BadgeTone } from "@/components/ui";
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

export default function Landing() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [actorName, setActorName] = useState("");
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
    function refreshProjects() {
      listProjects()
        .then((items) => {
          if (active) setProjects(items);
        })
        .catch(() => {
          if (active) setProjects([]);
        });
    }
    refreshProjects();
    const source = new EventSource(eventsUrl());
    source.onmessage = (message) => {
      const event = parseProjectEvent(message);
      if (
        event?.type === "project_created" ||
        event?.type === "project_updated" ||
        event?.type === "job_updated" ||
        event?.type === "run_published"
      ) {
        refreshProjects();
      }
    };
    return () => {
      active = false;
      source.close();
    };
  }, []);

  async function handleFile(file: File) {
    setError(null);
    if (!/\.(dwg|dxf)$/i.test(file.name)) {
      setError("Formato no soportado. Sube un archivo .dwg o .dxf.");
      return;
    }
    setUploading(true);
    try {
      const { project_id } = await uploadProject(file, getBrowserActor());
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

  const firstRun = projects !== null && projects.length === 0;

  if (!ready) {
    return (
      <div className="mx-auto max-w-5xl px-5 py-10 sm:px-6 sm:py-12">
        <Skeleton className="mb-10 h-12 w-64" />
        <Skeleton className="h-56" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:px-6 sm:py-12">
      <header className="rise-in mb-10 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-fg">
            <Buildings size={22} weight="duotone" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight">Klave</h1>
            <p className="text-sm text-muted">
              Ingeniería de costos a partir de planos estructurales.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {actorName && (
            <Link
              href="/bienvenida"
              title="Editar perfil"
              className="flex items-center gap-2 rounded-full border border-border bg-surface py-1 pl-1 pr-3 text-sm font-medium shadow-xs transition hover:bg-surface-2"
            >
              <Avatar name={actorName} src={avatarSrc} self size="sm" />
              <span className="max-w-32 truncate">{actorName}</span>
            </Link>
          )}
          <ThemeToggle />
        </div>
      </header>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) handleFile(f);
        }}
        className={`rise-in flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border border-dashed bg-surface px-6 py-14 text-center transition-colors sm:py-16 ${
          dragging
            ? "border-accent bg-accent-soft"
            : "border-border-strong hover:border-foreground/40 hover:bg-surface-2/60"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".dwg,.dxf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
        {uploading ? (
          <>
            <CircleNotch className="animate-spin text-accent" size={34} />
            <p className="font-medium">Subiendo y convirtiendo…</p>
            <p className="text-sm text-muted">Esto puede tardar unos segundos.</p>
          </>
        ) : (
          <>
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-surface-2">
              <CloudArrowUp className="text-foreground" size={28} weight="duotone" />
            </div>
            <p className="text-base font-medium">
              Arrastra un plano aquí o haz clic para seleccionar
            </p>
            <p className="text-sm text-muted">Formatos: DWG, DXF · procesamiento local</p>
          </>
        )}
      </label>

      {error && (
        <div className="mt-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {firstRun && (
        <section className="rise-in mt-10">
          <HowItWorks />
        </section>
      )}

      <section className="mt-12">
        <h2 className="microlabel mb-4">Proyectos recientes</h2>
        {projects === null ? (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-[76px]" />
            <Skeleton className="h-[76px]" />
          </div>
        ) : projects.length === 0 ? (
          <p className="text-sm text-muted">
            Aún no hay proyectos. Sube tu primer plano arriba para comenzar.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {projects.map((p) => (
              <Link
                key={p.project_id}
                href={`/proyecto/${p.project_id}`}
                className="card card-hover group flex items-center gap-3 p-4"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface-2">
                  <FileText size={18} weight="duotone" className="text-foreground" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="mt-1 flex items-center gap-2">
                    <Badge tone={STATUS_TONE[p.status ?? ""] ?? "default"}>
                      {STATUS_LABELS[p.status ?? ""] ?? p.status ?? "—"}
                    </Badge>
                    {p.created_at && (
                      <span className="text-xs text-faint">{formatDate(p.created_at)}</span>
                    )}
                  </div>
                </div>
                <ArrowRight
                  size={16}
                  weight="bold"
                  className="text-faint transition group-hover:translate-x-0.5 group-hover:text-foreground"
                />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" }).format(date);
}
