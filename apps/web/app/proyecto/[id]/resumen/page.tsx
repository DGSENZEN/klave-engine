"use client";

import { useCapabilities } from "@/components/Capabilities";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRef } from "react";
import {
  ArrowsClockwise,
  CheckCircle,
  CircleNotch,
  FilePlus,
  FileText,
  Ruler,
  Stack,
} from "@phosphor-icons/react";
import {
  addProjectFiles,
  apiMessage,
  hojasRepetidas,
  replaceProjectFile,
  retireProjectFile,
  getViews,
  getDimensions,
  getProject,
  getProjectReviews,
  processProject,
  getRunDiff,
  money,
  setVerification,
  type CostReport,
  type ProjectInfo,
  type RunDiff,
  type Views,
  type Dimensions,
  type ProjectReviews,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { FAMILY_LABELS } from "@/lib/families";
import { useCostReport } from "@/lib/useProjectReport";
import { phaseColor } from "@/lib/phases";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  Card,
  StatStrip,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonMetrics,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ReprocesarDialog } from "@/components/ReprocesarDialog";
import { KebabMenu, MenuItem } from "@/components/Menu";
import { timeAgo } from "@/lib/time";
import { uploadErrorMessage, validateDrawingFiles } from "@/lib/uploads";
import { moneyState, UnitsGate } from "@/components/MoneyGate";

