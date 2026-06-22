"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Loader2, CircleAlert, Building2 } from "lucide-react";
import { getStatus, type ProjectStatus } from "@/lib/api";
import { ProjectShell } from "@/components/ProjectShell";

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
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let active = true;
    async function poll() {
      try {
        const s = await getStatus(id);
        if (!active) return;
        setStatus(s);
        if (s.state !== "processed" && s.state !== "failed") {
          timer.current = setTimeout(poll, 1200);
        }
      } catch {
        if (active) timer.current = setTimeout(poll, 2000);
      }
    }
    poll();
    return () => {
      active = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [id]);

  if (status?.state === "processed") {
    return (
      <ProjectShell id={id} name={undefined}>
        {children}
      </ProjectShell>
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
        className="mb-8 inline-flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
      >
        <Building2 size={16} /> Klave
      </Link>
      <h1 className="text-xl font-semibold">
        {failed ? "No se pudo procesar el plano" : "Procesando tu plano…"}
      </h1>
      <p className="mt-1 text-sm text-[var(--muted)]">
        {failed
          ? "Revisa el archivo e inténtalo de nuevo."
          : "Leemos las entidades, detectamos elementos y calculamos el presupuesto."}
      </p>

      <div className="card mt-6 p-5">
        {STEPS.map((step) => {
          const done = reached(step.key);
          const isProcessed = step.key === "processed" && status?.state === "processed";
          return (
            <div key={step.key} className="flex items-center gap-3 py-2.5">
              {failed ? (
                <CircleAlert size={20} className="text-[var(--warning)]" />
              ) : done || isProcessed ? (
                <CheckCircle2 size={20} className="text-[var(--success)]" />
              ) : (
                <Loader2 size={20} className="animate-spin text-[var(--primary)]" />
              )}
              <span className={done ? "text-[var(--foreground)]" : "text-[var(--muted)]"}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {failed && status?.error && (
        <div className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          {status.error}
        </div>
      )}
      {failed && (
        <Link
          href="/"
          className="mt-6 inline-flex w-fit items-center rounded-lg bg-[var(--primary)] px-4 py-2 text-sm font-medium text-white"
        >
          Volver e intentar de nuevo
        </Link>
      )}
    </div>
  );
}
