"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CornersOut } from "@phosphor-icons/react";
import type { DetectionOverlay, Geometry } from "@/lib/api";
import { cssVar, subscribeTheme } from "@/lib/theme";

// Family-first palette; detection-type keys keep old runs rendering.
// Deliberately desaturated so overlays read as one harmonized system on both
// canvas themes; distinct hues remain because families must stay tellable.
export const FAMILY_COLORS: Record<string, string> = {
  castillo: "#c2703d",
  columna: "#b8504d",
  trabe: "#4a66c9",
  contratrabe: "#6f66b8",
  zapata: "#a07a3a",
  losa: "#4d9077",
  muro: "#8a67ad",
  eje: "#9aa0aa",
  interseccion_ejes: "#767d88",
  referencia_detalle: "#b06084",
  // Legacy detection-type fallbacks (runs without taxonomy).
  grid_line: "#9aa0aa",
  grid_intersection: "#767d88",
  column_tag: "#b8504d",
  beam_tag: "#4a66c9",
  footing: "#a07a3a",
  slab_region: "#4d9077",
  wall: "#8a67ad",
  detail_reference: "#b06084",
};

export const FAMILY_LABELS: Record<string, string> = {
  castillo: "Castillos",
  columna: "Columnas",
  trabe: "Trabes",
  contratrabe: "Contratrabes",
  zapata: "Zapatas",
  losa: "Losas",
  muro: "Muros",
  eje: "Ejes",
  interseccion_ejes: "Intersecciones",
  referencia_detalle: "Referencias",
  // Legacy detection-type fallbacks.
  grid_line: "Ejes",
  grid_intersection: "Intersecciones",
  column_tag: "Columnas/castillos",
  beam_tag: "Trabes",
  footing: "Zapatas/dados",
  slab_region: "Losas",
  wall: "Muros",
  detail_reference: "Referencias",
};

/** Grouping key for legend + visibility: family when available, else type. */
export function familyOf(d: DetectionOverlay): string {
  return d.family || d.type;
}

export function detectionTitle(d: DetectionOverlay): string {
  const base = d.family_label || FAMILY_LABELS[d.type] || d.type;
  const name = d.mark || d.display_label || d.label;
  return `${base} ${name}`.trim();
}

type View = { scale: number; ox: number; oy: number };

