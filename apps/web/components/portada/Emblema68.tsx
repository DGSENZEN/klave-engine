"use client";

import { useEffect, useRef } from "react";

const RADIOS = Array.from({ length: 12 }, (_, i) => 10 + i * 21);

/**
 * Two sets of concentric rings, one drifting over the other: the moiré of
 * 1968 op-art. The top set follows the pointer a little; when the pointer is
 * still it drifts on its own. Paused off screen and under reduced motion.
 */
export function Emblema68() {
  const ref = useRef<SVGSVGElement>(null);
  const capa = useRef<SVGGElement>(null);

  useEffect(() => {
    const svg = ref.current;
    const g = capa.current;
    if (!svg || !g || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let meta = { x: 0, y: 0 };
    let pos = { x: 0, y: 0 };
    let frame = 0;
    let vivo = false;

    const paso = () => {
      pos = { x: pos.x + (meta.x - pos.x) * 0.08, y: pos.y + (meta.y - pos.y) * 0.08 };
      g.setAttribute("transform", `translate(${pos.x.toFixed(2)} ${pos.y.toFixed(2)})`);
      frame = vivo && (Math.abs(meta.x - pos.x) > 0.05 || Math.abs(meta.y - pos.y) > 0.05)
        ? requestAnimationFrame(paso)
        : 0;
    };
    const mover = (event: PointerEvent) => {
      if (!vivo) return;
      const caja = svg.getBoundingClientRect();
      const dx = (event.clientX - (caja.left + caja.width / 2)) / window.innerWidth;
      const dy = (event.clientY - (caja.top + caja.height / 2)) / window.innerHeight;
      meta = { x: Math.max(-1, Math.min(1, dx)) * 26, y: Math.max(-1, Math.min(1, dy)) * 26 };
      if (!frame) frame = requestAnimationFrame(paso);
    };
    const vigia = new IntersectionObserver(([entrada]) => {
      vivo = entrada.isIntersecting;
      svg.classList.toggle("is-live", vivo);
    });

    vigia.observe(svg);
    window.addEventListener("pointermove", mover, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      vigia.disconnect();
      window.removeEventListener("pointermove", mover);
    };
  }, []);

  return (
    <svg ref={ref} className="l68-emblem" viewBox="-260 -260 520 520" aria-hidden="true">
      <g className="base">
        {RADIOS.map((r) => (
          <circle key={r} r={r} />
        ))}
      </g>
      <g ref={capa}>
        <g className="drift">
          {RADIOS.map((r) => (
            <circle key={r} r={r} />
          ))}
        </g>
      </g>
    </svg>
  );
}
