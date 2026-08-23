"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Check,
  CircleNotch,
  DownloadSimple,
  FileXls,
  PencilSimpleLine,
  Trash,
  Warning,
  X,
} from "@phosphor-icons/react";
import {
  addAdjustment,
  apiMessage,
  downloadFile,
  croquisUrl,
  getCatalog,
  getCroquis,
  getDimensions,
  getProjectReviews,
  money,
  money2,
  num,
  removeAdjustment,
  type BoqLine,
  type CatalogConcept,
  type CroquisItem,
  type Dimensions,
  type ProjectReviews,
} from "@/lib/api";
import { useCostReport } from "@/lib/useProjectReport";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  Card,
  EmptyState,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  SkeletonHeader,
  SkeletonMetrics,
  SkeletonTable,
  TableCard,
  Td,
  Th,
} from "@/components/ui";
import { ButtonMenu, MenuItem } from "@/components/Menu";
import { useProjectLive } from "@/components/ProjectLive";
import { moneyGate, UnitsGate, UnverifiedBanner } from "@/components/MoneyGate";
import { VersionsPanel } from "@/components/VersionsPanel";
import { ConceptPicker } from "@/components/ConceptPicker";
import { IndicatorsCard } from "@/components/IndicatorsCard";
import { SuggestionsBar } from "@/components/SuggestionsBar";

