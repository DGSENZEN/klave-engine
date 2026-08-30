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
  Trash,
  UploadSimple,
} from "@phosphor-icons/react";
import {
  ApiError,
  apiMessage,
  unitMismatch,
  adoptConceptReference,
  adoptReference,
  clearConceptPrice,
  createConcept,
  createInsumo,
  getCatalog,
  getEquipment,
  getLabor,
  getLaborPresets,
  previewLabor,
  type LaborPreviewRow,
  type RegionPreset,
  importCatalogPrices,
  importCustomSource,
  importDestajos,
  importMatrices,
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
  listProjects,
  type ProjectSummary,
  type ReferenceRow,
  type ReferenceSource,
  listImports,
  undoImport,
  type CatalogImport,
} from "@/lib/api";
import Link from "next/link";
import { getBrowserActor } from "@/lib/collab";
import { RESOURCE_TYPE_LABELS, downloadCsv } from "@/lib/format";
import {
  Badge,
  Button,
  Callout,
  Card,
  Checkbox,
  Disclosure,
  Input,
  PageHeader,
  SectionTitle,
  Select,
  Skeleton,
  SkeletonHeader,
  SkeletonTable,
  Tabs,
  Td,
  Th,
} from "@/components/ui";
import { AliasesSection } from "@/components/AliasesSection";
import { ButtonMenu, MenuItem } from "@/components/Menu";
import { Modal } from "@/components/Modal";
import { PlantillasSection } from "@/components/PlantillasSection";
import { VigenciaChip, VigenciaSection } from "@/components/VigenciaSection";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

type CatalogTab = "insumos" | "conceptos" | "fuentes" | "plantillas" | "salario";
const TABS: CatalogTab[] = ["insumos", "conceptos", "fuentes", "plantillas", "salario"];

