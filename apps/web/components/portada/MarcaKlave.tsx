"use client";

import { useEffect, useRef } from "react";

const CAPAS = ["w1", "w2", "w3", "w4", "w5", "w6", "w7"];

/** The wordmark in 68 lettering; an accent pulse runs out through its rings
 * while it is on screen. */
export function MarcaKlave() {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;
    const vigia = new IntersectionObserver(([entrada]) => {
      svg.classList.toggle("is-live", entrada.isIntersecting);
    });
    vigia.observe(svg);
    return () => vigia.disconnect();
  }, []);

  return (
    <svg ref={ref} className="l68-mark" viewBox="0 0 1240 330" role="img" aria-label="Klave">
      {CAPAS.map((capa) => (
        <text
          key={capa}
          className={capa}
          x="40"
          y="270"
          textLength="1160"
          lengthAdjust="spacingAndGlyphs"
        >
          Klave
        </text>
      ))}
    </svg>
  );
}
