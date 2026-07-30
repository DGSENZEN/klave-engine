"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { X } from "lucide-react";
import { getGeometry, type DetectionOverlay, type Geometry } from "@/lib/api";
import {
  PlanoCanvas,
  FAMILY_COLORS,
  FAMILY_LABELS,
  familyOf,
  detectionTitle,
} from "@/components/PlanoCanvas";
import { Badge, Skeleton } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

export default function PlanoPage() {
  const { id } = useParams<{ id: string }>();
  const [geom, setGeom] = useState<Geometry | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [visibleFamilies, setVisibleFamilies] = useState<Set<string>>(new Set());
  const [minConfidence, setMinConfidence] = useState(0);
  const [selected, setSelected] = useState<DetectionOverlay | null>(null);
  const { latestEvent, connectionEpoch } = useProjectLive();

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

  const families = useMemo(() => {
    if (!geom) return [] as { family: string; count: number }[];
    const counts: Record<string, number> = {};
    for (const d of geom.detections) counts[familyOf(d)] = (counts[familyOf(d)] ?? 0) + 1;
    return Object.entries(counts)
      .map(([family, count]) => ({ family, count }))
      .sort((a, b) => b.count - a.count);
  }, [geom]);

  const visibleCount = useMemo(() => {
    if (!geom) return 0;
    return geom.detections.filter(
      (d) => visibleFamilies.has(familyOf(d)) && d.confidence >= minConfidence,
    ).length;
  }, [geom, visibleFamilies, minConfidence]);

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
      <div className="flex h-screen">
        <div className="w-72 shrink-0 space-y-3 border-r border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-40" />
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-64" />
        </div>
        <div className="flex-1 bg-[var(--surface-2)]" />
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-8 py-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Visor del plano</h1>
          <p className="text-sm text-[var(--muted)]">
            {visibleCount.toLocaleString("es-MX")} detecciones visibles · rueda para zoom,
            arrastra para mover, clic para inspeccionar
          </p>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Elementos detectados
          </h3>
          <div className="mb-4 space-y-1">
            {families.map(({ family, count }) => (
              <label
                key={family}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm transition hover:bg-[var(--surface-2)]"
              >
                <input
                  type="checkbox"
                  checked={visibleFamilies.has(family)}
                  onChange={() => toggle(visibleFamilies, family, setVisibleFamilies)}
                  className="accent-[var(--primary)]"
                />
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: FAMILY_COLORS[family] ?? "#111827" }}
                />
                <span className="flex-1">{FAMILY_LABELS[family] ?? family}</span>
                <span className="tabular text-xs text-[var(--muted)]">{count}</span>
              </label>
            ))}
          </div>

          <div className="mb-4">
            <label className="mb-1.5 block text-xs font-medium text-[var(--muted)]">
              Confianza mínima: {(minConfidence * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Capas ({visibleLayers.size}/{geom.layers.length})
          </h3>
          <div className="space-y-0.5">
            {geom.layers.map((l) => (
              <label
                key={l.name}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm transition hover:bg-[var(--surface-2)]"
              >
                <input
                  type="checkbox"
                  checked={visibleLayers.has(l.name)}
                  onChange={() => toggle(visibleLayers, l.name, setVisibleLayers)}
                  className="accent-[var(--primary)]"
                />
                <span className="flex-1 truncate" title={l.name}>
                  {l.name}
                </span>
                <span className="tabular text-xs text-[var(--muted)]">{l.count}</span>
              </label>
            ))}
          </div>
        </aside>

        <div className="relative min-w-0 flex-1 bg-[var(--surface-2)]">
          <PlanoCanvas
            geometry={geom}
            visibleLayers={visibleLayers}
            visibleFamilies={visibleFamilies}
            minConfidence={minConfidence}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
          />
          {selected && (
            <div className="rise-in absolute bottom-4 left-4 z-10 w-[380px] max-w-[calc(100%-2rem)] rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 shadow-[var(--shadow-lg)]">
              <div className="mb-2 flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span
                    className="h-3 w-3 shrink-0 rounded-sm"
                    style={{ background: FAMILY_COLORS[familyOf(selected)] ?? "#111827" }}
                  />
                  <div>
                    <div className="font-semibold leading-tight">
                      {detectionTitle(selected)}
                    </div>
                    {selected.display_label && (
                      <div className="font-mono text-xs text-[var(--muted)]">
                        {selected.display_label}
                        {selected.mark && ` · etiqueta en plano: ${selected.mark}`}
                      </div>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  aria-label="Cerrar detalle"
                  className="rounded p-1 text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                >
                  <X size={14} />
                </button>
              </div>
              {selected.description && (
                <p className="mb-3 text-sm leading-relaxed text-[var(--muted)]">
                  {selected.description}
                </p>
              )}
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
