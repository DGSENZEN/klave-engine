"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Pause } from "@phosphor-icons/react";
import { colocarTarjeta, type Rect } from "@/lib/recorrido/colocar";
import type { Capitulo, Paso } from "@/lib/recorrido/tipos";
import { Button } from "@/components/ui";

const ANCHO = 340;

/** La tarjeta de un paso: qué es, cómo se usa, por qué. No es modal: el
 * trabajo sigue detrás de ella. Bajo md es una hoja al pie de la pantalla. */
export function TarjetaPaso({
  capitulo,
  paso,
  indice,
  rect,
  repaso,
  anclaPerdida,
  fueraDeRuta,
  ocupada,
  esUltimoCapitulo,
  onSiguiente,
  onAtras,
  onSaltar,
  onPausar,
  onVolver,
  onAccion,
}: {
  capitulo: Capitulo;
  paso: Paso | null;
  indice: number;
  rect: Rect | null;
  repaso: boolean;
  anclaPerdida: boolean;
  fueraDeRuta: boolean;
  ocupada: boolean;
  esUltimoCapitulo: boolean;
  onSiguiente: () => void;
  onAtras: () => void;
  onSaltar: () => void;
  onPausar: () => void;
  onVolver: () => void;
  onAccion: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [alto, setAlto] = useState(180);
  const [vista, setVista] = useState({ w: 1280, h: 800 });

  useLayoutEffect(() => {
    const nodo = ref.current;
    if (!nodo) return;
    const medir = () => {
      setAlto(nodo.offsetHeight);
      setVista({ w: window.innerWidth, h: window.innerHeight });
    };
    const observador = new ResizeObserver(medir);
    observador.observe(nodo);
    window.addEventListener("resize", medir);
    return () => {
      observador.disconnect();
      window.removeEventListener("resize", medir);
    };
  }, []);

  const hoja = vista.w < 768;
  const lugar = colocarTarjeta(
    fueraDeRuta || anclaPerdida ? null : rect,
    { w: ANCHO, h: alto },
    vista,
  );
  const transferencia = paso === null;
  const total = capitulo.pasos.length;
  const hacerVivo = paso?.tipo === "hacer" && !repaso;

  let titulo = paso?.titulo ?? "En tu obra";
  let cuerpo = paso?.cuerpo ?? capitulo.transferencia;
  if (fueraDeRuta) {
    titulo = "Saliste del recorrido";
    cuerpo = "Sigue explorando con calma; cuando quieras, vuelve al paso donde ibas.";
  } else if (anclaPerdida) {
    cuerpo = `No encuentro esto en esta pantalla. ${paso?.cuerpo ?? ""}`;
  }

  return (
    <div
      ref={ref}
      role="dialog"
      aria-modal="false"
      aria-live="polite"
      aria-label={`Recorrido: ${capitulo.titulo}`}
      data-recorrido-tarjeta=""
      className={`toast-in fixed z-[71] border border-border bg-surface p-4 shadow-lg ${
        hoja ? "inset-x-0 bottom-0 rounded-t-2xl" : "rounded-xl"
      }`}
      style={hoja ? undefined : { top: lugar.top, left: lugar.left, width: ANCHO }}
    >
      <div className="microlabel mb-1.5">
        {capitulo.titulo} · {transferencia ? "para tu obra" : `${indice + 1} de ${total}`}
      </div>
      <div className="font-medium">{titulo}</div>
      <p className="mt-1 text-sm leading-relaxed text-muted">{cuerpo}</p>
      {hacerVivo && !fueraDeRuta && (
        <p className="mt-2 text-xs text-faint">Hazlo en la pantalla: el recorrido sigue solo.</p>
      )}
      {repaso && paso?.tipo === "hacer" && (
        <p className="mt-2 text-xs text-faint">Ya lo hiciste en tu obra de ejemplo.</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {fueraDeRuta ? (
          <Button variant="primary" size="sm" onClick={onVolver}>
            Volver al recorrido
          </Button>
        ) : (
          <>
            {paso?.accion && !repaso && (
              <Button variant="primary" size="sm" onClick={onAccion} disabled={ocupada}>
                {ocupada
                  ? "Preparando…"
                  : paso.accion === "crear_obra"
                    ? "Crear mi obra de ejemplo"
                    : "Cargar la Rev B de ejemplo"}
              </Button>
            )}
            {(transferencia || paso?.tipo === "mirar" || repaso) && (
              <Button variant="primary" size="sm" onClick={onSiguiente}>
                {transferencia
                  ? esUltimoCapitulo
                    ? "Terminar"
                    : "Siguiente capítulo"
                  : "Siguiente"}
                <ArrowRight size={14} weight="bold" />
              </Button>
            )}
            {hacerVivo && (
              <Button variant="ghost" size="sm" onClick={onSaltar}>
                Saltar este paso
              </Button>
            )}
          </>
        )}
        <span className="ml-auto flex items-center gap-1">
          {indice > 0 && !fueraDeRuta && (
            <Button variant="ghost" size="sm" onClick={onAtras} aria-label="Paso anterior">
              <ArrowLeft size={14} weight="bold" />
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onPausar} aria-label="Pausar el recorrido">
            <Pause size={14} weight="bold" />
          </Button>
        </span>
      </div>
    </div>
  );
}