export default function CatalogoPage() {
  const [catalog, setCatalog] = useState<CatalogState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  // The tab lives in ?tab= so a link can open a section; read after mount
  // (static route, no Suspense) and mirrored with replaceState on change.
  const [tab, setTabState] = useState<CatalogTab>("insumos");
  useEffect(() => {
    const handle = window.setTimeout(() => {
      const param = new URLSearchParams(window.location.search).get("tab");
      if (TABS.includes(param as CatalogTab)) setTabState(param as CatalogTab);
    }, 0);
    return () => window.clearTimeout(handle);
  }, []);
  const setTab = useCallback((next: CatalogTab) => {
    setTabState(next);
    window.history.replaceState(null, "", next === "insumos" ? "/catalogo" : `/catalogo?tab=${next}`);
  }, []);
  const fileRef = useRef<HTMLInputElement>(null);
  const matricesRef = useRef<HTMLInputElement>(null);
  const destajosRef = useRef<HTMLInputElement>(null);

  // The projects this catálogo prices: a change here is theirs to recalculate.
  useEffect(() => {
    listProjects()
      .then((list) =>
        setProjects(
          list.filter((p) => !p.archived && p.status === "processed"),
        ),
      )
      .catch(() => {});
  }, []);

  const reload = useCallback(() => {
    getCatalog()
      .then((state) => {
        setCatalog(state);
        setError(null);
      })
      .catch(() =>
        setError(
          "No se pudo cargar el catálogo. Revisa que el servidor esté activo.",
        ),
      );
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
      setError(apiMessage(e, "No se pudo importar el CSV."));
    }
  }

  async function onImportMatrices(file: File) {
    try {
      const result = await importMatrices(
        file,
        file.name.replace(/\.[^.]+$/, ""),
        getBrowserActor(),
      );
      const problems = result.problems.length
        ? ` · ${result.problems.length} avisos: ${result.problems.slice(0, 3).join(" / ")}${result.problems.length > 3 ? "…" : ""}`
        : "";
      setNotice(
        `Matrices importadas de ${result.source}: ${result.concepts_created} conceptos nuevos, ` +
          `${result.concepts_updated} actualizados, ${result.insumos_upserted} insumos (cotización)${problems}`,
      );
      reload();
    } catch (e) {
      setError(apiMessage(e, "No se pudieron importar las matrices."));
    }
  }

  async function onImportDestajos(file: File) {
    try {
      const result = await importDestajos(
        file,
        file.name.replace(/\.[^.]+$/, ""),
        getBrowserActor(),
      );
      const avisos = result.problems.length
        ? ` · ${result.problems.length} avisos: ${result.problems[0]}`
        : "";
      setNotice(
        `Destajos importados de ${result.source}: ${result.concepts_created} matrices, ` +
          `${result.insumos_upserted} insumos con su costo de cuadrilla${avisos}`,
      );
      reload();
    } catch (e) {
      setError(apiMessage(e, "No se pudieron importar los destajos."));
    }
  }


  function exportCsv() {
    if (!catalog) return;
    downloadCsv("catalogo_insumos.csv", [
      [
        "code",
        "description",
        "unit",
        "resource_type",
        "unit_cost",
        "source",
        "vigencia",
      ],
      ...catalog.insumos.map((insumo) => [
        insumo.code,
        insumo.description,
        insumo.unit,
        insumo.resource_type,
        insumo.unit_cost,
        insumo.source,
        insumo.vigencia ?? "",
      ]),
    ]);
  }

  return (
    <div className="min-h-screen">
      <WorkspaceHeader active="catalogo" />
      <main className="mx-auto max-w-5xl px-5 py-8 sm:px-6">
        <PageHeader
          title="Catálogo del taller"
          sub="Insumos, matrices de precio unitario y rendimientos que usa cada cálculo. Cada precio indica su fuente: sustituye las referencias por tus cotizaciones. Los términos viven en el glosario (/glosario)."
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
              <input
                ref={matricesRef}
                type="file"
                accept=".csv,.xlsx"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onImportMatrices(file);
                  e.target.value = "";
                }}
              />
              <input
                ref={destajosRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onImportDestajos(file);
                  e.target.value = "";
                }}
              />
              <ButtonMenu
                label="Importar…"
                icon={<UploadSimple size={15} weight="bold" />}
                width="w-80"
              >
                {(close) => (
                  <>
                    <MenuItem
                      onSelect={() => {
                        close();
                        fileRef.current?.click();
                      }}
                      hint="CSV o XLSX con columnas clave y precio; actualiza el costo de insumos que ya existen."
                    >
                      Precios de insumos
                    </MenuItem>
                    <MenuItem
                      onSelect={() => {
                        close();
                        matricesRef.current?.click();
                      }}
                      hint="Catálogo de conceptos con insumos exportado de OPUS o Neodata (XLSX/CSV): crea conceptos con su matriz."
                    >
                      Matrices de OPUS / Neodata
                    </MenuItem>
                    <MenuItem
                      onSelect={() => {
                        close();
                        destajosRef.current?.click();
                      }}
                      hint="Catálogo de destajos por bloques (XLSX) con sus matrices y sus cuadrillas: trae el costo real de la mano de obra, que ninguna publicación da suelto."
                    >
                      Destajos con cuadrillas
                    </MenuItem>
                    <MenuItem
                      onSelect={() => {
                        close();
                        setTab("fuentes");
                      }}
                      hint="Tu libro de precios (clave, descripción, unidad, precio). Entra a la biblioteca de referencia como catálogo propio."
                    >
                      Catálogo propio
                    </MenuItem>
                    <MenuItem
                      onSelect={() => {
                        close();
                        setTab("fuentes");
                      }}
                      hint="Tabuladores oficiales (CDMX, SICT) descargados en el servidor; se importan con su vigencia."
                    >
                      Publicación oficial
                    </MenuItem>
                    <MenuItem
                      onSelect={() => {
                        close();
                        setTab("plantillas");
                      }}
                      hint="Un presupuesto terminado con sus m²: se vuelve reglas por m² y conceptos con precio."
                    >
                      Presupuesto anterior (plantilla)
                    </MenuItem>
                  </>
                )}
              </ButtonMenu>
              <Button onClick={exportCsv} disabled={!catalog}>
                <DownloadSimple size={15} weight="bold" /> Exportar insumos (CSV)
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
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setNotice(null)}
                >
                  <Check size={14} weight="bold" /> Entendido
                </Button>
              }
            >
              <span>
                {notice}.{" "}
                {projects.length === 0
                  ? "Los proyectos toman los cambios al recalcular."
                  : projects.length === 1
                    ? "Se aplica al recalcular "
                    : `Se aplica al recalcular cada proyecto (${projects.length}): `}
                {projects.slice(0, 4).map((p, i) => (
                  <span key={p.project_id}>
                    {i > 0 && ", "}
                    <Link
                      href={`/proyecto/${encodeURIComponent(p.project_id)}/parametros`}
                      className="font-medium underline"
                    >
                      {p.name}
                    </Link>
                  </span>
                ))}
                {projects.length > 4 && ` y ${projects.length - 4} más`}
                {projects.length > 0 && "."}
              </span>
            </Callout>
          </div>
        )}

        <Tabs
          className="mb-5"
          value={tab}
          onChange={setTab}
          items={[
            { key: "insumos", label: "Insumos", count: catalog?.insumos.length },
            { key: "conceptos", label: "Conceptos y matrices", count: catalog?.concepts.length },
            { key: "fuentes", label: "Fuentes de referencia" },
            { key: "plantillas", label: "Plantillas y paramétricos" },
            { key: "salario", label: "Salario real y vigencia" },
          ]}
        />

        {!catalog ? (
          <>
            <SkeletonHeader />
            <SkeletonTable rows={8} />
          </>
        ) : tab === "insumos" ? (
          <InsumosSection catalog={catalog} onChanged={reload} onError={setError} />
        ) : tab === "conceptos" ? (
          <>
            <ApusSection catalog={catalog} onChanged={reload} onError={setError} />
            <div className="mt-8">
              <AliasesSection onChanged={reload} onError={setError} />
            </div>
          </>
        ) : tab === "fuentes" ? (
          <FuentesSection
            catalog={catalog}
            onChanged={reload}
            onError={setError}
            onNotice={setNotice}
          />
        ) : tab === "plantillas" ? (
          <PlantillasSection onChanged={reload} onError={setError} onNotice={setNotice} />
        ) : (
          <>
            <SalarioRealSection onChanged={reload} onError={setError} onNotice={setNotice} />
            <VigenciaSection onChanged={reload} onError={setError} onNotice={setNotice} />
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
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.insumos.filter(
      (insumo) =>
        (!typeFilter || insumo.resource_type === typeFilter) &&
        (!q ||
          insumo.code.toLowerCase().includes(q) ||
          insumo.description.toLowerCase().includes(q) ||
          insumo.source.toLowerCase().includes(q)),
    );
  }, [catalog.insumos, query, typeFilter]);

  async function commitInsumo(
    code: string,
    patch: Partial<
      Pick<
        CatalogInsumo,
        "description" | "unit_cost" | "source" | "source_type" | "vigencia"
      >
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
      <div className="border-b border-border px-5 py-4">
        <SectionTitle sub="El costo unitario alimenta cada matriz de APU; descripción y costo se editan en su lugar. La fuente documenta de dónde viene el precio.">
          Insumos
        </SectionTitle>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-3">
        <div className="relative flex-1">
          <MagnifyingGlass
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar por clave, descripción o fuente…"
            className="w-full pl-9"
            aria-label="Buscar insumo"
          />
        </div>
        <Select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Tipo">
          <option value="">Todos los tipos</option>
          <option value="material">Material</option>
          <option value="mano_de_obra">Mano de obra</option>
          <option value="equipo">Equipo</option>
        </Select>
        <span className="text-xs text-muted">
          {visible.length === catalog.insumos.length
            ? `${catalog.insumos.length} insumos`
            : `${visible.length} de ${catalog.insumos.length}`}
        </span>
      </div>
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
            {visible.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-6 text-center text-sm text-muted">
                  Ningún insumo coincide con «{query.trim()}».
                </td>
              </tr>
            )}
            {visible.map((insumo) => (
              <tr
                key={insumo.code}
                className="border-b border-border last:border-0"
              >
                <Td className="px-5">
                  <CommitText
                    value={insumo.description}
                    placeholder="Descripción"
                    onCommit={(value) =>
                      commitInsumo(insumo.code, { description: value })
                    }
                  />
                  <div className="font-mono text-xs text-muted">
                    {insumo.code}
                  </div>
                </Td>
                <Td>
                  <Badge>
                    {RESOURCE_TYPE_LABELS[insumo.resource_type] ??
                      insumo.resource_type}
                  </Badge>
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
                      onCommit={(value) =>
                        commitInsumo(insumo.code, { unit_cost: value })
                      }
                    />
                  )}
                </Td>
                <Td className="px-5">
                  <CommitText
                    value={insumo.source}
                    placeholder="p. ej. cotización proveedor"
                    reference={insumo.source_type === "referencia"}
                    onCommit={(value) =>
                      commitInsumo(insumo.code, { source: value })
                    }
                  />
                  <div className="mt-1 flex items-center gap-1.5">
                    <Select
                      value={insumo.source_type}
                      onChange={(e) =>
                        commitInsumo(insumo.code, {
                          source_type: e.target
                            .value as CatalogInsumo["source_type"],
                        })
                      }
                      className="text-muted"
                      size="sm"
                    >
                      <option value="referencia">Referencia</option>
                      <option value="cotizacion">Cotización</option>
                      <option value="publicacion">Publicación</option>
                      <option value="calculado">Calculado</option>
                    </Select>
                    {insumo.resource_type === "equipo" &&
                      !insumo.is_labor_percentage && (
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
                    <VigenciaChip vigencia={insumo.vigencia} />
                  </div>
                </Td>
              </tr>
            ))}
            <tr>
              <td colSpan={5} className="px-0 py-0">
                {adding ? (
                  <NewInsumoRow
                    onDone={() => {
                      setAdding(false);
                      onChanged();
                    }}
                    onError={onError}
                  />
                ) : (
                  <button
                    type="button"
                    onClick={() => setAdding(true)}
                    className="w-full px-5 py-2.5 text-left text-sm text-faint transition-colors hover:bg-surface-2/60 hover:text-foreground"
                  >
                    + Nuevo insumo
                  </button>
                )}
              </td>
            </tr>
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
      <Select
        value={resourceType}
        onChange={(e) => setResourceType(e.target.value)}
      >
        <option value="material">Material</option>
        <option value="mano_de_obra">Mano de obra</option>
        <option value="equipo">Equipo</option>
      </Select>
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
  // Varios conceptos abiertos a la vez: la matriz es un renglón hijo de la
  // hoja, no un panel aparte — el idioma de OPUS con nuestra piel.
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [creatingIn, setCreatingIn] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const byPhase = useMemo(() => {
    const q = query.trim().toLowerCase();
    const phases = new Map<string, CatalogConcept[]>();
    for (const phase of catalog.phase_order) phases.set(phase, []);
    for (const concept of catalog.concepts) {
      if (
        q &&
        !concept.code.toLowerCase().includes(q) &&
        !concept.description.toLowerCase().includes(q) &&
        !(concept.price_clave ?? "").toLowerCase().includes(q)
      ) {
        continue;
      }
      const list = phases.get(concept.phase);
      if (list) list.push(concept);
      else phases.set(concept.phase, [concept]);
    }
    // Con búsqueda las fases vacías sobran; sin búsqueda se quedan para que
    // el renglón fantasma pueda crear el primer concepto de una fase.
    return [...phases.entries()].filter(([, concepts]) => !q || concepts.length > 0);
  }, [catalog, query]);
  const shown = byPhase.reduce((sum, [, concepts]) => sum + concepts.length, 0);

  function toggle(code: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  return (
    <div>
      <SectionTitle sub="Cantidad de cada recurso por unidad de concepto, editable en su lugar: cada celda guarda al salir. El costo directo se recalcula con la ecuación %MO para herramienta menor.">
        Matrices de precio unitario
      </SectionTitle>
      <div className="mb-4 mt-3 flex flex-wrap items-center gap-2">
        <div className="relative flex-1">
          <MagnifyingGlass
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar concepto por clave, descripción o clave de referencia…"
            className="w-full pl-9"
            aria-label="Buscar concepto"
          />
        </div>
        <span className="text-xs text-muted">
          {shown === catalog.concepts.length ? `${shown} conceptos` : `${shown} de ${catalog.concepts.length}`}
        </span>
      </div>
      {shown === 0 && query.trim() !== "" && (
        <p className="py-6 text-center text-sm text-muted">
          Ningún concepto coincide con «{query.trim()}».
        </p>
      )}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <Th className="px-5">Concepto / recurso</Th>
                <Th align="right">Cantidad</Th>
                <Th align="right">Costo</Th>
                <Th align="right" className="px-5">
                  Importe
                </Th>
              </tr>
            </thead>
            <tbody>
              {byPhase.map(([phase, concepts]) => (
                <PhaseRows
                  key={phase}
                  phase={phase}
                  concepts={concepts}
                  catalog={catalog}
                  open={open}
                  onToggle={toggle}
                  creating={creatingIn === phase}
                  onCreating={(value) => setCreatingIn(value ? phase : null)}
                  onChanged={onChanged}
                  onError={onError}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function PhaseRows({
  phase,
  concepts,
  catalog,
  open,
  onToggle,
  creating,
  onCreating,
  onChanged,
  onError,
}: {
  phase: string;
  concepts: CatalogConcept[];
  catalog: CatalogState;
  open: Set<string>;
  onToggle: (code: string) => void;
  creating: boolean;
  onCreating: (value: boolean) => void;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  return (
    <>
      <tr className="border-b border-border bg-surface-2/60">
        <td colSpan={4} className="px-5 py-1.5">
          <div className="flex items-center justify-between">
            <span className="microlabel">{phase}</span>
            <button
              type="button"
              onClick={() => onCreating(!creating)}
              className="rounded-md px-1.5 py-0.5 text-xs text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              + concepto
            </button>
          </div>
        </td>
      </tr>
      {creating && (
        <NewConceptRow
          phase={phase}
          insumos={catalog.insumos}
          onDone={() => {
            onCreating(false);
            onChanged();
          }}
          onError={onError}
        />
      )}
      {concepts.map((concept) => (
        <ConceptRows
          key={concept.code}
          concept={concept}
          components={catalog.apus[concept.code] ?? []}
          insumos={catalog.insumos}
          open={open.has(concept.code)}
          onToggle={() => onToggle(concept.code)}
          onChanged={onChanged}
          onError={onError}
        />
      ))}
    </>
  );
}

/**
 * Buscar un insumo tecleando, no desplegando quinientos: filtra por clave y
 * descripción, Enter toma el primero. El idioma de captura rápida de OPUS.
 */
function InsumoSearch({
  insumos,
  exclude,
  placeholder,
  onPick,
}: {
  insumos: CatalogInsumo[];
  exclude?: Set<string>;
  placeholder: string;
  onPick: (code: string) => void;
}) {
  const [term, setTerm] = useState("");
  const matches = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (q.length < 1) return [];
    return insumos
      .filter(
        (insumo) =>
          !exclude?.has(insumo.code) &&
          (insumo.code.toLowerCase().includes(q) ||
            insumo.description.toLowerCase().includes(q)),
      )
      .slice(0, 8);
  }, [insumos, exclude, term]);
  return (
    <div className="relative">
      <Input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-full px-2 py-1.5 text-sm"
        onKeyDown={(e) => {
          if (e.key === "Enter" && matches[0]) {
            e.preventDefault();
            onPick(matches[0].code);
            setTerm("");
          }
          if (e.key === "Escape") setTerm("");
        }}
      />
      {matches.length > 0 && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-64 w-full min-w-72 overflow-y-auto rounded-lg border border-border-strong bg-surface p-1 shadow-lg">
          {matches.map((insumo) => (
            <button
              key={insumo.code}
              type="button"
              onClick={() => {
                onPick(insumo.code);
                setTerm("");
              }}
              className="flex w-full items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-surface-2"
            >
              <span className="shrink-0 font-mono text-xs text-muted">{insumo.code}</span>
              <span className="min-w-0 flex-1 truncate">{insumo.description}</span>
              <span className="tabular shrink-0 text-xs text-muted">
                {insumo.is_labor_percentage
                  ? `${(insumo.unit_cost * 100).toFixed(1)}% MO`
                  : money2(insumo.unit_cost)}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function NewConceptRow({
  phase,
  insumos,
  onDone,
  onError,
}: {
  phase: string;
  insumos: CatalogInsumo[];
  onDone: () => void;
  onError: (message: string) => void;
}) {
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [unit, setUnit] = useState("");
  const [rate, setRate] = useState("");
  const [resourceCode, setResourceCode] = useState("");
  const [busy, setBusy] = useState(false);
  const primerRecurso = insumos.find((insumo) => insumo.code === resourceCode);

  async function submit() {
    const production = Number(rate);
    if (!code.trim() || description.trim().length < 3 || !unit.trim() || !(production > 0)) {
      onError("Completa clave, descripción, unidad y rendimiento positivo.");
      return;
    }
    if (!resourceCode) {
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
          components: [{ resource_code: resourceCode, quantity: 1 }],
        },
        getBrowserActor(),
      );
      onDone();
    } catch (e) {
      onError(apiMessage(e, "No se pudo crear el concepto."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="border-b border-border bg-surface-2/40">
      <td colSpan={4} className="px-5 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="CLAVE"
            className="w-28 px-2 py-1.5 font-mono text-xs uppercase"
          />
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Descripción del concepto"
            className="min-w-48 flex-1 px-2 py-1.5"
          />
          <Input
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            placeholder="UN"
            className="w-16 px-2 py-1.5 uppercase"
          />
          <Input
            type="number"
            step="any"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            placeholder="Rend./día"
            className="w-24 px-2 py-1.5 text-right tabular"
          />
          <div className="min-w-56 flex-1">
            {primerRecurso ? (
              <button
                type="button"
                onClick={() => setResourceCode("")}
                className="flex w-full items-baseline gap-2 rounded-lg border border-border px-2 py-1.5 text-left text-sm transition-colors hover:bg-surface-2"
                title="Cambiar recurso"
              >
                <span className="font-mono text-xs text-muted">{primerRecurso.code}</span>
                <span className="min-w-0 flex-1 truncate">{primerRecurso.description}</span>
              </button>
            ) : (
              <InsumoSearch
                insumos={insumos}
                placeholder="Primer recurso del APU (teclea para buscar)…"
                onPick={setResourceCode}
              />
            )}
          </div>
          <Button size="sm" variant="primary" onClick={submit} disabled={busy}>
            Crear
          </Button>
        </div>
      </td>
    </tr>
  );
}

/** Mirrors the backend equation: %MO lines cost = fraction × labor subtotal. */
function directUnitCost(
  components: ApuComponent[],
  insumos: CatalogInsumo[],
): number {
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

/**
 * El concepto y su matriz como renglones de la misma hoja: la fila abre en
 * su lugar, cada celda guarda al salir (sin botón de guardar) y el recurso
 * nuevo se busca tecleando. Quitar aparece al pasar el cursor.
 */
function ConceptRows({
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
  const [busy, setBusy] = useState(false);
  const [rate, setRate] = useState(String(concept.production_rate_per_day));
  const byCode = useMemo(
    () => new Map(insumos.map((insumo) => [insumo.code, insumo])),
    [insumos],
  );

  // Re-sync local drafts when fresh catalog state arrives (render-time adjust).
  const [lastComponents, setLastComponents] = useState(components);
  if (lastComponents !== components) {
    setLastComponents(components);
    setDraft(components);
    setRate(String(concept.production_rate_per_day));
  }

  async function saveDraft(next: ApuComponent[]) {
    if (next.length === 0) {
      onError("La matriz no puede quedar vacía: un concepto sin recursos no tiene costo.");
      setDraft(components);
      return;
    }
    if (next.some((component) => !(component.quantity > 0))) {
      return; // la celda sigue en edición; se guarda cuando la cantidad sea válida
    }
    setBusy(true);
    try {
      await updateApu(concept.code, next, getBrowserActor());
      onChanged();
    } catch {
      onError(`No se pudo guardar la matriz de ${concept.code}.`);
      setDraft(components);
    } finally {
      setBusy(false);
    }
  }

  function setQuantity(resourceCode: string, quantity: number) {
    setDraft((current) =>
      current.map((component) =>
        component.resource_code === resourceCode ? { ...component, quantity } : component,
      ),
    );
  }

  function commitQuantity(resourceCode: string) {
    const original = components.find((c) => c.resource_code === resourceCode)?.quantity;
    const edited = draft.find((c) => c.resource_code === resourceCode)?.quantity;
    if (edited == null || edited === original) return;
    if (!(edited > 0)) {
      setDraft(components);
      return;
    }
    void saveDraft(draft);
  }

  function removeComponent(resourceCode: string) {
    const next = draft.filter((component) => component.resource_code !== resourceCode);
    setDraft(next);
    void saveDraft(next);
  }

  function addComponent(resourceCode: string) {
    if (!resourceCode || draft.some((c) => c.resource_code === resourceCode)) return;
    const next = [...draft, { resource_code: resourceCode, quantity: 1 }];
    setDraft(next);
    void saveDraft(next);
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
  const enMatriz = new Set(draft.map((component) => component.resource_code));

  return (
    <>
      <tr
        className={`cursor-pointer border-b border-border transition-colors hover:bg-surface-2/50 ${
          open ? "bg-surface-2/40" : ""
        }`}
        onClick={onToggle}
        aria-expanded={open}
      >
        <Td className="px-5">
          <div className="flex items-center gap-2">
            <CaretDown
              size={13}
              weight="bold"
              className={`shrink-0 text-faint transition-transform ${open ? "" : "-rotate-90"}`}
            />
            <div className="min-w-0">
              <span className="font-mono text-xs text-muted">{concept.code}</span>{" "}
              <span className="font-medium">{concept.description}</span>{" "}
              {concept.detection_backed && <Badge tone="accent">Detección</Badge>}
              {concept.price_override != null && (
                <Badge tone="warning">
                  P.U. de {concept.price_source} · {concept.price_clave}
                </Badge>
              )}
            </div>
          </div>
        </Td>
        <Td align="right" className="text-muted">
          por {concept.unit}
        </Td>
        <Td align="right" className="tabular text-muted">
          {draft.length} recursos
        </Td>
        <Td align="right" className="tabular px-5 font-semibold">
          {money2(concept.price_override != null ? concept.price_override : preview)}
        </Td>
      </tr>
      {open && concept.price_override != null && (
        <tr className="border-b border-border bg-warning-soft/60">
          <td colSpan={4} className="px-5 py-2 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className="min-w-0 flex-1">
                Se costea a <strong>{money2(concept.price_override)}</strong> por {concept.unit},
                de {concept.price_source} · {concept.price_clave}
                {concept.price_vigencia ? ` · vigencia ${concept.price_vigencia}` : ""}. La
                matriz no se usa mientras el precio adoptado esté activo.
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={async (event) => {
                  event.stopPropagation();
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
          </td>
        </tr>
      )}
      {open &&
        draft.map((component) => {
          const insumo = byCode.get(component.resource_code);
          if (!insumo) return null;
          const amount = insumo.is_labor_percentage
            ? null
            : component.quantity * insumo.unit_cost;
          return (
            <tr
              key={component.resource_code}
              className="group border-b border-border bg-surface-2/20 last:border-0"
            >
              <Td className="px-5">
                <div className="flex items-center gap-2 pl-6">
                  <div className="min-w-0 flex-1">
                    <span className="text-sm">{insumo.description}</span>{" "}
                    <span className="font-mono text-xs text-muted">{insumo.code}</span>
                  </div>
                  <button
                    type="button"
                    aria-label={`Quitar ${insumo.code}`}
                    onClick={() => removeComponent(component.resource_code)}
                    className="rounded-md p-1 text-faint opacity-0 transition group-hover:opacity-100 hover:bg-danger-soft hover:text-danger"
                  >
                    <Trash size={14} />
                  </button>
                </div>
              </Td>
              <Td align="right">
                <Input
                  type="number"
                  step="any"
                  value={component.quantity}
                  onChange={(e) =>
                    setQuantity(component.resource_code, Number(e.target.value))
                  }
                  onBlur={() => commitQuantity(component.resource_code)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                  aria-label={`Cantidad de ${insumo.code} por ${concept.unit}`}
                  className="w-24 px-2 py-1 text-right tabular"
                />
              </Td>
              <Td align="right" className="tabular text-muted">
                {insumo.is_labor_percentage
                  ? `${(insumo.unit_cost * 100).toFixed(1)}% MO`
                  : money2(insumo.unit_cost)}
              </Td>
              <Td align="right" className="tabular px-5">
                {amount == null ? "—" : money2(amount)}
              </Td>
            </tr>
          );
        })}
      {open && (
        <tr className="border-b border-border bg-surface-2/20">
          <Td className="px-5">
            <div className="pl-6">
              <InsumoSearch
                insumos={insumos}
                exclude={enMatriz}
                placeholder="+ recurso (teclea para buscar)…"
                onPick={addComponent}
              />
            </div>
          </Td>
          <Td align="right" colSpan={2}>
            <label className="flex items-center justify-end gap-2 text-xs text-muted">
              Rendimiento
              <Input
                type="number"
                step="any"
                value={rate}
                onChange={(e) => setRate(e.target.value)}
                onBlur={commitRate}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                }}
                aria-label={`Rendimiento de ${concept.code}`}
                className="w-24 px-2 py-1 text-right tabular"
              />
              {concept.unit}/día
            </label>
          </Td>
          <Td align="right" className="px-5">
            <span className="text-xs text-muted">CD </span>
            <span className="tabular text-sm font-semibold">{money2(preview)}</span>
          </Td>
        </tr>
      )}
    </>
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
      title={
        reference
          ? "Precio de referencia: sustitúyelo por tu cotización"
          : undefined
      }
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
  /** Per reference row: "insumo:CODE" or "concept:CODE" — one verb, explicit scope. */
  const [adopting, setAdopting] = useState<Record<number, string>>({});
  const [ownFile, setOwnFile] = useState<File | null>(null);
  const [ownName, setOwnName] = useState("");
  const [ownVigencia, setOwnVigencia] = useState("");
  const [ownBusy, setOwnBusy] = useState(false);

  const [sourcesError, setSourcesError] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [searchAttempt, setSearchAttempt] = useState(0);

  const loadSources = useCallback(() => {
    listReferenceSources()
      .then((list) => {
        setSources(list);
        setSourcesError(false);
      })
      .catch(() => {
        setSources([]);
        setSourcesError(true);
      });
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  useEffect(() => {
    if (query.trim().length < 2) {
      const handle = window.setTimeout(() => {
        setRows(null);
        setSearching(false);
        setSearchError(false);
      }, 0);
      return () => window.clearTimeout(handle);
    }
    let active = true;
    const handle = window.setTimeout(() => {
      setSearching(true);
      setSearchError(false);
      searchReference(query.trim(), sourceKey || undefined)
        .then((found) => {
          if (!active) return;
          setRows(found);
        })
        .catch(() => {
          if (!active) return;
          setRows([]);
          setSearchError(true);
        })
        .finally(() => active && setSearching(false));
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, [query, sourceKey, searchAttempt]);

  async function runImport(source: ReferenceSource) {
    setImporting(source.key);
    try {
      const result = await importReferenceSource(source.key, getBrowserActor());
      onNotice(
        `${source.name}: ${result.rows.toLocaleString("es-MX")} renglones importados`,
      );
      loadSources();
    } catch (e) {
      onError(apiMessage(e, `No se pudo importar ${source.name}.`));
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
      onNotice(
        `${result.name}: ${result.rows.toLocaleString("es-MX")} conceptos importados como catálogo propio`,
      );
      setOwnFile(null);
      setOwnName("");
      loadSources();
    } catch (e) {
      onError(apiMessage(e, "No se pudo importar el catálogo."));
    } finally {
      setOwnBusy(false);
    }
  }

  async function applyReference(row: ReferenceRow) {
    const target = adopting[row.ref_id] ?? "";
    const [scope, code] = target.split(":");
    if (!code) return;
    try {
      if (scope === "concept") {
        await adoptConceptReference(code, row.ref_id, getBrowserActor());
        onNotice(
          `${code} se costea a ${money2(row.price)} por ${row.unit} (${row.source_name}, ${row.clave}); su matriz queda en pausa`,
        );
      } else {
        await adoptReference(code, row.ref_id, getBrowserActor());
        onNotice(
          `${code} ahora vale ${money2(row.price)} (${row.source_name}, ${row.clave})`,
        );
      }
      setAdopting((a) => ({ ...a, [row.ref_id]: "" }));
      onChanged();
    } catch (e) {
      const mismatch = unitMismatch(e);
      onError(
        mismatch
          ? `${mismatch.message} (elige un insumo o concepto en ${mismatch.reference_unit}, o adopta desde el presupuesto con una nota).`
          : apiMessage(e, `No se pudo usar la referencia en ${code}.`),
      );
    }
  }

  const imported = (sources ?? []).filter((s) => s.imported);

  return (
    <>
    <Importaciones onError={onError} onNotice={onNotice} onChanged={onChanged} />
    <Card className="mb-8 overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <SectionTitle sub="Publicaciones oficiales con fecha y región. Un precio adoptado de aquí queda marcado como publicación, con clave y vigencia.">
          Fuentes de referencia
        </SectionTitle>
      </div>
      <ul className="divide-y divide-border">
        {sources === null ? (
          <li className="space-y-3 px-5 py-3" aria-busy="true">
            <Skeleton className="h-9" />
            <Skeleton className="h-9" />
            <Skeleton className="h-9 w-4/5" />
          </li>
        ) : sourcesError ? (
          <li className="px-5 py-3">
            <Callout
              tone="danger"
              action={
                <Button size="sm" onClick={loadSources}>
                  Reintentar
                </Button>
              }
            >
              No se pudieron cargar las fuentes de referencia.
            </Callout>
          </li>
        ) : (
          sources.map((source) => (
            <li
              key={source.key}
              className="flex flex-wrap items-center gap-3 px-5 py-3"
            >
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
                <div className="truncate text-sm font-medium">
                  {source.name}
                </div>
                <div className="truncate text-xs text-muted">
                  {source.publisher} · {source.region} · vigencia{" "}
                  {source.vigencia}
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
                  title="El archivo no está en el servidor; pide a tu administrador que descargue la publicación"
                >
                  No descargada
                </a>
              )}
              {source.custom ? (
                <span className="text-xs text-muted">
                  Vuelve a subir el archivo para actualizarlo
                </span>
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
          Tu libro de precios en XLSX o CSV (clave, descripción, unidad, precio
          unitario). Entra a la biblioteca marcado como catálogo propio, nunca
          como publicación.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="file"
            accept=".xlsx,.xlsm,.csv"
            className="text-xs text-muted file:mr-2 file:rounded-md file:border file:border-border file:bg-surface-2 file:px-2 file:py-1 file:text-xs file:text-foreground"
            onChange={(e) => {
              const f = e.target.files?.[0] ?? null;
              setOwnFile(f);
              if (f && !ownName)
                setOwnName(f.name.replace(/\.(xlsx|xlsm|csv)$/i, ""));
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
          <Button
            size="sm"
            variant="secondary"
            disabled={!ownFile || ownBusy}
            onClick={importOwn}
          >
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
            <Select
              value={sourceKey}
              onChange={(e) => setSourceKey(e.target.value)}
            >
              <option value="">Todas las fuentes</option>
              {imported.map((s) => (
                <option key={s.key} value={s.key}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          {searching && rows === null && (
            <div className="mt-3 space-y-2" aria-busy="true">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
              <Skeleton className="h-10 w-3/4" />
            </div>
          )}
          {rows && (
            <div
              className={`mt-3 overflow-x-auto ${searching ? "opacity-60" : ""}`}
              aria-busy={searching}
            >
              {searchError ? (
                <Callout
                  tone="danger"
                  action={
                    <Button
                      size="sm"
                      onClick={() => setSearchAttempt((n) => n + 1)}
                    >
                      Reintentar
                    </Button>
                  }
                >
                  La búsqueda falló; el servidor no respondió.
                </Callout>
              ) : rows.length === 0 ? (
                <p className="py-3 text-sm text-muted">
                  Nada en {sourceKey ? "esa fuente" : "las fuentes importadas"}{" "}
                  para «{query.trim()}».
                  {imported.length === 0 && " Importa primero una publicación."}
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="py-1.5 pr-3 font-medium">Clave</th>
                      <th className="py-1.5 pr-3 font-medium">Concepto</th>
                      <th className="py-1.5 pr-3 font-medium">Unidad</th>
                      <th className="py-1.5 pr-3 text-right font-medium">
                        Precio
                      </th>
                      <th className="py-1.5 font-medium">
                        Usar este precio como…
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.ref_id}
                        className="border-t border-border align-top"
                      >
                        <td className="py-2 pr-3 font-mono text-xs">
                          {row.clave}
                        </td>
                        <td className="py-2 pr-3">
                          <div>{row.description}</div>
                          {row.group_description && (
                            <div className="text-xs text-faint">
                              {row.group_description}
                            </div>
                          )}
                          <div className="text-xs text-faint">
                            {row.source_name} · {row.source_vigencia}
                          </div>
                        </td>
                        <td className="py-2 pr-3 text-muted">{row.unit}</td>
                        <td className="py-2 pr-3 text-right tabular">
                          {money2(row.price)}
                        </td>
                        <td className="py-2">
                          <div className="flex items-center gap-1.5">
                            <Select
                              value={adopting[row.ref_id] ?? ""}
                              onChange={(e) =>
                                setAdopting((a) => ({
                                  ...a,
                                  [row.ref_id]: e.target.value,
                                }))
                              }
                              className="max-w-64"
                              aria-label="Dónde usar este precio"
                              size="sm"
                            >
                              <option value="">elige insumo o concepto…</option>
                              <optgroup label="Costo de un insumo (material, mano de obra, equipo)">
                                {catalog.insumos
                                  .filter((i) => !i.is_labor_percentage)
                                  .map((i) => (
                                    <option
                                      key={i.code}
                                      value={`insumo:${i.code}`}
                                    >
                                      {i.code} · {i.unit} ·{" "}
                                      {i.description.slice(0, 40)}
                                    </option>
                                  ))}
                              </optgroup>
                              <optgroup
                                label={`P.U. de un concepto en ${row.unit} (pausa su matriz)`}
                              >
                                {catalog.concepts
                                  .filter(
                                    (c) =>
                                      c.unit.toUpperCase() ===
                                      row.unit.toUpperCase(),
                                  )
                                  .map((c) => (
                                    <option
                                      key={c.code}
                                      value={`concept:${c.code}`}
                                    >
                                      {c.code} · {c.description.slice(0, 40)}
                                    </option>
                                  ))}
                              </optgroup>
                            </Select>
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={!adopting[row.ref_id]}
                              onClick={() => applyReference(row)}
                            >
                              Usar este precio
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
    </>
  );
}

/**
 * Las importaciones de matrices que se pueden deshacer.
 *
 * La primera importación de un taller casi nunca es la buena —una zona que no
 * era, un archivo cuyas claves no son conceptos presupuestables— y sin esta
 * lista habría que recordar cómo se llamaba el archivo, que es justo lo que
 * no se recuerda.
 */
function Importaciones({
  onError,
  onNotice,
  onChanged,
}: {
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onChanged: () => void;
}) {
  const [lista, setLista] = useState<CatalogImport[] | null>(null);
  const [quitando, setQuitando] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState<string | null>(null);

  const leer = useCallback(() => {
    listImports()
      .then((r) => setLista(r.imports))
      .catch(() => setLista([]));
  }, []);

  useEffect(() => {
    let vivo = true;
    listImports()
      .then((r) => vivo && setLista(r.imports))
      .catch(() => vivo && setLista([]));
    return () => {
      vivo = false;
    };
  }, []);

  async function deshacer(source: string) {
    setQuitando(source);
    try {
      const r = await undoImport(source, getBrowserActor());
      const conservados = r.kept_with_price.length
        ? ` · ${r.kept_with_price.length} se conservaron porque tienen precio adoptado`
        : "";
      onNotice(`«${source}» deshecha: ${r.removed} conceptos quitados${conservados}`);
      leer();
      onChanged();
    } catch (e) {
      onError(apiMessage(e, "No se pudo deshacer esa importación."));
    } finally {
      setQuitando(null);
      setConfirmar(null);
    }
  }

  if (!lista || lista.length === 0) return null;

  return (
    <Card className="mb-8 overflow-hidden">
      <div className="border-b border-border px-5 py-4">
        <SectionTitle sub="Deshacer quita sólo los conceptos que nacieron de esa importación: los del motor, los escritos a mano y los que ya tengan precio adoptado se quedan.">
          Importaciones de matrices
        </SectionTitle>
      </div>
      <ul className="divide-y divide-border">
        {lista.map((imp) => (
          <li key={imp.source} className="flex flex-wrap items-center gap-3 px-5 py-3">
            <span className="min-w-0 flex-1">
              <span className="font-medium">{imp.source}</span>
              <span className="mt-0.5 block text-xs text-muted">
                {imp.concepts.toLocaleString("es-MX")} conceptos
                {imp.with_price > 0 && ` · ${imp.with_price} con precio adoptado`}
              </span>
            </span>
            {confirmar === imp.source ? (
              <span className="flex items-center gap-2">
                <span className="text-xs text-danger">
                  ¿Quitar {imp.concepts - imp.with_price} conceptos?
                </span>
                <Button variant="ghost" onClick={() => setConfirmar(null)}>
                  No
                </Button>
                <Button
                  onClick={() => void deshacer(imp.source)}
                  disabled={quitando !== null}
                >
                  {quitando === imp.source ? "Quitando…" : "Sí, deshacer"}
                </Button>
              </span>
            ) : (
              <Button variant="ghost" onClick={() => setConfirmar(imp.source)}>
                Deshacer
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/* -------------------------------------------------------- salario real --- */

const FSR_FIELDS: { key: keyof FsrParameters; label: string; step?: string }[] =
  [
    { key: "uma", label: "UMA diaria ($)" },
    {
      key: "riesgo_trabajo_pct",
      label: "Riesgo de trabajo (%)",
      step: "0.001",
    },
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
  const [presets, setPresets] = useState<RegionPreset[]>([]);
  const [presetKey, setPresetKey] = useState("");
  const [preview, setPreview] = useState<LaborPreviewRow[] | null>(null);

  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    getLabor()
      .then((s) => {
        setState(s);
        setParams(s.params);
        setCategories(
          s.categories.map(({ code, description, salario_nominal }) => ({
            code,
            description,
            salario_nominal,
          })),
        );
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
    getLaborPresets()
      .then((r) => setPresets(r.presets))
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** A region fills the form (its ISN, no category below its minimum);
   *  nothing is written until "Aplicar" after the preview. */
  function fillPreset(key: string) {
    const preset = presets.find((p) => p.key === key);
    if (!preset || !params) return;
    setPresetKey(key);
    setParams({ ...params, isn_pct: preset.isn_pct });
    setCategories((list) =>
      list.map((c) => ({
        ...c,
        salario_nominal: Math.max(c.salario_nominal, preset.salario_minimo),
      })),
    );
    setDirty(true);
  }

  async function openPreview() {
    if (!params) return;
    setBusy(true);
    try {
      setPreview((await previewLabor(params, categories)).rows);
    } catch {
      onError("No se pudo calcular el salario real.");
    } finally {
      setBusy(false);
    }
  }

  async function apply() {
    if (!params) return;
    setBusy(true);
    try {
      const result = await putLabor(params, categories, getBrowserActor());
      setState(result);
      setDirty(false);
      setPreview(null);
      const preset = presets.find((p) => p.key === presetKey);
      onNotice(
        `Salario real aplicado a ${result.categories.length} categorías de mano de obra${
          preset
            ? ` con ISN y salario mínimo de ${preset.label} (${preset.source})`
            : ""
        }`,
      );
      setPresetKey("");
      onChanged();
    } catch (e) {
      onError(apiMessage(e, "No se pudo aplicar el salario real."));
    } finally {
      setBusy(false);
    }
  }

  const first = state?.categories[0]?.breakdown;

  return (
    <>
      <Disclosure
        className="mb-8"
        open={open}
        onToggle={() => setOpen((v) => !v)}
        icon={<HardHat size={16} weight="duotone" />}
        title="Salario real (Fsr) — RLOPSRM art. 190–191"
        summary={
          (first
            ? `Factor ${first.fsr.toFixed(4)} para el peón · ${first.tp} días pagados / ${first.tl} laborados · CONASAMI, UMA e IMSS ${params?.year ?? ""}`
            : "Salario nominal × factor de salario real con CONASAMI, UMA, IMSS e INFONAVIT vigentes, desglosado por ramo.") +
          (state?.applied_at
            ? ` · aplicado ${state.applied_at}`
            : " · sin aplicar")
        }
      >
        {loadError && (
          <Callout
            tone="danger"
            action={
              <Button size="sm" onClick={load}>
                Reintentar
              </Button>
            }
          >
            No se pudo cargar el salario real.
          </Callout>
        )}
        {!params && !loadError && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        )}
        {params && (
          <div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th className="py-1.5 pr-3 font-medium">Categoría</th>
                  <th className="py-1.5 pr-3 text-right font-medium">
                    Sn (día)
                  </th>
                  <th
                    className="py-1.5 pr-3 text-right font-medium"
                    title="Salario base de cotización (IMSS)"
                  >
                    SBC
                  </th>
                  <th
                    className="py-1.5 pr-3 text-right font-medium"
                    title="Prestaciones: cuotas patronales IMSS, INFONAVIT e ISN por día"
                  >
                    Ps
                  </th>
                  <th
                    className="py-1.5 pr-3 text-right font-medium"
                    title="Factor de salario real = Ps · (Tp / Tl) — días pagados entre días laborados"
                  >
                    Fsr
                  </th>
                  <th className="py-1.5 text-right font-medium">
                    Salario real
                  </th>
                </tr>
              </thead>
              <tbody>
                {categories.map((category, index) => {
                  const breakdown = state?.categories.find(
                    (c) => c.code === category.code,
                  )?.breakdown;
                  return (
                    <tr key={category.code} className="border-t border-border">
                      <td className="py-1.5 pr-3">
                        <div>{category.description}</div>
                        <div className="font-mono text-xs text-muted">
                          {category.code}
                        </div>
                      </td>
                      <td className="py-1.5 pr-3 text-right">
                        <Input
                          type="number"
                          step="0.01"
                          value={category.salario_nominal}
                          onChange={(e) => {
                            const value = Number(e.target.value);
                            setCategories((list) =>
                              list.map((c, i) =>
                                i === index
                                  ? { ...c, salario_nominal: value }
                                  : c,
                              ),
                            );
                            setDirty(true);
                          }}
                          className="w-28 px-2 py-1 text-right tabular"
                        />
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular text-muted">
                        {breakdown
                          ? money2(breakdown.salario_base_cotizacion)
                          : "—"}
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
                El salario base de cotización, las prestaciones y el factor de salario real se recalculan al aplicar.
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-2 text-xs text-muted">
                Región / estado
                <Select
                  value={presetKey}
                  onChange={(e) => fillPreset(e.target.value)}
                  aria-label="Región para ISN y salario mínimo"
                  disabled={busy || presets.length === 0}
                  size="sm"
                >
                  <option value="">Tomar ISN y salario mínimo de…</option>
                  {presets.map((preset) => (
                    <option key={preset.key} value={preset.key}>
                      {preset.label} · ISN {preset.isn_pct}% · SM $
                      {preset.salario_minimo}
                    </option>
                  ))}
                </Select>
              </label>
              {presetKey && (
                <span className="text-xs text-muted">
                  Se aplica al confirmar ·{" "}
                  {presets.find((p) => p.key === presetKey)?.source}
                </span>
              )}
              <button
                type="button"
                onClick={() => setShowParams((v) => !v)}
                className="text-xs font-medium text-muted hover:text-foreground"
              >
                {showParams
                  ? "Ocultar parámetros"
                  : "Parámetros (UMA, IMSS, LFT, ISN)"}
              </button>
            </div>
            {showParams && (
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                {FSR_FIELDS.map((field) => (
                  <label
                    key={field.key}
                    className="flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="text-muted">{field.label}</span>
                    <Input
                      type="number"
                      step={field.step ?? "any"}
                      value={Number(params[field.key])}
                      onChange={(e) => {
                        setParams({
                          ...params,
                          [field.key]: Number(e.target.value),
                        });
                        setDirty(true);
                      }}
                      className="w-24 px-2 py-1 text-right tabular"
                    />
                  </label>
                ))}
                <label className="flex items-center gap-2 text-xs text-muted">
                  <Checkbox
                    checked={params.isn_in_fsr}
                    onChange={(e) => {
                      setParams({ ...params, isn_in_fsr: e.target.checked });
                      setDirty(true);
                    }}
                  />
                  Incluir el impuesto sobre nómina en el factor de salario real (por defecto va en indirectos)
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
              <Button variant="primary" onClick={openPreview} disabled={busy}>
                {busy && !preview
                  ? "Calculando…"
                  : "Aplicar salario real al catálogo…"}
              </Button>
            </div>
          </div>
        )}
      </Disclosure>
      <Modal
        open={preview !== null}
        title="Aplicar salario real al catálogo"
        sub="Cada categoría de mano de obra queda con este precio (Sn × Fsr), marcado como calculado con su vigencia de este mes. Las matrices que la usan cambian al recalcular."
        onClose={() => setPreview(null)}
        busy={busy}
        size="lg"
        footer={
          <>
            <Button onClick={() => setPreview(null)} disabled={busy}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={apply} disabled={busy}>
              {busy
                ? "Aplicando…"
                : `Aplicar a ${preview?.length ?? 0} categorías`}
            </Button>
          </>
        }
      >
        {preview && (
          <p className="mb-3 text-xs text-muted">
            {(() => {
              const changed = preview.filter(
                (r) => r.from == null || Math.abs(r.to - r.from) >= 0.005,
              ).length;
              return changed === 0
                ? "Ningún precio cambia: las categorías ya están en este salario real (el ISN solo entra al Fsr si lo marcas en parámetros)."
                : `${changed} de ${preview.length} categorías cambian de precio.`;
            })()}
          </p>
        )}
        {preview && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2">
                  <Th>Categoría</Th>
                  <Th align="right">Sn (día)</Th>
                  <Th align="right">Fsr</Th>
                  <Th align="right">En el catálogo</Th>
                  <Th align="right">Nuevo</Th>
                </tr>
              </thead>
              <tbody>
                {preview.map((row) => {
                  const delta = row.from == null ? null : row.to - row.from;
                  return (
                    <tr key={row.code} className="border-t border-border">
                      <Td>
                        <div>{row.description}</div>
                        <div className="font-mono text-xs text-muted">
                          {row.code}
                        </div>
                      </Td>
                      <Td align="right" className="tabular">
                        {money2(row.salario_nominal)}
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {row.fsr.toFixed(4)}
                      </Td>
                      <Td align="right" className="tabular text-muted">
                        {row.from == null ? "sin precio" : money2(row.from)}
                      </Td>
                      <Td align="right" className="tabular font-medium">
                        {money2(row.to)}
                        {delta != null && Math.abs(delta) >= 0.005 && (
                          <span
                            className={`ml-1.5 text-xs ${delta > 0 ? "text-warning" : "text-success"}`}
                          >
                            {delta > 0 ? "+" : "−"}
                            {money2(Math.abs(delta))}
                          </span>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Modal>
    </>
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
  vm: 1000000,
  vr: 100000,
  ve: 10000,
  hea: 2000,
  i: 0.12,
  s: 0.03,
  ko: 0.8,
  gh: 0,
  pc: 25,
  ah: 0,
  ga: 0,
  pa: 90,
  pn: 0,
  vn: 0,
  pa_e: 0,
  va: 0,
  sr: 0,
  ht: 8,
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
  }, [insumo.code]);

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
      const row = await putEquipment(
        insumo.code,
        params,
        undefined,
        getBrowserActor(),
      );
      setBreakdown(row.breakdown);
      onSaved();
    } catch {
      onError(`No se pudo guardar el costo horario de ${insumo.code}.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open
      size="lg"
      busy={busy}
      onClose={onClose}
      title={`Costo horario · ${insumo.description}`}
      sub="RLOPSRM art. 194–206: cargos fijos + consumos + operación por hora efectiva. El resultado sustituye el costo unitario del insumo y queda marcado como calculado."
      footer={
        params !== null && (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={save} disabled={busy}>
              {busy ? "Guardando…" : "Guardar y aplicar"}
            </Button>
          </>
        )
      }
    >
      {params === null ? (
        <div className="grid gap-2 sm:grid-cols-2" aria-busy="true">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-7" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-2 sm:grid-cols-2">
            {EQ_FIELDS.map((field) => (
              <label
                key={field.key}
                className="flex items-center justify-between gap-2 text-xs"
              >
                <span className="text-muted">{field.label}</span>
                <Input
                  type="number"
                  step="any"
                  value={params[field.key]}
                  onChange={(e) =>
                    setParams({
                      ...params,
                      [field.key]: Number(e.target.value),
                    })
                  }
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
                  Guardado: fijos {money2(breakdown.cargos_fijos)} · consumos{" "}
                  {money2(breakdown.consumos)} · operación{" "}
                  {money2(breakdown.operacion)}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </Modal>
  );
}