export default function Resumen() {
  const caps = useCapabilities();
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [views, setViews] = useState<Views | null>(null);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const [reviews, setReviews] = useState<ProjectReviews | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  /** Sections that failed to load, by name; each shows its own error with a retry. */
  const [failed, setFailed] = useState<Set<"reviews" | "diff">>(() => new Set());
  const [attempt, setAttempt] = useState(0);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reprocessing, setReprocessing] = useState(false);
  const [confirmReprocess, setConfirmReprocess] = useState(false);
  const { latestEvent, connectionEpoch, actorName } = useProjectLive();

  function markFailed(key: "reviews" | "diff", value: boolean) {
    setFailed((current) => {
      const next = new Set(current);
      if (value) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getViews(id).then(setViews).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
    getProjectReviews(id)
      .then((r) => {
        setReviews(r);
        markFailed("reviews", false);
      })
      .catch(() => markFailed("reviews", true));
    getProject(id).then(setProject).catch(() => {});
    getRunDiff(id)
      .then((d) => {
        setDiff(d);
        markFailed("diff", false);
      })
      .catch(() => markFailed("diff", true));
  }, [id, connectionEpoch, attempt]);

  useEffect(() => {
    if (latestEvent?.type === "run_published") {
      getViews(id).then(setViews).catch(() => {});
      getDimensions(id).then(setDims).catch(() => {});
      getRunDiff(id).then(setDiff).catch(() => {});
    }
    if (latestEvent?.type === "run_published" || latestEvent?.type === "review_updated") {
      getProjectReviews(id).then(setReviews).catch(() => {});
    }
  }, [id, latestEvent]);

  const months = costs ? Math.round(costs.schedule.total_duration_days / 24) : 0;
  const verification = reviews?.verification;
  const verified = Boolean(
    verification?.units_confirmed_at &&
      verification?.detections_confirmed_at &&
      verification?.assumptions_confirmed_at,
  );

  async function confirmStep(step: "units" | "detections" | "assumptions", value: boolean) {
    setActionError(null);
    try {
      setReviews(await setVerification(id, step, value, actorName));
    } catch {
      setActionError(
        value ? "No se pudo marcar el paso como verificado." : "No se pudo deshacer la verificación.",
      );
    }
  }

  async function reprocessNow() {
    setActionError(null);
    setReprocessing(true);
    try {
      await processProject(id);
      setProject(await getProject(id));
    } catch {
      setActionError("No se pudo encolar el reprocesamiento; inténtalo de nuevo.");
    } finally {
      setReprocessing(false);
    }
  }

  return (
    <div className="px-4 py-5 sm:px-6">
      <ReprocesarDialog
        open={confirmReprocess}
        onConfirm={() => {
          setConfirmReprocess(false);
          void reprocessNow();
        }}
        onCancel={() => setConfirmReprocess(false)}
      />
      <PageHeader
        title={
          <span className="flex items-center gap-2.5" data-tour="resumen.sello">
            Resumen del proyecto
            {reviews &&
              (verified ? (
                <Badge tone="success" dot>
                  Verificado
                </Badge>
              ) : (
                <Badge tone="warning" dot>
                  Sin verificar
                </Badge>
              ))}
          </span>
        }
        sub={project?.client ? `Cliente: ${project.client}` : undefined}
      />

      {error && (
        <Callout tone="danger">
          No se pudo cargar el resumen de costos. Revisa que el servidor esté activo.
        </Callout>
      )}
      {actionError && (
        <div className="mb-4">
          <Callout
            tone="danger"
            action={
              <Button size="sm" variant="ghost" onClick={() => setActionError(null)}>
                Cerrar
              </Button>
            }
          >
            {actionError}
          </Callout>
        </div>
      )}
      {failed.size > 0 && (
        <div className="mb-4">
          <Callout
            tone="warning"
            action={
              <Button size="sm" onClick={() => setAttempt((n) => n + 1)}>
                Reintentar
              </Button>
            }
          >
            {failed.has("reviews")
              ? "No se pudo cargar la ruta de verificación ni las revisiones."
              : "No se pudieron cargar los cambios del último procesamiento."}
          </Callout>
        </div>
      )}

      {project?.engine?.stale && (
        <div className="mb-4">
          <Callout
            tone="info"
            action={
              caps.editProject && <Button size="sm" onClick={() => setConfirmReprocess(true)} disabled={reprocessing}>
                {reprocessing ? (
                  <CircleNotch size={14} className="animate-spin" />
                ) : (
                  <ArrowsClockwise size={14} />
                )}
                {reprocessing ? "Encolando…" : "Reprocesar"}
              </Button>
            }
          >
            Este proyecto se leyó con una versión anterior del motor
            {project.engine.processed_at ? ` (${timeAgo(project.engine.processed_at)})` : ""}.
            Reprocesa para aplicar las mejoras de lectura; tus revisiones y ajustes se conservan.
          </Callout>
        </div>
      )}

      {/* Rendered above the gate below, on the blocked project's own page:
          without the flag it showed the peso delta of the total the gate
          three lines down is withholding. The family counts stay — those are
          the reading, and they are the reason to look at this card. */}
      {diff?.available && (
        <RunDiffCard diff={diff} blocked={!costs || moneyState(costs) === "blocked"} />
      )}

      {costs && reviews && !verified && (
        <VerificationPath
          id={id}
          costs={costs}
          reviews={reviews}
          onConfirm={confirmStep}
        />
      )}

      {costs && moneyState(costs) === "blocked" && (
        <div className="mb-6">
          <UnitsGate id={id} costs={costs} actorName={actorName} />
          {/* El arreglo que el candado pide —corregir el archivo— es
              reemplazar la hoja: la lista no se esconde tras él. */}
          {project && <SheetsCard id={id} project={project} />}
        </div>
      )}

      {costs && moneyState(costs) !== "blocked" && (
        <div>
          <StatStrip
            stats={[
              { label: "Costo directo", value: money(costs.integration.direct_cost) },
              {
                label: "Precio de venta",
                value: money(costs.integration.sale_price),
                hint: `factor ${costs.integration.overcost_factor.toFixed(3)}`,
              },
              {
                label: "Total c/ contingencia",
                value: money(costs.integration.grand_total),
                tone: "accent",
              },
              {
                label: "Plazo estimado",
                value: `${costs.schedule.total_duration_days} días`,
                hint: `~${months} meses · ${costs.schedule.phases.length} fases`,
              },
            ]}
          />

          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card className="p-4 lg:col-span-2">
              <SectionTitle sub="Importe del costo directo por fase de obra">
                Costo directo por fase
              </SectionTitle>
              <PhaseBars totals={costs.boq.totals_by_phase} />
            </Card>

            <Card className="p-4">
              <div className="flex items-start justify-between gap-3">
                <SectionTitle>Lectura del plano</SectionTitle>
                <Link
                  href={`/proyecto/${id}/lectura`}
                  className="shrink-0 text-xs font-medium text-accent hover:underline"
                >
                  Ver lectura completa
                </Link>
              </div>
              <dl className="space-y-2 text-[13px]">
                <Row
                  icon={<Ruler />}
                  label="Unidades"
                  value={`${costs.drawing_units.unit} · ${Math.round(
                    costs.drawing_units.confidence * 100,
                  )}%`}
                />
                {views?.is_segmented && (
                  <Row
                    icon={<Stack />}
                    label="Vistas de planta"
                    value={`${views.views.filter((v) => v.kind === "plan").length} · NPT ${
                      views.npt_levels.length
                    }`}
                  />
                )}
                {dims && (
                  <>
                    <Row
                      icon={<Ruler />}
                      label="Cotas leídas"
                      value={`${dims.dimension_count}`}
                    />
                    {dims.typical_wall_thickness_cm && (
                      <Row
                        label="Espesor de muro"
                        value={`${dims.typical_wall_thickness_cm} cm`}
                      />
                    )}
                    {dims.vigueta_system && (
                      <Row label="Sistema de losa" value={`vigueta ${dims.vigueta_system}`} />
                    )}
                  </>
                )}
              </dl>
            </Card>
          </div>

          {project && <SheetsCard id={id} project={project} />}

          <p className="mt-6 text-xs text-muted">
            Precios de insumos de referencia (MXN); sustituir por cotizaciones del proyecto.
            Cantidades deduplicadas por vista; revisar conceptos de baja confianza.
          </p>
        </div>
      )}

      {!costs && !error && (
        <div>
          <SkeletonMetrics count={4} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <Skeleton className="h-4 w-40" />
              <div className="mt-5 space-y-4">
                {Array.from({ length: 3 }, (_, i) => (
                  <div key={i}>
                    <div className="mb-2 flex justify-between">
                      <Skeleton className="h-3.5 w-28" />
                      <Skeleton className="h-3.5 w-20" />
                    </div>
                    <Skeleton className="h-2.5" />
                  </div>
                ))}
              </div>
            </Card>
            <Card className="p-4">
              <Skeleton className="h-4 w-32" />
              <div className="mt-5 space-y-3">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i} className="flex justify-between">
                    <Skeleton className="h-3.5 w-24" />
                    <Skeleton className="h-3.5 w-16" />
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function SheetsCard({ id, project }: { id: string; project: ProjectInfo }) {
  const caps = useCapabilities();
  const inputRef = useRef<HTMLInputElement>(null);
  const replaceRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Una hoja con un número que ya está: casi siempre es su revisión, y
  // sumarla contaría dos veces la misma hoja. Se pregunta antes.
  const [repetidas, setRepetidas] = useState<{
    files: File[];
    pares: { nueva: string; existente: string }[];
  } | null>(null);
  const [reemplazar, setReemplazar] = useState<string | null>(null);
  const [retirar, setRetirar] = useState<string | null>(null);

  const nombre = (path: string) => path.split("/").pop() ?? path;
  const etiqueta = (path: string) =>
    project.source_files.find((s) => nombre(s.path) === path)?.sheet_number ?? path;

  async function subir(files: File[], modo?: "reemplazar" | "agregar") {
    setBusy(true);
    setError(null);
    try {
      await addProjectFiles(id, files, getBrowserActor(), modo);
      setRepetidas(null);
      // The re-enqueued job flips the project gate to the processing screen.
    } catch (e) {
      const pares = modo ? null : hojasRepetidas(e);
      if (pares) setRepetidas({ files, pares });
      else setError(uploadErrorMessage(e, "No se pudieron agregar las hojas."));
      setBusy(false);
    }
  }

  function onFiles(list: FileList) {
    const files = [...list].filter((f) => /\.(dwg|dxf)$/i.test(f.name));
    if (files.length === 0) return;
    // Mismo límite que la subida inicial: todo viaja en una sola petición.
    const invalid = validateDrawingFiles(files);
    if (invalid) {
      setError(invalid);
      return;
    }
    void subir(files);
  }

  async function onReplacement(file: File) {
    const hoja = reemplazar;
    setReemplazar(null);
    if (!hoja) return;
    const invalid = validateDrawingFiles([file]);
    if (invalid) {
      setError(invalid);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await replaceProjectFile(id, hoja, file, getBrowserActor());
    } catch (e) {
      setError(uploadErrorMessage(e, "No se pudo reemplazar la hoja."));
      setBusy(false);
    }
  }

  async function onRetire(hoja: string) {
    setRetirar(null);
    setBusy(true);
    setError(null);
    try {
      await retireProjectFile(id, hoja, getBrowserActor());
    } catch (e) {
      setError(apiMessage(e, "No se pudo retirar la hoja."));
      setBusy(false);
    }
  }

  const unica = project.source_files.length <= 1;
  return (
    <Card className="mt-4 p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionTitle sub="Todas las hojas se leen como un solo conjunto. Una revisión nueva reemplaza a su hoja; agregar, reemplazar o retirar vuelve a procesar el proyecto.">
          Hojas del proyecto ({project.source_files.length})
        </SectionTitle>
        <input
          ref={inputRef}
          type="file"
          accept=".dwg,.dxf"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) onFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={replaceRef}
          type="file"
          accept=".dwg,.dxf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void onReplacement(file);
            e.target.value = "";
          }}
        />
        {caps.manageProject && <Button size="sm" onClick={() => inputRef.current?.click()} disabled={busy}>
          {busy ? (
            <CircleNotch size={14} className="animate-spin" />
          ) : (
            <FilePlus size={14} />
          )}
          {busy ? "Procesando…" : "Agregar hojas y reprocesar"}
        </Button>}
      </div>
      {error && <p className="mb-2 text-sm text-danger">{error}</p>}
      {repetidas && (
        <div className="mb-3 space-y-2 rounded-lg bg-warning-soft px-4 py-3 text-sm text-warning">
          <p className="font-medium">
            {repetidas.pares.length === 1
              ? "Esta hoja ya está en el proyecto:"
              : `Estas ${repetidas.pares.length} hojas ya están en el proyecto:`}
          </p>
          <ul className="space-y-0.5">
            {repetidas.pares.map((p) => (
              <li key={p.nueva}>
                {p.nueva} → {etiqueta(p.existente)} ({p.existente})
              </li>
            ))}
          </ul>
          <p>
            Si son su revisión nueva, reemplázalas: la anterior se guarda aparte y «Cambios»
            compara las dos. Agregarlas como hojas nuevas contaría dos veces lo que repiten.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              size="sm"
              variant="primary"
              disabled={busy}
              onClick={() => void subir(repetidas.files, "reemplazar")}
            >
              Reemplazar y reprocesar
            </Button>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => void subir(repetidas.files, "agregar")}
            >
              Agregar como hojas nuevas
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRepetidas(null)}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
      <ul className="divide-y divide-border rounded-lg border border-border">
        {project.source_files.map((sheet) => {
          const archivo = nombre(sheet.path);
          return (
            <li key={sheet.file_id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <FileText className="shrink-0 text-muted" />
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium text-foreground">
                  {sheet.sheet_number ?? archivo}
                </span>
                {sheet.sheet_number && (
                  <span className="ml-2 text-xs text-muted">{archivo}</span>
                )}
              </span>
              <span className="text-xs uppercase text-faint">{sheet.file_type}</span>
              {caps.manageProject && <KebabMenu label={`Opciones de ${sheet.sheet_number ?? archivo}`}>
                {(close) => (
                  <>
                    <MenuItem
                      onSelect={() => {
                        close();
                        setReemplazar(archivo);
                        replaceRef.current?.click();
                      }}
                      hint="La revisión nueva ocupa su lugar; la anterior se guarda aparte."
                    >
                      Reemplazar con otra revisión
                    </MenuItem>
                    {!unica && (
                      <MenuItem
                        danger
                        onSelect={() => {
                          close();
                          setRetirar(archivo);
                        }}
                        hint="Deja de leerse; el archivo se guarda aparte."
                      >
                        Retirar del proyecto
                      </MenuItem>
                    )}
                  </>
                )}
              </KebabMenu>}
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={retirar !== null}
        title={`Retirar ${retirar ? etiqueta(retirar) : "la hoja"}`}
        description="Deja de leerse y el proyecto se vuelve a procesar sin ella: sus cantidades salen del presupuesto. El archivo se guarda aparte; para volver a usarlo, súbelo de nuevo."
        confirmLabel="Retirar y reprocesar"
        onConfirm={() => retirar && void onRetire(retirar)}
        onCancel={() => setRetirar(null)}
      />
    </Card>
  );
}

function RunDiffCard({ diff, blocked }: { diff: RunDiff; blocked: boolean }) {
  const families = Object.entries(diff.families ?? {}).filter(
    ([, counts]) => counts.prev !== counts.new,
  );
  const totalDelta =
    !blocked && diff.prev_grand_total != null && diff.new_grand_total != null
      ? diff.new_grand_total - diff.prev_grand_total
      : null;
  const changed =
    families.length > 0 ||
    (diff.added_labels?.length ?? 0) > 0 ||
    (diff.removed_labels?.length ?? 0) > 0 ||
    (totalDelta != null && Math.abs(totalDelta) > 0.5);
  if (!changed) return null;
  return (
    <Card className="mb-4 p-4">
      <SectionTitle sub="Comparado con el procesamiento anterior de este proyecto.">
        Cambios del último procesamiento
      </SectionTitle>
      <div className="flex flex-wrap gap-2">
        {families.map(([family, counts]) => (
          <span
            key={family}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 text-xs"
          >
            {FAMILY_LABELS[family] ?? family}
            <span className="tabular text-muted">{counts.prev}</span>
            <span className="text-faint">→</span>
            <span
              className={`tabular font-semibold ${
                counts.new > counts.prev ? "text-success" : "text-danger"
              }`}
            >
              {counts.new}
            </span>
          </span>
        ))}
        {totalDelta != null && Math.abs(totalDelta) > 0.5 && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium ${
              totalDelta > 0 ? "text-danger" : "text-success"
            }`}
          >
            Total {totalDelta > 0 ? "▲" : "▼"} {money(Math.abs(totalDelta))}
          </span>
        )}
      </div>
      {((diff.added_labels?.length ?? 0) > 0 || (diff.removed_labels?.length ?? 0) > 0) && (
        <p className="mt-3 text-xs text-muted">
          {(diff.added_labels?.length ?? 0) > 0 && (
            <>Nuevos: {diff.added_labels?.slice(0, 8).join(", ")}. </>
          )}
          {(diff.removed_labels?.length ?? 0) > 0 && (
            <>Ya no aparecen: {diff.removed_labels?.slice(0, 8).join(", ")}.</>
          )}
        </p>
      )}
    </Card>
  );
}

function VerificationPath({
  id,
  costs,
  reviews,
  onConfirm,
}: {
  id: string;
  costs: CostReport;
  reviews: ProjectReviews;
  onConfirm: (step: "units" | "detections" | "assumptions", value: boolean) => void;
}) {
  const caps = useCapabilities();
  const v = reviews.verification;
  const steps = [
    {
      key: "units" as const,
      title: "Unidades del plano",
      detail: `${costs.drawing_units.unit} · confianza ${Math.round(
        costs.drawing_units.confidence * 100,
      )}%. Si no corresponde, corrige el archivo y vuelve a procesar.`,
      done: Boolean(v.units_confirmed_at),
      by: v.units_confirmed_by,
      href: null,
      linkLabel: null,
    },
    {
      key: "detections" as const,
      title: "Elementos revisados",
      detail:
        reviews.summary.confirmed + reviews.summary.excluded > 0
          ? `${reviews.summary.confirmed} confirmadas · ${reviews.summary.excluded} excluidas. Confirma cuando el plano esté revisado.`
          : "Recorre el plano: confirma lo correcto y excluye lo que no sea un elemento real.",
      done: Boolean(v.detections_confirmed_at),
      by: v.detections_confirmed_by,
      href: `/proyecto/${id}/plano`,
      linkLabel: "Ir al plano",
    },
    {
      key: "assumptions" as const,
      title: "Supuestos de cálculo",
      detail:
        "Alturas, secciones y porcentajes que convierten elementos en cantidades y dinero.",
      done: Boolean(v.assumptions_confirmed_at),
      by: v.assumptions_confirmed_by,
      href: `/proyecto/${id}/parametros`,
      linkLabel: "Ver parámetros",
    },
  ];

  return (
    <Card className="mb-4 p-4" tour="resumen.verificacion">
      <SectionTitle sub="Verifica la lectura del plano antes de confiar en las cifras. Tres pasos, una vez por procesamiento.">
        Ruta de verificación
      </SectionTitle>
      <div className="divide-y divide-border">
        {steps.map((step, index) => (
          <div
            key={step.key}
            // The actions drop under the text on narrow screens rather than
            // squeezing «Unidades del plano» into a one-word column.
            className="flex flex-wrap items-start gap-x-3 gap-y-2 py-2.5"
          >
            {step.done ? (
              <span
                title={`Verificado${step.by ? ` por ${step.by}` : ""}`}
                className="mt-0.5 shrink-0 text-success"
              >
                <CheckCircle size={20} weight="fill" />
              </span>
            ) : (
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border-strong text-xs font-semibold text-muted">
                {index + 1}
              </span>
            )}
            <div className="min-w-0 flex-1 basis-64">
              <div className={`text-sm font-medium ${step.done ? "text-muted line-through" : ""}`}>
                {step.title}
              </div>
              <p className="mt-0.5 text-[13px] text-muted">
                {step.done && step.by ? `Verificado por ${step.by}. ` : ""}
                {step.detail}
              </p>
            </div>
            <div className="ml-8 flex shrink-0 items-center gap-2 sm:ml-0">
              {step.href && !step.done && (
                <Link href={step.href} className={buttonClasses("ghost", "sm")}>
                  {step.linkLabel}
                </Link>
              )}
              {!caps.editProject ? null : step.done ? (
                <Button size="sm" variant="ghost" onClick={() => onConfirm(step.key, false)}>
                  Deshacer
                </Button>
              ) : (
                <Button size="sm" onClick={() => onConfirm(step.key, true)}>
                  Marcar como verificado
                </Button>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Row({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <dt className="flex items-center gap-2 text-muted">
        {icon}
        {label}
      </dt>
      <dd className="font-medium tabular">{value}</dd>
    </div>
  );
}

function PhaseBars({ totals }: { totals: Record<string, number> }) {
  const entries = Object.entries(totals);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  const sum = entries.reduce((acc, [, v]) => acc + v, 0) || 1;
  return (
    <div className="space-y-4">
      {entries.map(([phase, value], index) => (
        <div key={phase}>
          <div className="mb-1.5 flex items-baseline justify-between text-sm">
            <span className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ background: phaseColor(phase, index) }}
              />
              {phase}
              <span className="text-xs text-muted">
                {((value / sum) * 100).toFixed(0)}%
              </span>
            </span>
            <span className="font-medium tabular">{money(value)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-surface-2">
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{
                width: `${(value / max) * 100}%`,
                background: phaseColor(phase, index),
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
