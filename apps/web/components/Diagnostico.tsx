"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CaretDown,
  CheckCircle,
  CircleNotch,
  Info,
  Prohibit,
  Sparkle,
  Warning,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  apiMessage,
  aplicarAccion,
  type CopilotAccion,
  type Diagnostico,
  type Hallazgo,
  type Severity,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { Card, buttonClasses } from "@/components/ui";

/**
 * What is wrong with this presupuesto, ranked by what it costs.
 *
 * Three rules this component exists to enforce:
 *  · Severity is never carried by colour alone — every tier states its own
 *    name and shows its own icon, so it survives a colour-blind reader, a
 *    printout and a glance.
 *  · A finding shows its stake next to it (pesos when the engine can derive
 *    them, the physical quantity when it honestly cannot) — the reader must
 *    never open something else to learn whether a warning matters.
 *  · A finding that can be acted on carries the route to act on it, so the
 *    answer to "y ahora qué" is one click, not a hunt through the nav.
 */

const TIERS: Record<
  Severity,
  {
    label: string;
    /** Spanish plurals are irregular enough to spell out, not append "s" to. */
    count: (n: number) => string;
    sub: string;
    icon: React.ReactNode;
    box: string;
    text: string;
  }
> = {
  bloqueante: {
    label: "Bloqueante",
    count: (n) => `${n} bloqueante${n === 1 ? "" : "s"}`,
    sub: "entregarlo así estaría mal",
    icon: <Prohibit size={15} weight="bold" />,
    box: "border-danger/35 bg-danger-soft",
    text: "text-danger",
  },
  dinero: {
    label: "Dinero faltante",
    count: (n) => `${n} con dinero faltante`,
    sub: "hay cantidad sin costo: el total va corto",
    icon: <WarningCircle size={15} weight="bold" />,
    box: "border-warning/40 bg-warning-soft",
    text: "text-warning",
  },
  revisar: {
    label: "Por revisar",
    count: (n) => `${n} por revisar`,
    sub: "falta una decisión tuya; el número se sostiene sin ella",
    icon: <Warning size={15} weight="bold" />,
    box: "border-border bg-surface-2/60",
    text: "text-foreground",
  },
};

const ORDER: Severity[] = ["bloqueante", "dinero", "revisar"];

/** When fixing it stops being cheap — the estimating analogue of an alarm's
 * time-to-respond, and what lets someone triage without reading everything. */
const MOMENTO: Record<Hallazgo["momento"], string> = {
  entregar: "antes de entregar",
  cotizar: "antes de cotizar",
  contratar: "antes de contratar",
  sin_urgencia: "sin urgencia",
};

function money(value: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 0,
  }).format(value);
}

/** A finding's route, resolved: bare names hang off the project, a leading
 * slash is a workspace route, "" is the project's Resumen. */
function href(target: string | null, projectId: string): string | null {
  if (target === null) return null;
  if (target.startsWith("/")) return target;
  return target ? `/proyecto/${projectId}/${target}` : `/proyecto/${projectId}`;
}

