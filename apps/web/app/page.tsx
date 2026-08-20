"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Building2,
  UploadCloud,
  FileText,
  ArrowRight,
  Loader2,
  ScanSearch,
  Receipt,
} from "lucide-react";
import { ApiError, listProjects, uploadProject, type ProjectSummary } from "@/lib/api";
import { eventsUrl, getBrowserActor, parseProjectEvent } from "@/lib/collab";
import { Badge, Callout, Card, Skeleton, type BadgeTone } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

const STATUS_TONE: Record<string, BadgeTone> = {
  processed: "success",
  running: "primary",
  queued: "primary",
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
  const inputRef = useRef<HTMLInputElement>(null);

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

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:px-6 sm:py-12">
      <header className="rise-in mb-10 flex items-start justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-fg shadow-md">
            <Building2 size={24} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Klave</h1>
            <p className="text-sm text-muted">
              Ingeniería de costos a partir de planos estructurales.
            </p>
          </div>
        </div>
        <ThemeToggle />
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
        className={`rise-in flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed bg-surface px-6 py-14 text-center shadow-xs transition sm:py-16 ${
          dragging
            ? "border-primary bg-primary-soft"
            : "border-border-strong hover:border-primary hover:bg-primary-soft/40"
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
            <Loader2 className="animate-spin text-primary" size={34} />
            <p className="font-medium">Subiendo y convirtiendo…</p>
            <p className="text-sm text-muted">Esto puede tardar unos segundos.</p>
          </>
        ) : (
          <>
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary-soft">
              <UploadCloud className="text-primary" size={28} />
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
        <section className="rise-in mt-10 grid gap-3 sm:grid-cols-3">
          <HowStep
            n={1}
            icon={<UploadCloud size={18} />}
            title="Sube tu plano"
            text="DWG o DXF estructural; la conversión y lectura corren en tu equipo."
          />
          <HowStep
            n={2}
            icon={<ScanSearch size={18} />}
            title="Detección con evidencia"
            text="Ejes, columnas, trabes, zapatas y muros, cada uno con su origen y confianza."
          />
          <HowStep
            n={3}
            icon={<Receipt size={18} />}
            title="Presupuesto completo"
            text="Cantidades, precios unitarios, programa de obra, flujo y riesgos revisables."
          />
        </section>
      )}

      <section className="mt-12">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-muted">
          Proyectos recientes
        </h2>
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
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft">
                  <FileText size={18} className="text-primary" />
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
                  size={18}
                  className="text-muted transition group-hover:translate-x-0.5 group-hover:text-primary"
                />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function HowStep({
  n,
  icon,
  title,
  text,
}: {
  n: number;
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <Card className="p-4">
      <div className="mb-2 flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
          {icon}
        </div>
        <span className="text-xs font-semibold uppercase tracking-wide text-faint">
          Paso {n}
        </span>
      </div>
      <div className="font-medium">{title}</div>
      <p className="mt-1 text-sm leading-relaxed text-muted">{text}</p>
    </Card>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short" }).format(date);
}
