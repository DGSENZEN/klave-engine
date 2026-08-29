"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Buildings,
  CheckCircle,
  CircleNotch,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  ApiError,
  getProject,
  getStatus,
  processProject,
  type ProjectStatus,
} from "@/lib/api";
import { parseProjectEvent, projectEventsUrl } from "@/lib/collab";
import { ProjectLiveProvider } from "@/components/ProjectLive";
import { ProjectShell } from "@/components/ProjectShell";
import { Button, Callout, Skeleton, SkeletonHeader, buttonClasses } from "@/components/ui";

const STEPS = [
  { key: "ingested", label: "Ingesta del proyecto" },
  { key: "converted", label: "Conversión DWG → DXF" },
  { key: "parsed", label: "Lectura de entidades" },
  { key: "processed", label: "Detección, vistas y costos" },
];

// Qué está haciendo el motor en cada paso, en frases honestas que rotan:
// la pantalla dice trabajo real, nunca inventa cifras.
const STEP_DETAIL: Record<string, string[]> = {
  ingested: ["Registrando las hojas del proyecto…", "Preparando la carpeta de trabajo…"],
  converted: [
    "Convirtiendo cada DWG a DXF…",
    "Verificando qué tan completa quedó cada conversión…",
    "Resolviendo referencias externas…",
  ],
  parsed: [
    "Leyendo entidades y capas…",
    "Reventando bloques y sus atributos…",
    "Detectando la unidad de dibujo…",
    "Armando el índice de prefabricados…",
  ],
  processed: [
    "Detectando ejes, columnas y zapatas…",
    "Cerrando tableros de losa entre trabes…",
    "Leyendo corridas de instalación por diámetro…",
    "Segmentando plantas y niveles…",
    "Cuantificando conceptos y armando el presupuesto…",
  ],
};

const ORDER = ["queued", "ingested", "converted", "running", "parsed", "processed"];
// El estado terminal no se queda esperando eventos; todo lo demás sí.
const TERMINAL = new Set(["processed", "failed"]);
const POLL_MS = 5000;

