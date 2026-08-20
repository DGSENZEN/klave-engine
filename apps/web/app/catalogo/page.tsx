"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CaretDown,
  Check,
  DownloadSimple,
  Plus,
  Trash,
  UploadSimple,
} from "@phosphor-icons/react";
import {
  ApiError,
  createInsumo,
  getCatalog,
  importCatalogPrices,
  money2,
  updateApu,
  updateInsumo,
  updateRendimiento,
  type ApuComponent,
  type CatalogConcept,
  type CatalogInsumo,
  type CatalogState,
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
import { ThemeToggle } from "@/components/ThemeToggle";

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
    <div className="mx-auto max-w-5xl px-5 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-foreground"
        >
          <ArrowLeft size={13} weight="bold" /> Proyectos
        </Link>
        <ThemeToggle />
      </div>

      <PageHeader
        title="Catálogo del taller"
        sub="Insumos, matrices de precio unitario y rendimientos que usa cada cálculo. Cada precio indica su fuente: sustituye las referencias por tus cotizaciones."
        actions={
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onImportFile(file);
                e.target.value = "";
              }}
            />
            <Button onClick={() => fileRef.current?.click()}>
              <UploadSimple size={15} weight="bold" /> Importar CSV
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
          <InsumosSection catalog={catalog} onChanged={reload} onError={setError} />
          <ApusSection catalog={catalog} onChanged={reload} onError={setError} />
        </>
      )}
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

  async function commitInsumo(
    code: string,
    patch: Partial<Pick<CatalogInsumo, "description" | "unit_cost" | "source">>,
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
                    reference={insumo.source === "Referencia Klave"}
                    onCommit={(value) => commitInsumo(insumo.code, { source: value })}
                  />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

  return (
    <div>
      <SectionTitle sub="Cantidad de cada recurso por unidad de concepto. El costo directo unitario se recalcula con la ecuación %MO para herramienta menor.">
        Matrices de precio unitario
      </SectionTitle>
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
          <span className="font-medium">{concept.description}</span>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-semibold tabular">{money2(preview)}</div>
          <div className="text-xs text-muted">por {concept.unit}</div>
        </div>
        <CaretDown
          size={15}
          weight="bold"
          className={`shrink-0 text-faint transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="border-t border-border">
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