export default function PresupuestoPage() {
  const { id } = useParams<{ id: string }>();
  const { costs, error } = useCostReport(id);
  const [dims, setDims] = useState<Dimensions | null>(null);
  const [reviews, setReviews] = useState<ProjectReviews | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [concepts, setConcepts] = useState<CatalogConcept[] | null>(null);
  const { latestEvent, sendActivity, connectionEpoch, actorName, clientId } =
    useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getDimensions(id).then(setDims).catch(() => {});
    getProjectReviews(id).then(setReviews).catch(() => {});
    getCatalog()
      .then((catalog) => setConcepts(catalog.concepts))
      .catch(() => {});
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type === "run_published") {
      getDimensions(id).then(setDims).catch(() => {});
    }
    if (latestEvent?.type === "run_published" || latestEvent?.type === "review_updated") {
      getProjectReviews(id).then(setReviews).catch(() => {});
    }
  }, [id, latestEvent]);

  function downloadCsv() {
    if (!costs) return;
    sendActivity("exporting_budget", "Presupuesto CSV");
    const rows = [
      ["clave", "concepto", "unidad", "cantidad", "p_unitario", "importe", "fase", "confianza"],
      ...costs.boq.lines.map((l) => [
        l.concept_code,
        `"${l.description}"`,
        l.unit,
        l.quantity,
        l.unit_price,
        l.amount,
        l.phase,
        l.confidence,
      ]),
      [],
      ["", "COSTO DIRECTO", "", "", "", costs.boq.direct_cost_total],
      ["", "PRECIO DE VENTA", "", "", "", costs.integration.sale_price],
      ["", "TOTAL", "", "", "", costs.integration.grand_total],
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "presupuesto.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Presupuesto" />
        <Callout tone="danger">
          No se pudo cargar el presupuesto. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!costs) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <SkeletonMetrics count={3} />
        <SkeletonTable rows={8} />
      </div>
    );
  }

  if (moneyGate(costs, reviews) === "blocked") {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Presupuesto" />
        <UnitsGate id={id} costs={costs} actorName={actorName} />
      </div>
    );
  }

  const parametricCount = costs.boq.lines.filter((l) => l.parametric).length;
  const conceptCodes = new Set(costs.boq.lines.map((l) => l.concept_code));
  const avgConf =
    costs.boq.lines.reduce((s, l) => s + l.confidence, 0) / (costs.boq.lines.length || 1);
  const phases = [...new Set(costs.boq.lines.map((l) => l.phase))];

  async function exportFile(label: string, path: string, fallbackName: string) {
    sendActivity("exporting_budget", label);
    setExporting(label);
    setExportError(null);
    try {
      await downloadFile(path, fallbackName);
    } catch (e) {
      setExportError(apiMessage(e, `No se pudo generar «${label}».`));
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Presupuesto"
        sub="Cantidades deducidas del plano · precios de referencia (MXN)"
        actions={
          <ButtonMenu
            label={exporting ? `Generando ${exporting}…` : "Exportar"}
            icon={
              exporting ? (
                <CircleNotch size={16} className="animate-spin" />
              ) : (
                <DownloadSimple size={16} weight="bold" />
              )
            }
          >
            {(close) => (
              <>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Excel Klave", `/projects/${id}/export/presupuesto.xlsx`, "presupuesto.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Excel completo (Klave)
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Excel OPUS", `/projects/${id}/export/presupuesto.xlsx?format=opus`, "presupuesto.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Excel para OPUS
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Excel Neodata", `/projects/${id}/export/presupuesto.xlsx?format=neodata`, "presupuesto.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Excel para Neodata
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Catálogo de licitación", `/projects/${id}/export/presupuesto.xlsx?format=licitacion`, "presupuesto.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Catálogo de licitación (P.U. con letra)
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Catálogo de licitación (descripciones largas)", `/projects/${id}/export/presupuesto.xlsx?format=licitacion_larga`, "presupuesto.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Licitación con descripciones LOPSRM
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    void exportFile("Explosión de insumos", `/projects/${id}/export/explosion.xlsx`, "explosion_insumos.xlsx");
                  }}
                >
                  <FileXls size={15} weight="duotone" /> Explosión de insumos
                </MenuItem>
                <MenuItem
                  onSelect={() => {
                    close();
                    downloadCsv();
                  }}
                >
                  <DownloadSimple size={15} weight="bold" /> CSV simple
                </MenuItem>
              </>
            )}
          </ButtonMenu>
        }
      />

      {exportError && (
        <div className="mb-4">
          <Callout
            tone="danger"
            action={
              <Button size="sm" variant="ghost" onClick={() => setExportError(null)}>
                Cerrar
              </Button>
            }
          >
            {exportError}
          </Callout>
        </div>
      )}
      <UnverifiedBanner id={id} costs={costs} reviews={reviews} />
      <SuggestionsBar projectId={id} actorName={actorName} conceptCodes={conceptCodes} />
      {parametricCount > 0 && (
        <div className="mb-4">
          <Callout tone="info">
            {parametricCount} concepto{parametricCount === 1 ? "" : "s"} paramétrico
            {parametricCount === 1 ? "" : "s"}: cantidades propuestas desde la historia del
            taller (por m², por planta o por local), no leídas del plano. Revísalos o fíjalos;
            las reglas viven en Catálogo → Plantillas.
          </Callout>
        </div>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric label="Costo directo" value={money(costs.boq.direct_cost_total)} />
        <Metric label="Conceptos" value={costs.boq.lines.length} />
        <Metric
          label="Confianza promedio"
          value={`${(avgConf * 100).toFixed(0)}%`}
          accent={avgConf >= 0.7 ? "success" : undefined}
        />
      </div>

      {costs.boq.lines.length === 0 && (
        <div className="mb-6">
          <EmptyState
            icon={<FileXls size={22} weight="duotone" />}
            title="El plano no produjo ningún concepto"
            hint={
              costs.boq.warnings[0] ??
              "No se detectaron elementos estructurales ni de albañilería que el catálogo sepa costear. Revisa la lectura del plano o agrega los conceptos a mano abajo."
            }
            action={
              <Link href={`/proyecto/${id}/lectura`} className={buttonClasses("secondary", "sm")}>
                Ver la lectura del plano
              </Link>
            }
          />
        </div>
      )}

      <TableCard className={`mb-6 ${costs.boq.lines.length === 0 ? "hidden" : ""}`}>
        <thead>
          <tr className="border-b border-border bg-surface-2">
            <Th>Clave</Th>
            <Th>Concepto</Th>
            <Th align="right">Cantidad</Th>
            <Th align="right">P.U.</Th>
            <Th align="right">Importe</Th>
            <Th align="center">Conf.</Th>
          </tr>
        </thead>
        <tbody>
          {phases.map((phase) => {
            const lines = costs.boq.lines.filter((l) => l.phase === phase);
            const subtotal = lines.reduce((s, l) => s + l.amount, 0);
            return (
              <PhaseGroup
                key={phase}
                phase={phase}
                lines={lines}
                subtotal={subtotal}
                projectId={id}
                actorName={actorName}
                clientId={clientId}
                onReviews={setReviews}
              />
            );
          })}
        </tbody>
        <tfoot>
          <tr className="bg-surface-2 font-semibold">
            <Td colSpan={4}>Costo directo</Td>
            <Td align="right" className="tabular" colSpan={2}>
              {money2(costs.boq.direct_cost_total)}
            </Td>
          </tr>
        </tfoot>
      </TableCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle>Integración del precio</SectionTitle>
          <div className="space-y-2 text-sm">
            <Line label="Costo directo" value={money2(costs.integration.direct_cost)} bold />
            {costs.integration.lines.map((l) => (
              <Line
                key={l.description}
                label={`${l.description} (${l.percentage}%)`}
                value={money2(l.amount)}
                muted
              />
            ))}
            <div className="my-2 border-t border-border" />
            <Line
              label={`Precio de venta · factor ${costs.integration.overcost_factor.toFixed(3)}`}
              value={money2(costs.integration.sale_price)}
              bold
            />
            <Line label="Contingencia" value={money2(costs.integration.contingency)} muted />
            <Line
              label="Total con contingencia"
              value={money2(costs.integration.grand_total)}
              bold
              accent
            />
          </div>
        </Card>

        <Card className="p-5">
          <SectionTitle sub="Fuente de verdad leída del archivo">
            Dimensiones detectadas
          </SectionTitle>
          {dims ? (
            <div className="space-y-2.5 text-sm">
              <Line
                label="Sección típica"
                value={
                  dims.typical_section_cm
                    ? `${dims.typical_section_cm[0]}×${dims.typical_section_cm[1]} cm`
                    : "—"
                }
              />
              <Line
                label="Espesor de muro"
                value={
                  dims.typical_wall_thickness_cm ? `${dims.typical_wall_thickness_cm} cm` : "—"
                }
              />
              <Line label="Sistema de losa" value={dims.vigueta_system ?? "—"} />
              <Line label="Cotas (DIMENSION)" value={`${dims.dimension_count}`} />
              {dims.typical_wall_thickness_source && (
                <p className="pt-1 text-xs text-muted">
                  Espesor de muro · fuente: {dims.typical_wall_thickness_source}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted">Sin dimensiones detectadas.</p>
          )}
        </Card>
      </div>

      {costs.indicators && <IndicatorsCard indicators={costs.indicators} />}

      <Card className="mt-6 p-5">
        <SectionTitle sub="Lo que el plano no trae y el presupuesto necesita: un concepto con su cantidad y el motivo, con autor. Para corregir una cantidad leída usa el lápiz de su línea.">
          Conceptos agregados a mano
        </SectionTitle>
        <AdjustmentsPanel
          projectId={id}
          reviews={reviews}
          boqLines={costs.boq.lines}
          concepts={concepts}
          actorName={actorName}
          clientId={clientId}
          onChanged={setReviews}
        />
      </Card>

      <Card className="mt-6 p-5">
        <SectionTitle sub="Guarda el presupuesto tal como está — con tus revisiones, ajustes y parámetros — para compararlo después y volver a él.">
          Versiones del presupuesto
        </SectionTitle>
        <VersionsPanel projectId={id} />
      </Card>

      {costs.boq.warnings.length > 0 && (
        <Card className="mt-6 p-5">
          <SectionTitle sub="Revisar antes de usar el presupuesto como referencia.">
            Advertencias ({costs.boq.warnings.length})
          </SectionTitle>
          <ul className="space-y-1.5 text-sm text-warning">
            {costs.boq.warnings.slice(0, 8).map((w, i) => (
              <li key={i} className="flex items-start gap-2">
                <Warning size={15} weight="bold" className="mt-0.5 shrink-0" />
                {w}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function PhaseGroup({
  phase,
  lines,
  subtotal,
  projectId,
  actorName,
  clientId,
  onReviews,
}: {
  phase: string;
  lines: BoqLine[];
  subtotal: number;
  projectId: string;
  actorName: string;
  clientId: string | null;
  onReviews: (reviews: ProjectReviews) => void;
}) {
  const [openCode, setOpenCode] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);
  return (
    <>
      <tr className="border-b border-border bg-surface-2/60">
        <td
          colSpan={4}
          className="px-4 py-2 text-xs font-semibold uppercase tracking-wide text-muted"
        >
          {phase}
        </td>
        <td
          colSpan={2}
          className="px-4 py-2 text-right text-xs font-semibold tabular text-muted"
        >
          {money2(subtotal)}
        </td>
      </tr>
      {lines.map((l) => {
        const open = openCode === l.concept_code;
        const levels = l.by_view ? Object.entries(l.by_view) : [];
        return (
          <Fragment key={l.concept_code}>
            <tr
              className={`border-b border-border transition-colors hover:bg-surface-2/60 ${
                open ? "bg-surface-2/40" : ""
              }`}
              onClick={() => setOpenCode(open ? null : l.concept_code)}
              title="Ver de dónde sale esta cantidad"
            >
              <Td className="font-mono text-xs text-muted">
                {l.taller_clave ? (
                  <span title={`Concepto del taller (Klave ${l.concept_code})`}>
                    {l.taller_clave}
                    <span className="block text-[10px] text-faint">{l.concept_code}</span>
                  </span>
                ) : (
                  l.concept_code
                )}
              </Td>
              <Td>
                {l.description}
                {l.parametric && (
                  <span className="ml-1.5 align-middle">
                    <Badge tone="warning">paramétrico</Badge>
                  </span>
                )}
                {levels.length > 1 && (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {levels.map(([title, qty]) => (
                      <span
                        key={title}
                        className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[11px] tabular text-muted"
                        title={`${title}: ${num(qty)} ${l.unit}`}
                      >
                        {title.replace(/^[A-Z]{1,3}-\d{2,4}[A-Z]?\s*·\s*/, "")} {num(qty)}
                      </span>
                    ))}
                  </div>
                )}
              </Td>
              <Td align="right" className="tabular">
                {
                  <span className="group/qty inline-flex items-center justify-end gap-1.5">
                    {l.engine_quantity != null && l.engine_quantity !== l.quantity && (
                      <span
                        className="text-xs text-faint line-through"
                        title="Lo que leyó el motor"
                      >
                        {num(l.engine_quantity)}
                      </span>
                    )}
                    {num(l.quantity)} <span className="text-xs text-muted">{l.unit}</span>
                    <button
                      type="button"
                      aria-label={`Editar cantidad de ${l.concept_code}`}
                      title="Fijar la cantidad a mano (con motivo)"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditing(l.concept_code);
                      }}
                      className="rounded-md p-0.5 text-faint opacity-0 transition-opacity hover:text-accent group-hover/qty:opacity-100 focus:opacity-100"
                    >
                      <PencilSimpleLine size={13} />
                    </button>
                  </span>
                }
              </Td>
              <Td align="right" className="tabular text-muted">
                {money2(l.unit_price)}
              </Td>
              <Td align="right" className="font-medium tabular">
                {money2(l.amount)}
              </Td>
              <Td align="center">
                <Badge dot tone={l.confidence >= 0.7 ? "success" : "warning"}>
                  {(l.confidence * 100).toFixed(0)}%
                </Badge>
              </Td>
            </tr>
            {editing === l.concept_code && (
              <tr className="border-b border-border bg-accent-soft/40">
                <td colSpan={6} className="px-4 py-2.5">
                  <QuantityEditor
                    line={l}
                    projectId={projectId}
                    actorName={actorName}
                    clientId={clientId}
                    onDone={(reviews) => {
                      setEditing(null);
                      if (reviews) onReviews(reviews);
                    }}
                  />
                </td>
              </tr>
            )}
            {open && (
              <tr className="border-b border-border bg-surface-2/30">
                <td colSpan={6} className="px-4 py-3 text-xs text-muted">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="font-medium text-foreground">
                      Concepto del taller:{" "}
                      {l.taller_clave ? (
                        <span className="font-mono">{l.taller_clave}</span>
                      ) : (
                        <span className="text-muted">ninguno (clave Klave {l.concept_code})</span>
                      )}
                    </span>
                    <button
                      type="button"
                      className="text-xs underline"
                      onClick={(e) => {
                        e.stopPropagation();
                        setPicking(picking === l.concept_code ? null : l.concept_code);
                      }}
                    >
                      {picking === l.concept_code ? "cerrar" : l.taller_clave ? "cambiar" : "elegir de mi catálogo"}
                    </button>
                  </div>
                  {picking === l.concept_code && (
                    <div className="mb-3" onClick={(e) => e.stopPropagation()}>
                      <ConceptPicker
                        conceptCode={l.concept_code}
                        conceptDescription={l.description}
                        unit={l.unit}
                        currentClave={l.taller_clave ?? ""}
                        projectId={projectId}
                        actorName={actorName}
                        onDone={() => setPicking(null)}
                      />
                    </div>
                  )}
                  <div className="mb-1.5 font-medium text-foreground">
                    De dónde sale: {l.source_detection_count} elemento
                    {l.source_detection_count === 1 ? "" : "s"} del plano
                    {l.source_detection_count > 0 && (
                      <>
                        {" · "}
                        <Link
                          href={`/proyecto/${projectId}/plano?concept=${encodeURIComponent(l.concept_code)}`}
                          className="underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          verlos en el plano
                        </Link>
                      </>
                    )}
                  </div>
                  <ul className="list-disc space-y-0.5 pl-4">
                    {l.assumptions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                    {l.assumptions.length === 0 && <li>Sin supuestos adicionales.</li>}
                  </ul>
                  {l.source_detection_count > 0 && (
                    <CroquisStrip projectId={projectId} conceptCode={l.concept_code} />
                  )}
                </td>
              </tr>
            )}
          </Fragment>
        );
      })}
    </>
  );
}

/** The croquis of the generador: each planta with the concept's elements
 * marked on it, rendered by the API from the sheet and cached per run. */
function CroquisStrip({ projectId, conceptCode }: { projectId: string; conceptCode: string }) {
  const [items, setItems] = useState<CroquisItem[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    getCroquis(projectId, conceptCode)
      .then((r) => {
        if (active) setItems(r.croquis);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [projectId, conceptCode]);
  if (failed) return null;
  if (items === null) {
    return (
      <div className="mt-3" aria-busy="true">
        <div className="mb-1.5 font-medium text-foreground">Croquis del generador</div>
        <div className="flex gap-3">
          <Skeleton className="h-36 w-52 rounded-lg" />
          <Skeleton className="h-36 w-52 rounded-lg" />
        </div>
      </div>
    );
  }
  if (items.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="mb-1.5 font-medium text-foreground">Croquis del generador</div>
      <div className="flex flex-wrap gap-3">
        {items.map((item) => (
          <a
            key={item.view_id}
            href={croquisUrl(item)}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="block rounded-lg border border-border bg-surface p-1.5 transition-colors hover:border-accent"
            title={`${item.title} · ${item.count} elemento${item.count === 1 ? "" : "s"} · abrir en grande`}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={croquisUrl(item)}
              alt={`Croquis ${item.title}`}
              className="h-36 w-auto max-w-64 rounded object-contain"
            />
            <div className="mt-1 max-w-64 truncate text-[11px] text-muted">
              {item.title.replace(/^[A-Z]{1,3}-\d{2,4}[A-Z]?\s*·\s*/, "")} · {item.count}
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}

/** Edit the quantity in place: the new figure replaces the engine's, the
 * engine's stays visible, and the reason is required — a number that
 * changes without a why is exactly what a presupuesto cannot carry. */
function QuantityEditor({
  line,
  projectId,
  actorName,
  clientId,
  onDone,
}: {
  line: BoqLine;
  projectId: string;
  actorName: string;
  clientId: string | null;
  onDone: (reviews: ProjectReviews | null) => void;
}) {
  const [value, setValue] = useState(String(Math.round(line.quantity * 100) / 100));
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const quantity = Number(value);
    if (!Number.isFinite(quantity) || quantity < 0) {
      setError("Cantidad inválida.");
      return;
    }
    if (!reason.trim()) {
      setError("Di por qué cambia.");
      return;
    }
    if (Math.abs(quantity - line.quantity) < 0.005) {
      onDone(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onDone(
        await addAdjustment(
          projectId,
          { concept_code: line.concept_code, quantity_set: quantity, note: reason.trim() },
          actorName,
          clientId,
        ),
      );
    } catch {
      setError("No se pudo guardar.");
      setBusy(false);
    }
  }

  return (
    <div
      className="flex flex-wrap items-center gap-2 text-sm"
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Escape") onDone(null);
        if (e.key === "Enter") void save();
      }}
    >
      <span className="text-xs text-muted">
        Fijar {line.concept_code} · leído {num(line.quantity)} {line.unit} →
      </span>
      <Input
        type="number"
        step="any"
        min={0}
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Nueva cantidad"
        className="w-28 px-2 py-1 text-right tabular"
      />
      <span className="text-xs text-muted">{line.unit}</span>
      <Input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Por qué (obligatorio)"
        maxLength={300}
        aria-label="Motivo del cambio"
        className="min-w-48 flex-1 px-2 py-1"
      />
      <Button size="sm" variant="primary" onClick={save} disabled={busy}>
        <Check size={13} weight="bold" /> Fijar
      </Button>
      <Button size="sm" onClick={() => onDone(null)} disabled={busy} aria-label="Cancelar">
        <X size={13} weight="bold" />
      </Button>
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}

function AdjustmentsPanel({
  projectId,
  reviews,
  boqLines,
  concepts,
  actorName,
  clientId,
  onChanged,
}: {
  projectId: string;
  reviews: ProjectReviews | null;
  boqLines: BoqLine[];
  /** Full workspace catalog: manual concepts are adjustable even without a
   * detected quantity — that is exactly what they exist for. */
  concepts: CatalogConcept[] | null;
  actorName: string;
  clientId: string | null;
  onChanged: (reviews: ProjectReviews) => void;
}) {
  const [conceptCode, setConceptCode] = useState("");
  const [delta, setDelta] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const adjustments = reviews?.adjustments ?? [];
  const unitOf = new Map<string, string>([
    ...boqLines.map((line) => [line.concept_code, line.unit] as [string, string]),
    ...(concepts ?? []).map(
      (concept) => [concept.code, concept.unit] as [string, string],
    ),
  ]);
  const selectable =
    concepts ??
    boqLines.map((line) => ({
      code: line.concept_code,
      description: line.description,
    }));

  const inBoq = new Set(boqLines.map((line) => line.concept_code));

  async function submit() {
    const quantity = Number(delta);
    if (!conceptCode || !quantity) {
      setFormError("Elige un concepto y una cantidad distinta de cero.");
      return;
    }
    if (!note.trim()) {
      setFormError("Di por qué: el motivo queda en el presupuesto junto a tu nombre.");
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      const updated = await addAdjustment(
        projectId,
        { concept_code: conceptCode, quantity_delta: quantity, note: note.trim() },
        actorName,
        clientId,
      );
      onChanged(updated);
      setDelta("");
      setNote("");
    } catch (e) {
      setFormError(apiMessage(e, "No se pudo guardar el concepto."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(adjustmentId: string) {
    try {
      onChanged(await removeAdjustment(projectId, adjustmentId, actorName, clientId));
    } catch {
      setFormError("No se pudo eliminar el ajuste.");
    }
  }

  return (
    <div>
      {adjustments.length > 0 && (
        <ul className="mb-4 divide-y divide-border">
          {adjustments.map((adjustment) => (
            <li key={adjustment.adjustment_id} className="flex items-center gap-3 py-2.5">
              <PencilSimpleLine size={15} className="shrink-0 text-muted" />
              <div className="min-w-0 flex-1 text-sm">
                <span className="font-mono text-xs text-muted">
                  {adjustment.concept_code}
                </span>{" "}
                <span className="tabular font-medium">
                  {adjustment.quantity_set != null
                    ? `= ${num(adjustment.quantity_set)}`
                    : `${adjustment.quantity_delta > 0 ? "+" : ""}${num(adjustment.quantity_delta)}`}{" "}
                  {unitOf.get(adjustment.concept_code) ?? ""}
                </span>
                {adjustment.note && <span className="text-muted"> · {adjustment.note}</span>}
                {adjustment.actor && (
                  <span className="text-xs text-faint"> — {adjustment.actor}</span>
                )}
              </div>
              <button
                type="button"
                aria-label="Eliminar ajuste"
                onClick={() => remove(adjustment.adjustment_id)}
                className="rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
              >
                <Trash size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={conceptCode}
          onChange={(e) => setConceptCode(e.target.value)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
        >
          <option value="">Concepto…</option>
          {selectable.map((concept) => (
            <option key={concept.code} value={concept.code}>
              {concept.code} · {concept.description.slice(0, 48)}
              {inBoq.has(concept.code) ? " (ya en el presupuesto)" : ""}
            </option>
          ))}
        </select>
        <Input
          type="number"
          step="any"
          value={delta}
          onChange={(e) => setDelta(e.target.value)}
          placeholder={`Cantidad${conceptCode && unitOf.get(conceptCode) ? ` (${unitOf.get(conceptCode)})` : ""}`}
          className="w-36 px-2 py-1.5 text-right tabular"
          aria-label="Cantidad"
        />
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Motivo (obligatorio): qué es y de dónde sale"
          maxLength={300}
          className="min-w-52 flex-1 px-2 py-1.5"
          aria-label="Motivo"
        />
        <Button size="sm" variant="primary" onClick={submit} disabled={busy}>
          Agregar concepto
        </Button>
      </div>
      {formError && <p className="mt-2 text-sm text-danger">{formError}</p>}
      {conceptCode && inBoq.has(conceptCode) && !formError && (
        <p className="mt-2 text-xs text-muted">
          Este concepto ya tiene cantidad leída; lo que captures se suma. Para sustituirla, usa el
          lápiz de su línea.
        </p>
      )}
      {adjustments.length === 0 && !formError && (
        <p className="mt-2 text-xs text-faint">
          Úsalo cuando el plano tenga elementos que la detección no captó. El concepto queda
          documentado con tu motivo y tu nombre.
        </p>
      )}
    </div>
  );
}

function Line({
  label,
  value,
  bold,
  muted,
  accent,
}: {
  label: string;
  value: string;
  bold?: boolean;
  muted?: boolean;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className={muted ? "text-muted" : ""}>{label}</span>
      <span
        className={`tabular ${bold ? "font-semibold" : ""} ${accent ? "text-accent" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
