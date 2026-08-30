"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CornersOut } from "@phosphor-icons/react";
import type { DetectionOverlay, Geometry } from "@/lib/api";
import { FAMILY_COLORS, detectionTitle, familyOf } from "@/lib/families";
import { cssVar, subscribeTheme } from "@/lib/theme";

type View = { scale: number; ox: number; oy: number };

export type MeasureMode = "distancia" | "area" | "conteo";

export type MeasureState = { mode: MeasureMode; points: [number, number][] };

export function PlanoCanvas({
  geometry,
  visibleLayers,
  visibleFamilies,
  minConfidence,
  selectedId,
  onSelect,
  measure,
  onWorldClick,
  focus,
}: {
  geometry: Geometry;
  visibleLayers: Set<string>;
  visibleFamilies: Set<string>;
  minConfidence: number;
  selectedId?: string | null;
  onSelect?: (detection: DetectionOverlay | null) => void;
  /** Active measurement: clicks add world points instead of selecting. */
  measure?: MeasureState | null;
  onWorldClick?: (point: [number, number]) => void;
  /** Fit the view to a world bbox whenever `nonce` changes (sheet navigation). */
  focus?: { bbox: [number, number, number, number]; nonce: number } | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<View | null>(null);
  const dragRef = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    text: string;
    medidas: { label: string; value: string }[];
  } | null>(null);
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

  const fitTo = useCallback((bbox: [number, number, number, number]) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const spanX = Math.max(bbox[2] - bbox[0], 1e-6);
    const spanY = Math.max(bbox[3] - bbox[1], 1e-6);
    const scale = Math.min(w / spanX, h / spanY) * 0.95;
    viewRef.current = {
      scale,
      ox: (w - spanX * scale) / 2 - bbox[0] * scale,
      oy: (h + spanY * scale) / 2 + bbox[1] * scale,
    };
    force((n) => n + 1);
  }, []);

  useEffect(() => {
    if (focus) fitTo(focus.bbox);
  }, [focus, fitTo]);

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

    // Base geometry: linework first, then hatches, cotas and texts so the
    // sheet reads like the sheet — not a skeleton of it.
    const stroke = cssVar("--canvas-stroke") || "#cbd5e1";
    const ink = cssVar("--canvas-ink") || cssVar("--foreground") || "#334155";
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = stroke;
    ctx.beginPath();
    for (const s of geometry.shapes) {
      if (!visibleLayers.has(s.layer)) continue;
      if (s.t === "hatch" || s.t === "text" || s.t === "dim" || s.t === "arc") continue;
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
      } else if (s.t === "box") {
        const [x1, y1] = toScreen(s.bbox[0], s.bbox[1], v);
        const [x2, y2] = toScreen(s.bbox[2], s.bbox[3], v);
        ctx.rect(x1, y1, x2 - x1, y2 - y1);
      }
    }
    ctx.stroke();

    // Arcs (DXF angles are counter-clockwise in degrees; the screen Y is flipped).
    ctx.beginPath();
    for (const s of geometry.shapes) {
      if (s.t !== "arc" || !visibleLayers.has(s.layer)) continue;
      const [cx, cy] = toScreen(s.c[0], s.c[1], v);
      const r = Math.max(s.r * v.scale, 0.5);
      const a0 = (-s.a0 * Math.PI) / 180;
      const a1 = (-s.a1 * Math.PI) / 180;
      ctx.moveTo(cx + r * Math.cos(a0), cy + r * Math.sin(a0));
      ctx.arc(cx, cy, r, a0, a1, true);
    }
    ctx.stroke();

    // Hatches: the outline with a faint fill.
    ctx.fillStyle = `${stroke}33`;
    for (const s of geometry.shapes) {
      if (s.t !== "hatch" || !visibleLayers.has(s.layer)) continue;
      ctx.beginPath();
      s.pts.forEach(([px, py], i) => {
        const [sx, sy] = toScreen(px, py, v);
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    // Cotas: the measured span and its value, once there is room to read it.
    const cotaColor = cssVar("--canvas-cota") || "#94a3b8";
    ctx.strokeStyle = cotaColor;
    ctx.fillStyle = cotaColor;
    ctx.beginPath();
    for (const s of geometry.shapes) {
      if (s.t !== "dim" || !visibleLayers.has(s.layer) || s.pts.length < 2) continue;
      const [x1, y1] = toScreen(s.pts[0][0], s.pts[0][1], v);
      const [x2, y2] = toScreen(s.pts[1][0], s.pts[1][1], v);
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
    }
    ctx.stroke();
    if (v.scale > 12) {
      ctx.font = "10px ui-sans-serif, system-ui";
      ctx.textAlign = "center";
      for (const s of geometry.shapes) {
        if (s.t !== "dim" || !visibleLayers.has(s.layer) || !s.label || s.pts.length < 2) continue;
        const [x1, y1] = toScreen(s.pts[0][0], s.pts[0][1], v);
        const [x2, y2] = toScreen(s.pts[1][0], s.pts[1][1], v);
        const angle = Math.atan2(y2 - y1, x2 - x1);
        ctx.save();
        ctx.translate((x1 + x2) / 2, (y1 + y2) / 2);
        ctx.rotate(Math.abs(angle) > Math.PI / 2 ? angle + Math.PI : angle);
        ctx.fillText(s.label, 0, -3);
        ctx.restore();
      }
      ctx.textAlign = "start";
    }

    // Texts: drawn at their real height once it is legible on screen.
    ctx.fillStyle = ink;
    for (const s of geometry.shapes) {
      if (s.t !== "text" || !visibleLayers.has(s.layer)) continue;
      const px = s.h * v.scale;
      if (px < 4) continue;
      const [sx, sy] = toScreen(s.p[0], s.p[1], v);
      ctx.save();
      ctx.translate(sx, sy);
      if (s.rot) ctx.rotate((-s.rot * Math.PI) / 180);
      ctx.font = `${Math.min(px, 64)}px ui-sans-serif, system-ui`;
      ctx.fillText(s.s, 0, 0);
      ctx.restore();
    }

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
      const outline = d.polygon && d.polygon.length >= 3 ? d.polygon : null;
      ctx.globalAlpha = excluded ? 0.35 : 1;
      ctx.setLineDash(excluded ? [5, 4] : []);
      ctx.strokeStyle = color;
      ctx.lineWidth = selected ? 2.4 : d.review === "confirmed" ? 1.9 : 1.4;
      if (outline) {
        // A tablero is drawn as its real outline, lightly filled so the
        // slab system reads at a glance.
        ctx.beginPath();
        outline.forEach(([px, py], i) => {
          const [sx, sy] = toScreen(px, py, v);
          if (i === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        ctx.closePath();
        ctx.fillStyle = `${color}${selected ? "40" : "1a"}`;
        ctx.fill();
        ctx.stroke();
      } else {
        if (selected) {
          ctx.fillStyle = `${color}2e`;
          ctx.fillRect(rx - 2, ry - 2, rw + 4, rh + 4);
        }
        ctx.strokeRect(rx, ry, rw, rh);
      }
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

    // Measurement overlay: always on top, in the accent color.
    if (measure && measure.points.length > 0) {
      const accent = cssVar("--accent") || "#2b4acb";
      const screenPoints = measure.points.map(([x, y]) => toScreen(x, y, v));
      ctx.strokeStyle = accent;
      ctx.fillStyle = accent;
      ctx.lineWidth = 1.6;
      if (measure.mode === "conteo") {
        ctx.font = "600 10px ui-sans-serif, system-ui";
        screenPoints.forEach(([sx, sy], index) => {
          ctx.beginPath();
          ctx.arc(sx, sy, 8, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = "#ffffff";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(String(index + 1), sx, sy);
          ctx.fillStyle = accent;
        });
        ctx.textAlign = "start";
        ctx.textBaseline = "alphabetic";
      } else {
        ctx.beginPath();
        screenPoints.forEach(([sx, sy], index) => {
          if (index === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        if (measure.mode === "area" && screenPoints.length > 2) {
          ctx.closePath();
          ctx.save();
          ctx.globalAlpha = 0.15;
          ctx.fill();
          ctx.restore();
        }
        ctx.stroke();
        for (const [sx, sy] of screenPoints) {
          ctx.beginPath();
          ctx.arc(sx, sy, 3.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
  }, [geometry, visibleLayers, isVisible, selectedId, measure]);

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
            medidas: hit.medidas ?? [],
          }
        : null,
    );
  }
  function onMouseUp(e: React.MouseEvent) {
    const wasDrag = dragRef.current?.moved;
    dragRef.current = null;
    if (wasDrag) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    if (measure && onWorldClick) {
      const v = viewRef.current;
      if (!v) return;
      onWorldClick([(mx - v.ox) / v.scale, -(my - v.oy) / v.scale]);
      return;
    }
    if (!onSelect) return;
    const hit = hitTest(mx, my);
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
        className={
          measure
            ? "h-full w-full cursor-crosshair"
            : "h-full w-full cursor-grab active:cursor-grabbing"
        }
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
          <div className="font-medium">{tooltip.text}</div>
          {tooltip.medidas.length > 0 && (
            <div className="mt-1 space-y-0.5 border-t border-background/25 pt-1">
              {tooltip.medidas.map((m) => (
                <div key={m.label} className="flex justify-between gap-3">
                  <span className="opacity-75">{m.label}</span>
                  <span className="tabular font-medium">{m.value}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
