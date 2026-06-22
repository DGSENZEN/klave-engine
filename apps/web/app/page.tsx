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
  CircleAlert,
} from "lucide-react";
import { ApiError, listProjects, uploadProject, type ProjectSummary } from "@/lib/api";
import { Badge } from "@/components/ui";

const STATUS_TONE: Record<string, "success" | "warning" | "primary" | "default"> = {
  processed: "success",
  running: "primary",
  queued: "primary",
  failed: "warning",
};

export default function Landing() {
  const router = useRouter();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  async function handleFile(file: File) {
    setError(null);
    if (!/\.(dwg|dxf)$/i.test(file.name)) {
      setError("Formato no soportado. Sube un archivo .dwg o .dxf.");
      return;
    }
    setUploading(true);
    try {
      const { project_id } = await uploadProject(file);
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

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <header className="mb-10 flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--primary)] text-white">
          <Building2 size={22} />
        </div>
        <div>
          <h1 className="text-xl font-semibold">Klave · Ingeniería de Costos</h1>
          <p className="text-sm text-[var(--muted)]">
            Sube un plano estructural y obtén presupuesto, programa y flujo financiero.
          </p>
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
        className={`card flex cursor-pointer flex-col items-center justify-center gap-3 px-6 py-14 text-center transition ${
          dragging ? "border-[var(--primary)] bg-blue-50/40" : "hover:border-[var(--primary)]"
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
            <Loader2 className="animate-spin text-[var(--primary)]" size={34} />
            <p className="font-medium">Subiendo y convirtiendo…</p>
            <p className="text-sm text-[var(--muted)]">Esto puede tardar unos segundos.</p>
          </>
        ) : (
          <>
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[var(--surface-2)]">
              <UploadCloud className="text-[var(--primary)]" size={28} />
            </div>
            <p className="text-base font-medium">
              Arrastra un plano aquí o haz clic para seleccionar
            </p>
            <p className="text-sm text-[var(--muted)]">Formatos: DWG, DXF · CPU, sin nube</p>
          </>
        )}
      </label>

      {error && (
        <div className="mt-4 flex items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          <CircleAlert size={16} /> {error}
        </div>
      )}

      <section className="mt-12">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--muted)]">
          Proyectos recientes
        </h2>
        {projects === null ? (
          <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
            <Loader2 className="animate-spin" size={16} /> Cargando…
          </div>
        ) : projects.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">
            Aún no hay proyectos. Sube tu primer plano arriba.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {projects.map((p) => (
              <Link
                key={p.project_id}
                href={`/proyecto/${p.project_id}`}
                className="card group flex items-center gap-3 p-4 transition hover:shadow-sm"
              >
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)]">
                  <FileText size={18} className="text-[var(--muted)]" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.name}</div>
                  <div className="mt-0.5">
                    <Badge tone={STATUS_TONE[p.status ?? ""] ?? "default"}>
                      {p.status ?? "—"}
                    </Badge>
                  </div>
                </div>
                <ArrowRight
                  size={18}
                  className="text-[var(--muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--primary)]"
                />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
