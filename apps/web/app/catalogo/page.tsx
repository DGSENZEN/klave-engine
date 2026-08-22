"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Books,
  CaretDown,
  Check,
  Crane,
  DownloadSimple,
  HardHat,
  MagnifyingGlass,
  Plus,
  Trash,
  UploadSimple,
} from "@phosphor-icons/react";
import {
  ApiError,
  adoptConceptReference,
  adoptReference,
  clearConceptPrice,
  createConcept,
  createInsumo,
  getCatalog,
  getEquipment,
  getLabor,
  importCatalogPrices,
  importCustomSource,
  importReferenceSource,
  listReferenceSources,
  money2,
  putEquipment,
  putLabor,
  searchReference,
  updateApu,
  updateInsumo,
  updateRendimiento,
  type ApuComponent,
  type CatalogConcept,
  type CatalogInsumo,
  type CatalogState,
  type EquipmentBreakdown,
  type EquipmentParameters,
  type FsrParameters,
  type LaborCategory,
  type LaborState,
  type ReferenceRow,
  type ReferenceSource,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  Input,
  PageHeader,
  SectionTitle,
  SkeletonHeader,
  SkeletonTable,
  Td,
  Th,
} from "@/components/ui";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

const TYPE_LABELS: Record<string, string> = {
  material: "Material",
  mano_de_obra: "Mano de obra",
  equipo: "Equipo",
};

export default function CatalogoPage() {
  const [catalog, setCatalog] = useState<CatalogState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    getCatalog()
      .then((state) => {
        setCatalog(state);
        setError(null);
      })
      .catch(() => setError("No se pudo cargar el catálogo. Revisa que el servidor esté activo."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onImportFile(file: File) {
    try {
      const result = await importCatalogPrices(
        file,
        `Importación CSV ${new Date().toLocaleDateString("es-MX")}`,
        getBrowserActor(),
      );
      const skipped = result.skipped.length
        ? ` · ${result.skipped.length} claves omitidas (${result.skipped.slice(0, 5).join(", ")}${result.skipped.length > 5 ? "…" : ""})`
        : "";
      setNotice(`${result.updated} precios actualizados${skipped}`);
      reload();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      setError(detail || "No se pudo importar el CSV.");
    }
  }

  function exportCsv() {
    if (!catalog) return;
    const rows = [
      ["code", "description", "unit", "resource_type", "unit_cost", "source"],
      ...catalog.insumos.map((insumo) => [
        insumo.code,
        `"${insumo.description}"`,
        insumo.unit,
        insumo.resource_type,
        insumo.unit_cost,
        `"${insumo.source}"`,
      ]),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.map((row) => row.join(",")).join("\n")], { type: "text/csv" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "catalogo_insumos.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen">
      <WorkspaceHeader active="catalogo" />
      <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6">
      <PageHeader
        title="Catálogo del taller"
        sub="Insumos, matrices de precio unitario y rendimientos que usa cada cálculo. Cada precio indica su fuente: sustituye las referencias por tus cotizaciones."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onImportFile(file);
                e.target.value = "";
              }}
            />
            <Button
              onClick={() => fileRef.current?.click()}
              title="CSV o XLSX (exportado de OPUS/Neodata) con columnas clave y precio"
            >
              <UploadSimple size={15} weight="bold" /> Importar precios
            </Button>
            <Button onClick={exportCsv} disabled={!catalog}>
              <DownloadSimple size={15} weight="bold" /> Exportar
            </Button>
          </>
        }
      />

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}
      {notice && (
        <div className="mb-4">
          <Callout
            tone="info"
            action={
              <Button size="sm" variant="ghost" onClick={() => setNotice(null)}>
                <Check size={14} weight="bold" /> Entendido
              </Button>
            }
          >
            {notice}. Los proyectos abiertos deben recalcular para aplicar los cambios.
          </Callout>
        </div>
      )}

      {!catalog ? (
        <>
          <SkeletonHeader />
          <SkeletonTable rows={8} />
        </>
      ) : (
        <>
          <FuentesSection catalog={catalog} onChanged={reload} onError={setError} onNotice={setNotice} />
          <SalarioRealSection onChanged={reload} onError={setError} onNotice={setNotice} />
          <InsumosSection catalog={catalog} onChanged={reload} onError={setError} />
          <ApusSection catalog={catalog} onChanged={reload} onError={setError} />
        </>
      )}
      </main>
    </div>
  );
}

/* ------------------------------------------------------------- insumos --- */

