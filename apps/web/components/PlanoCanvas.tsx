"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Geometry } from "@/lib/api";

export const DETECTION_COLORS: Record<string, string> = {
  grid_line: "#94a3b8",
  grid_intersection: "#64748b",
  column_tag: "#dc2626",
  beam_tag: "#2563eb",
  footing: "#b45309",
  slab_region: "#059669",
  wall: "#7c3aed",
  detail_reference: "#db2777",
};

export const DETECTION_LABELS: Record<string, string> = {
  grid_line: "Ejes",
  grid_intersection: "Intersecciones",
  column_tag: "Columnas/castillos",
  beam_tag: "Trabes",
  footing: "Zapatas/dados",
  slab_region: "Losas",
  wall: "Muros",
  detail_reference: "Referencias",
};

type View = { scale: number; ox: number; oy: number };

export function PlanoCanvas({
  geometry,
  visibleLayers,
  visibleTypes,
  minConfidence,
}: {
  geometry: Geometry;
  visibleLayers: Set<string>;
  visibleTypes: Set<string>;
  minConfidence: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<View | null>(null);
  const dragRef = useRef<{ x: number; y: number } | null>(null);
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
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, w, h);

    // Base geometry
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = "#cbd5e1";
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
      if (!visibleTypes.has(d.type) || d.confidence < minConfidence) continue;
      const color = DETECTION_COLORS[d.type] ?? "#111827";
      const [x1, y1] = toScreen(d.bbox[0], d.bbox[1], v);
      const [x2, y2] = toScreen(d.bbox[2], d.bbox[3], v);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.4;
      ctx.strokeRect(
        Math.min(x1, x2),
        Math.min(y1, y2),
        Math.abs(x2 - x1) || 2,
        Math.abs(y2 - y1) || 2,
      );
      if (showLabels) {
        ctx.fillStyle = color;
        ctx.font = "10px ui-sans-serif, system-ui";
        ctx.fillText(d.label, Math.min(x1, x2), Math.min(y1, y2) - 3);
      }
    }
  }, [geometry, visibleLayers, visibleTypes, minConfidence]);

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
    dragRef.current = { x: e.clientX, y: e.clientY };
  }
  function onMouseMove(e: React.MouseEvent) {
    const v = viewRef.current;
    if (!v) return;
    if (dragRef.current) {
      v.ox += e.clientX - dragRef.current.x;
      v.oy += e.clientY - dragRef.current.y;
      dragRef.current = { x: e.clientX, y: e.clientY };
      draw();
      return;
    }
    // hover tooltip: nearest detection containing the cursor (world space)
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const wx = (mx - v.ox) / v.scale;
    const wy = -(my - v.oy) / v.scale;
    let hit: string | null = null;
    for (const d of geometry.detections) {
      if (!visibleTypes.has(d.type) || d.confidence < minConfidence) continue;
      const [a, b, c, dd] = d.bbox;
      if (wx >= a - 0.05 && wx <= c + 0.05 && wy >= b - 0.05 && wy <= dd + 0.05) {
        hit = `${DETECTION_LABELS[d.type] ?? d.type}: ${d.label} · ${(d.confidence * 100).toFixed(0)}%`;
        break;
      }
    }
    setTooltip(hit ? { x: mx, y: my, text: hit } : null);
  }
  function onMouseUp() {
    dragRef.current = null;
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
          onMouseUp();
          setTooltip(null);
        }}
        className="h-full w-full cursor-grab active:cursor-grabbing"
      />
      <button
        onClick={fit}
        className="absolute right-3 top-3 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-medium shadow-sm hover:bg-[var(--surface-2)]"
      >
        Ajustar vista
      </button>
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 rounded-md bg-slate-900 px-2 py-1 text-xs text-white shadow-lg"
          style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