export function PlanoCanvas({
  geometry,
  visibleLayers,
  visibleFamilies,
  minConfidence,
  selectedId,
  onSelect,
}: {
  geometry: Geometry;
  visibleLayers: Set<string>;
  visibleFamilies: Set<string>;
  minConfidence: number;
  selectedId?: string | null;
  onSelect?: (detection: DetectionOverlay | null) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<View | null>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);
  const [, force] = useState(0);

  const [minx, miny, maxx, maxy] = geometry.extent;

  const fit = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const spanX = Math.max(maxx - minx, 1e-6);
    const spanY = Math.max(maxy - miny, 1e-6);
    const scale = Math.min(w / spanX, h / spanY) * 0.92;
    viewRef.current = {
      scale,
      ox: (w - spanX * scale) / 2 - minx * scale,
      oy: (h + spanY * scale) / 2 + miny * scale, // Y flipped (drawing up)
    };
    force((n) => n + 1);
  }, [minx, miny, maxx, maxy]);

  // World → screen
  const toScreen = (x: number, y: number, v: View): [number, number] => [
    x * v.scale + v.ox,
    -y * v.scale + v.oy,
  ];

  const isVisible = useCallback(
    (d: DetectionOverlay) => visibleFamilies.has(familyOf(d)) && d.confidence >= minConfidence,
    [visibleFamilies, minConfidence],
  );

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const v = viewRef.current;
    if (!canvas || !v) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = cssVar("--canvas-bg") || "#ffffff";
    ctx.fillRect(0, 0, w, h);

    // Base geometry
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = cssVar("--canvas-stroke") || "#cbd5e1";
    ctx.beginPath();
    for (const s of geometry.shapes) {
      if (!visibleLayers.has(s.layer)) continue;
      if (s.t === "path") {
        const pts = s.pts;
        for (let i = 0; i < pts.length; i++) {
          const [sx, sy] = toScreen(pts[i][0], pts[i][1], v);
          if (i === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        }
        if (s.closed && pts.length > 2) {
          const [sx, sy] = toScreen(pts[0][0], pts[0][1], v);
          ctx.lineTo(sx, sy);
        }
      } else if (s.t === "circle") {
        const [cx, cy] = toScreen(s.c[0], s.c[1], v);
        ctx.moveTo(cx + s.r * v.scale, cy);
        ctx.arc(cx, cy, Math.max(s.r * v.scale, 0.5), 0, Math.PI * 2);
      } else {
        const [x1, y1] = toScreen(s.bbox[0], s.bbox[1], v);
        const [x2, y2] = toScreen(s.bbox[2], s.bbox[3], v);
        ctx.rect(x1, y1, x2 - x1, y2 - y1);
      }
    }
    ctx.stroke();

    // Detection overlays
    const showLabels = v.scale > 6;
    for (const d of geometry.detections) {
      if (!isVisible(d)) continue;
      const color = FAMILY_COLORS[familyOf(d)] ?? "#111827";
      const selected = d.id === selectedId;
      const [x1, y1] = toScreen(d.bbox[0], d.bbox[1], v);
      const [x2, y2] = toScreen(d.bbox[2], d.bbox[3], v);
      const rx = Math.min(x1, x2);
      const ry = Math.min(y1, y2);
      const rw = Math.abs(x2 - x1) || 2;
      const rh = Math.abs(y2 - y1) || 2;
      // Human verdicts change how the element reads: excluded fades to a
      // dashed outline, confirmed draws slightly heavier.
      const excluded = d.review === "excluded";
      if (selected) {
        ctx.fillStyle = `${color}2e`;
        ctx.fillRect(rx - 2, ry - 2, rw + 4, rh + 4);
      }
      ctx.globalAlpha = excluded ? 0.35 : 1;
      ctx.setLineDash(excluded ? [5, 4] : []);
      ctx.strokeStyle = color;
      ctx.lineWidth = selected ? 2.4 : d.review === "confirmed" ? 1.9 : 1.4;
      ctx.strokeRect(rx, ry, rw, rh);
      if (showLabels || selected) {
        ctx.fillStyle = color;
        ctx.font = selected
          ? "600 11px ui-sans-serif, system-ui"
          : "10px ui-sans-serif, system-ui";
        ctx.fillText(d.mark || d.display_label || d.label, rx, ry - 3);
      }
      ctx.globalAlpha = 1;
      ctx.setLineDash([]);
    }
  }, [geometry, visibleLayers, isVisible, selectedId]);

  useEffect(() => {
    fit();
  }, [fit]);

  useEffect(() => {
    draw();
  });

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [draw]);

  // The canvas palette lives in CSS tokens; redraw when the theme flips.
  useEffect(() => subscribeTheme(() => draw()), [draw]);

  function hitTest(mx: number, my: number): DetectionOverlay | null {
    const v = viewRef.current;
    if (!v) return null;
    const wx = (mx - v.ox) / v.scale;
    const wy = -(my - v.oy) / v.scale;
    let best: DetectionOverlay | null = null;
    let bestArea = Infinity;
    for (const d of geometry.detections) {
      if (!isVisible(d)) continue;
      const [a, b, c, dd] = d.bbox;
      if (wx >= a - 0.05 && wx <= c + 0.05 && wy >= b - 0.05 && wy <= dd + 0.05) {
        const area = Math.max(c - a, 0.01) * Math.max(dd - b, 0.01);
        if (area < bestArea) {
          best = d;
          bestArea = area;
        }
      }
    }
    return best;
  }

  function onWheel(e: React.WheelEvent) {
    const v = viewRef.current;
    const canvas = canvasRef.current;
    if (!v || !canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const ns = v.scale * factor;
    // keep cursor point fixed
    v.ox = mx - (mx - v.ox) * factor;
    v.oy = my - (my - v.oy) * factor;
    v.scale = ns;
    draw();
  }

  function onMouseDown(e: React.MouseEvent) {
    dragRef.current = { x: e.clientX, y: e.clientY, moved: false };
  }
  function onMouseMove(e: React.MouseEvent) {
    const v = viewRef.current;
    if (!v) return;
    if (dragRef.current) {
      const dx = e.clientX - dragRef.current.x;
      const dy = e.clientY - dragRef.current.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) dragRef.current.moved = true;
      v.ox += dx;
      v.oy += dy;
      dragRef.current = { ...dragRef.current, x: e.clientX, y: e.clientY };
      draw();
      return;
    }
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = hitTest(mx, my);
    setTooltip(
      hit
        ? {
            x: mx,
            y: my,
            text: `${detectionTitle(hit)} · ${(hit.confidence * 100).toFixed(0)}%`,
          }
        : null,
    );
  }
  function onMouseUp(e: React.MouseEvent) {
    const wasDrag = dragRef.current?.moved;
    dragRef.current = null;
    if (wasDrag || !onSelect) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const hit = hitTest(e.clientX - rect.left, e.clientY - rect.top);
    onSelect(hit && hit.id === selectedId ? null : hit);
  }

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <canvas
        ref={canvasRef}
        onWheel={onWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => {
          dragRef.current = null;
          setTooltip(null);
        }}
        className="h-full w-full cursor-grab active:cursor-grabbing"
      />
      <button
        onClick={fit}
        className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium shadow-sm transition hover:bg-surface-2"
      >
        <CornersOut size={13} weight="bold" /> Ajustar vista
      </button>
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 max-w-xs rounded-md bg-foreground/95 px-2.5 py-1.5 text-xs text-background shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
