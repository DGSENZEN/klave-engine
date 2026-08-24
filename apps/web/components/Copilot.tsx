"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, usePathname } from "next/navigation";
import {
  ArrowUp,
  BookOpen,
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
import { buttonClasses } from "@/components/ui";

/**
 * El copiloto de Klave: una herramienta del taller, no una ventana de chat.
 *
 * La diferencia está en qué aparece primero. Un chat abre con un campo vacío
 * y espera; esto abre con **el estado de la obra y lo que puede resolver hoy**,
 * porque eso es lo que el ingeniero vino a hacer. Preguntar es la segunda
 * opción, no la principal.
 *
 * Lo demás sigue las mismas reglas que el resto de la aplicación: cada
 * respuesta trae las fuentes que la sostienen; cuando el servidor no puede
 * respaldarla lo dice en vez de sonar igual de seguro; y nada se aplica sin
 * que alguien vea antes qué cambia.
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
 * sirven para llenar un hueco, las de la pantalla sirven para trabajar. */
function sugerencias(pathname: string, hayProyecto: boolean): string[] {
  if (pathname.includes("/programa")) {
    return [
      "¿Por qué casi todo mi programa es ruta crítica?",
      "¿El plazo va en días naturales o hábiles?",
      "¿Qué programas debo entregar en una licitación?",
    ];
  }
  if (pathname.includes("/presupuesto") || pathname.includes("/apus")) {
    return [
      "¿Por qué no puedo entregar este presupuesto?",
      "¿Por qué hay conceptos «sin precio» en vez de en cero?",
      "¿Cómo adopto un precio de mi catálogo?",
    ];
  }
  if (pathname.includes("/revision") || pathname.includes("/lectura")) {
    return [
      "¿Qué significa el sello SIN VERIFICAR?",
      "¿Qué puede y qué no puede hacer la lectura con IA?",
      "¿Por qué me propone revisar solo un lote?",
    ];
  }
  if (pathname.includes("/flujo") || pathname.includes("/parametros")) {
    return [
      "¿Cuánto anticipo puedo pedir?",
      "¿Cómo se amortiza el anticipo?",
      "¿Cada cuándo se estiman los trabajos?",
    ];
  }
  return hayProyecto
    ? [
        "¿Por qué no puedo entregar este presupuesto?",
        "¿Qué me falta para cerrar esta obra?",
        "¿Cuánto anticipo puedo pedir?",
      ]
    : [
        "¿Qué programas necesito para entregar una licitación?",
        "¿Cuánto anticipo puedo pedir?",
        "¿El plazo va en días naturales o hábiles?",
      ];
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
  const finalRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  const aplicables = acciones.filter((a) => a.aplicable);
  const pendientes = acciones.filter((a) => !a.aplicable);

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
        <header className="flex items-start gap-2 border-b border-border px-4 py-3">
          <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
            <Sparkle size={16} weight="duotone" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium">Klave</div>
            <p className="text-xs leading-snug text-muted">
              {diagnostico?.resumen ??
                (projectId
                  ? "Cargando el estado de esta obra…"
                  : "Normativa de obra y cómo funciona la aplicación.")}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="shrink-0 rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {disponible === false && (
            <p className="mb-3 rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
              Preguntar necesita credenciales de IA en el servidor. Sin ellas no responde
              — no inventa. Lo que Klave puede <em>hacer</em> aquí abajo no usa IA y sigue
              funcionando.
            </p>
          )}

          {/* Lo primero es lo que puede resolver, no un campo en blanco. */}
          {projectId && (
            <section className="mb-5">
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                <Lightning size={13} weight="fill" className="text-accent" />
                Lo que puedo hacer por esta obra
              </h3>
              {aplicables.length === 0 && pendientes.length === 0 ? (
                <p className="flex items-start gap-2 text-sm text-muted">
                  <CheckCircle size={15} weight="fill" className="mt-0.5 shrink-0 text-success" />
                  Nada pendiente que yo pueda resolver solo. Si algo te falta, pregúntame
                  abajo.
                </p>
              ) : (
                <div className="space-y-3">
                  {aplicables.map((accion) => (
                    <div
                      key={`${accion.tipo}-${accion.hallazgo_id}`}
                      className="rounded-lg border border-border bg-surface-2/40 p-3"
                    >
                      <div className="text-sm font-medium">{accion.titulo}</div>
                      <AccionDeKlave
                        accion={accion}
                        projectId={projectId}
                        onApplied={cargarObra}
                      />
                    </div>
                  ))}
                  {pendientes.map((accion) => (
                    <div
                      key={`${accion.tipo}-${accion.hallazgo_id}`}
                      className="rounded-lg border border-border/70 p-3"
                    >
                      <div className="text-sm font-medium">{accion.titulo}</div>
                      <p className="mt-0.5 text-sm text-muted">
                        <span className="font-medium text-foreground">Necesito un dato: </span>
                        {accion.requiere}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {turnos.length === 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                O pregúntame
              </h3>
              <div className="flex flex-col items-start gap-1.5">
                {sugerencias(pathname, Boolean(projectId)).map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void preguntar(s)}
                    className="rounded-lg border border-border px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-surface-2"
                  >
                    {s}
                  </button>
                ))}
              </div>
              <p className="mt-2.5 text-xs text-faint">
                Respondo con la normativa que tengo cargada y con la documentación de
                Klave, citando de dónde sale cada cosa. Lo que no puedo respaldar, te lo
                digo en lugar de inventarlo.
              </p>
            </section>
          )}

          <div className="space-y-4">
            {turnos.map((turno, i) => (
              <div key={i} className="border-t border-border/60 pt-3 first:border-t-0">
                <p className="text-xs font-medium uppercase tracking-wide text-faint">
                  {turno.pregunta}
                </p>
                {turno.error && <p className="mt-2 text-sm text-danger">{turno.error}</p>}
                {turno.texto && (
                  <div className="mt-1.5">
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
              placeholder="Pregunta sobre la obra, la normativa o la app…"
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
