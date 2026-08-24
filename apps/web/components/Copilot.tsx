"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowUp, BookOpen, CircleNotch, Sparkle, Warning, X } from "@phosphor-icons/react";
import { apiMessage, askCopilot, copilotStatus, type CopilotCita } from "@/lib/api";
import { buttonClasses } from "@/components/ui";

/**
 * Pregúntale a Klave: la normativa, la aplicación, y este proyecto.
 *
 * Dos decisiones que lo separan de un chat cualquiera:
 *
 * · Cada respuesta llega con las fuentes que la sustentan, y cuando el
 *   servidor no puede respaldarla lo dice en la propia burbuja en vez de
 *   sonar igual de segura. Un copiloto de costos que inventa un artículo le
 *   cuesta a alguien una licitación.
 * · Sabe en qué proyecto estás. Las preguntas sobre la obra abierta se
 *   responden con sus hallazgos de este momento, no con lo que se dijo antes
 *   en la conversación.
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

const SUGERENCIAS = [
  "¿Qué programas necesito para entregar una licitación?",
  "¿Por qué mi presupuesto no se puede entregar?",
  "¿Cuánto anticipo puedo pedir?",
  "¿El plazo va en días naturales o hábiles?",
];

export function Copilot({ open, onClose }: { open: boolean; onClose: () => void }) {
  const params = useParams<{ id?: string }>();
  const projectId = typeof params?.id === "string" ? params.id : undefined;
  const [turnos, setTurnos] = useState<Turno[]>([]);
  const [texto, setTexto] = useState("");
  const [pensando, setPensando] = useState(false);
  const [disponible, setDisponible] = useState<boolean | null>(null);
  const finalRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    copilotStatus()
      .then((s) => setDisponible(s.available))
      .catch(() => setDisponible(false));
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    finalRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turnos, pensando]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
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

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-background/50 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className="fixed right-0 top-0 z-50 flex h-full w-full max-w-lg flex-col border-l border-border bg-surface shadow-2xl"
        role="dialog"
        aria-label="Copiloto de Klave"
      >
        <header className="flex items-center gap-2 border-b border-border px-4 py-3">
          <Sparkle size={17} weight="duotone" className="text-accent" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">Pregúntale a Klave</div>
            <p className="text-xs text-muted">
              Normativa de obra, cómo funciona la app, y esta obra
              {projectId ? " en particular" : ""}.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {disponible === false && (
            <p className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
              El copiloto necesita credenciales de IA en el servidor. Sin ellas no
              responde — no inventa.
            </p>
          )}
          {turnos.length === 0 && (
            <div>
              <p className="text-sm text-muted">
                Respondo con la normativa que tengo cargada y con la documentación de
                Klave, citando de dónde sale cada cosa. Lo que no puedo respaldar, te lo
                digo en lugar de inventarlo.
              </p>
              <div className="mt-3 flex flex-col items-start gap-1.5">
                {SUGERENCIAS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void preguntar(s)}
                    className="text-left text-sm text-accent hover:underline"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-4">
            {turnos.map((turno, i) => (
              <div key={i}>
                <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-surface-3 px-3 py-2 text-sm">
                  {turno.pregunta}
                </p>
                {turno.error && (
                  <p className="mt-2 text-sm text-danger">{turno.error}</p>
                )}
                {turno.texto && (
                  <div className="mt-2">
                    {turno.fundamentada === false && (
                      <p className="mb-1.5 flex items-start gap-1.5 text-xs text-warning">
                        <Warning size={13} weight="bold" className="mt-0.5 shrink-0" />
                        Esto no quedó bien respaldado por mis fuentes: tómalo como una
                        pista, no como una respuesta.
                      </p>
                    )}
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {turno.texto}
                    </p>
                    {turno.conContexto && (
                      <p className="mt-1 text-xs text-faint">
                        Respondido con los hallazgos actuales de esta obra.
                      </p>
                    )}
                    {turno.aviso && (
                      <p className="mt-2 rounded-lg bg-surface-2/70 px-2.5 py-1.5 text-xs text-muted">
                        {turno.aviso}
                      </p>
                    )}
                    {turno.citas && turno.citas.length > 0 && (
                      <Fuentes citas={turno.citas} />
                    )}
                  </div>
                )}
              </div>
            ))}
            {pensando && (
              <p className="flex items-center gap-2 text-sm text-muted">
                <CircleNotch size={14} className="animate-spin" /> Buscando en la
                normativa…
              </p>
            )}
          </div>
          <div ref={finalRef} />
        </div>

        <form
          className="border-t border-border p-3"
          onSubmit={(e) => {
            e.preventDefault();
            void preguntar(texto);
          }}
        >
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void preguntar(texto);
                }
              }}
              rows={2}
              maxLength={500}
              placeholder="¿Qué necesitas saber?"
              className="max-h-32 min-h-[42px] flex-1 resize-y rounded-lg border border-border bg-surface px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={pensando || !texto.trim()}
              className={`${buttonClasses("primary", "sm")} h-[42px] shrink-0`}
              aria-label="Preguntar"
            >
              <ArrowUp size={15} weight="bold" />
            </button>
          </div>
        </form>
      </aside>
    </>
  );
}

function Fuentes({ citas }: { citas: CopilotCita[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs text-muted hover:text-foreground"
        aria-expanded={open}
      >
        <BookOpen size={13} />
        {open ? "Ocultar fuentes" : `Fuentes (${citas.length})`}
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1">
          {citas.map((c) => (
            <li key={`${c.fuente}-${c.titulo}`} className="text-xs">
              <span className="text-foreground">{c.titulo}</span>{" "}
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
              {c.vigencia && <span className="text-faint"> · {c.vigencia}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
