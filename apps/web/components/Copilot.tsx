"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import {
  ArrowUp,
  CaretDown,
  CheckCircle,
  CircleNotch,
  Lightning,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";
import {
  apiMessage,
  askCopilot,
  copilotStatus,
  getAcciones,
  getDiagnostico,
  type CopilotAccion,
  type CopilotCita,
  type Diagnostico,
} from "@/lib/api";
import { AccionDeKlave } from "@/components/Diagnostico";

/**
 * El copiloto: un panel que acompaña el trabajo, no una ventana que lo tapa.
 *
 * Tres decisiones de forma, y las tres salen de para qué sirve:
 *
 * · **Chico y anclado.** Vive sobre su botón, en una esquina, sin oscurecer la
 *   pantalla. Quien pregunta por el presupuesto necesita seguir viendo el
 *   presupuesto; un cajón de pantalla completa obliga a cerrarlo para mirar
 *   aquello de lo que se está hablando.
 * · **Abre con lo que puede resolver.** Un chat abre con un cuadro en blanco y
 *   espera. Esto abre con el estado de la obra y las acciones que cierran sus
 *   hallazgos; preguntar es la segunda opción.
 * · **Denso, no ruidoso.** Una línea por acción, la explicación al desplegarla.
 */

type Turno = {
  pregunta: string;
  texto?: string;
  citas?: CopilotCita[];
  fundamentada?: boolean;
  aviso?: string;
  conContexto?: boolean;
  error?: string;
};

/** Preguntas que dependen de dónde está parado el usuario: las genéricas
 * llenan un hueco, las de la pantalla sirven para trabajar. */
function sugerencias(pathname: string, hayProyecto: boolean): string[] {
  if (pathname.includes("/programa")) {
    return [
      "¿Por qué casi todo es ruta crítica?",
      "¿Días naturales o hábiles?",
      "¿Qué programas pide una licitación?",
    ];
  }
  if (pathname.includes("/presupuesto") || pathname.includes("/apus")) {
    return [
      "¿Por qué no puedo entregarlo?",
      "¿Por qué hay conceptos «sin precio»?",
      "¿Cómo adopto un precio de mi catálogo?",
    ];
  }
  if (pathname.includes("/revision") || pathname.includes("/lectura")) {
    return [
      "¿Qué significa SIN VERIFICAR?",
      "¿Qué puede y qué no la lectura con IA?",
      "¿Por qué revisar solo un lote?",
    ];
  }
  if (pathname.includes("/flujo") || pathname.includes("/parametros")) {
    return [
      "¿Cuánto anticipo puedo pedir?",
      "¿Cómo se amortiza el anticipo?",
      "¿Cada cuándo se estima?",
    ];
  }
  return hayProyecto
    ? ["¿Por qué no puedo entregarlo?", "¿Qué me falta para cerrar esta obra?"]
    : ["¿Qué programas pide una licitación?", "¿Cuánto anticipo puedo pedir?"];
}

