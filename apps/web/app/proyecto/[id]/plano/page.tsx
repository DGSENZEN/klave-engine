"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Check, Prohibit, SlidersHorizontal, X } from "@phosphor-icons/react";
import {
  getGeometry,
  setDetectionReview,
  type DetectionOverlay,
  type Geometry,
  type ReviewStatus,
} from "@/lib/api";
import {
  PlanoCanvas,
  FAMILY_COLORS,
  FAMILY_LABELS,
  familyOf,
  detectionTitle,
} from "@/components/PlanoCanvas";
import { Badge, Button, IconButton, Input, Skeleton } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function PlanoPage() {
  const { id } = useParams<{ id: string }>();
  const [geom, setGeom] = useState<Geometry | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [visibleFamilies, setVisibleFamilies] = useState<Set<string>>(new Set());
  const [minConfidence, setMinConfidence] = useState(0);
  const [selected, setSelected] = useState<DetectionOverlay | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showExcluded, setShowExcluded] = useState(true);
  const [hiddenSheets, setHiddenSheets] = useState<Set<number>>(new Set());
  const { latestEvent, connectionEpoch, actorName, clientId } = useProjectLive();

  // connectionEpoch: a reconnect may have skipped events, so reload everything.
  useEffect(() => {
    getGeometry(id).then((g) => {
      setGeom(g);
      setVisibleLayers(new Set(g.layers.slice(0, 14).map((l) => l.name)));
      setVisibleFamilies(new Set(g.detections.map(familyOf)));
      setSelected(null);
    });
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getGeometry(id).then((g) => {
      setGeom(g);
      setVisibleLayers(new Set(g.layers.slice(0, 14).map((l) => l.name)));
      setVisibleFamilies(new Set(g.detections.map(familyOf)));
      setSelected(null);
    });
  }, [id, latestEvent]);

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

  async function review(detection: DetectionOverlay, status: ReviewStatus | "none", note = "") {
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
  }

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
  }, [geom, showExcluded, hiddenSheets]);

  const visibleCount = useMemo(() => {
    if (!canvasGeom) return 0;
    return canvasGeom.detections.filter(
      (d) => visibleFamilies.has(familyOf(d)) && d.confidence >= minConfidence,
    ).length;
  }, [canvasGeom, visibleFamilies, minConfidence]);

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
      geom={geom}
      families={families}
      visibleFamilies={visibleFamilies}
      visibleLayers={visibleLayers}
      minConfidence={minConfidence}
      showExcluded={showExcluded}
      hiddenSheets={hiddenSheets}
      onToggleFamily={(f) => toggle(visibleFamilies, f, setVisibleFamilies)}
      onToggleLayer={(l) => toggle(visibleLayers, l, setVisibleLayers)}
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
          <PlanoCanvas
            geometry={canvasGeom ?? geom}
            visibleLayers={visibleLayers}
            visibleFamilies={visibleFamilies}
            minConfidence={minConfidence}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
          />
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
  geom,
  families,
  visibleFamilies,
  visibleLayers,
  minConfidence,
  showExcluded,
  hiddenSheets,
  onToggleFamily,
  onToggleLayer,
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
