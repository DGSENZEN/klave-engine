"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useRef } from "react";
import {
  CheckCircle,
  CircleNotch,
  FilePlus,
  FileText,
  Ruler,
  Stack,
  Money,
  TrendUp,
  ShieldCheck,
  CalendarBlank,
} from "@phosphor-icons/react";
import {
  addProjectFiles,
  getViews,
  getDimensions,
  getProject,
  getProjectReviews,
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
import { FAMILY_LABELS } from "@/components/PlanoCanvas";
import { useCostReport } from "@/lib/useProjectReport";
import { phaseColor } from "@/lib/phases";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  Card,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonMetrics,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function Resumen() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [views, setViews] = useState<Views | null>(null);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const [reviews, setReviews] = useState<ProjectReviews | null>(null);
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const { latestEvent, connectionEpoch, actorName } = useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getViews(id).then(setViews).catch(() => {});
    getDimensions(id).then(setDims).catch(() => {});
    getProjectReviews(id).then(setReviews).catch(() => {});
    getProject(id).then(setProject).catch(() => {});
    getRunDiff(id).then(setDiff).catch(() => {});
  }, [id, connectionEpoch]);

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
    try {
      setReviews(await setVerification(id, step, value, actorName));
    } catch {}
  }

  return (
    <div className="px-6 py-7 lg:px-8">
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
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

      {diff?.available && <RunDiffCard diff={diff} />}

      {costs && reviews && !verified && (
        <VerificationPath
          id={id}
          costs={costs}
          reviews={reviews}
          onConfirm={confirmStep}
        />
      )}

      {costs && (
        <div className="rise-in">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Costo directo"
              value={money(costs.integration.direct_cost)}
              icon={<Money size={16} weight="duotone" />}
            />
            <Metric
              label="Precio de venta"
              value={money(costs.integration.sale_price)}
              hint={`factor ${costs.integration.overcost_factor.toFixed(3)}`}
              icon={<TrendUp size={16} weight="duotone" />}
            />
            <Metric
              label="Total c/ contingencia"
              value={money(costs.integration.grand_total)}
              accent="accent"
              icon={<ShieldCheck size={16} weight="duotone" />}
            />
            <Metric
              label="Plazo estimado"
              value={`${costs.schedule.total_duration_days} días`}
              hint={`~${months} meses · ${costs.schedule.phases.length} fases`}
              icon={<CalendarBlank size={16} weight="duotone" />}
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <Card className="p-5 lg:col-span-2">
              <SectionTitle sub="Importe del costo directo por fase de obra">
                Costo directo por fase
              </SectionTitle>
              <PhaseBars totals={costs.boq.totals_by_phase} />
            </Card>

            <Card className="p-5">
              <div className="flex items-start justify-between gap-3">
                <SectionTitle>Lectura del plano</SectionTitle>
                <Link
                  href={`/proyecto/${id}/lectura`}
                  className="shrink-0 text-xs font-medium text-accent hover:underline"
                >
                  Ver lectura completa
                </Link>
              </div>
              <dl className="space-y-3 text-sm">
                <Row
                  icon={<Ruler size={15} />}
                  label="Unidades"
                  value={`${costs.drawing_units.unit} · ${Math.round(
                    costs.drawing_units.confidence * 100,
                  )}%`}
                />
                {views?.is_segmented && (
                  <Row
                    icon={<Stack size={15} />}
                    label="Vistas de planta"
                    value={`${views.views.filter((v) => v.kind === "plan").length} · NPT ${
                      views.npt_levels.length
                    }`}
                  />
                )}
                {dims && (
                  <>
                    <Row
                      icon={<Ruler size={15} />}
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
            <Card className="p-5">
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
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onFiles(list: FileList) {
    const files = [...list].filter((f) => /\.(dwg|dxf)$/i.test(f.name));
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await addProjectFiles(id, files, getBrowserActor());
      // The re-enqueued job flips the project gate to the processing screen.
    } catch {
      setError("No se pudieron agregar las hojas.");
      setBusy(false);
    }
  }

  return (
    <Card className="mt-4 p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <SectionTitle sub="Todas las hojas se leen como un solo conjunto; agregar hojas vuelve a procesar el proyecto.">
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
        <Button size="sm" onClick={() => inputRef.current?.click()} disabled={busy}>
          {busy ? (
            <CircleNotch size={14} className="animate-spin" />
          ) : (
            <FilePlus size={14} weight="bold" />
          )}
          Agregar hojas
        </Button>
      </div>
      {error && <p className="mb-2 text-sm text-danger">{error}</p>}
      <div className="flex flex-wrap gap-2">
        {project.source_files.map((sheet) => (
          <span
            key={sheet.file_id}
            title={sheet.path}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 text-xs"
          >
            <FileText size={13} className="text-muted" />
            {sheet.sheet_number ?? sheet.path.split("/").pop()}
            <span className="uppercase text-faint">{sheet.file_type}</span>
          </span>
        ))}
      </div>
    </Card>
  );
}

function RunDiffCard({ diff }: { diff: RunDiff }) {
  const families = Object.entries(diff.families ?? {}).filter(
    ([, counts]) => counts.prev !== counts.new,
  );
  const totalDelta =
    diff.prev_grand_total != null && diff.new_grand_total != null
      ? diff.new_grand_total - diff.prev_grand_total
      : null;
  const changed =
    families.length > 0 ||
    (diff.added_labels?.length ?? 0) > 0 ||
    (diff.removed_labels?.length ?? 0) > 0 ||
    (totalDelta != null && Math.abs(totalDelta) > 0.5);
  if (!changed) return null;
  return (
    <Card className="rise-in mb-6 p-5">
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
      title: "Detecciones revisadas",
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
        "Alturas, secciones y porcentajes que convierten detecciones en cantidades y dinero.",
      done: Boolean(v.assumptions_confirmed_at),
      by: v.assumptions_confirmed_by,
      href: `/proyecto/${id}/parametros`,
      linkLabel: "Ver parámetros",
    },
  ];

  return (
    <Card className="rise-in mb-6 p-5">
      <SectionTitle sub="Verifica la lectura del plano antes de confiar en las cifras. Tres pasos, una vez por procesamiento.">
        Ruta de verificación
      </SectionTitle>
      <div className="space-y-1">
        {steps.map((step, index) => (
          <div
            key={step.key}
            className="flex items-start gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-surface-2/50"
          >
            {step.done ? (
              <button
                type="button"
                title={`Verificado${step.by ? ` por ${step.by}` : ""} — clic para deshacer`}
                onClick={() => onConfirm(step.key, false)}
                className="mt-0.5 shrink-0 text-success"
              >
                <CheckCircle size={20} weight="fill" />
              </button>
            ) : (
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border-strong text-[11px] font-semibold text-muted">
                {index + 1}
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-medium ${step.done ? "text-muted line-through" : ""}`}>
                {step.title}
              </div>
              <p className="mt-0.5 text-sm text-muted">{step.detail}</p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {step.href && !step.done && (
                <Link href={step.href} className={buttonClasses("ghost", "sm")}>
                  {step.linkLabel}
                </Link>
              )}
              {!step.done && (
                <Button size="sm" onClick={() => onConfirm(step.key, true)}>
                  Confirmar
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