export function Copilot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const params = useParams<{ id?: string }>();
  const pathname = usePathname() ?? "";
  const projectId = typeof params?.id === "string" ? params.id : undefined;
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [pensando, setPensando] = useState(false);
  const [disponible, setDisponible] = useState<boolean | null>(null);
  const [acciones, setAcciones] = useState<CopilotAccion[]>([]);
  const [diagnostico, setDiagnostico] = useState<Diagnostico | null>(null);
  const panelRef = useRef<HTMLElement>(null);
  const finalRef = useRef<HTMLDivElement>(null);

  const cargarObra = useCallback(() => {
    if (!projectId) return;
    getAcciones(projectId)
      .then((r) => setAcciones(r.acciones))
      .catch(() => setAcciones([]));
    getDiagnostico(projectId)
      .then(setDiagnostico)
      .catch(() => setDiagnostico(null));
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    copilotStatus()
      .then((s) => setDisponible(s.available))
      .catch(() => setDisponible(false));
    cargarObra();
  }, [open, cargarObra]);

  useEffect(() => {
    if (turnos.length > 0 || pensando) {
      finalRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [turnos, pensando]);

  // Cerrar con Escape o al hacer clic fuera — sin oscurecer nada: el panel
  // acompaña el trabajo, no lo interrumpe.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    function onDown(e: PointerEvent) {
      const destino = e.target as Node;
      if (panelRef.current?.contains(destino)) return;
      if ((destino as HTMLElement).closest?.("[data-copiloto-boton]")) return;
      onClose();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onDown);
    };
  }, [open, onClose]);

  async function preguntar(pregunta: string) {
    const limpia = pregunta.trim();
    if (!limpia || pensando) return;
    setTexto("");
    setTurnos((t) => [...t, { pregunta: limpia }]);
    setPensando(true);
    try {
      const r = await askCopilot(limpia, projectId);
      setTurnos((t) =>
        t.map((turno, i) =>
          i === t.length - 1
            ? {
                ...turno,
                texto: r.texto,
                citas: r.citas,
                fundamentada: r.fundamentada,
                aviso: r.aviso,
                conContexto: r.con_contexto,
              }
            : turno,
        ),
      );
    } catch (e) {
      const mensaje = apiMessage(e, "No se pudo preguntar. ¿Está activo el servidor?");
      setTurnos((t) =>
        t.map((turno, i) => (i === t.length - 1 ? { ...turno, error: mensaje } : turno)),
      );
    } finally {
      setPensando(false);
    }
  }

  if (!open) return null;

  const aplicables = acciones.filter((a) => a.aplicable);
  const pendientes = acciones.filter((a) => !a.aplicable);

  return (
    <aside
      ref={panelRef}
      className="toast-in fixed bottom-20 right-5 z-[60] flex max-h-[min(70vh,32rem)] w-[min(23rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
      role="dialog"
      aria-label="Copiloto de Klave"
    >
      <header className="flex items-center gap-2.5 border-b border-border px-3 py-2.5">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <Sparkle size={15} weight="duotone" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold leading-tight">Klave</div>
          {diagnostico?.resumen && (
            <p className="truncate text-[11px] leading-tight text-muted">
              {diagnostico.resumen}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="shrink-0 rounded-md p-1 text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <X size={14} />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2.5">
        {disponible === false && (
          <p className="mb-2 rounded-lg bg-warning-soft px-2.5 py-1.5 text-[12px] leading-snug text-warning">
            Preguntar necesita credenciales de IA. Las acciones de abajo no usan IA y
            siguen funcionando.
          </p>
        )}

        {projectId && (aplicables.length > 0 || pendientes.length > 0) && (
          <section className="mb-3">
            <h3 className="mb-1.5 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
              <Lightning size={11} weight="fill" className="text-accent" />
              Puedo hacer
            </h3>
            <div className="space-y-1.5">
              {aplicables.map((accion) => (
                <AccionCompacta
                  key={`${accion.tipo}-${accion.hallazgo_id}`}
                  accion={accion}
                  projectId={projectId}
                  onApplied={cargarObra}
                />
              ))}
              {pendientes.map((accion) => (
                <details
                  key={`${accion.tipo}-${accion.hallazgo_id}`}
                  className="rounded-lg border border-border/70 px-2.5 py-1.5"
                >
                  <summary className="cursor-pointer list-none text-[13px] leading-snug text-muted marker:hidden">
                    {accion.titulo}{" "}
                    <span className="text-[11px] text-faint">· necesito un dato</span>
                  </summary>
                  <p className="mt-1 text-[12px] leading-snug text-muted">{accion.requiere}</p>
                </details>
              ))}
            </div>
          </section>
        )}

        {projectId && aplicables.length === 0 && pendientes.length === 0 && turnos.length === 0 && (
          <p className="mb-3 flex items-start gap-1.5 text-[13px] leading-snug text-muted">
            <CheckCircle size={14} weight="fill" className="mt-px shrink-0 text-success" />
            Nada que yo pueda resolver solo por ahora.
          </p>
        )}

        {turnos.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {sugerencias(pathname, Boolean(projectId)).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void preguntar(s)}
                className="rounded-full border border-border px-2.5 py-1 text-[12px] leading-tight text-muted transition-colors hover:bg-surface-2 hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="space-y-2.5">
          {turnos.map((turno, i) => (
            <div key={i}>
              <p className="flex justify-end">
                <span className="max-w-[85%] rounded-2xl rounded-br-md bg-surface-2 px-3 py-1.5 text-[13px] leading-snug">
                  {turno.pregunta}
                </span>
              </p>
              {turno.error && (
                <p className="mt-1 text-[13px] text-danger">{turno.error}</p>
              )}
              {turno.texto && (
                <div className="mt-1">
                  {turno.fundamentada === false && (
                    <p className="mb-1 flex items-start gap-1 text-[11px] leading-snug text-warning">
                      <Warning size={11} weight="bold" className="mt-0.5 shrink-0" />
                      Sin buen respaldo en mis fuentes: tómalo como pista.
                    </p>
                  )}
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed">
                    {turno.texto}
                  </p>
                  {turno.aviso && (
                    <p className="mt-1.5 rounded-md bg-surface-2/70 px-2 py-1 text-[11px] leading-snug text-muted">
                      {turno.aviso}
                    </p>
                  )}
                  {turno.citas && turno.citas.length > 0 && <Fuentes citas={turno.citas} />}
                </div>
              )}
            </div>
          ))}
          {pensando && (
            <p className="flex items-center gap-1.5 text-[13px] text-muted">
              <CircleNotch size={13} className="animate-spin" /> Buscando…
            </p>
          )}
        </div>
        <div ref={finalRef} />
      </div>

      <form
        className="border-t border-border p-2"
        onSubmit={(e) => {
          e.preventDefault();
          void preguntar(texto);
        }}
      >
        <div className="flex items-center gap-1.5 rounded-full border border-border bg-surface py-1 pl-3.5 pr-1 transition focus-within:border-border-strong focus-within:ring-2 focus-within:ring-ring">
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={500}
            placeholder="Pregúntale a Klave…"
            className="min-w-0 flex-1 bg-transparent text-[13px] outline-none"
          />
          <button
            type="submit"
            disabled={pensando || !texto.trim()}
            aria-label="Preguntar"
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-primary-fg transition disabled:opacity-40"
          >
            <ArrowUp size={13} weight="bold" />
          </button>
        </div>
      </form>
    </aside>
  );
}

/** Una acción por renglón; el detalle y la vista previa al desplegar. */
function AccionCompacta({
  accion,
  projectId,
  onApplied,
}: {
  accion: CopilotAccion;
  projectId: string;
  onApplied: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  return (
    <div className="rounded-lg border border-accent/30 bg-accent-soft/40">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-start gap-1.5 px-2.5 py-1.5 text-left"
      >
        <Lightning size={12} weight="fill" className="mt-1 shrink-0 text-accent" />
        <span className="min-w-0 flex-1 text-[13px] font-medium leading-snug">
          {accion.titulo}
        </span>
        <CaretDown
          size={12}
          weight="bold"
          className={`mt-1 shrink-0 text-faint ${abierto ? "rotate-180" : ""}`}
        />
      </button>
      {abierto && (
        <div className="px-2.5 pb-2">
          <AccionDeKlave accion={accion} projectId={projectId} onApplied={onApplied} />
        </div>
      )}
    </div>
  );
}

function Fuentes({ citas }: { citas: CopilotCita[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[11px] text-muted hover:text-foreground"
        aria-expanded={open}
      >
        {open ? "Ocultar fuentes" : `${citas.length} fuente${citas.length === 1 ? "" : "s"}`}
      </button>
      {open && (
        <ul className="mt-1 space-y-0.5">
          {citas.map((c) => (
            <li key={`${c.fuente}-${c.titulo}`} className="text-[11px] leading-snug">
              {c.url ? (
                <a
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline"
                >
                  {c.fuente}
                </a>
              ) : (
                <span className="text-muted">{c.fuente}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
