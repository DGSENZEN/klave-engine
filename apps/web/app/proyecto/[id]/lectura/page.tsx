"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ArrowsClockwise,
  FileText,
  Layout,
  Ruler,
  Scan,
  Stack,
  Warning,
} from "@phosphor-icons/react";
import {
  addInventoryMapping,
  ApiError,
  deleteInventoryMapping,
  frameRenderUrl,
  getAiReads,
  getCatalog,
  getCostingConfig,
  getLectura,
  listInventoryMappings,
  num,
  recompute,
  startAiRead,
  type AiReads,
  type AiSheetReading,
  type CatalogConcept,
  type InventoryMapping,
  type Lectura,
  type LecturaSheet,
  type SheetInventory,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { FAMILY_LABELS } from "@/components/PlanoCanvas";
import { useProjectLive } from "@/components/ProjectLive";
import {
  Badge,
  Button,
  Callout,
  Card,
  Metric,
  PageHeader,
  SectionTitle,
  SkeletonCards,
  SkeletonHeader,
  SkeletonMetrics,
} from "@/components/ui";

export default function LecturaPage() {
  const { id } = useParams<{ id: string }>();
  const [lectura, setLectura] = useState<Lectura | null>(null);
  const [concepts, setConcepts] = useState<CatalogConcept[]>([]);
  const [mappings, setMappings] = useState<InventoryMapping[]>([]);
  const [mappingNotice, setMappingNotice] = useState<string | null>(null);
  const [aiReads, setAiReads] = useState<AiReads | null>(null);
  const [aiNotice, setAiNotice] = useState<string | null>(null);
  const reloadAiReads = useCallback(() => {
    getAiReads(id).then(setAiReads).catch(() => setAiReads(null));
  }, [id]);
  useEffect(() => {
    reloadAiReads();
  }, [reloadAiReads]);
  // While a reading runs, poll it; the job lasts a few minutes per project.
  useEffect(() => {
    if (!aiReads?.running) return;
    const handle = window.setInterval(reloadAiReads, 5000);
    return () => window.clearInterval(handle);
  }, [aiReads?.running, reloadAiReads]);

  async function readWithAi() {
    try {
      await startAiRead(id, getBrowserActor());
      setAiNotice("Leyendo las hojas con IA… cada hoja toma unos segundos.");
      reloadAiReads();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      setAiNotice(detail || "No se pudo iniciar la lectura con IA.");
    }
  }
  const reloadMappings = useCallback(() => {
    listInventoryMappings().then(setMappings).catch(() => setMappings([]));
  }, []);
  useEffect(() => {
    getCatalog().then((c) => setConcepts(c.concepts)).catch(() => setConcepts([]));
    reloadMappings();
  }, [reloadMappings]);

  async function assign(
    kind: "block" | "layer" | "tag" | "area",
    pattern: string,
    conceptCode: string,
  ) {
    try {
      await addInventoryMapping({ kind, pattern, concept_code: conceptCode }, getBrowserActor());
      reloadMappings();
      // The presupuesto follows: recompute with the project's current parameters.
      const cfg = await getCostingConfig(id);
      await recompute(
        id,
        { config: cfg.config, insumo_prices: cfg.insumo_prices, version: cfg.version },
        getBrowserActor(),
      );
      setMappingNotice(`«${pattern}» ahora cuenta como ${conceptCode}; presupuesto actualizado.`);
    } catch {
      setMappingNotice(`No se pudo asignar «${pattern}» a ${conceptCode}.`);
    }
  }

  async function unassign(mapping: InventoryMapping) {
    try {
      await deleteInventoryMapping(mapping.id, getBrowserActor());
      reloadMappings();
      const cfg = await getCostingConfig(id);
      await recompute(
        id,
        { config: cfg.config, insumo_prices: cfg.insumo_prices, version: cfg.version },
        getBrowserActor(),
      );
      setMappingNotice(`«${mapping.pattern}» vuelve a ser solo un conteo.`);
    } catch {
      setMappingNotice(`No se pudo quitar la asignación de «${mapping.pattern}».`);
    }
  }
  const [error, setError] = useState(false);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getLectura(id)
      .then((data) => {
        if (active) {
          setLectura(data);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getLectura(id).then(setLectura).catch(() => {});
  }, [id, latestEvent]);

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Lectura del plano" />
        <Callout tone="danger">
          No se pudo cargar la lectura. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!lectura) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <SkeletonMetrics count={4} />
        <SkeletonCards count={2} />
      </div>
    );
  }

  const totalEntities = lectura.sheets.reduce(
    (sum, sheet) => sum + (sheet.parse?.entity_count ?? 0),
    0,
  );
  const maxLayerCount = Math.max(...lectura.layers.map((l) => l.entity_count), 1);

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Lectura del plano"
        sub="Qué leyó Klave de tus archivos: conversión, entidades, capas, bloques y lo que se omitió. Aquí se decide si puedes confiar en lo demás."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Unidades"
          value={lectura.units?.unit ?? "—"}
          hint={
            lectura.units
              ? `${Math.round(lectura.units.confidence * 100)}% · ${lectura.units.source_label}`
              : undefined
          }
          icon={<Ruler size={16} weight="duotone" />}
          accent={lectura.units && lectura.units.confidence >= 0.7 ? "success" : undefined}
        />
        <Metric
          label={lectura.frames && lectura.frames.total > 0 ? "Hojas" : "Archivos"}
          value={lectura.frames && lectura.frames.total > 0 ? lectura.frames.total : lectura.sheets.length}
          icon={<FileText size={16} weight="duotone" />}
        />
        <Metric
          label="Entidades leídas"
          value={num(totalEntities, 0)}
          icon={<Stack size={16} weight="duotone" />}
        />
        <Metric
          label="Detecciones"
          value={lectura.detection_total}
          icon={<Scan size={16} weight="duotone" />}
        />
      </div>

      <div className="mb-6 space-y-3">
        {lectura.sheets.map((sheet) => (
          <SheetCard key={sheet.name} sheet={sheet} labels={lectura.entity_type_labels} />
        ))}
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle
            sub={
              lectura.layer_total > lectura.layers.length
                ? `Las ${lectura.layers.length} capas con más entidades de ${lectura.layer_total}.`
                : "Todas las capas del dibujo."
            }
          >
            Capas
          </SectionTitle>
          <div className="space-y-2">
            {lectura.layers.map((layer) => (
              <div key={layer.layer}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                  <span className="truncate font-mono text-xs">{layer.layer}</span>
                  <span className="tabular text-xs text-muted">{layer.entity_count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-chart-2"
                    style={{ width: `${(layer.entity_count / maxLayerCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle sub="Familias estructurales que la detección encontró.">
              Detecciones por familia
            </SectionTitle>
            {lectura.detection_total === 0 ? (
              <p className="text-sm text-muted">
                Sin detecciones: el visor y las herramientas de medición siguen
                disponibles.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {Object.entries(lectura.detections_by_family).map(([family, count]) => (
                  <span
                    key={family}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 text-xs"
                  >
                    {FAMILY_LABELS[family] ?? family}
                    <span className="tabular font-semibold">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </Card>

          <Card className="p-5">
            <SectionTitle sub="Un modelo de visión lee la imagen de cada hoja — cajetín, cuadros, notas, marcas — y lo que lee entra como sugerencia con procedencia, por debajo de lo que las reglas leyeron; se aplica al reprocesar.">
              Lectura asistida por IA
            </SectionTitle>
            {aiReads && !aiReads.available && (
              <p className="mb-3 text-sm text-muted">
                No configurada en este servidor: falta <code>ANTHROPIC_API_KEY</code>. Las
                imágenes de las hojas sí están disponibles en el visor.
              </p>
            )}
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={!aiReads?.available || aiReads.running}
                onClick={readWithAi}
              >
                {aiReads?.running ? "Leyendo…" : "Leer hojas con IA"}
              </Button>
              {aiReads?.status === "done" && (
                <span className="text-xs text-muted">
                  {aiReads.readings.length} hojas leídas · {num(aiReads.input_tokens)} tokens de
                  entrada · {aiReads.model}
                </span>
              )}
              {aiReads?.status === "failed" && (
                <span className="text-xs text-warning">Falló: {aiReads.error}</span>
              )}
            </div>
            {aiNotice && <p className="mb-3 text-sm text-muted">{aiNotice}</p>}
            {aiReads?.notes.map((n, i) => (
              <p key={i} className="mb-1 text-xs text-muted">
                {n}
              </p>
            ))}
            {aiReads && aiReads.readings.length > 0 && (
              <div className="mt-3 space-y-2">
                {aiReads.readings.map((r) => (
                  <AiReadingCard key={r.frame_code} reading={r} projectId={id} />
                ))}
              </div>
            )}
          </Card>

          {lectura.inventory && lectura.inventory.sheets.length > 0 && (
            <Card className="p-5">
              <SectionTitle sub="Lo que cada hoja contiene, contado: símbolos por bloque y metros de trazo por capa. Un conteo no es una cantidad hasta que se asigna a un concepto del catálogo.">
                Levantamiento por hoja
              </SectionTitle>
              {mappingNotice && <p className="mb-3 text-sm text-muted">{mappingNotice}</p>}
              <div className="space-y-4">
                {lectura.inventory.sheets.map((sheet) => (
                  <InventoryCard
                    key={sheet.sheet}
                    sheet={sheet}
                    unit={lectura.inventory?.unit ?? null}
                    concepts={concepts}
                    mappings={mappings}
                    onAssign={assign}
                    onUnassign={unassign}
                  />
                ))}
              </div>
            </Card>
          )}

          {lectura.blocks.length > 0 && (
            <Card className="p-5">
              <SectionTitle sub="Definiciones de bloque más usadas; su geometría interna se expande para la detección.">
                Bloques
              </SectionTitle>
              <div className="flex flex-wrap gap-2">
                {lectura.blocks.map((block) => (
                  <span
                    key={block.block_name}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 font-mono text-xs"
                  >
                    {block.block_name}
                    <span className="tabular font-semibold">×{block.insert_count}</span>
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {lectura.schedules && (lectura.schedules.by_mark.length > 0 || lectura.schedules.by_family.length > 0) && (
        <Card className="mb-6 p-5">
          <SectionTitle sub="Secciones y armados que el plano declara por marca; mandan sobre el marcador medido y sobre los supuestos.">
            Especificaciones del plano
          </SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-1.5 pr-3 font-medium">Marca</th>
                  <th className="py-1.5 pr-3 font-medium">Familia</th>
                  <th className="py-1.5 pr-3 font-medium">Sección</th>
                  <th className="py-1.5 pr-3 font-medium">Armado</th>
                  <th className="py-1.5 pr-3 font-medium">Estribos</th>
                  <th className="py-1.5 font-medium">Fuente</th>
                </tr>
              </thead>
              <tbody>
                {[...lectura.schedules.by_mark, ...lectura.schedules.by_family].map((spec) => (
                  <tr key={`${spec.source}-${spec.mark}`} className="border-t border-border">
                    <td className="py-1.5 pr-3 font-mono text-xs">{spec.mark}</td>
                    <td className="py-1.5 pr-3 capitalize">{spec.family}</td>
                    <td className="py-1.5 pr-3 tabular">
                      {spec.section_cm ? `${spec.section_cm[0]}×${spec.section_cm[1]} cm` : "—"}
                    </td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{spec.rebar ?? "—"}</td>
                    <td className="py-1.5 pr-3 font-mono text-xs">{spec.stirrups ?? "—"}</td>
                    <td className="py-1.5">
                      <Badge tone={spec.source === "cuadro" ? "success" : "default"}>
                        {spec.source === "cuadro" ? "Cuadro" : spec.source === "detalle" ? "Detalle" : "Nota"}
                      </Badge>
                      <span className="ml-2 text-xs text-faint">«{spec.source_text.slice(0, 48)}»</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {lectura.warning_groups.length > 0 && (
        <Card className="p-5">
          <SectionTitle sub="Nada se omite en silencio: esto es lo que no se pudo leer o se ajustó.">
            Avisos de lectura
          </SectionTitle>
          <ul className="space-y-3">
            {lectura.warning_groups.map((group) => (
              <li key={group.type} className="text-sm">
                <div className="flex items-center gap-2">
                  <Warning size={15} weight="bold" className="shrink-0 text-warning" />
                  <span className="font-medium">{group.label}</span>
                  <span className="tabular text-xs text-muted">×{group.count}</span>
                </div>
                {group.samples[0] && (
                  <p className="ml-6 mt-0.5 text-xs text-faint">{group.samples[0]}</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

const DISCIPLINE_LABELS: Record<string, string> = {
  hidraulica: "Hidráulica",
  sanitaria: "Sanitaria",
  electrica: "Eléctrica",
  gas: "Gas",
  aire: "Aire acondicionado",
  cctv: "CCTV / seguridad",
  canceleria: "Cancelería",
  acabados: "Acabados",
  carpinteria: "Carpintería",
  estructural: "Estructural",
};

function MappingControl({
  kind,
  pattern,
  unit,
  concepts,
  mappings,
  onAssign,
  onUnassign,
}: {
  kind: "block" | "layer" | "tag" | "area";
  pattern: string;
  unit: string;
  concepts: CatalogConcept[];
  mappings: InventoryMapping[];
  onAssign: (kind: "block" | "layer" | "tag" | "area", pattern: string, conceptCode: string) => void;
  onUnassign: (mapping: InventoryMapping) => void;
}) {
  const current = mappings.find(
    (m) => m.kind === kind && m.pattern.toLowerCase() === pattern.toLowerCase(),
  );
  if (current) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px]">
        <Badge tone="success">→ {current.concept_code}</Badge>
        <button
          type="button"
          className="text-muted underline"
          onClick={(e) => {
            e.stopPropagation();
            onUnassign(current);
          }}
        >
          quitar
        </button>
      </span>
    );
  }
  const options = concepts.filter((c) => c.unit.toUpperCase() === unit);
  return (
    <select
      value=""
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => {
        if (e.target.value) onAssign(kind, pattern, e.target.value);
      }}
      className="max-w-44 rounded-md border border-border bg-surface px-1 py-0.5 text-[11px]"
      title={`Contar «${pattern}» como un concepto (${unit})`}
    >
      <option value="">concepto ({unit})…</option>
      {options.map((c) => (
        <option key={c.code} value={c.code}>
          {c.code} · {c.description.slice(0, 38)}
        </option>
      ))}
    </select>
  );
}

function AiReadingCard({ reading, projectId }: { reading: AiSheetReading; projectId: string }) {
  const [open, setOpen] = useState(false);
  const r = reading.read;
  const fc = Object.entries(r.concrete_fc);
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-3 px-4 py-2.5 text-left"
      >
        <span className="font-mono text-xs text-muted">{reading.frame_code}</span>
        <span className="min-w-0 flex-1 truncate text-sm">
          {r.title || reading.frame_title || "(sin título leído)"}
          {r.level ? ` · ${r.level}` : ""}
        </span>
        <span className="text-xs text-muted">
          {r.elements.length} elementos · {r.uncertainties.length} dudas
        </span>
        <a
          href={frameRenderUrl(projectId, reading.frame_code)}
          target="_blank"
          rel="noreferrer"
          className="text-xs underline"
          onClick={(e) => e.stopPropagation()}
        >
          imagen
        </a>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-4 py-3 text-sm">
          {(fc.length > 0 || r.steel_fy || r.slab_system || r.desplante_m) && (
            <div className="text-xs text-muted">
              {fc.map(([k, v]) => `f'c ${k} ${v}`).join(" · ")}
              {r.steel_fy ? ` · fy ${r.steel_fy}` : ""}
              {r.slab_system ? ` · losa: ${r.slab_system}` : ""}
              {r.desplante_m ? ` · desplante ${num(r.desplante_m)} m` : ""}
            </div>
          )}
          {r.elements.length > 0 && (
            <ul className="space-y-0.5">
              {r.elements.slice(0, 40).map((e, i) => (
                <li key={`${e.mark}-${i}`} className="flex items-baseline gap-2">
                  <span className="font-mono text-xs">{e.mark}</span>
                  <span className="min-w-0 flex-1 truncate text-xs text-muted">
                    {e.family}
                    {e.section_cm ? ` · ${e.section_cm}` : ""}
                    {e.rebar ? ` · ${e.rebar}` : ""}
                    {e.stirrups ? ` · ${e.stirrups}` : ""}
                    {e.length_m ? ` · L ${num(e.length_m)} m` : ""}
                  </span>
                  <span className="text-[11px] tabular text-muted">{Math.round(e.confidence * 100)}%</span>
                </li>
              ))}
            </ul>
          )}
          {r.notes.length > 0 && (
            <div className="text-xs text-muted">Notas: {r.notes.slice(0, 6).join(" · ")}</div>
          )}
          {r.uncertainties.length > 0 && (
            <div className="text-xs text-warning">Dudas: {r.uncertainties.slice(0, 6).join(" · ")}</div>
          )}
        </div>
      )}
    </div>
  );
}

