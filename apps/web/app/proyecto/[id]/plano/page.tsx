"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import {
  Check,
  Cursor,
  Hash,
  PencilSimpleLine,
  Polygon,
  Prohibit,
  Ruler,
  SlidersHorizontal,
  X,
} from "@phosphor-icons/react";
import {
  addAdjustment,
  getCatalog,
  frameRenderUrl,
  getCosts,
  getGeometry,
  setDetectionReview,
  type CatalogConcept,
  type DetectionOverlay,
  type Geometry,
  type ReviewStatus,
} from "@/lib/api";
import { FAMILY_COLORS, FAMILY_LABELS, HIDDEN_BY_DEFAULT, PlanoCanvas, detectionTitle, familyOf, type MeasureMode } from "@/components/PlanoCanvas";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  IconButton,
  Input,
  PageHeader,
  Skeleton,
} from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function PlanoPage() {
  const { id } = useParams<{ id: string }>();
  const [geom, setGeom] = useState<Geometry | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [focus, setFocus] = useState<{
    bbox: [number, number, number, number];
    nonce: number;
  } | null>(null);
  // Open on the first planta when the drawing is a set of tiled sheets
  // (render-time adjust: no effect, no extra frame).
  const [focusedGeom, setFocusedGeom] = useState<Geometry | null>(null);
  if (geom && geom !== focusedGeom) {
    setFocusedGeom(geom);
    const first = geom.frames?.find((f) => f.kind === "plan") ?? geom.frames?.[0];
    if (first) setFocus((f) => ({ bbox: first.bbox, nonce: (f?.nonce ?? 0) + 1 }));
  }
  const [visibleFamilies, setVisibleFamilies] = useState<Set<string>>(new Set());
  const [minConfidence, setMinConfidence] = useState(0);
  const [selected, setSelected] = useState<DetectionOverlay | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showExcluded, setShowExcluded] = useState(true);
  const [hiddenSheets, setHiddenSheets] = useState<Set<number>>(new Set());
  const [measureMode, setMeasureMode] = useState<MeasureMode | null>(null);
  const [measurePoints, setMeasurePoints] = useState<[number, number][]>([]);
  const { latestEvent, connectionEpoch, actorName, clientId } = useProjectLive();

  const searchParams = useSearchParams();
  const conceptParam = searchParams.get("concept") ?? "";
  const bboxParam = searchParams.get("bbox") ?? "";
  // ?bbox=x0,y0,x1,y1 — a risk finding or a colleague's pointer: fit there.
  const bboxFit = useMemo(() => {
    const parts = bboxParam.split(",").map(Number);
    if (parts.length !== 4 || parts.some((v) => !Number.isFinite(v))) return null;
    const [x0, y0, x1, y1] = parts;
    const pad = Math.max(x1 - x0, y1 - y0, 1) * 2;
    return { bbox: [x0 - pad, y0 - pad, x1 + pad, y1 + pad] as [number, number, number, number], nonce: -2 };
  }, [bboxParam]);
  const [fetchedFocus, setConceptFocus] = useState<{ concept: string; ids: Set<string> } | null>(
    null,
  );
  // The focus is only what the URL asks for: clearing ?concept= clears it
  // without a state write.
  const conceptFocus =
    conceptParam && fetchedFocus?.concept === conceptParam ? fetchedFocus : null;
  const [geomError, setGeomError] = useState<string | null>(null);
  const router = useRouter();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    let active = true;
    getGeometry(id)
      .then((g) => {
        if (!active) return;
        setGeomError(null);
        setGeom(g);
        setVisibleLayers(new Set(g.layers.slice(0, 14).map((l) => l.name)));
        setVisibleFamilies(
          new Set(g.detections.map(familyOf).filter((f) => !HIDDEN_BY_DEFAULT.has(f))),
        );
        setSelected(null);
      })
      .catch(() => {
        if (active) setGeomError("No se pudo cargar la geometría del plano.");
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getGeometry(id)
      .then((g) => {
        setGeom(g);
        setVisibleLayers(new Set(g.layers.slice(0, 14).map((l) => l.name)));
        setVisibleFamilies(
          new Set(g.detections.map(familyOf).filter((f) => !HIDDEN_BY_DEFAULT.has(f))),
        );
        setSelected(null);
      })
      .catch(() => {});
  }, [id, latestEvent]);

  // ?concept=EST-004 — arriving from a presupuesto line: show only the
  // elements that produce that quantity, every family they belong to visible.
  useEffect(() => {
    if (!conceptParam) return;
    let active = true;
    getCosts(id)
      .then((costs) => {
        if (!active) return;
        const line = costs.boq.lines.find((l) => l.concept_code === conceptParam);
        const ids = new Set<string>(line?.source_detections ?? []);
        setConceptFocus({ concept: conceptParam, ids });
      })
      .catch(() => {
        if (active) setConceptFocus({ concept: conceptParam, ids: new Set() });
      });
    return () => {
      active = false;
    };
  }, [id, conceptParam]);

  // While a concept is focused, its elements' families are the visible ones
  // (derived at render time, so the user's own family toggles come back
  // untouched when the focus is cleared).
  const focusFamilies = useMemo(() => {
    if (!conceptFocus || !geom || conceptFocus.ids.size === 0) return null;
    const families = new Set(
      geom.detections.filter((d) => conceptFocus.ids.has(d.id)).map(familyOf),
    );
    return families.size > 0 ? families : null;
  }, [conceptFocus, geom]);
  const effectiveFamilies = focusFamilies ?? visibleFamilies;
  // Arriving with ?concept=, the first fit is the elements' extent, not the
  // whole tiling; a frame click afterwards takes over through `focus`.
  const conceptFit = useMemo(() => {
    if (!conceptFocus || !geom || conceptFocus.ids.size === 0) return null;
    const boxes = geom.detections.filter((d) => conceptFocus.ids.has(d.id)).map((d) => d.bbox);
    if (boxes.length === 0) return null;
    const bbox: [number, number, number, number] = [
      Math.min(...boxes.map((b) => b[0])),
      Math.min(...boxes.map((b) => b[1])),
      Math.max(...boxes.map((b) => b[2])),
      Math.max(...boxes.map((b) => b[3])),
    ];
    return { bbox, nonce: -1 };
  }, [conceptFocus, geom]);

  // A collaborator reviewed something: refresh verdicts, keep the selection.
  useEffect(() => {
    if (latestEvent?.type !== "review_updated") return;
    getGeometry(id).then((g) => {
      setGeom(g);
      setSelected((current) =>
        current ? (g.detections.find((d) => d.id === current.id) ?? null) : null,
      );
    });
  }, [id, latestEvent]);

  const review = useCallback(
    async (detection: DetectionOverlay, status: ReviewStatus | "none", note = "") => {
      try {
        await setDetectionReview(id, detection.review_key, status, note, actorName, clientId);
      } catch {
        return;
      }
      setGeom((current) => {
        if (!current) return current;
        const detections = current.detections.map((d) =>
          d.review_key === detection.review_key
            ? { ...d, review: status === "none" ? ("" as const) : status, review_note: note }
            : d,
        );
        return { ...current, detections };
      });
      setSelected((current) =>
        current && current.review_key === detection.review_key
          ? { ...current, review: status === "none" ? "" : status, review_note: note }
          : current,
      );
    },
    [actorName, clientId, id],
  );

  const families = useMemo(() => {
    if (!geom) return [] as { family: string; count: number }[];
    const counts: Record<string, number> = {};
    for (const d of geom.detections) counts[familyOf(d)] = (counts[familyOf(d)] ?? 0) + 1;
    return Object.entries(counts)
      .map(([family, count]) => ({ family, count }))
      .sort((a, b) => b.count - a.count);
  }, [geom]);

  const canvasGeom = useMemo(() => {
    if (!geom) return geom;
    let detections = geom.detections;
    let shapes = geom.shapes;
    if (conceptFocus && conceptFocus.ids.size > 0) {
      detections = detections.filter((d) => conceptFocus.ids.has(d.id));
    }
    if (!showExcluded) {
      detections = detections.filter((d) => d.review !== "excluded");
    }
    if (hiddenSheets.size > 0) {
      shapes = shapes.filter((s) => s.sheet == null || !hiddenSheets.has(s.sheet));
      detections = detections.filter(
        (d) => d.sheet == null || !hiddenSheets.has(d.sheet),
      );
    }
    if (detections === geom.detections && shapes === geom.shapes) return geom;
    return { ...geom, detections, shapes };
  }, [geom, showExcluded, hiddenSheets, conceptFocus]);

  const visibleCount = useMemo(() => {
    if (!canvasGeom) return 0;
    return canvasGeom.detections.filter(
      (d) => effectiveFamilies.has(familyOf(d)) && d.confidence >= minConfidence,
    ).length;
  }, [canvasGeom, effectiveFamilies, minConfidence]);

  // The review loop lives on the keyboard: arrows cycle visible detections,
  // C confirms, X excludes, Q clears, Escape deselects. Repetition should be
  // muscle memory, not clicking.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ("value" in target || target.isContentEditable)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape") {
        if (measureMode) {
          setMeasurePoints([]);
          setMeasureMode(null);
        } else {
          setSelected(null);
        }
        return;
      }
      if (measureMode) {
        if (event.key === "Backspace") {
          event.preventDefault();
          setMeasurePoints((current) => current.slice(0, -1));
        }
        return;
      }
      if (!canvasGeom) return;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        const visible = canvasGeom.detections.filter(
          (d) => effectiveFamilies.has(familyOf(d)) && d.confidence >= minConfidence,
        );
        if (visible.length === 0) return;
        event.preventDefault();
        setSelected((current) => {
          const index = current
            ? visible.findIndex((d) => d.id === current.id)
            : -1;
          const step = event.key === "ArrowRight" ? 1 : -1;
          return visible[(index + step + visible.length) % visible.length];
        });
        return;
      }
      if (!selected) return;
      const key = event.key.toLowerCase();
      if (key === "c") void review(selected, "confirmed");
      else if (key === "x") void review(selected, "excluded");
      else if (key === "q") void review(selected, "none");
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [canvasGeom, measureMode, minConfidence, review, selected, effectiveFamilies]);

  const reviewCounts = useMemo(() => {
    const counts = { confirmed: 0, excluded: 0 };
    for (const d of geom?.detections ?? []) {
      if (d.review === "confirmed") counts.confirmed += 1;
      if (d.review === "excluded") counts.excluded += 1;
    }
    return counts;
  }, [geom]);

  function toggle(set: Set<string>, key: string, setter: (s: Set<string>) => void) {
    const next = new Set(set);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    setter(next);
  }

  if (geomError) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Visor del plano" />
        <Callout
          tone="danger"
          action={
            <Button size="sm" onClick={() => window.location.reload()}>
              Reintentar
            </Button>
          }
        >
          {geomError} Si el proyecto acaba de procesarse, espera unos segundos y reintenta.
        </Callout>
      </div>
    );
  }

  if (!geom) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] lg:h-screen">
        <div className="hidden w-72 shrink-0 space-y-3 border-r border-border bg-surface px-4 py-4 md:block">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-40" />
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-64" />
        </div>
        <div className="flex-1 bg-surface-2" />
      </div>
    );
  }

  const filterPanel = (
    <FilterPanel
      projectId={id}
      geom={geom}
      families={families}
      visibleFamilies={effectiveFamilies}
      visibleLayers={visibleLayers}
      minConfidence={minConfidence}
      showExcluded={showExcluded}
      hiddenSheets={hiddenSheets}
      onToggleFamily={(f) => toggle(visibleFamilies, f, setVisibleFamilies)}
      onToggleLayer={(l) => toggle(visibleLayers, l, setVisibleLayers)}
      onFocusFrame={(bbox) => setFocus((f) => ({ bbox, nonce: (f?.nonce ?? 0) + 1 }))}
      onMinConfidence={setMinConfidence}
      onToggleExcluded={() => setShowExcluded((current) => !current)}
      onToggleSheet={(index) =>
        setHiddenSheets((current) => {
          const next = new Set(current);
          if (next.has(index)) next.delete(index);
          else next.add(index);
          return next;
        })
      }
    />
  );

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col lg:h-screen">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-surface px-4 py-4 lg:px-8">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">Visor del plano</h1>
          <p className="truncate text-sm text-muted">
            {conceptFocus && (
              <span className="mr-2 inline-flex items-center gap-2">
                <Badge tone="accent" dot>
                  {conceptFocus.ids.size > 0
                    ? `${conceptFocus.ids.size} elementos de ${conceptFocus.concept}`
                    : `${conceptFocus.concept}: sin elementos en esta corrida`}
                </Badge>
                <button
                  type="button"
                  className="text-xs underline"
                  onClick={() => router.replace(`/proyecto/${id}/plano`)}
                >
                  ver todo
                </button>
                ·
              </span>
            )}
            {visibleCount.toLocaleString("es-MX")} detecciones visibles
            {reviewCounts.confirmed > 0 && ` · ${reviewCounts.confirmed} confirmadas`}
            {reviewCounts.excluded > 0 && ` · ${reviewCounts.excluded} excluidas`} · clic
            para inspeccionar y revisar
          </p>
        </div>
        <button
          type="button"
          onClick={() => setFiltersOpen(true)}
          className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2 text-sm font-medium shadow-sm transition hover:bg-surface-2 md:hidden"
        >
          <SlidersHorizontal size={15} /> Filtros
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-border bg-surface px-4 py-4 md:block">
          {filterPanel}
        </aside>

        {filtersOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <button
              type="button"
              aria-label="Cerrar filtros"
              onClick={() => setFiltersOpen(false)}
              className="absolute inset-0 bg-foreground/30"
            />
            <aside className="toast-in absolute inset-y-0 left-0 w-80 overflow-y-auto border-r border-border bg-surface px-4 py-4 shadow-lg">
              <div className="mb-2 flex justify-end">
                <IconButton aria-label="Cerrar filtros" onClick={() => setFiltersOpen(false)}>
                  <X size={18} />
                </IconButton>
              </div>
              {filterPanel}
            </aside>
          </div>
        )}

        <div className="relative min-w-0 flex-1 bg-surface-2">
          <MeasureToolbar
            mode={measureMode}
            onMode={(mode) => {
              setMeasureMode(mode);
              setMeasurePoints([]);
              if (mode) setSelected(null);
            }}
          />
          <PlanoCanvas
            geometry={canvasGeom ?? geom}
            visibleLayers={visibleLayers}
            visibleFamilies={effectiveFamilies}
            minConfidence={minConfidence}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            measure={measureMode ? { mode: measureMode, points: measurePoints } : null}
            onWorldClick={(point) =>
              setMeasurePoints((current) => [...current, point])
            }
            focus={focus ?? conceptFit ?? bboxFit}
          />
          {geom.detections.length === 0 && !measureMode && (
            <div className="pointer-events-none absolute inset-x-0 top-14 z-10 flex justify-center px-4">
              <div className="pointer-events-auto max-w-md rounded-xl border border-border bg-surface/95 p-4 text-sm shadow-lg backdrop-blur">
                <div className="font-medium">El motor no detectó elementos en este plano</div>
                <p className="mt-1 text-muted">
                  Se dibuja la geometría tal cual. Suele pasar cuando las capas no siguen una
                  convención conocida o el archivo es un levantamiento; la lectura dice qué se
                  reconoció por capa.
                </p>
                <Link
                  href={`/proyecto/${id}/lectura`}
                  className={`${buttonClasses("secondary", "sm")} mt-3`}
                >
                  Ver la lectura del plano
                </Link>
              </div>
            </div>
          )}
          {measureMode && (
            <MeasureResult
              projectId={id}
              mode={measureMode}
              points={measurePoints}
              toMeters={geom.units?.to_meters ?? null}
              actorName={actorName}
              clientId={clientId}
              onUndo={() => setMeasurePoints((current) => current.slice(0, -1))}
              onClear={() => setMeasurePoints([])}
            />
          )}
          {selected && (
            <div className="rise-in absolute bottom-4 left-4 z-10 w-[380px] max-w-[calc(100%-2rem)] rounded-xl border border-border bg-surface p-4 shadow-lg">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 shrink-0 rounded-sm"
                    style={{ background: FAMILY_COLORS[familyOf(selected)] ?? "var(--chart-5)" }}
                  />
                  <div>
                    <div className="font-semibold leading-tight">
                      {detectionTitle(selected)}
                    </div>
                    {selected.display_label && (
                      <div className="font-mono text-xs text-muted">
                        {selected.display_label}
                        {selected.mark && ` · etiqueta en plano: ${selected.mark}`}
                      </div>
                    )}
                  </div>
                </div>
                <IconButton aria-label="Cerrar detalle" onClick={() => setSelected(null)}>
                  <X size={14} />
                </IconButton>
              </div>
              {selected.description && (
                <p className="mb-3 text-sm leading-relaxed text-muted">
                  {selected.description}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Badge
                  dot
                  tone={
                    selected.confidence >= 0.7
                      ? "success"
                      : selected.confidence >= 0.45
                        ? "warning"
                        : "danger"
                  }
                >
                  Confianza {(selected.confidence * 100).toFixed(0)}%
                </Badge>
                {selected.review === "confirmed" && (
                  <Badge tone="success" dot>
                    Confirmada
                  </Badge>
                )}
                {selected.review === "excluded" && (
                  <Badge tone="danger" dot>
                    Excluida del presupuesto
                  </Badge>
                )}
              </div>
              <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
                {selected.review !== "confirmed" && (
                  <Button size="sm" onClick={() => review(selected, "confirmed")}>
                    <Check size={14} weight="bold" /> Confirmar
                  </Button>
                )}
                {selected.review !== "excluded" && (
                  <Button size="sm" variant="danger" onClick={() => review(selected, "excluded")}>
                    <Prohibit size={14} weight="bold" /> Excluir
                  </Button>
                )}
                {selected.review && (
                  <Button size="sm" variant="ghost" onClick={() => review(selected, "none")}>
                    Quitar revisión
                  </Button>
                )}
              </div>
              <p className="mt-2 text-[11px] text-faint">
                Teclas: C confirmar · X excluir · Q quitar · ← → siguiente
              </p>
              {selected.review === "excluded" && (
                <ReviewNote
                  key={selected.review_key}
                  initial={selected.review_note}
                  onCommit={(note) => review(selected, "excluded", note)}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function MeasureToolbar({
  mode,
  onMode,
}: {
  mode: MeasureMode | null;
  onMode: (mode: MeasureMode | null) => void;
}) {
  const tools: { key: MeasureMode | null; label: string; icon: React.ReactNode }[] = [
    { key: null, label: "Navegar", icon: <Cursor size={15} /> },
    { key: "distancia", label: "Distancia", icon: <Ruler size={15} /> },
    { key: "area", label: "Área", icon: <Polygon size={15} /> },
    { key: "conteo", label: "Conteo", icon: <Hash size={15} /> },
  ];
  return (
    <div className="absolute left-3 top-3 z-10 flex rounded-lg border border-border bg-surface p-0.5 shadow-sm">
      {tools.map((tool) => (
        <button
          key={tool.label}
          type="button"
          title={tool.label}
          onClick={() => onMode(tool.key)}
          className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors ${
            mode === tool.key
              ? "bg-surface-3 text-foreground"
              : "text-muted hover:text-foreground"
          }`}
        >
          {tool.icon}
          <span className="hidden lg:inline">{tool.label}</span>
        </button>
      ))}
    </div>
  );
}

function measureValue(
  mode: MeasureMode,
  points: [number, number][],
  toMeters: number | null,
): { value: number; label: string } {
  if (mode === "conteo") return { value: points.length, label: "elementos" };
  const scale = toMeters ?? 1;
  const unit = toMeters != null ? "m" : "u.dib";
  if (mode === "distancia") {
    let total = 0;
    for (let i = 1; i < points.length; i++) {
      total += Math.hypot(
        points[i][0] - points[i - 1][0],
        points[i][1] - points[i - 1][1],
      );
    }
    return { value: total * scale, label: unit };
  }
  // Shoelace area of the clicked polygon.
  let doubled = 0;
  for (let i = 0; i < points.length; i++) {
    const [x1, y1] = points[i];
    const [x2, y2] = points[(i + 1) % points.length];
    doubled += x1 * y2 - x2 * y1;
  }
  return { value: (Math.abs(doubled) / 2) * scale * scale, label: `${unit}²` };
}

function MeasureResult({
  projectId,
  mode,
  points,
  toMeters,
  actorName,
  clientId,
  onUndo,
  onClear,
}: {
  projectId: string;
  mode: MeasureMode;
  points: [number, number][];
  toMeters: number | null;
  actorName: string;
  clientId: string | null;
  onUndo: () => void;
  onClear: () => void;
}) {
  const [concepts, setConcepts] = useState<CatalogConcept[] | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [conceptCode, setConceptCode] = useState("");
  const [qty, setQty] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { value, label } = measureValue(mode, points, toMeters);
  const ready =
    (mode === "distancia" && points.length >= 2) ||
    (mode === "area" && points.length >= 3) ||
    (mode === "conteo" && points.length >= 1);
  const display = mode === "conteo" ? String(value) : value.toFixed(2);

  function openForm() {
    setFormOpen(true);
    setQty(display);
    setSent(null);
    if (concepts === null) {
      getCatalog()
        .then((catalog) => setConcepts(catalog.concepts))
        .catch(() => setConcepts([]));
    }
  }

  async function submit() {
    const quantity = Number(qty);
    if (!conceptCode || !quantity) {
      setError("Elige un concepto y una cantidad.");
      return;
    }
    setError(null);
    try {
      await addAdjustment(
        projectId,
        {
          concept_code: conceptCode,
          quantity_delta: quantity,
          note: `Medido en visor: ${mode} ${display} ${label}`,
        },
        actorName,
        clientId,
      );
      setSent(`Ajuste de ${quantity} enviado a ${conceptCode}.`);
      setFormOpen(false);
      onClear();
    } catch {
      setError("No se pudo crear el ajuste.");
    }
  }

  return (
    <div className="absolute bottom-4 left-1/2 z-10 w-[440px] max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-xl border border-border bg-surface p-3 shadow-lg">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm">
          <span className="tabular text-lg font-semibold">{display}</span>{" "}
          <span className="text-muted">{label}</span>
          {toMeters == null && mode !== "conteo" && (
            <span
              className="ml-2 text-xs text-warning"
              title="Las unidades del plano no se detectaron; el valor está en unidades de dibujo."
            >
              sin unidades
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" onClick={onUndo} disabled={points.length === 0}>
            Deshacer
          </Button>
          <Button size="sm" variant="ghost" onClick={onClear} disabled={points.length === 0}>
            Limpiar
          </Button>
          <Button size="sm" onClick={openForm} disabled={!ready}>
            <PencilSimpleLine size={14} weight="bold" /> Crear ajuste
          </Button>
        </div>
      </div>
      <p className="mt-1 text-[11px] text-faint">
        Clic para agregar puntos · Backspace deshace · Esc sale
      </p>
      {sent && <p className="mt-1 text-xs text-success">{sent}</p>}
      {formOpen && (
        <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border pt-2">
          <select
            value={conceptCode}
            onChange={(e) => setConceptCode(e.target.value)}
            className="min-w-44 flex-1 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
          >
            <option value="">Concepto…</option>
            {(concepts ?? []).map((concept) => (
              <option key={concept.code} value={concept.code}>
                {concept.code} · {concept.description.slice(0, 40)}
              </option>
            ))}
          </select>
          <Input
            type="number"
            step="any"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-28 px-2 py-1.5 text-right tabular"
          />
          <Button size="sm" variant="primary" onClick={submit}>
            Agregar
          </Button>
        </div>
      )}
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}

function ReviewNote({
  initial,
  onCommit,
}: {
  initial: string;
  onCommit: (note: string) => void;
}) {
  const [note, setNote] = useState(initial);
  return (
    <Input
      value={note}
      onChange={(e) => setNote(e.target.value)}
      onBlur={() => {
        if (note.trim() !== initial) onCommit(note.trim());
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      placeholder="Motivo de la exclusión (opcional)"
      maxLength={300}
      className="mt-2 w-full px-2.5 py-1.5 text-xs"
    />
  );
}

function FilterPanel({
  projectId,
  geom,
  families,
  visibleFamilies,
  visibleLayers,
  minConfidence,
  showExcluded,
  hiddenSheets,
  onToggleFamily,
  onToggleLayer,
  onFocusFrame,
  onMinConfidence,
  onToggleExcluded,
  onToggleSheet,
}: {
  geom: Geometry;
  families: { family: string; count: number }[];
  visibleFamilies: Set<string>;
  visibleLayers: Set<string>;
  minConfidence: number;
  showExcluded: boolean;
  hiddenSheets: Set<number>;
  onToggleFamily: (family: string) => void;
  onToggleLayer: (layer: string) => void;
  onFocusFrame: (bbox: [number, number, number, number]) => void;
  projectId: string;
  onMinConfidence: (value: number) => void;
  onToggleExcluded: () => void;
  onToggleSheet: (index: number) => void;
}) {
  return (
    <>
      {(geom.sheets?.length ?? 0) > 1 && (
        <>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Hojas ({geom.sheets.length - hiddenSheets.size}/{geom.sheets.length})
          </h3>
          <div className="mb-4 space-y-1">
            {geom.sheets.map((sheet, index) => (
              <label
                key={index}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition hover:bg-surface-2"
              >
                <input
                  type="checkbox"
                  checked={!hiddenSheets.has(index)}
                  onChange={() => onToggleSheet(index)}
                  className="accent-[var(--primary)]"
                />
                <span className="flex-1 truncate" title={sheet.name}>
                  {sheet.sheet_number ?? sheet.name}
                </span>
                <span className="tabular text-xs text-muted">{sheet.count}</span>
              </label>
            ))}
          </div>
        </>
      )}

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
        Elementos detectados
      </h3>
      <div className="mb-4 space-y-1">
        {families.map(({ family, count }) => (
          <label
            key={family}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition hover:bg-surface-2"
          >
            <input
              type="checkbox"
              checked={visibleFamilies.has(family)}
              onChange={() => onToggleFamily(family)}
              className="accent-[var(--primary)]"
            />
            <span
              className="h-2.5 w-2.5 rounded-sm"
              style={{ background: FAMILY_COLORS[family] ?? "var(--chart-5)" }}
            />
            <span className="flex-1">{FAMILY_LABELS[family] ?? family}</span>
            <span className="tabular text-xs text-muted">{count}</span>
          </label>
        ))}
      </div>

      <div className="mb-4">
        <label className="mb-1.5 block text-xs font-medium text-muted">
          Confianza mínima: {(minConfidence * 100).toFixed(0)}%
        </label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={minConfidence}
          onChange={(e) => onMinConfidence(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <label className="mb-4 flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition hover:bg-surface-2">
        <input
          type="checkbox"
          checked={showExcluded}
          onChange={onToggleExcluded}
          className="accent-[var(--primary)]"
        />
        <span className="flex-1">Mostrar excluidas</span>
      </label>

      {(geom.frames ?? []).length > 0 && (
        <>
          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
            Hojas ({(geom.frames ?? []).length})
          </h3>
          <div className="space-y-0.5">
            {(geom.frames ?? []).map((f, i) => (
              <button
                key={`${f.code}-${i}`}
                type="button"
                onClick={() => onFocusFrame(f.bbox)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm transition hover:bg-surface-2"
                title={f.title || f.code}
              >
                <span className="font-mono text-xs text-muted">{f.code || "—"}</span>
                <span className="flex-1 truncate">{f.title || "(sin título)"}</span>
                {f.kind === "plan" && <Badge tone="accent">planta</Badge>}
                {f.code && (
                  <a
                    href={frameRenderUrl(projectId, f.code)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[11px] text-muted underline"
                    title="Ver la hoja como imagen"
                    onClick={(e) => e.stopPropagation()}
                  >
                    img
                  </a>
                )}
              </button>
            ))}
          </div>
        </>
      )}

      <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
        Capas ({visibleLayers.size}/{geom.layers.length})
      </h3>
      <div className="space-y-0.5">
        {geom.layers.map((l) => (
          <label
            key={l.name}
            className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm transition hover:bg-surface-2"
          >
            <input
              type="checkbox"
              checked={visibleLayers.has(l.name)}
              onChange={() => onToggleLayer(l.name)}
              className="accent-[var(--primary)]"
            />
            <span className="flex-1 truncate" title={l.name}>
              {l.name}
            </span>
            <span className="tabular text-xs text-muted">{l.count}</span>
          </label>
        ))}
      </div>
    </>
  );
}
