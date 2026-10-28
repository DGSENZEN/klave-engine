"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** px per ms the hero train travels. */
const VELOCIDAD = 0.9;
const CADA_MS = 8000;

const pesos = (el: HTMLElement, valor: number) => {
  const decimales = Number(el.dataset.decimales ?? 0);
  el.textContent = valor.toLocaleString("es-MX", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  });
};

/** Count a figure from one value to another with an expo ease-out. */
function contar(el: HTMLElement, de: number, a: number, ms: number, relojes: number[]) {
  const inicio = performance.now();
  const paso = (ahora: number) => {
    const t = Math.min(1, (ahora - inicio) / ms);
    // Money eases out; whole counts tick evenly.
    const curva = el.dataset.decimales ? 1 - Math.pow(2, -10 * t) : t;
    pesos(el, de + (a - de) * curva);
    if (t < 1) relojes.push(requestAnimationFrame(paso));
    else pesos(el, a);
  };
  relojes.push(requestAnimationFrame(paso));
}

/**
 * The line of the portada: the bundle of strokes that runs under the hero,
 * bends down and carries every stage below. A train runs the hero line, a
 * second one rides the bundle as the visitor scrolls carrying the number of
 * the stage in view, and each drawn screen plays its sequence the first time
 * it scrolls into view. Everything is drawn and readable without this script;
 * it only adds the motion.
 */
export function RutaPortada({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ruta = ref.current;
    if (!ruta) return;
    const quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const estaciones = Array.from(ruta.querySelectorAll<HTMLElement>("[data-estacion]"));
    const placa = ruta.querySelector<HTMLElement>(".l68-vbundle i");
    const tren = ruta.querySelector<HTMLElement>(".l68-htrain");
    const relojes: number[] = [];
    const cuadros: number[] = [];
    let frame = 0;
    let actual: HTMLElement | null = null;

    const medir = () => {
      frame = 0;
      const caja = ruta.getBoundingClientRect();
      const mitad = window.innerHeight * 0.55;
      const avance = (mitad - caja.top - 102) / Math.max(1, caja.height - 102);
      ruta.style.setProperty("--l68-progress", String(Math.min(1, Math.max(0, avance))));
      let aqui: HTMLElement | null = null;
      for (const estacion of estaciones) {
        if (estacion.getBoundingClientRect().top < mitad) aqui = estacion;
      }
      if (aqui === actual) return;
      actual = aqui;
      for (const estacion of estaciones) estacion.classList.toggle("is-here", estacion === aqui);
      if (placa) placa.textContent = aqui?.dataset.estacion ?? "";
    };
    const pedir = () => {
      if (!frame) frame = requestAnimationFrame(medir);
    };

    // The hero train: along the accent stroke, round the bend and down.
    let viaje: Animation | null = null;
    const correr = () => {
      if (!tren || document.hidden || getComputedStyle(tren).display === "none") return;
      const caja = ruta.getBoundingClientRect();
      const ancho = caja.width;
      const x0 = -caja.left - 60;
      const curva = ancho - 102;
      tren.style.offsetPath = `path("M ${x0} 32 H ${curva} A 70 70 0 0 1 ${ancho - 32} 102 V 190")`;
      const largo = curva - x0 + (Math.PI * 70) / 2 + 88;
      viaje?.cancel();
      viaje = tren.animate(
        [
          { offsetDistance: "0px", opacity: 0 },
          { offsetDistance: "80px", opacity: 1, offset: 0.06 },
          { offsetDistance: `${largo - 60}px`, opacity: 1, offset: 0.94 },
          { offsetDistance: `${largo}px`, opacity: 0 },
        ],
        { duration: largo / VELOCIDAD, easing: "cubic-bezier(0.45, 0, 0.2, 1)", fill: "both" },
      );
    };
    let ciclo = 0;
    const vigia = new IntersectionObserver(([entrada]) => {
      window.clearInterval(ciclo);
      if (!entrada.isIntersecting || quieto) return;
      relojes.push(window.setTimeout(correr, 400));
      ciclo = window.setInterval(correr, CADA_MS);
    });
    vigia.observe(ruta);

    // Drawn screens: hold them at their first frame until they are seen.
    const pantallas = Array.from(ruta.querySelectorAll<HTMLElement>("[data-play]"));
    const tocar = (pantalla: HTMLElement) => {
      pantalla.classList.remove("is-armed");
      for (const cifra of pantalla.querySelectorAll<HTMLElement>("[data-cuenta]")) {
        const meta = Number(cifra.dataset.cuenta);
        contar(cifra, 0, meta, Number(cifra.dataset.dur ?? 1200), cuadros);
        const luego = cifra.dataset.luego;
        if (luego) {
          relojes.push(
            window.setTimeout(
              () => contar(cifra, meta, Number(luego), 700, cuadros),
              Number(cifra.dataset.luegoMs ?? 2500),
            ),
          );
        }
      }
    };
    let lector: IntersectionObserver | null = null;
    if (!quieto) {
      lector = new IntersectionObserver(
        (entradas) => {
          for (const entrada of entradas) {
            if (!entrada.isIntersecting) continue;
            lector?.unobserve(entrada.target);
            tocar(entrada.target as HTMLElement);
          }
        },
        { threshold: 0.35 },
      );
      for (const pantalla of pantallas) {
        if (pantalla.getBoundingClientRect().top < window.innerHeight * 0.8) continue;
        pantalla.classList.add("is-armed");
        for (const cifra of pantalla.querySelectorAll<HTMLElement>("[data-cuenta]")) pesos(cifra, 0);
        lector.observe(pantalla);
      }
    }

    medir();
    window.addEventListener("scroll", pedir, { passive: true });
    window.addEventListener("resize", pedir);
    return () => {
      cancelAnimationFrame(frame);
      window.clearInterval(ciclo);
      relojes.forEach((reloj) => window.clearTimeout(reloj));
      cuadros.forEach((cuadro) => cancelAnimationFrame(cuadro));
      viaje?.cancel();
      vigia.disconnect();
      lector?.disconnect();
      window.removeEventListener("scroll", pedir);
      window.removeEventListener("resize", pedir);
    };
  }, []);

  return (
    <div ref={ref} className="l68-route">
      <div className="l68-hbundle" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <svg className="l68-corner" viewBox="0 0 102 102" aria-hidden="true">
        <path d="M0 2 A100 100 0 0 1 100 102" />
        <path d="M0 12 A90 90 0 0 1 90 102" />
        <path d="M0 22 A80 80 0 0 1 80 102" />
        <path className="is-accent" d="M0 32 A70 70 0 0 1 70 102" />
      </svg>
      <div className="l68-vbundle" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
        <i />
      </div>
      <span className="l68-htrain" aria-hidden="true" />
      {children}
    </div>
  );
}