export default function ProjectLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [name, setName] = useState<string | undefined>(undefined);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let active = true;
    getStatus(id)
      .then((s) => {
        if (active) {
          setStatus(s);
          setLoadError(null);
        }
      })
      .catch((e: unknown) => {
        if (!active) return;
        const notFound = e instanceof ApiError && e.status === 404;
        setLoadError(
          notFound
            ? "Este proyecto no existe o no tienes acceso a él."
            : "No se pudo consultar el estado del proyecto. ¿Está activo el servidor?",
        );
      });
    getProject(id)
      .then((p) => {
        if (active) setName(p.project_name || undefined);
      })
      .catch(() => {});

    // Stay subscribed even when processed: adding sheets re-enqueues the
    // project and the gate must flip back to the processing timeline.
    const source = new EventSource(projectEventsUrl(id), { withCredentials: true });
    // El bus de eventos vive en memoria con ventana corta: una reconexión
    // pudo saltarse el evento terminal. Cada (re)apertura vuelve a
    // preguntar el estado — el empuje avisa rápido, el jalón no se pierde.
    source.onopen = () => {
      getStatus(id)
        .then((s) => {
          if (active) setStatus(s);
        })
        .catch(() => {});
    };
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
  }, [id, attempt]);

  // Mientras el proyecto procesa, el estado también se jala por intervalo:
  // si el evento terminal se perdió (pestaña dormida, stream caído, ventana
  // del bus rebasada), la pantalla de procesamiento no puede quedarse
  // varada — era el bug de «terminó y no llegó la pantalla principal».
  const processing = status !== null && !TERMINAL.has(status.state);
  useEffect(() => {
    if (!processing) return;
    let active = true;
    const refetch = () => {
      getStatus(id)
        .then((s) => {
          if (active) setStatus(s);
        })
        .catch(() => {});
    };
    const timer = window.setInterval(refetch, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") refetch();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [id, processing]);

  // El reloj de la pantalla de procesamiento: rota la frase del paso actual
  // y cuenta el tiempo transcurrido. Texto que cambia, no animación.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [processing]);

  const failed = status?.state === "failed";
  const notStarted =
    status !== null && !ORDER.includes(status.state) && status.state !== "failed";

  async function startProcessing() {
    setStarting(true);
    try {
      await processProject(id);
      setAttempt((n) => n + 1);
    } catch {
      setLoadError("No se pudo iniciar el procesamiento.");
    } finally {
      setStarting(false);
    }
  }

  // Failure stays useful: with readable artifacts from a previous (or
  // partial) run, the full shell opens — viewer, lectura, adjustments —
  // behind an explicit warning instead of a dead end.
  if (status?.state === "processed" || (failed && status.artifacts_available)) {
    return (
      <ProjectLiveProvider projectId={id}>
        <ProjectShell id={id} name={name}>
          {failed && (
            <div className="px-6 pt-5 lg:px-8">
              <Callout tone="danger">
                El último procesamiento falló
                {status?.error ? `: ${status.error}` : "."} Estás viendo los datos del
                último procesamiento legible; revisa la Lectura del Plano y corrige el
                archivo.
              </Callout>
            </div>
          )}
          {children}
        </ProjectShell>
      </ProjectLiveProvider>
    );
  }
  const reached = (key: string) => {
    const current = ORDER.indexOf(status?.state ?? "queued");
    return current >= ORDER.indexOf(key);
  };

  if (loadError) {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
        <Link href="/" className="mb-8 inline-flex items-center gap-2 text-sm text-muted">
          <Buildings size={16} weight="duotone" /> Klave
        </Link>
        <h1 className="text-xl font-semibold">No se pudo abrir el proyecto</h1>
        <p className="mt-1 text-sm text-muted">{loadError}</p>
        <div className="mt-5 flex gap-2">
          <Button variant="primary" onClick={() => setAttempt((n) => n + 1)}>
            Reintentar
          </Button>
          <Link href="/" className="inline-flex">
            <Button>Volver a proyectos</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (status === null) {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
        <SkeletonHeader />
        <Skeleton className="h-48" />
      </div>
    );
  }

  if (notStarted || (failed && !status.artifacts_available)) {
    return (
      <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
        <Link href="/" className="mb-8 inline-flex items-center gap-2 text-sm text-muted">
          <Buildings size={16} weight="duotone" /> Klave
        </Link>
        <h1 className="text-xl font-semibold">
          {failed ? "No se pudo procesar el plano" : "Este proyecto aún no se procesa"}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {failed
            ? `El último intento falló${status.error ? `: ${status.error}` : "."} Revisa el archivo en Lectura del Plano cuando termine, o inténtalo de nuevo.`
            : "Los archivos están subidos. Al procesar leemos las entidades, detectamos elementos y calculamos el presupuesto."}
        </p>
        <div className="mt-5 flex gap-2">
          <Button variant="primary" onClick={startProcessing} disabled={starting}>
            {starting ? "Iniciando…" : failed ? "Intentar de nuevo" : "Procesar ahora"}
          </Button>
          <Link href="/" className="inline-flex">
            <Button>Volver a proyectos</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6">
      <Link
        href="/"
        className="mb-8 inline-flex items-center gap-2 text-sm text-muted transition hover:text-foreground"
      >
        <Buildings size={16} weight="duotone" /> Klave
      </Link>
      <h1 className="flex items-baseline gap-3 text-xl font-semibold">
        {failed ? "No se pudo procesar el plano" : "Procesando tu plano…"}
        {!failed && tick >= 3 && (
          <span className="tabular text-sm font-normal text-faint">
            {Math.floor(tick / 60)}:{String(tick % 60).padStart(2, "0")}
          </span>
        )}
      </h1>
      <p className="mt-1 text-sm text-muted">
        {failed
          ? "Revisa el archivo e inténtalo de nuevo."
          : status?.stage && status.stage !== "Desconocido"
            ? status.stage
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
                <WarningCircle size={20} weight="fill" className="shrink-0 text-warning" />
              ) : done || isProcessed ? (
                <CheckCircle size={20} weight="fill" className="shrink-0 text-success" />
              ) : isCurrent ? (
                <CircleNotch size={20} className="shrink-0 animate-spin text-accent" />
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
                {isCurrent && !failed && (
                  <span className="block text-xs font-normal text-faint">
                    {STEP_DETAIL[step.key][
                      Math.floor(tick / 4) % STEP_DETAIL[step.key].length
                    ]}
                  </span>
                )}
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
        <Link href="/" className={buttonClasses("primary", "md", "mt-6 w-fit")}>
          <ArrowLeft size={15} weight="bold" /> Volver e intentar de nuevo
        </Link>
      )}
    </div>
  );
}