function HallazgoRow({
  hallazgo,
  projectId,
  accion,
  onApplied,
}: {
  hallazgo: Hallazgo;
  projectId: string;
  accion?: CopilotAccion;
  onApplied?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const tier = TIERS[hallazgo.severity];
  const link = href(hallazgo.target, projectId);
  const stake =
    hallazgo.monto_afectado != null
      ? money(hallazgo.monto_afectado)
      : hallazgo.exposicion ?? null;

  return (
    <li className="border-t border-border/60 first:border-t-0">
      <div className="flex items-start gap-3 px-4 py-3">
        <span className={`mt-0.5 shrink-0 ${tier.text}`}>{tier.icon}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="text-sm font-medium">{hallazgo.title}</span>
            <span className="text-xs text-faint">{MOMENTO[hallazgo.momento]}</span>
            {stake && (
              <span
                className={`tabular rounded px-1.5 py-0.5 text-xs font-semibold ${tier.text} bg-surface-3/70`}
                title={
                  hallazgo.monto_afectado != null
                    ? "Dinero ya contado que depende de esto"
                    : "Cantidad en juego; su costo no se puede saber desde aquí"
                }
              >
                {stake}
              </span>
            )}
          </div>
          {hallazgo.detail && (
            <>
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
                aria-expanded={open}
              >
                {open ? "Menos" : "Por qué importa"}
                <CaretDown size={11} weight="bold" className={open ? "rotate-180" : ""} />
              </button>
              {open && (
                <p className="mt-1 text-sm leading-relaxed text-muted">{hallazgo.detail}</p>
              )}
            </>
          )}
          {hallazgo.verificar && (
            <p className="mt-1 text-sm text-muted">
              <span className="font-medium text-foreground">Cómo comprobarlo: </span>
              {hallazgo.verificar}
            </p>
          )}
          {hallazgo.action && (
            <p className="mt-1 text-sm text-muted">
              <span className="font-medium text-foreground">Qué hacer: </span>
              {hallazgo.action}
            </p>
          )}
          {accion && (
            <AccionDeKlave accion={accion} projectId={projectId} onApplied={onApplied} />
          )}
        </div>
        {link && (
          <Link href={link} className={`${buttonClasses("ghost", "sm")} shrink-0`}>
            Ir <ArrowRight size={13} weight="bold" />
          </Link>
        )}
      </div>
    </li>
  );
}


/**
 * Lo que Klave puede hacer con este hallazgo, y qué cambiaría si lo hace.
 *
 * El cambio se ve antes de aceptarlo, con su procedencia: la evidencia sobre
 * decisiones asistidas por máquina dice que un valor ya puesto ancla a quien
 * decide, así que aquí no se pone nada hasta que alguien lo acepta. Y cuando
 * el motor no puede saber el dato — cuánto cuesta un concepto sin fuente — no
 * hay botón, hay una frase diciendo qué falta.
 */
export function AccionDeKlave({
  accion,
  projectId,
  onApplied,
}: {
  accion: CopilotAccion;
  projectId: string;
  onApplied?: () => void;
}) {
  const [abierto, setAbierto] = useState(false);
  const [aplicando, setAplicando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hecho, setHecho] = useState<{ antes: number | null; despues: number } | null>(null);

  if (hecho) {
    return (
      <p className="mt-1.5 flex items-center gap-1.5 text-sm text-success">
        <CheckCircle size={14} weight="fill" className="shrink-0" />
        Hecho. El total pasó de {hecho.antes != null ? money(hecho.antes) : "—"} a{" "}
        {money(hecho.despues)}.
      </p>
    );
  }

  if (!accion.aplicable) {
    return (
      <p className="mt-1.5 text-sm text-muted">
        <span className="font-medium text-foreground">Klave no puede hacerlo solo: </span>
        {accion.requiere}
      </p>
    );
  }

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className={buttonClasses("secondary", "sm")}
      >
        <Sparkle size={14} weight="duotone" /> Que Klave lo haga
      </button>
      {abierto && (
        <div className="mt-2 rounded-lg border border-border bg-surface-2/50 p-3">
          <p className="text-sm text-muted">{accion.descripcion}</p>
          {accion.vista_previa.length > 0 && (
            <ul className="mt-2 space-y-1">
              {accion.vista_previa.map((c) => (
                <li key={c.concepto} className="flex flex-wrap items-baseline gap-1.5 text-sm">
                  <span className="font-mono text-xs">{c.concepto}</span>
                  <span className="text-muted line-through">{c.de}</span>
                  <span aria-hidden className="text-faint">→</span>
                  <span className="font-medium">{c.a}</span>
                </li>
              ))}
            </ul>
          )}
          {accion.reversible && (
            <p className="mt-2 text-xs text-faint">{accion.reversible}</p>
          )}
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
          <div className="mt-2.5 flex gap-2">
            <button
              type="button"
              disabled={aplicando}
              className={buttonClasses("primary", "sm")}
              onClick={async () => {
                setAplicando(true);
                setError(null);
                try {
                  const r = await aplicarAccion(
                    projectId,
                    accion.tipo,
                    accion.hallazgo_id,
                    getBrowserActor(),
                  );
                  setHecho({ antes: r.total_antes, despues: r.total_despues });
                  onApplied?.();
                } catch (e) {
                  setError(apiMessage(e, "No se pudo aplicar."));
                } finally {
                  setAplicando(false);
                }
              }}
            >
              {aplicando ? (
                <>
                  <CircleNotch size={14} className="animate-spin" /> Aplicando…
                </>
              ) : (
                "Aplicar y recalcular"
              )}
            </button>
            <button
              type="button"
              onClick={() => setAbierto(false)}
              className={buttonClasses("ghost", "sm")}
            >
              Ahora no
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The full panel: the honest headline, then every finding by consequence. */
export function DiagnosticoPanel({
  diagnostico,
  projectId,
  acciones = [],
  onApplied,
}: {
  diagnostico: Diagnostico;
  projectId: string;
  /** What Klave can do about each finding, derived from the same diagnosis. */
  acciones?: CopilotAccion[];
  onApplied?: () => void;
}) {
  const groups = ORDER.map((severity) => ({
    severity,
    items: diagnostico.hallazgos.filter((h) => h.severity === severity),
  })).filter((g) => g.items.length > 0);

  if (groups.length === 0) {
    return (
      <Card className="mb-5 p-4">
        <div className="flex items-center gap-2.5">
          <CheckCircle size={18} weight="fill" className="shrink-0 text-success" />
          <div>
            <div className="text-sm font-medium">Sin hallazgos abiertos</div>
            <p className="text-sm text-muted">{diagnostico.resumen}</p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <section className="mb-5" aria-label="Estado del presupuesto">
      <Card className="overflow-hidden p-0">
        <div className="border-b border-border px-4 py-3">
          <p className="text-[15px] font-medium leading-snug">{diagnostico.resumen}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {groups.map(({ severity, items }) => (
              <span
                key={severity}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${TIERS[severity].box} ${TIERS[severity].text}`}
                title={TIERS[severity].sub}
              >
                {TIERS[severity].icon}
                {TIERS[severity].count(items.length)}
              </span>
            ))}
          </div>
        </div>
        {groups.map(({ severity, items }) => (
          <TierGroup
            key={severity}
            severity={severity}
            items={items}
            projectId={projectId}
            acciones={acciones}
            onApplied={onApplied}
            // Only the tiers that change what you may deliver open by default;
            // the rest stay one click away so the page keeps its shape.
            defaultOpen={severity === "bloqueante" || severity === "dinero"}
          />
        ))}
        <Criterios items={diagnostico.criterios} />
      </Card>
    </section>
  );
}

function TierGroup({
  severity,
  items,
  projectId,
  defaultOpen,
  acciones,
  onApplied,
}: {
  severity: Severity;
  items: Hallazgo[];
  projectId: string;
  defaultOpen: boolean;
  acciones: CopilotAccion[];
  onApplied?: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const tier = TIERS[severity];
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-surface-2/50"
      >
        <span className={tier.text}>{tier.icon}</span>
        <span className="text-xs font-semibold uppercase tracking-wide">{tier.label}</span>
        <span className="text-xs text-muted">· {tier.sub}</span>
        <span className="tabular ml-auto text-xs text-faint">{items.length}</span>
        <CaretDown
          size={12}
          weight="bold"
          className={`text-faint ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <ul>
          {items.map((h) => (
            <HallazgoRow
              key={h.id}
              hallazgo={h}
              projectId={projectId}
              accion={acciones.find((a) => a.hallazgo_id === h.id)}
              onApplied={onApplied}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The engine's declared choices. Not alarms — nothing here asks anything of
 * the reader — but exactly what defends a number under scrutiny months from
 * now, so they are recorded beside the findings instead of inside them.
 */
function Criterios({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="border-t border-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-2 text-left transition-colors hover:bg-surface-2/50"
      >
        <Info size={15} weight="bold" className="text-faint" />
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">
          Criterios adoptados
        </span>
        <span className="text-xs text-muted">· lo que el motor decidió, y por qué</span>
        <span className="tabular ml-auto text-xs text-faint">{items.length}</span>
        <CaretDown size={12} weight="bold" className={`text-faint ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul className="space-y-1.5 px-4 pb-3">
          {items.map((c) => (
            <li key={c} className="flex gap-2 text-sm text-muted">
              <span className="text-faint">·</span>
              <span>{c}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The way past a blocking finding — a written reason, not a dismissed banner.
 *
 * A red notice beside a working download button is clicked through: the
 * browser-warning field studies put that at around 70% of the time. So the
 * file stops here, and the only way to it is to say why in writing. What
 * gets typed is stamped into the workbook's carátula, so the person who
 * receives the file learns it from the file rather than from whoever sent it.
 */
export function ExportBlockedDialog({
  label,
  message,
  bloqueantes,
  onCancel,
  onConfirm,
}: {
  label: string;
  message: string;
  bloqueantes: string[];
  onCancel: () => void;
  onConfirm: (motivo: string) => void;
}) {
  const [motivo, setMotivo] = useState("");
  const enough = motivo.trim().length >= 15;
  return (
    <div className="mb-5">
      <Card className="border-danger/40 p-5">
        <div className="mb-2 flex items-center gap-2">
          <Prohibit size={17} weight="bold" className="shrink-0 text-danger" />
          <h2 className="font-medium">«{label}» no se generó</h2>
        </div>
        <p className="text-sm text-muted">{message}</p>
        {bloqueantes.length > 0 && (
          <ul className="mt-2 space-y-1">
            {bloqueantes.map((b) => (
              <li key={b} className="flex gap-2 text-sm">
                <span className="text-danger">•</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        )}
        <label className="mt-3 block">
          <span className="mb-1 block text-xs text-muted">
            Si aun así lo entregas, escribe por qué. Queda impreso en la carátula del
            Excel, con tu nombre.
          </span>
          <input
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            maxLength={300}
            placeholder="p. ej. el cliente confirmó por correo que la losa va a f'c=250"
            className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm"
          />
        </label>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onCancel}
            className={buttonClasses("primary", "sm")}
          >
            Mejor lo resuelvo
          </button>
          <button
            type="button"
            disabled={!enough}
            onClick={() => onConfirm(motivo.trim())}
            className={buttonClasses("ghost", "sm")}
          >
            Entregar de todos modos
          </button>
          {!enough && motivo.length > 0 && (
            <span className="self-center text-xs text-muted">
              Escribe una razón que se entienda sola (15 caracteres o más).
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}

/** One line for pages that are not about the findings: the state, and a way in. */
export function DiagnosticoStrip({
  diagnostico,
  projectId,
  href: target,
}: {
  diagnostico: Diagnostico;
  projectId: string;
  href?: string;
}) {
  const blocking = diagnostico.by_severity.bloqueante ?? 0;
  const money_ = diagnostico.by_severity.dinero ?? 0;
  if (blocking === 0 && money_ === 0) return null;
  const tier = TIERS[blocking > 0 ? "bloqueante" : "dinero"];
  return (
    <Link
      href={target ?? `/proyecto/${projectId}/presupuesto`}
      className={`mb-4 flex items-center gap-2.5 rounded-lg border px-4 py-2.5 text-sm transition-colors hover:brightness-105 ${tier.box}`}
    >
      <span className={tier.text}>{tier.icon}</span>
      <span className="min-w-0 flex-1">{diagnostico.resumen}</span>
      <ArrowRight size={14} weight="bold" className={`shrink-0 ${tier.text}`} />
    </Link>
  );
}