function InventoryCard({
  sheet,
  unit,
  concepts,
  mappings,
  onAssign,
  onUnassign,
}: {
  sheet: SheetInventory;
  unit: string | null;
  concepts: CatalogConcept[];
  mappings: InventoryMapping[];
  onAssign: (kind: "block" | "layer" | "tag" | "area", pattern: string, conceptCode: string) => void;
  onUnassign: (mapping: InventoryMapping) => void;
}) {
  const [open, setOpen] = useState(false);
  const symbols =
    sheet.blocks.reduce((s, b) => s + b.count, 0) +
    (sheet.tags ?? []).reduce((s, t) => s + t.count, 0);
  const metres = sheet.runs.reduce((s, r) => s + (r.length_m ?? 0), 0);
  const levels = new Set<string>();
  sheet.blocks.forEach((b) => Object.keys(b.by_view).forEach((k) => levels.add(k)));
  sheet.runs.forEach((r) => Object.keys(r.by_view).forEach((k) => levels.add(k)));
  const short = (title: string) => title.replace(/^[A-Z]{1,3}-\d{2,4}[A-Z]?\s*·\s*/, "");
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left"
      >
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {sheet.label || sheet.sheet}
        </span>
        {sheet.discipline && (
          <Badge tone="accent">{DISCIPLINE_LABELS[sheet.discipline] ?? sheet.discipline}</Badge>
        )}
        <span className="text-xs tabular text-muted">
          {num(symbols)} símbolos · {unit ? `${num(metres)} m` : "longitud sin unidad"} en{" "}
          {sheet.runs.length} capas
        </span>
      </button>
      {open && (
        <div className="grid gap-4 border-t border-border px-4 py-3 text-sm md:grid-cols-2">
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              Símbolos (bloques)
            </div>
            {sheet.blocks.length === 0 && <div className="text-xs text-muted">Ninguno.</div>}
            <ul className="space-y-1">
              {sheet.blocks.slice(0, 30).map((b) => (
                <li key={`${b.block_name}|${b.layer}`} className="flex items-baseline gap-2">
                  <span className="tabular font-medium">{b.count}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {b.block_name} <span className="text-xs text-muted">· {b.layer}</span>
                  </span>
                  {Object.keys(b.by_view).length > 1 && (
                    <span className="text-[11px] tabular text-muted">
                      {Object.entries(b.by_view)
                        .map(([t, n]) => `${short(t)} ${n}`)
                        .join(" · ")}
                    </span>
                  )}
                  <MappingControl
                    kind="block"
                    pattern={b.block_name}
                    unit="PZA"
                    concepts={concepts}
                    mappings={mappings}
                    onAssign={onAssign}
                    onUnassign={onUnassign}
                  />
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
              Trazos por capa
            </div>
            {sheet.runs.length === 0 && <div className="text-xs text-muted">Ninguno.</div>}
            <ul className="space-y-1">
              {sheet.runs.slice(0, 30).map((r) => (
                <li key={r.layer} className="flex items-baseline gap-2">
                  <span className="tabular font-medium">
                    {r.length_m != null ? `${num(r.length_m)} m` : `${num(r.length_du)} u.`}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {r.layer} <span className="text-xs text-muted">· {r.segments} tramos</span>
                  </span>
                  {Object.keys(r.by_view).length > 1 && (
                    <span className="text-[11px] tabular text-muted">
                      {Object.entries(r.by_view)
                        .map(([t, n]) => `${short(t)} ${num(n)}`)
                        .join(" · ")}
                    </span>
                  )}
                  {r.length_m != null && (
                    <MappingControl
                      kind="layer"
                      pattern={r.layer}
                      unit="M"
                      concepts={concepts}
                      mappings={mappings}
                      onAssign={onAssign}
                      onUnassign={onUnassign}
                    />
                  )}
                </li>
              ))}
            </ul>
            {(sheet.areas ?? []).length > 0 && (
              <div className="mt-3">
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                  Áreas por capa (contornos cerrados y achurados)
                </div>
                <ul className="space-y-1">
                  {(sheet.areas ?? []).slice(0, 20).map((a) => (
                    <li key={a.layer} className="flex items-baseline gap-2">
                      <span className="tabular font-medium">
                        {a.area_m2 != null ? `${num(a.area_m2)} m²` : `${num(a.area_du2)} u.²`}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {a.layer} <span className="text-xs text-muted">· {a.count} figuras</span>
                      </span>
                      {Object.keys(a.by_view).length > 1 && (
                        <span className="text-[11px] tabular text-muted">
                          {Object.entries(a.by_view)
                            .map(([v, n]) => `${short(v)} ${num(n)}`)
                            .join(" · ")}
                        </span>
                      )}
                      {a.area_m2 != null && (
                        <MappingControl
                          kind="area"
                          pattern={a.layer}
                          unit="M2"
                          concepts={concepts}
                          mappings={mappings}
                          onAssign={onAssign}
                          onUnassign={onUnassign}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {(sheet.tags ?? []).length > 0 && (
              <div className="mt-3">
                <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                  Etiquetas repetidas (tipos de elemento)
                </div>
                <ul className="space-y-1">
                  {(sheet.tags ?? []).slice(0, 30).map((t) => (
                    <li key={t.tag} className="flex items-baseline gap-2">
                      <span className="tabular font-medium">{t.count}</span>
                      <span className="min-w-0 flex-1 truncate font-mono text-xs">{t.tag}</span>
                      {Object.keys(t.by_view).length > 1 && (
                        <span className="text-[11px] tabular text-muted">
                          {Object.entries(t.by_view)
                            .map(([v, n]) => `${short(v)} ${n}`)
                            .join(" · ")}
                        </span>
                      )}
                      <MappingControl
                        kind="tag"
                        pattern={t.tag}
                        unit="PZA"
                        concepts={concepts}
                        mappings={mappings}
                        onAssign={onAssign}
                        onUnassign={onUnassign}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {sheet.specs.length > 0 && (
              <div className="mt-3 text-xs text-muted">
                Especificaciones leídas: {sheet.specs.slice(0, 12).join(" · ")}
              </div>
            )}
            {levels.size > 0 && (
              <div className="mt-2 text-[11px] text-faint">
                Plantas: {[...levels].map(short).join(", ")}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function SheetCard({
  sheet,
  labels,
}: {
  sheet: LecturaSheet;
  labels: Record<string, string>;
}) {
  const parse = sheet.parse;
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FileText size={16} weight="duotone" className="text-muted" />
        <span className="font-medium">{sheet.sheet_number ?? sheet.name}</span>
        <span className="text-xs text-faint">{sheet.name}</span>
        <span className="uppercase text-xs text-faint">{sheet.file_type}</span>
        {sheet.conversion && (
          <Badge tone={sheet.conversion.status === "success" ? "success" : "warning"}>
            {sheet.conversion.status === "success" ? "Convertido" : "Conversión con avisos"}
          </Badge>
        )}
        {parse?.recovered && (
          <Badge tone="warning" dot>
            <ArrowsClockwise size={11} weight="bold" /> Leído en recuperación
          </Badge>
        )}
      </div>
      {parse ? (
        <>
          <div className="flex flex-wrap gap-2">
            {Object.entries(parse.entities_by_type).map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2/70 px-2.5 py-1.5 text-xs"
              >
                {labels[type] ?? type}
                <span className="tabular font-semibold">{count}</span>
              </span>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {parse.from_block_count > 0 && (
              <span>{parse.from_block_count} entidades expandidas de bloques</span>
            )}
            {Object.entries(parse.derived_by_type).map(([type, count]) => (
              <span key={type}>
                {count} de {type}
              </span>
            ))}
            {Object.entries(parse.dropped_by_type).length > 0 && (
              <span className="text-warning">
                Omitidas:{" "}
                {Object.entries(parse.dropped_by_type)
                  .map(([type, count]) => `${type}×${count}`)
                  .join(", ")}
              </span>
            )}
          </div>
          {(parse.layouts?.length ?? 0) > 0 && (
            <div className="mt-3 space-y-1.5 border-t border-border pt-3">
              <div className="microlabel">Presentaciones (espacio papel)</div>
              {parse.layouts!.map((layout) => (
                <div key={layout.name} className="flex flex-wrap items-center gap-x-2 text-xs text-muted">
                  <span className="inline-flex items-center gap-1 font-medium text-foreground">
                    <Layout size={13} weight="duotone" /> {layout.name}
                  </span>
                  <span>
                    {layout.viewports.length === 0
                      ? "sin ventanas al modelo"
                      : layout.viewports.length === 1
                        ? "1 ventana al modelo"
                        : `${layout.viewports.length} ventanas al modelo`}
                  </span>
                  {layout.viewports
                    .map((v) => v.scale_label)
                    .filter((label): label is string => Boolean(label))
                    .filter((label, i, arr) => arr.indexOf(label) === i)
                    .map((label) => (
                      <Badge key={label}>{label}</Badge>
                    ))}
                  {Object.keys(layout.attributes).length > 0 && (
                    <span className="truncate">
                      {Object.entries(layout.attributes)
                        .slice(0, 3)
                        .map(([tag, value]) => `${tag}: ${value}`)
                        .join(" · ")}
                    </span>
                  )}
                  {Object.keys(layout.attributes).length === 0 && layout.texts[0] && (
                    <span className="truncate">«{layout.texts[0]}»</span>
                  )}
                </div>
              ))}
            </div>
          )}
          {(parse.xrefs?.length ?? 0) > 0 && (
            <div className="mt-3 space-y-1.5 border-t border-border pt-3">
              <div className="microlabel">Referencias externas</div>
              {parse.xrefs!.map((xref) => (
                <div key={xref.name} className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-mono">{xref.name}</span>
                  <span className="truncate text-faint">{xref.path}</span>
                  <Badge tone={xref.status === "embedded" ? "success" : "warning"}>
                    {xref.status === "embedded"
                      ? "Incorporada"
                      : xref.status === "missing"
                        ? "Falta: súbela como hoja"
                        : "No se pudo incorporar"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </>
      ) : (
        <p className="text-sm text-muted">
          Sin resumen de lectura para esta hoja (procesamiento anterior a esta versión;
          vuelve a procesar el proyecto).
        </p>
      )}
    </Card>
  );
}
