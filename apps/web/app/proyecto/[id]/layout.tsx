"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Loader2, CircleAlert, Building2, ArrowLeft } from "lucide-react";
import { getStatus, type ProjectStatus } from "@/lib/api";
import { parseProjectEvent, projectEventsUrl } from "@/lib/collab";
import { ProjectLiveProvider } from "@/components/ProjectLive";
import { ProjectShell } from "@/components/ProjectShell";
import { Callout } from "@/components/ui";

const STEPS = [
  { key: "ingested", label: "Ingesta del proyecto" },
  { key: "converted", label: "Conversión DWG → DXF" },
  { key: "parsed", label: "Lectura de entidades" },
  { key: "processed", label: "Detección, vistas y costos" },
];

const ORDER = ["queued", "ingested", "converted", "running", "parsed", "processed"];

export default function ProjectLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [status, setStatus] = useState<ProjectStatus | null>(null);

  useEffect(() => {
    let active = true;
    getStatus(id)
      .then((s) => {
        if (active) setStatus(s);
      })
      .catch(() => {});

    if (status?.state === "processed") {
      return () => {
        active = false;
      };
    }

    const source = new EventSource(projectEventsUrl(id));
    source.onmessage = (message) => {
      const event = parseProjectEvent(message);
      if (!event || !active) return;
      if (event.type === "job_updated") {
        const data = event.data;
        setStatus({
          project_id: id,
          job_id: typeof data.job_id === "string" ? data.job_id : undefined,
          run_id: typeof data.run_id === "string" ? data.run_id : undefined,
          state: typeof data.state === "string" ? data.state : "unknown",
          stage: typeof data.stage === "string" ? data.stage : "Desconocido",
          error: typeof data.error === "string" ? data.error : null,
          entity_count: typeof data.entity_count === "number" ? data.entity_count : undefined,
          detection_count:
            typeof data.detection_count === "number" ? data.detection_count : undefined,
        });
      } else if (event.type === "run_published") {
        getStatus(id)
          .then((s) => {
            if (active) setStatus(s);
          })
          .catch(() => {});
      }
    };
    return () => {
      active = false;
      source.close();
    };
  }, [id, status?.state]);

  if (status?.state === "processed") {
    return (
      <ProjectLiveProvider projectId={id}>
        <ProjectShell id={id} name={undefined}>
          {children}
        </ProjectShell>
      </ProjectLiveProvider>
    );
  }

  const failed = status?.state === "failed";
  const reached = (key: string) => {
    const current = ORDER.indexOf(status?.state ?? "queued");
    return current >= ORDER.indexOf(key);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm text-muted transition hover:text-foreground"
      >
        <Building2 size={16} /> Klave
      </Link>
      <h1 className="text-xl font-semibold">
        {failed ? "No se pudo procesar el plano" : "Procesando tu plano…"}
      </h1>
      <p className="mt-1 text-sm text-muted">
        {failed
          ? "Revisa el archivo e inténtalo de nuevo."
          : "Leemos las entidades, detectamos elementos y calculamos el presupuesto."}
      </p>

      <div className="card rise-in mt-6 p-5">
        {STEPS.map((step, index) => {
          const done = reached(step.key);
          const isProcessed = step.key === "processed" && status?.state === "processed";
          const isCurrent = !done && (index === 0 || reached(STEPS[index - 1].key));
          return (
            <div key={step.key} className="relative flex items-center gap-3 py-3">
              {index < STEPS.length - 1 && (
                <span
                  className={`absolute left-[9.5px] top-[34px] h-[calc(100%-26px)] w-px ${
                    done ? "bg-success/40" : "bg-border"
                  }`}
                />
              )}
              {failed ? (
                <CircleAlert size={20} className="shrink-0 text-warning" />
              ) : done || isProcessed ? (
                <CheckCircle2 size={20} className="shrink-0 text-success" />
              ) : isCurrent ? (
                <Loader2 size={20} className="shrink-0 animate-spin text-primary" />
              ) : (
                <span className="mx-[3px] h-3.5 w-3.5 shrink-0 rounded-full border-2 border-border-strong" />
              )}
              <span
                className={
                  done
                    ? "text-foreground"
                    : isCurrent
                      ? "font-medium text-foreground"
                      : "text-muted"
                }
              >
                {step.label}
              </span>
              {step.key === "parsed" && done && status?.entity_count != null && (
                <span className="ml-auto tabular text-xs text-faint">
                  {status.entity_count.toLocaleString("es-MX")} entidades
                </span>
              )}
              {step.key === "processed" && done && status?.detection_count != null && (
                <span className="ml-auto tabular text-xs text-faint">
                  {status.detection_count.toLocaleString("es-MX")} detecciones
                </span>
              )}
            </div>
          );
        })}
      </div>

      {failed && status?.error && (
        <div className="mt-4">
          <Callout tone="danger">{status.error}</Callout>
        </div>
      )}
      {failed && (
        <Link
          href="/"
          className="mt-6 inline-flex w-fit items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg transition hover:bg-primary-hover"
        >
          <ArrowLeft size={15} /> Volver e intentar de nuevo
        </Link>
      )}
    </div>
  );
}
