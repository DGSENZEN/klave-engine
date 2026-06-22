"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { getGeometry, type Geometry } from "@/lib/api";
import {
  PlanoCanvas,
  DETECTION_COLORS,
  DETECTION_LABELS,
} from "@/components/PlanoCanvas";
import { Spinner } from "@/components/ui";

export default function PlanoPage() {
  const { id } = useParams<{ id: string }>();
  const [geom, setGeom] = useState<Geometry | null>(null);
  const [visibleLayers, setVisibleLayers] = useState<Set<string>>(new Set());
  const [visibleTypes, setVisibleTypes] = useState<Set<string>>(new Set());
  const [minConfidence, setMinConfidence] = useState(0);

  useEffect(() => {
    getGeometry(id).then((g) => {
      setGeom(g);
      setVisibleLayers(new Set(g.layers.slice(0, 14).map((l) => l.name)));
      setVisibleTypes(new Set(g.detections.map((d) => d.type)));
    });
  }, [id]);

  const types = useMemo(() => {
    if (!geom) return [] as { type: string; count: number }[];
    const counts: Record<string, number> = {};
    for (const d of geom.detections) counts[d.type] = (counts[d.type] ?? 0) + 1;
    return Object.entries(counts)
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count);
  }, [geom]);

  const visibleCount = useMemo(() => {
    if (!geom) return 0;
    return geom.detections.filter(
      (d) => visibleTypes.has(d.type) && d.confidence >= minConfidence,
    ).length;
  }, [geom, visibleTypes, minConfidence]);

  function toggle(set: Set<string>, key: string, setter: (s: Set<string>) => void) {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    setter(next);
  }

  if (!geom) {
    return (
      <div className="flex h-screen items-center justify-center gap-2 text-sm text-[var(--muted)]">
        <Spinner className="h-5 w-5" /> Cargando geometría…
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-8 py-4">
        <div>
          <h1 className="text-xl font-semibold">Visor del plano</h1>
          <p className="text-sm text-[var(--muted)]">
            {visibleCount.toLocaleString("es-MX")} detecciones visibles · rueda para zoom,
            arrastra para mover
          </p>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-[var(--border)] bg-[var(--surface)] px-4 py-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Detecciones
          </h3>
          <div className="mb-4 space-y-1">
            {types.map(({ type, count }) => (
              <label
                key={type}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]"
              >
                <input
                  type="checkbox"
                  checked={visibleTypes.has(type)}
                  onChange={() => toggle(visibleTypes, type, setVisibleTypes)}
                  className="accent-[var(--primary)]"
                />
                <span
                  className="h-2.5 w-2.5 rounded-sm"
                  style={{ background: DETECTION_COLORS[type] ?? "#111827" }}
                />
                <span className="flex-1">{DETECTION_LABELS[type] ?? type}</span>
                <span className="tabular text-xs text-[var(--muted)]">{count}</span>
              </label>
            ))}
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
              Confianza mínima: {(minConfidence * 100).toFixed(0)}%
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-full accent-[var(--primary)]"
            />
          </div>

          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Capas ({visibleLayers.size}/{geom.layers.length})
          </h3>
          <div className="space-y-0.5">
            {geom.layers.map((l) => (
              <label
                key={l.name}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-[var(--surface-2)]"
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

        <div className="min-w-0 flex-1 bg-[var(--surface-2)]">
          <PlanoCanvas
            geometry={geom}
            visibleLayers={visibleLayers}
            visibleTypes={visibleTypes}
            minConfidence={minConfidence}
          />
        </div>
      </div>
    </div>
  );
}