function InsumosSection({
  catalog,
  onChanged,
  onError,
}: {
  catalog: CatalogState;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [equipmentCode, setEquipmentCode] = useState<string | null>(null);

  async function commitInsumo(
    code: string,
    patch: Partial<
      Pick<CatalogInsumo, "description" | "unit_cost" | "source" | "source_type" | "vigencia">
    >,
  ) {
    try {
      await updateInsumo(code, patch, getBrowserActor());
      onChanged();
    } catch {
      onError(`No se pudo guardar el insumo ${code}.`);
    }
  }

  return (
    <Card className="mb-8 overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <SectionTitle sub="El costo unitario alimenta cada matriz de APU. La fuente documenta de dónde viene el precio.">
          Insumos
        </SectionTitle>
        <Button size="sm" onClick={() => setAdding((current) => !current)}>
          <Plus size={14} weight="bold" /> Agregar insumo
        </Button>
      </div>
      {adding && (
        <NewInsumoRow
          onDone={() => {
            setAdding(false);
            onChanged();
          }}
          onError={onError}
        />
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-2">
              <Th className="px-5">Insumo</Th>
              <Th>Tipo</Th>
              <Th>Unidad</Th>
              <Th align="right">Costo unitario</Th>
              <Th className="px-5">Fuente</Th>
            </tr>
          </thead>
          <tbody>
            {catalog.insumos.map((insumo) => (
              <tr key={insumo.code} className="border-b border-border last:border-0">
                <Td className="px-5">
                  <div>{insumo.description}</div>
                  <div className="font-mono text-xs text-muted">{insumo.code}</div>
                </Td>
                <Td>
                  <Badge>{TYPE_LABELS[insumo.resource_type] ?? insumo.resource_type}</Badge>
                </Td>
                <Td className="text-muted">{insumo.unit}</Td>
                <Td align="right">
                  {insumo.is_labor_percentage ? (
                    <span
                      className="tabular text-muted"
                      title="Fracción de la mano de obra (ecuación %MO)"
                    >
                      {(insumo.unit_cost * 100).toFixed(1)}% MO
                    </span>
                  ) : (
                    <CommitNumber
                      value={insumo.unit_cost}
                      onCommit={(value) => commitInsumo(insumo.code, { unit_cost: value })}
                    />
                  )}
                </Td>
                <Td className="px-5">
                  <CommitText
                    value={insumo.source}
                    placeholder="p. ej. cotización proveedor"
                    reference={insumo.source_type === "referencia"}
                    onCommit={(value) => commitInsumo(insumo.code, { source: value })}
                  />
                  <div className="mt-1 flex items-center gap-1.5">
                    <select
                      value={insumo.source_type}
                      onChange={(e) =>
                        commitInsumo(insumo.code, {
                          source_type: e.target.value as CatalogInsumo["source_type"],
                        })
                      }
                      className="rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] text-muted"
                    >
                      <option value="referencia">Referencia</option>
                      <option value="cotizacion">Cotización</option>
                      <option value="publicacion">Publicación</option>
                      <option value="calculado">Calculado</option>
                    </select>
                    {insumo.resource_type === "equipo" && !insumo.is_labor_percentage && (
                      <button
                        type="button"
                        onClick={() => setEquipmentCode(insumo.code)}
                        className="rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] text-muted hover:text-foreground"
                        title="Costo horario por RLOPSRM"
                      >
                        Costo horario
                      </button>
                    )}
                    <input
                      type="month"
                      value={insumo.vigencia}
                      onChange={(e) =>
                        commitInsumo(insumo.code, { vigencia: e.target.value })
                      }
                      title="Vigencia del precio"
                      className="rounded-md border border-border bg-surface px-1.5 py-0.5 text-[11px] text-muted"
                    />
                  </div>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {equipmentCode && (
        <EquipmentDialog
          insumo={catalog.insumos.find((i) => i.code === equipmentCode)!}
          onClose={() => setEquipmentCode(null)}
          onSaved={() => {
            setEquipmentCode(null);
            onChanged();
          }}
          onError={onError}
        />
      )}
    </Card>
  );
}

function NewInsumoRow({
  onDone,
  onError,
}: {
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [resourceType, setResourceType] = useState("material");
  const [unitCost, setUnitCost] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const cost = Number(unitCost);
    if (!code.trim() || !description.trim() || !unit.trim() || !(cost > 0)) {
      onError("Completa clave, descripción, unidad y un costo positivo.");
      return;
    }
    setBusy(true);
    try {
      await createInsumo(
        {
          code: code.trim().toUpperCase(),
          description: description.trim(),
          unit: unit.trim().toUpperCase(),
          resource_type: resourceType,
          unit_cost: cost,
          source: source.trim(),
        },
        getBrowserActor(),
      );
      onDone();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.status === 409
          ? `La clave ${code.trim().toUpperCase()} ya existe.`
          : "No se pudo crear el insumo.";
      onError(detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2/50 px-5 py-3">
      <Input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="CLAVE"
        className="w-36 px-2 py-1.5 font-mono text-xs uppercase"
      />
      <Input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Descripción"
        className="min-w-48 flex-1 px-2 py-1.5"
      />
      <Input
        value={unit}
        onChange={(e) => setUnit(e.target.value)}
        placeholder="UN"
        className="w-16 px-2 py-1.5 uppercase"
      />
      <select
        value={resourceType}
        onChange={(e) => setResourceType(e.target.value)}
        className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
      >
        <option value="material">Material</option>
        <option value="mano_de_obra">Mano de obra</option>
        <option value="equipo">Equipo</option>
      </select>
      <Input
        type="number"
        step="any"
        value={unitCost}
        onChange={(e) => setUnitCost(e.target.value)}
        placeholder="Costo"
        className="w-28 px-2 py-1.5 text-right tabular"
      />
      <Input
        value={source}
        onChange={(e) => setSource(e.target.value)}
        placeholder="Fuente"
        className="w-44 px-2 py-1.5"
      />
      <Button size="sm" variant="primary" onClick={submit} disabled={busy}>
        Crear
      </Button>
    </div>
  );
}

/* ---------------------------------------------------------------- apus --- */

function ApusSection({
  catalog,
  onChanged,
  onError,
}: {
  catalog: CatalogState;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(catalog.concepts[0]?.code ?? null);
  const byPhase = useMemo(() => {
    const phases = new Map<string, CatalogConcept[]>();
    for (const phase of catalog.phase_order) phases.set(phase, []);
    for (const concept of catalog.concepts) {
      const list = phases.get(concept.phase);
      if (list) list.push(concept);
      else phases.set(concept.phase, [concept]);
    }
    return [...phases.entries()].filter(([, concepts]) => concepts.length > 0);
  }, [catalog]);

  const [creating, setCreating] = useState(false);
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <SectionTitle sub="Cantidad de cada recurso por unidad de concepto. El costo directo unitario se recalcula con la ecuación %MO para herramienta menor.">
          Matrices de precio unitario
        </SectionTitle>
        <Button size="sm" onClick={() => setCreating((value) => !value)}>
          <Plus size={14} weight="bold" /> Agregar concepto
        </Button>
      </div>
      {creating && (
        <NewConceptCard
          catalog={catalog}
          onDone={() => {
            setCreating(false);
            onChanged();
          }}
          onError={onError}
        />
      )}
      {byPhase.map(([phase, concepts]) => (
        <div key={phase} className="mb-6">
          <div className="microlabel mb-2">{phase}</div>
          <div className="space-y-3">
            {concepts.map((concept) => (
              <ApuEditor
                key={concept.code}
                concept={concept}
                components={catalog.apus[concept.code] ?? []}
                insumos={catalog.insumos}
                open={open === concept.code}
                onToggle={() => setOpen(open === concept.code ? null : concept.code)}
                onChanged={onChanged}
                onError={onError}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function NewConceptCard({
  catalog,
  onDone,
  onError,
}: {
  catalog: CatalogState;
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [phase, setPhase] = useState(catalog.phase_order[0] ?? "Estructura");
  const [rate, setRate] = useState("");
  const [resourceCode, setResourceCode] = useState("");
  const [resourceQty, setResourceQty] = useState("1");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const production = Number(rate);
    const quantity = Number(resourceQty);
    if (!code.trim() || description.trim().length < 3 || !unit.trim() || !(production > 0)) {
      onError("Completa clave, descripción, unidad y rendimiento positivo.");
      return;
    }
    if (!resourceCode || !(quantity > 0)) {
      onError("Un concepto nace con al menos un recurso en su APU (sin precio no hay costo).");
      return;
    }
    setBusy(true);
    try {
      await createConcept(
        {
          code: code.trim().toUpperCase(),
          description: description.trim(),
          unit: unit.trim().toUpperCase(),
          phase,
          production_rate_per_day: production,
          components: [{ resource_code: resourceCode, quantity }],
        },
        getBrowserActor(),
      );
      onDone();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      onError(detail || "No se pudo crear el concepto.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mb-4 p-4">
      <p className="mb-3 text-sm text-muted">
        Concepto manual: su cantidad se captura con ajustes documentados o mediciones del
        visor; su precio sale de la matriz que definas aquí.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="CLAVE"
          className="w-32 px-2 py-1.5 font-mono text-xs uppercase"
        />
        <Input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Descripción del concepto"
          className="min-w-56 flex-1 px-2 py-1.5"
        />
        <Input
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          placeholder="UN"
          className="w-16 px-2 py-1.5 uppercase"
        />
        <select
          value={phase}
          onChange={(e) => setPhase(e.target.value)}
          className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
        >
          {catalog.phase_order.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <Input
          type="number"
          step="any"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
          placeholder="Rend./día"
          className="w-24 px-2 py-1.5 text-right tabular"
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted">Primer recurso del APU:</span>
        <select
          value={resourceCode}
          onChange={(e) => setResourceCode(e.target.value)}
          className="min-w-52 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
        >
          <option value="">Recurso…</option>
          {catalog.insumos.map((insumo) => (
            <option key={insumo.code} value={insumo.code}>
              {insumo.code} · {insumo.description}
            </option>
          ))}
        </select>
        <Input
          type="number"
          step="any"
          value={resourceQty}
          onChange={(e) => setResourceQty(e.target.value)}
          className="w-24 px-2 py-1.5 text-right tabular"
        />
        <Button size="sm" variant="primary" onClick={submit} disabled={busy}>
          Crear concepto
        </Button>
      </div>
    </Card>
  );
}

/** Mirrors the backend equation: %MO lines cost = fraction × labor subtotal. */
function directUnitCost(components: ApuComponent[], insumos: CatalogInsumo[]): number {
  const byCode = new Map(insumos.map((insumo) => [insumo.code, insumo]));
  let total = 0;
  let laborSubtotal = 0;
  const percentLines: { fraction: number }[] = [];
  for (const component of components) {
    const insumo = byCode.get(component.resource_code);
    if (!insumo) continue;
    if (insumo.is_labor_percentage) {
      percentLines.push({ fraction: insumo.unit_cost * component.quantity });
      continue;
    }
    const amount = component.quantity * insumo.unit_cost;
    total += amount;
    if (insumo.resource_type === "mano_de_obra") laborSubtotal += amount;
  }
  for (const line of percentLines) total += line.fraction * laborSubtotal;
  return total;
}

function ApuEditor({
  concept,
  components,
  insumos,
  open,
  onToggle,
  onChanged,
  onError,
}: {
  concept: CatalogConcept;
  components: ApuComponent[];
  insumos: CatalogInsumo[];
  open: boolean;
  onToggle: () => void;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [draft, setDraft] = useState<ApuComponent[]>(components);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [rate, setRate] = useState(String(concept.production_rate_per_day));
  const byCode = useMemo(
    () => new Map(insumos.map((insumo) => [insumo.code, insumo])),
    [insumos],
  );
  const available = insumos.filter(
    (insumo) => !draft.some((component) => component.resource_code === insumo.code),
  );

  // Re-sync local drafts when fresh catalog state arrives (render-time adjust).
  const [lastComponents, setLastComponents] = useState(components);
  if (lastComponents !== components) {
    setLastComponents(components);
    setDraft(components);
    setDirty(false);
    setRate(String(concept.production_rate_per_day));
  }

  function setQuantity(resourceCode: string, quantity: number) {
    setDraft((current) =>
      current.map((component) =>
        component.resource_code === resourceCode ? { ...component, quantity } : component,
      ),
    );
    setDirty(true);
  }

  function removeComponent(resourceCode: string) {
    setDraft((current) =>
      current.filter((component) => component.resource_code !== resourceCode),
    );
    setDirty(true);
  }

  function addComponent(resourceCode: string) {
    if (!resourceCode) return;
    setDraft((current) => [...current, { resource_code: resourceCode, quantity: 1 }]);
    setDirty(true);
  }

  async function save() {
    const invalid = draft.some((component) => !(component.quantity > 0));
    if (invalid || draft.length === 0) {
      onError("Todas las cantidades deben ser positivas y la matriz no puede quedar vacía.");
      return;
    }
    setBusy(true);
    try {
      await updateApu(concept.code, draft, getBrowserActor());
      onChanged();
    } catch {
      onError(`No se pudo guardar la matriz de ${concept.code}.`);
    } finally {
      setBusy(false);
    }
  }

  async function commitRate() {
    const value = Number(rate);
    if (!(value > 0)) {
      setRate(String(concept.production_rate_per_day));
      return;
    }
    if (value === concept.production_rate_per_day) return;
    try {
      await updateRendimiento(concept.code, value, getBrowserActor());
      onChanged();
    } catch {
      onError(`No se pudo guardar el rendimiento de ${concept.code}.`);
    }
  }

  const preview = directUnitCost(draft, insumos);

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-4 px-5 py-3.5 text-left transition hover:bg-surface-2/50"
      >
        <div className="min-w-0 flex-1">
          <span className="font-mono text-xs text-muted">{concept.code}</span>{" "}
          <span className="font-medium">{concept.description}</span>{" "}
          <Badge tone={concept.detection_backed ? "accent" : "default"}>
            {concept.detection_backed ? "Detección" : "Manual"}
          </Badge>
          {concept.price_override != null && (
            <Badge tone="warning">
              P.U. de {concept.price_source} · {concept.price_clave}
              {concept.price_vigencia ? ` · ${concept.price_vigencia}` : ""}
            </Badge>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className="font-semibold tabular">
            {money2(concept.price_override != null ? concept.price_override : preview)}
          </div>
          <div className="text-xs text-muted">
            por {concept.unit}
            {concept.price_override != null ? " · matriz en pausa" : ""}
          </div>
        </div>
        <CaretDown
          size={15}
          weight="bold"
          className={`shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="border-t border-border">
          {concept.price_override != null && (
            <div className="flex flex-wrap items-center gap-3 border-b border-border bg-surface-2/60 px-5 py-3 text-sm">
              <span className="min-w-0 flex-1">
                Este concepto se costea a <strong>{money2(concept.price_override)}</strong> por{" "}
                {concept.unit}, tomado de {concept.price_source} · {concept.price_clave}
                {concept.price_vigencia ? ` · vigencia ${concept.price_vigencia}` : ""}. La matriz
                de abajo no se usa mientras el precio adoptado esté activo.
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await clearConceptPrice(concept.code, getBrowserActor());
                    onChanged();
                  } catch {
                    onError(`No se pudo quitar el precio adoptado de ${concept.code}.`);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Volver a la matriz
              </Button>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-2">
                  <Th className="px-5">Recurso</Th>
                  <Th align="right">Cantidad / {concept.unit}</Th>
                  <Th align="right">Costo unitario</Th>
                  <Th align="right">Importe</Th>
                  <Th align="center" className="w-12" aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {draft.map((component) => {
                  const insumo = byCode.get(component.resource_code);
                  if (!insumo) return null;
                  const amount = insumo.is_labor_percentage
                    ? null
                    : component.quantity * insumo.unit_cost;
                  return (
                    <tr key={component.resource_code} className="border-b border-border last:border-0">
                      <Td className="px-5">
                        <div>{insumo.description}</div>
                        <div className="font-mono text-xs text-muted">{insumo.code}</div>
                      </Td>
                      <Td align="right">
                        <Input
                          type="number"
                          step="any"
                          value={component.quantity}
                          onChange={(e) =>
                            setQuantity(component.resource_code, Number(e.target.value))
                          }
                          className="w-24 px-2 py-1 text-right tabular"
                        />
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {insumo.is_labor_percentage
                          ? `${(insumo.unit_cost * 100).toFixed(1)}% MO`
                          : money2(insumo.unit_cost)}
                      </Td>
                      <Td align="right" className="tabular">
                        {amount == null ? "—" : money2(amount)}
                      </Td>
                      <Td align="center">
                        <button
                          type="button"
                          aria-label={`Quitar ${insumo.code}`}
                          onClick={() => removeComponent(component.resource_code)}
                          className="rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
                        >
                          <Trash size={14} />
                        </button>
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3">
            <div className="flex flex-wrap items-center gap-3">
              <select
                value=""
                onChange={(e) => addComponent(e.target.value)}
                className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-muted"
              >
                <option value="">+ Agregar recurso…</option>
                {available.map((insumo) => (
                  <option key={insumo.code} value={insumo.code}>
                    {insumo.code} · {insumo.description}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-sm text-muted">
                Rendimiento
                <Input
                  type="number"
                  step="any"
                  value={rate}
                  onChange={(e) => setRate(e.target.value)}
                  onBlur={commitRate}
                  className="w-24 px-2 py-1 text-right tabular"
                />
                {concept.unit}/día
              </label>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-muted">
                CD unitario: <span className="tabular font-semibold text-foreground">{money2(preview)}</span>
              </span>
              <Button size="sm" variant="primary" onClick={save} disabled={!dirty || busy}>
                Guardar matriz
              </Button>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------------------------------- inline commits --- */

function CommitNumber({
  value,
  onCommit,
}: {
  value: number;
  onCommit: (value: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const [lastValue, setLastValue] = useState(value);
  if (lastValue !== value) {
    setLastValue(value);
    setDraft(String(value));
  }
  return (
    <Input
      type="number"
      step="any"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        const parsed = Number(draft);
        if (parsed > 0 && parsed !== value) onCommit(parsed);
        else setDraft(String(value));
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      className="w-28 px-2 py-1 text-right tabular"
    />
  );
}

function CommitText({
  value,
  onCommit,
  placeholder,
  reference,
}: {
  value: string;
  onCommit: (value: string) => void;
  placeholder?: string;
  reference?: boolean;
}) {
  const [draft, setDraft] = useState(value);
  const [lastValue, setLastValue] = useState(value);
  if (lastValue !== value) {
    setLastValue(value);
    setDraft(value);
  }
  return (
    <Input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      placeholder={placeholder}
      onBlur={() => {
        if (draft.trim() !== value) onCommit(draft.trim());
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      className={`w-48 px-2 py-1 text-xs ${reference ? "text-warning" : ""}`}
      title={reference ? "Precio de referencia: sustitúyelo por tu cotización" : undefined}
    />
  );
}


/* ------------------------------------------------------------- fuentes --- */

function FuentesSection({
  catalog,
  onChanged,
  onError,
  onNotice,
}: {
  catalog: CatalogState;
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [sources, setSources] = useState<ReferenceSource[] | null>(null);
  const [importing, setImporting] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sourceKey, setSourceKey] = useState("");
  const [rows, setRows] = useState<ReferenceRow[] | null>(null);
  const [adopting, setAdopting] = useState<Record<number, string>>({});
  const [adoptingConcept, setAdoptingConcept] = useState<Record<number, string>>({});
  const [ownFile, setOwnFile] = useState<File | null>(null);
  const [ownName, setOwnName] = useState("");
  const [ownVigencia, setOwnVigencia] = useState("");
  const [ownBusy, setOwnBusy] = useState(false);

  const loadSources = useCallback(() => {
    listReferenceSources().then(setSources).catch(() => setSources([]));
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (query.trim().length < 2) {
      const handle = window.setTimeout(() => setRows(null), 0);
      return () => window.clearTimeout(handle);
    }
    let active = true;
    const handle = window.setTimeout(() => {
      searchReference(query.trim(), sourceKey || undefined)
        .then((found) => active && setRows(found))
        .catch(() => active && setRows([]));
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, [query, sourceKey]);

  async function runImport(source: ReferenceSource) {
    setImporting(source.key);
    try {
      const result = await importReferenceSource(source.key, getBrowserActor());
      onNotice(`${source.name}: ${result.rows.toLocaleString("es-MX")} renglones importados`);
      loadSources();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      onError(detail || `No se pudo importar ${source.name}.`);
    } finally {
      setImporting(null);
    }
  }

  async function importOwn() {
    if (!ownFile) return;
    setOwnBusy(true);
    try {
      const result = await importCustomSource(
        ownFile,
        ownName.trim(),
        ownVigencia.trim(),
        getBrowserActor(),
      );
      onNotice(`${result.name}: ${result.rows.toLocaleString("es-MX")} conceptos importados como catálogo propio`);
      setOwnFile(null);
      setOwnName("");
      loadSources();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      onError(detail || "No se pudo importar el catálogo.");
    } finally {
      setOwnBusy(false);
    }
  }

  async function adoptForConcept(row: ReferenceRow) {
    const code = adoptingConcept[row.ref_id];
    if (!code) return;
    try {
      await adoptConceptReference(code, row.ref_id, getBrowserActor());
      onNotice(
        `${code} se costea a ${money2(row.price)} por ${row.unit} (${row.source_name}, ${row.clave}); su matriz queda en pausa`,
      );
      onChanged();
    } catch {
      onError(`No se pudo aplicar la referencia al concepto ${code}.`);
    }
  }

  async function adopt(row: ReferenceRow) {
    const code = adopting[row.ref_id];
    if (!code) return;
    try {
      await adoptReference(code, row.ref_id, getBrowserActor());
      onNotice(`${code} ahora vale ${money2(row.price)} (${row.source_name}, ${row.clave})`);
      onChanged();
    } catch {
      onError(`No se pudo aplicar la referencia a ${code}.`);
    }
  }

  const imported = (sources ?? []).filter((s) => s.imported);

  return (
    <Card className="mb-8 overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <SectionTitle sub="Publicaciones oficiales con fecha y región. Un precio adoptado de aquí queda marcado como publicación, con clave y vigencia.">
          Fuentes de referencia
        </SectionTitle>
      </div>
      <ul className="divide-y divide-border">
        {sources === null ? (
          <li className="px-5 py-3 text-sm text-muted">Cargando fuentes…</li>
        ) : (
          sources.map((source) => (
            <li key={source.key} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-foreground">
                {source.custom ? (
                  <UploadSimple size={16} weight="duotone" />
                ) : source.kind === "costo_horario" ? (
                  <Crane size={16} weight="duotone" />
                ) : (
                  <Books size={16} weight="duotone" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium">{source.name}</div>
                <div className="truncate text-xs text-muted">
                  {source.publisher} · {source.region} · vigencia {source.vigencia}
                </div>
              </div>
              {source.imported ? (
                <Badge tone="success">
                  {source.imported.row_count.toLocaleString("es-MX")} renglones
                </Badge>
              ) : source.available ? (
                <Badge>Descargada</Badge>
              ) : (
                <a
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-muted underline"
                  title={`Guárdala como data/sources/${source.filename}`}
                >
                  No descargada
                </a>
              )}
              {source.custom ? (
                <span className="text-xs text-muted">Vuelve a subir el archivo para actualizarlo</span>
              ) : (
                <Button
                  size="sm"
                  variant={source.imported ? "ghost" : "secondary"}
                  disabled={!source.available || importing !== null}
                  onClick={() => runImport(source)}
                >
                  {importing === source.key
                    ? "Importando…"
                    : source.imported
                      ? "Reimportar"
                      : "Importar"}
                </Button>
              )}
            </li>
          ))
        )}
      </ul>
      <div className="border-t border-border px-5 py-4">
        <div className="mb-2 text-sm font-medium">Catálogo propio</div>
        <p className="mb-3 text-xs text-muted">
          Tu libro de precios en XLSX o CSV (clave, descripción, unidad, precio unitario). Entra a
          la biblioteca marcado como catálogo propio, nunca como publicación.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept=".xlsx,.xlsm,.csv"
            className="text-xs text-muted file:mr-2 file:rounded-md file:border file:border-border file:bg-surface-2 file:px-2 file:py-1 file:text-xs file:text-foreground"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setOwnFile(f);
              if (f && !ownName) setOwnName(f.name.replace(/\.(xlsx|xlsm|csv)$/i, ""));
            }}
          />
          <Input
            value={ownName}
            onChange={(e) => setOwnName(e.target.value)}
            placeholder="Nombre del catálogo"
            className="w-56"
          />
          <Input
            value={ownVigencia}
            onChange={(e) => setOwnVigencia(e.target.value)}
            placeholder="Vigencia (AAAA-MM)"
            className="w-40"
          />
          <Button size="sm" variant="secondary" disabled={!ownFile || ownBusy} onClick={importOwn}>
            {ownBusy ? "Importando…" : "Importar catálogo"}
          </Button>
        </div>
      </div>
      {imported.length > 0 && (
        <div className="border-t border-border px-5 py-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-64 flex-1">
              <MagnifyingGlass
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
              />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar en las publicaciones: tabique, concreto f'c=250, retroexcavadora…"
                className="w-full pl-9"
              />
            </div>
            <select
              value={sourceKey}
              onChange={(e) => setSourceKey(e.target.value)}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">Todas las fuentes</option>
              {imported.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          {rows && (
            <div className="mt-3 overflow-x-auto">
              {rows.length === 0 ? (
                <p className="py-3 text-sm text-muted">Sin resultados.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="py-1.5 pr-3 font-medium">Clave</th>
                      <th className="py-1.5 pr-3 font-medium">Concepto</th>
                      <th className="py-1.5 pr-3 font-medium">Unidad</th>
                      <th className="py-1.5 pr-3 text-right font-medium">P.U.</th>
                      <th className="py-1.5 font-medium">Usar como precio de</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.ref_id} className="border-t border-border align-top">
                        <td className="py-2 pr-3 font-mono text-xs">{row.clave}</td>
                        <td className="py-2 pr-3">
                          <div>{row.description}</div>
                          {row.group_description && (
                            <div className="text-xs text-faint">{row.group_description}</div>
                          )}
                          <div className="text-xs text-faint">
                            {row.source_name} · {row.source_vigencia}
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-muted">{row.unit}</td>
                        <td className="py-2 pr-3 text-right tabular">{money2(row.price)}</td>
                        <td className="py-2">
                          <div className="flex items-center gap-1.5">
                            <select
                              value={adopting[row.ref_id] ?? ""}
                              onChange={(e) =>
                                setAdopting((a) => ({ ...a, [row.ref_id]: e.target.value }))
                              }
                              className="max-w-48 rounded-md border border-border bg-surface px-1.5 py-1 text-xs"
                            >
                              <option value="">insumo…</option>
                              {catalog.insumos
                                .filter((i) => !i.is_labor_percentage)
                                .map((i) => (
                                  <option key={i.code} value={i.code}>
                                    {i.code} · {i.unit}
                                  </option>
                                ))}
                            </select>
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={!adopting[row.ref_id]}
                              onClick={() => adopt(row)}
                            >
                              Aplicar
                            </Button>
                            <select
                              value={adoptingConcept[row.ref_id] ?? ""}
                              onChange={(e) =>
                                setAdoptingConcept((a) => ({ ...a, [row.ref_id]: e.target.value }))
                              }
                              className="max-w-48 rounded-md border border-border bg-surface px-1.5 py-1 text-xs"
                              title="Usar este precio como P.U. del concepto (sustituye su matriz)"
                            >
                              <option value="">concepto…</option>
                              {catalog.concepts
                                .filter((c) => c.unit.toUpperCase() === row.unit.toUpperCase())
                                .map((c) => (
                                  <option key={c.code} value={c.code}>
                                    {c.code} · {c.unit}
                                  </option>
                                ))}
                            </select>
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={!adoptingConcept[row.ref_id]}
                              onClick={() => adoptForConcept(row)}
                            >
                              P.U.
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/* -------------------------------------------------------- salario real --- */

const FSR_FIELDS: { key: keyof FsrParameters; label: string; step?: string }[] = [
  { key: "uma", label: "UMA diaria ($)" },
  { key: "riesgo_trabajo_pct", label: "Riesgo de trabajo (%)", step: "0.001" },
  { key: "infonavit_pct", label: "INFONAVIT (%)" },
  { key: "aguinaldo_days", label: "Aguinaldo (días)" },
  { key: "vacation_days", label: "Vacaciones (días)" },
  { key: "prima_vacacional_pct", label: "Prima vacacional (%)" },
  { key: "holidays", label: "Festivos LFT (días)" },
  { key: "customary_days", label: "Días de costumbre" },
  { key: "isn_pct", label: "ISN estatal (%)" },
];

function SalarioRealSection({
  onChanged,
  onError,
  onNotice,
}: {
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [state, setState] = useState<LaborState | null>(null);
  const [params, setParams] = useState<FsrParameters | null>(null);
  const [categories, setCategories] = useState<LaborCategory[]>([]);
  const [open, setOpen] = useState(false);
  const [showParams, setShowParams] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    getLabor()
      .then((s) => {
        setState(s);
        setParams(s.params);
        setCategories(s.categories.map(({ code, description, salario_nominal }) => ({ code, description, salario_nominal })));
      })
      .catch(() => {});
  }, []);

  async function apply() {
    if (!params) return;
    setBusy(true);
    try {
      const result = await putLabor(params, categories, getBrowserActor());
      setState(result);
      setDirty(false);
      onNotice(`Salario real aplicado a ${result.categories.length} categorías de mano de obra`);
      onChanged();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      onError(detail || "No se pudo aplicar el salario real.");
    } finally {
      setBusy(false);
    }
  }

  const first = state?.categories[0]?.breakdown;

  return (
    <Card className="mb-8 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-foreground">
          <HardHat size={16} weight="duotone" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">Salario real (Fsr) — RLOPSRM art. 190–191</div>
          <div className="text-xs text-muted">
            {first
              ? `Fsr ${first.fsr.toFixed(4)} para el peón · Tp ${first.tp} / Tl ${first.tl} · CONASAMI, UMA e IMSS ${params?.year ?? ""}`
              : "Sn × Fsr con CONASAMI, UMA, IMSS e INFONAVIT vigentes, desglosado por ramo."}
            {state?.applied_at ? ` · aplicado ${state.applied_at}` : " · sin aplicar"}
          </div>
        </div>
        <CaretDown size={14} className={`text-muted transition ${open ? "rotate-180" : ""}`} />
      </button>
      {open && params && (
        <div className="border-t border-border px-5 py-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="py-1.5 pr-3 font-medium">Categoría</th>
                <th className="py-1.5 pr-3 text-right font-medium">Sn (día)</th>
                <th className="py-1.5 pr-3 text-right font-medium">SBC</th>
                <th className="py-1.5 pr-3 text-right font-medium">Ps</th>
                <th className="py-1.5 pr-3 text-right font-medium">Fsr</th>
                <th className="py-1.5 text-right font-medium">Salario real</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((category, index) => {
                const breakdown = state?.categories.find((c) => c.code === category.code)?.breakdown;
                return (
                  <tr key={category.code} className="border-t border-border">
                    <td className="py-1.5 pr-3">
                      <div>{category.description}</div>
                      <div className="font-mono text-xs text-muted">{category.code}</div>
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      <Input
                        type="number"
                        step="0.01"
                        value={category.salario_nominal}
                        onChange={(e) => {
                          const value = Number(e.target.value);
                          setCategories((list) =>
                            list.map((c, i) => (i === index ? { ...c, salario_nominal: value } : c)),
                          );
                          setDirty(true);
                        }}
                        className="w-28 px-2 py-1 text-right tabular"
                      />
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular text-muted">
                      {breakdown ? money2(breakdown.salario_base_cotizacion) : "—"}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular text-muted">
                      {breakdown ? breakdown.ps.toFixed(4) : "—"}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular">
                      {breakdown ? breakdown.fsr.toFixed(4) : "—"}
                    </td>
                    <td className="py-1.5 text-right tabular font-medium">
                      {breakdown ? money2(breakdown.salario_real) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {dirty && (
            <p className="mt-2 text-xs text-muted">
              Los valores de SBC, Ps y Fsr se recalculan al aplicar.
            </p>
          )}
          <button
            type="button"
            onClick={() => setShowParams((v) => !v)}
            className="mt-3 text-xs font-medium text-muted hover:text-foreground"
          >
            {showParams ? "Ocultar parámetros" : "Parámetros (UMA, IMSS, LFT, ISN)"}
          </button>
          {showParams && (
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              {FSR_FIELDS.map((field) => (
                <label key={field.key} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-muted">{field.label}</span>
                  <Input
                    type="number"
                    step={field.step ?? "any"}
                    value={Number(params[field.key])}
                    onChange={(e) => {
                      setParams({ ...params, [field.key]: Number(e.target.value) });
                      setDirty(true);
                    }}
                    className="w-24 px-2 py-1 text-right tabular"
                  />
                </label>
              ))}
              <label className="flex items-center gap-2 text-xs text-muted">
                <input
                  type="checkbox"
                  checked={params.isn_in_fsr}
                  onChange={(e) => {
                    setParams({ ...params, isn_in_fsr: e.target.checked });
                    setDirty(true);
                  }}
                  className="h-4 w-4 accent-accent"
                />
                Incluir ISN en el Fsr (por defecto va en indirectos)
              </label>
            </div>
          )}
          {first && (
            <ul className="mt-3 space-y-0.5 text-xs text-faint">
              {first.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex justify-end">
            <Button variant="primary" onClick={apply} disabled={busy}>
              {busy ? "Aplicando…" : "Aplicar salario real al catálogo"}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

/* -------------------------------------------------------- costo horario --- */

const EQ_FIELDS: { key: keyof EquipmentParameters; label: string }[] = [
  { key: "vm", label: "Vm · valor de la máquina ($)" },
  { key: "vr", label: "Vr · valor de rescate ($)" },
  { key: "ve", label: "Ve · vida económica (h)" },
  { key: "hea", label: "Hea · horas efectivas/año" },
  { key: "i", label: "i · tasa de interés anual" },
  { key: "s", label: "s · prima de seguros" },
  { key: "ko", label: "Ko · coef. mantenimiento" },
  { key: "gh", label: "Gh · combustible (l/h)" },
  { key: "pc", label: "Pc · precio combustible ($/l)" },
  { key: "ah", label: "Ah · aceite consumido (l/h)" },
  { key: "ga", label: "Ga · aceite por cambios (l/h)" },
  { key: "pa", label: "Pa · precio del aceite ($/l)" },
  { key: "pn", label: "Pn · valor de llantas ($)" },
  { key: "vn", label: "Vn · vida de llantas (h)" },
  { key: "pa_e", label: "Pa · piezas especiales ($)" },
  { key: "va", label: "Va · vida piezas esp. (h)" },
  { key: "sr", label: "Sr · salario real operador/turno" },
  { key: "ht", label: "Ht · horas efectivas/turno" },
  { key: "other_energy", label: "Otras energías ($/h)" },
];

const EQ_DEFAULTS: EquipmentParameters = {
  vm: 1000000, vr: 100000, ve: 10000, hea: 2000, i: 0.12, s: 0.03, ko: 0.8,
  gh: 0, pc: 25, ah: 0, ga: 0, pa: 90, pn: 0, vn: 0, pa_e: 0, va: 0, sr: 0, ht: 8,
  other_energy: 0,
};

function EquipmentDialog({
  insumo,
  onClose,
  onSaved,
  onError,
}: {
  insumo: CatalogInsumo;
  onClose: () => void;
  onSaved: () => void;
  onError: (message: string) => void;
}) {
  const [params, setParams] = useState<EquipmentParameters | null>(null);
  const [breakdown, setBreakdown] = useState<EquipmentBreakdown | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getEquipment(insumo.code)
      .then((r) => {
        setParams(r.params ?? EQ_DEFAULTS);
        setBreakdown(r.breakdown);
      })
      .catch(() => setParams(EQ_DEFAULTS));
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [insumo.code, onClose]);

  const estimate = useMemo(() => {
    if (!params) return null;
    const d = (params.vm - params.vr) / params.ve;
    const base = (params.vm + params.vr) / (2 * params.hea);
    const fijos = d + base * params.i + base * params.s + params.ko * d;
    const consumos =
      params.gh * params.pc +
      (params.ah + params.ga) * params.pa +
      (params.vn > 0 ? params.pn / params.vn : 0) +
      (params.va > 0 ? params.pa_e / params.va : 0) +
      params.other_energy;
    return fijos + consumos + params.sr / params.ht;
  }, [params]);

  async function save() {
    if (!params) return;
    setBusy(true);
    try {
      const row = await putEquipment(insumo.code, params, undefined, getBrowserActor());
      setBreakdown(row.breakdown);
      onSaved();
    } catch {
      onError(`No se pudo guardar el costo horario de ${insumo.code}.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <button type="button" aria-label="Cerrar" onClick={onClose} className="absolute inset-0 bg-foreground/40 backdrop-blur-[2px]" />
      <div role="dialog" aria-modal="true" className="toast-in relative w-full max-w-2xl rounded-xl border border-border bg-surface p-5 shadow-lg">
        <h2 className="text-[0.95rem] font-semibold">Costo horario · {insumo.description}</h2>
        <p className="mb-4 text-xs text-muted">
          RLOPSRM art. 194–206: cargos fijos + consumos + operación por hora efectiva. El resultado sustituye el costo unitario del insumo y queda marcado como calculado.
        </p>
        {params === null ? (
          <p className="text-sm text-muted">Cargando…</p>
        ) : (
          <>
            <div className="grid max-h-80 gap-2 overflow-y-auto pr-1 sm:grid-cols-2">
              {EQ_FIELDS.map((field) => (
                <label key={field.key} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-muted">{field.label}</span>
                  <Input
                    type="number"
                    step="any"
                    value={params[field.key]}
                    onChange={(e) => setParams({ ...params, [field.key]: Number(e.target.value) })}
                    className="w-32 px-2 py-1 text-right tabular"
                  />
                </label>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-end justify-between gap-3 border-t border-border pt-3">
              <div>
                <div className="microlabel">Costo horario estimado</div>
                <div className="font-display text-xl font-semibold tabular">
                  {estimate != null ? money2(estimate) : "—"} / hr
                </div>
                {breakdown && (
                  <div className="text-xs text-muted">
                    Guardado: fijos {money2(breakdown.cargos_fijos)} · consumos {money2(breakdown.consumos)} · operación {money2(breakdown.operacion)}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={onClose}>
                  Cancelar
                </Button>
                <Button variant="primary" onClick={save} disabled={busy}>
                  Guardar y aplicar
                </Button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
