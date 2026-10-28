"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  apiMessage,
  decidirEstructura,
  getEstructura,
  quitarDecisionEstructural,
  type DatoEstructural,
  type DecisionEstructural,
  type Estructura,
  type FuenteEstructural,
  type ResumenFamilia,
  type Verificacion,
} from "@/lib/api";
import { money, num } from "@/lib/format";
import { Badge, Button, Callout, Disclosure, Skeleton, Td, Th } from "@/components/ui";
import { ConfirmDialog } from "@/components/ConfirmDialog";

/**
 * «Lectura estructural»: lo que el plano dice de cada familia (y lo que no),
 * los hallazgos del propio plano agrupados por causa, y la decisión de una
 * persona cuando el plano se contradice. Cada valor dice quién lo dijo; una
 * decisión lleva su nota, recalcula el presupuesto y se puede quitar.
 */

const FUENTE: Record<FuenteEstructural, string> = {
  humano: "decisión",
  cuadro: "cuadro",
  detalle: "detalle",
  seccion_dibujada: "sección dibujada",
  nota: "nota",
  medido: "medido",
  regla: "regla",
  supuesto: "supuesto",
  ia: "IA (por confirmar)",
};

// Cada número es una causa: así se agrupan los hallazgos, no uno por uno.
const CAUSA: Record<number, string> = {
  1: "Marcas colocadas que el plano no define",
  2: "Marcas definidas que nunca se colocan",
  7: "Datos críticos que faltan o se suponen",
  8: "El plano se contradice",
  10: "Marcas escritas sin elemento colocado",
  11: "Textos de armado que nadie leyó",
};

const SEVERIDAD: {
  key: Verificacion["severidad"];
  label: string;
  tone: "danger" | "warning" | "default";
}[] = [
  { key: "bloquea", label: "Bloquea", tone: "danger" },
  { key: "duda", label: "Duda", tone: "warning" },
  { key: "aviso", label: "Aviso", tone: "default" },
];

const FAMILIA: Record<string, string> = {
  muro_concreto: "Muros de concreto",
  general: "General",
};

const nombreFamilia = (f: string) =>
  FAMILIA[f] ?? f.charAt(0).toUpperCase() + f.slice(1).replace(/_/g, " ");

const POR_GRUPO = 20;

const cuantos = (n: number, uno: string, varios: string) =>
  `${num(n, 0)} ${n === 1 ? uno : varios}`;

function esPar(v: unknown): v is [number, number] {
  return Array.isArray(v) && v.length === 2 && v.every((x) => typeof x === "number" && x > 0);
}

/** El valor como lo escribe un ingeniero, o null si sólo el texto del plano lo dice bien. */
function formatValor(campo: string, valor: unknown): string | null {
  if (valor == null) return null;
  if (typeof valor === "string") return valor.trim() || null;
  if (typeof valor === "number") {
    if (campo === "recubrimiento_m") return `${num(valor * 100, 1)} cm`;
    if (campo.endsWith("_m")) return `${num(valor, 2)} m`;
    return num(valor, 2);
  }
  if (esPar(valor))
    return `${num(valor[0], 1)} × ${num(valor[1], 1)}${campo === "seccion_cm" ? " cm" : ""}`;
  if (typeof valor === "object" && !Array.isArray(valor)) {
    const area = (valor as { area_cm2?: unknown }).area_cm2;
    return typeof area === "number" ? `${num(area, 0)} cm²` : null;
  }
  if (Array.isArray(valor)) {
    const piezas = valor.map((p) => {
      if (!p || typeof p !== "object") return null;
      const { cantidad, numero, tipo, zonas } = p as {
        cantidad?: number;
        numero?: string;
        tipo?: string;
        zonas?: { separacion_m?: number | null }[];
      };
      if (!numero) return null;
      if (tipo === "estribo") {
        const sep = zonas?.find((z) => z.separacion_m)?.separacion_m;
        return `${cantidad && cantidad > 1 ? cantidad : ""}E#${numero}${sep ? ` @${num(sep * 100, 0)}` : ""}`;
      }
      return `${cantidad ?? ""}#${numero}`;
    });
    return piezas.every(Boolean) && piezas.length ? piezas.join(" + ") : null;
  }
  return null;
}

// Lo que lee el plano. Un supuesto, una regla o la IA nunca se ofrecen para decidir: decidir
// es escoger entre lo que el plano dice cuando se contradice.
const DEL_PLANO = new Set<FuenteEstructural>([
  "cuadro",
  "detalle",
  "seccion_dibujada",
  "nota",
  "medido",
]);

const esPieza = (p: unknown): p is { tipo?: string } => !!p && typeof p === "object";

/** Si ese valor es algo que el campo puede tomar como decisión. */
function decidible(campo: string, valor: unknown): boolean {
  if (valor == null) return false;
  if (campo === "seccion_cm")
    return (
      esPar(valor) ||
      (typeof valor === "object" &&
        !Array.isArray(valor) &&
        typeof (valor as { area_cm2?: unknown }).area_cm2 === "number")
    );
  if (campo === "longitud_m") return typeof valor === "number" && valor > 0;
  if (typeof valor === "string")
    return ["longitudinales", "estribos", "parrillas"].includes(campo) && valor.trim() !== "";
  if (!Array.isArray(valor) || valor.length === 0 || !valor.every(esPieza)) return false;
  // Unos estribos son estribos, y unas varillas longitudinales no lo son.
  if (campo === "estribos") return valor.every((p) => p.tipo === "estribo");
  if (campo === "longitudinales") return valor.every((p) => p.tipo !== "estribo");
  return campo === "parrillas";
}

/** Los valores distintos del plano entre los que una persona puede escoger, o ninguno. */
function opciones(v: Verificacion, campos: Set<string>): DatoEstructural[] {
  if (v.severidad === "aviso" || v.marcas.length !== 1 || !campos.has(v.campo)) return [];
  if (v.numero !== 8 && !v.datos.some((d) => d.en_conflicto)) return [];
  const vistos = new Set<string>();
  const out: DatoEstructural[] = [];
  for (const d of v.datos) {
    if (!DEL_PLANO.has(d.fuente) || !decidible(v.campo, d.valor)) continue;
    const clave = JSON.stringify(d.valor);
    if (vistos.has(clave)) continue;
    vistos.add(clave);
    out.push(d);
  }
  return out.length >= 2 ? out : [];
}

/** Las fuentes de un hallazgo sin repetir: veinte copias del mismo texto son una. */
function fuentesDistintas(datos: DatoEstructural[]): DatoEstructural[] {
  const vistos = new Set<string>();
  return datos.filter((d) => {
    if (!d.texto && d.valor == null) return false;
    const clave = `${d.fuente}|${JSON.stringify(d.valor)}|${d.texto}`;
    if (vistos.has(clave)) return false;
    vistos.add(clave);
    return true;
  });
}

function enJuego(v: Verificacion): string | null {
  const e = v.en_juego;
  const partes: string[] = [];
  if (e.acero_kg) partes.push(`${num(e.acero_kg, 0)} kg de acero`);
  if (e.concreto_m3) partes.push(`${num(e.concreto_m3, 2)} m³ de concreto`);
  if (e.volumen_m3) partes.push(`${num(e.volumen_m3, 2)} m³ de piezas sin el dato`);
  if (e.piezas) partes.push(cuantos(e.piezas, "pieza", "piezas"));
  if (!partes.length)
    return v.cantidad === "desconocida" ? "Sin cifra: el plano no permite medirlo" : null;
  const prefijo =
    v.cantidad === "estimada"
      ? "Estimado"
      : v.cantidad === "desconocida"
        ? "Sin cifra"
        : "En juego";
  return `${prefijo}: ${partes.join(" · ")}`;
}

function enJuegoFamilia(r: ResumenFamilia): { texto: string; orden: number } {
  if (r.en_juego_mxn != null)
    return { texto: r.en_juego_mxn > 0 ? money(r.en_juego_mxn) : "—", orden: r.en_juego_mxn };
  if (r.en_juego_mxn_conocido > 0)
    return { texto: `≥ ${money(r.en_juego_mxn_conocido)}`, orden: r.en_juego_mxn_conocido };
  const cantidades = [
    r.en_juego_cantidad.acero_kg ? `${num(r.en_juego_cantidad.acero_kg, 0)} kg` : null,
    r.en_juego_cantidad.concreto_m3 ? `${num(r.en_juego_cantidad.concreto_m3, 2)} m³` : null,
  ].filter(Boolean);
  return {
    // «Sin cifra» sólo cuando hay un hallazgo abierto que no se puede medir; si no, nada en juego.
    texto: cantidades.length
      ? `${cantidades.join(" · ")} sin precio`
      : r.en_juego_desconocido > 0
        ? "Sin cifra"
        : "—",
    orden: 0,
  };
}

const hojaCorta = (hoja: string) => hoja.replace(/\.(dxf|dwg)$/i, "");

export function EstructuraSection({
  projectId,
  actorName,
  clientId,
  reloadKey,
}: {
  projectId: string;
  actorName: string;
  clientId: string | null;
  reloadKey?: unknown;
}) {
  const [state, setState] = useState<Estructura | null>(null);
  // "no_disponible": el servidor todavía no tiene esta lectura (404 de la ruta).
  const [failed, setFailed] = useState<null | "error" | "no_disponible">(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abiertos, setAbiertos] = useState<Record<string, boolean>>({});
  const [todos, setTodos] = useState<Record<string, boolean>>({});
  const [eleccion, setEleccion] = useState<{ id: string; indice: number; nota: string } | null>(
    null,
  );
  const [quitar, setQuitar] = useState<DecisionEstructural | null>(null);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getEstructura(projectId)
        .then((s) => {
          if (!alive) return;
          setState(s);
          setFailed(null);
        })
        .catch((err) => {
          if (!alive) return;
          const sinRuta =
            err instanceof ApiError &&
            err.status === 404 &&
            !(err.detail && typeof err.detail === "object");
          setFailed(sinRuta ? "no_disponible" : "error");
        });
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [projectId, reloadKey]);

  const nombreCampo = (campo: string) =>
    state?.campos_decidibles.find((c) => c.campo === campo)?.nombre ?? campo.replace(/_/g, " ");

  const decidir = async (v: Verificacion, dato: DatoEstructural, nota: string) => {
    setBusy(true);
    setError(null);
    try {
      const nueva = await decidirEstructura(
        projectId,
        { marca: v.marcas[0], campo: v.campo, valor: dato.valor, nota: nota.trim() },
        actorName,
        clientId,
      );
      setState(nueva);
      setEleccion(null);
      setNotice(
        `Decidido: ${v.marcas[0]}, ${nombreCampo(v.campo)} = ${formatValor(v.campo, dato.valor) ?? dato.texto}. El presupuesto se recalculó con ese valor.`,
      );
    } catch (err) {
      setError(apiMessage(err, "No se pudo guardar la decisión."));
    } finally {
      setBusy(false);
    }
  };

  const quitarDecision = async (d: DecisionEstructural) => {
    setQuitar(null);
    setBusy(true);
    setError(null);
    try {
      const nueva = await quitarDecisionEstructural(projectId, d, actorName, clientId);
      setState(nueva);
      setNotice(
        `Se quitó la decisión sobre ${d.marca} (${nombreCampo(d.campo)}). El presupuesto volvió a lo que dice el plano.`,
      );
    } catch (err) {
      setError(apiMessage(err, "No se pudo quitar la decisión."));
    } finally {
      setBusy(false);
    }
  };

  const encabezado = (
    <div>
      <h2 className="text-base font-semibold text-foreground">Lectura estructural</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Lo que el plano dice de cada familia y de dónde sale cada valor. Los hallazgos son del
        propio plano: lo que falta, lo que se supone y lo que se contradice. Cuando el plano da dos
        valores, eliges tú y dejas una nota.
      </p>
    </div>
  );

  if (failed)
    return (
      <section className="space-y-3">
        {encabezado}
        <Callout tone={failed === "no_disponible" ? "info" : "warning"}>
          {failed === "no_disponible"
            ? "La lectura estructural todavía no está disponible en este servidor."
            : "No se pudo leer la lectura estructural."}
        </Callout>
      </section>
    );
  if (state === null)
    return (
      <section className="space-y-3">
        {encabezado}
        <Skeleton className="h-24" />
      </section>
    );
  if (!state.disponible)
    return (
      <section className="space-y-3">
        {encabezado}
        <Callout tone="info">
          {state.avisos[0] ?? "Esta corrida no tiene lectura estructural."}
        </Callout>
      </section>
    );

  const campos = new Set(state.campos_decidibles.map((c) => c.campo));
  const familias = [...state.resumen]
    .map((r) => ({ r, juego: enJuegoFamilia(r) }))
    .sort(
      (a, b) => b.juego.orden - a.juego.orden || b.r.bloquea + b.r.duda - (a.r.bloquea + a.r.duda),
    );

  return (
    <section className="space-y-5">
      {encabezado}
      {!state.al_dia && (
        <Callout tone="warning">
          Hay decisiones guardadas que esta lectura todavía no tiene aplicadas. Reprocesa o vuelve a
          decidir para que el presupuesto las tome.
        </Callout>
      )}
      {state.avisos.length > 0 && (
        <ul className="space-y-1 text-sm text-muted">
          {state.avisos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      {notice && <Callout tone="info">{notice}</Callout>}
      {error && <Callout tone="danger">{error}</Callout>}

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-data">
          <thead>
            <tr>
              <Th>Familia</Th>
              <Th align="right">Colocadas</Th>
              <Th align="right">Con definición</Th>
              <Th align="right">Del plano</Th>
              <Th align="right">Bloquea</Th>
              <Th align="right">Dudas</Th>
              <Th align="right">En juego</Th>
            </tr>
          </thead>
          <tbody>
            {familias.map(({ r, juego }) => (
              <tr key={r.familia} className="border-t border-border">
                <Td className="text-foreground">{nombreFamilia(r.familia)}</Td>
                <Td align="right" className="tabular-nums">
                  {num(r.colocaciones, 0)}
                </Td>
                <Td align="right" className="tabular-nums">
                  {r.colocaciones
                    ? `${num(r.con_definicion, 0)} de ${num(r.colocaciones, 0)}`
                    : "—"}
                </Td>
                <Td
                  align="right"
                  className="tabular-nums"
                  title="De los datos críticos que la familia necesita, cuántos da el plano. Supuestos, reglas e IA no cuentan aquí."
                >
                  {r.criticos_total
                    ? `${num(r.criticos_del_plano, 0)} de ${num(r.criticos_total, 0)}`
                    : "—"}
                  {r.criticos_humanos > 0 && (
                    <span className="text-muted"> · {num(r.criticos_humanos, 0)} decididos</span>
                  )}
                </Td>
                <Td
                  align="right"
                  className={`tabular-nums ${r.bloquea ? "text-danger" : "text-muted"}`}
                >
                  {num(r.bloquea, 0)}
                </Td>
                <Td
                  align="right"
                  className={`tabular-nums ${r.duda ? "text-warning" : "text-muted"}`}
                >
                  {num(r.duda, 0)}
                </Td>
                <Td align="right" className="tabular-nums">
                  {juego.texto}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {state.decisiones_guardadas.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-foreground">Decisiones de la oficina</h3>
          <ul className="divide-y divide-border rounded-lg border border-border">
            {state.decisiones_guardadas.map((d) => (
              <li
                key={`${d.marca}|${d.campo}|${d.para_muro_cm ?? ""}`}
                className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm"
              >
                <span>
                  <span className="font-medium text-foreground">{d.marca}</span>
                  <span className="text-muted">
                    {" "}
                    · {nombreCampo(d.campo)}
                    {d.para_muro_cm != null ? ` (muros de ${num(d.para_muro_cm, 0)} cm)` : ""}:{" "}
                  </span>
                  {formatValor(d.campo, d.valor) ?? JSON.stringify(d.valor)}
                  {d.nota && <span className="text-muted"> — «{d.nota}»</span>}
                  {d.actor && <span className="text-muted"> · {d.actor}</span>}
                </span>
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => setQuitar(d)}>
                  Quitar
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {SEVERIDAD.map(({ key, label, tone }) => {
        const deEsta = state.verificaciones.filter((v) => v.severidad === key);
        if (!deEsta.length) return null;
        const causas = new Map<number, Verificacion[]>();
        for (const v of deEsta) causas.set(v.numero, [...(causas.get(v.numero) ?? []), v]);
        return (
          <div key={key} className="space-y-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Badge tone={tone}>{label}</Badge>
              {cuantos(deEsta.length, "hallazgo", "hallazgos")}
            </h3>
            {[...causas.entries()].map(([numero, lista]) => {
              const grupo = `${key}-${numero}`;
              const visibles = todos[grupo] ? lista : lista.slice(0, POR_GRUPO);
              // Lo que bloquea se ve de entrada, y un grupo corto nunca se esconde tras un clic.
              const abiertoDeInicio = key === "bloquea" || lista.length <= 5;
              return (
                <Disclosure
                  key={grupo}
                  open={abiertos[grupo] ?? abiertoDeInicio}
                  onToggle={() =>
                    setAbiertos((a) => ({ ...a, [grupo]: !(a[grupo] ?? abiertoDeInicio) }))
                  }
                  title={CAUSA[numero] ?? "Otros hallazgos del plano"}
                  summary={`${cuantos(lista.length, "hallazgo", "hallazgos")} · ${cuantos(new Set(lista.flatMap((v) => v.marcas)).size, "marca", "marcas")}`}
                >
                  <ul className="space-y-4">
                    {visibles.map((v) => (
                      <Hallazgo
                        key={v.id}
                        v={v}
                        projectId={projectId}
                        opciones={opciones(v, campos)}
                        nombreCampo={nombreCampo}
                        eleccion={eleccion?.id === v.id ? eleccion : null}
                        busy={busy}
                        onElegir={(indice) => setEleccion({ id: v.id, indice, nota: "" })}
                        onNota={(nota) => setEleccion((e) => (e ? { ...e, nota } : e))}
                        onCancelar={() => setEleccion(null)}
                        onDecidir={(dato, nota) => decidir(v, dato, nota)}
                      />
                    ))}
                  </ul>
                  {lista.length > visibles.length && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="mt-3"
                      onClick={() => setTodos((t) => ({ ...t, [grupo]: true }))}
                    >
                      Mostrar los {num(lista.length - visibles.length, 0)} restantes
                    </Button>
                  )}
                </Disclosure>
              );
            })}
          </div>
        );
      })}

      <ConfirmDialog
        open={quitar !== null}
        title="Quitar la decisión"
        description={
          quitar
            ? `${quitar.marca} · ${nombreCampo(quitar.campo)}: vuelve a lo que dice el plano y el presupuesto se recalcula sin la decisión.`
            : ""
        }
        confirmLabel="Quitar la decisión"
        onConfirm={() => quitar && quitarDecision(quitar)}
        onCancel={() => setQuitar(null)}
      />
    </section>
  );
}

function Hallazgo({
  v,
  projectId,
  opciones,
  nombreCampo,
  eleccion,
  busy,
  onElegir,
  onNota,
  onCancelar,
  onDecidir,
}: {
  v: Verificacion;
  projectId: string;
  opciones: DatoEstructural[];
  nombreCampo: (campo: string) => string;
  eleccion: { indice: number; nota: string } | null;
  busy: boolean;
  onElegir: (indice: number) => void;
  onNota: (nota: string) => void;
  onCancelar: () => void;
  onDecidir: (dato: DatoEstructural, nota: string) => void;
}) {
  const juego = enJuego(v);
  const marcas =
    v.marcas.length > 8
      ? `${v.marcas.slice(0, 8).join(", ")} y ${v.marcas.length - 8} más`
      : v.marcas.join(", ");
  const datos = opciones.length ? opciones : fuentesDistintas(v.datos).slice(0, 4);
  const elegido = eleccion ? opciones[eleccion.indice] : null;
  return (
    <li className="space-y-2 text-sm">
      <p className="text-foreground">{v.mensaje}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {marcas && <span>{marcas}</span>}
        {juego && <span>{juego}</span>}
        {v.bbox && (
          <Link
            href={`/proyecto/${projectId}/plano?bbox=${v.bbox.map((x) => x.toFixed(3)).join(",")}`}
            className="text-accent hover:underline"
          >
            Ver en el plano{v.hoja ? ` · ${hojaCorta(v.hoja)}` : ""}
          </Link>
        )}
      </div>
      {datos.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {datos.map((d, i) => {
            const valor = formatValor(v.campo, d.valor);
            const hojas = (d.hojas.length ? d.hojas : d.hoja ? [d.hoja] : []).map(hojaCorta);
            return (
              <div key={i} className="rounded-lg border border-border bg-surface px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted">
                    {FUENTE[d.fuente] ?? d.fuente}
                  </span>
                  {hojas.length > 0 && (
                    <span className="text-xs text-muted">
                      {hojas.length > 3
                        ? `${hojas.slice(0, 3).join(", ")} y ${hojas.length - 3} más`
                        : hojas.join(", ")}
                    </span>
                  )}
                </div>
                {valor && (
                  <div className="mt-1 font-medium tabular-nums text-foreground">{valor}</div>
                )}
                {d.texto && <div className="mt-0.5 text-xs text-muted">{d.texto}</div>}
                {opciones.length > 0 && !eleccion && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2"
                    disabled={busy}
                    onClick={() => onElegir(i)}
                  >
                    Usar este valor
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {eleccion && elegido && (
        <form
          className="space-y-2 rounded-lg border border-border bg-surface-2 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (eleccion.nota.trim()) onDecidir(elegido, eleccion.nota);
          }}
        >
          <label className="block text-xs font-medium text-muted" htmlFor={`nota-${v.id}`}>
            {v.marcas[0]}, {nombreCampo(v.campo)} ={" "}
            {formatValor(v.campo, elegido.valor) ?? elegido.texto}. ¿Por qué este valor?
            (obligatorio)
          </label>
          <textarea
            id={`nota-${v.id}`}
            value={eleccion.nota}
            onChange={(e) => onNota(e.target.value)}
            maxLength={300}
            rows={2}
            placeholder="Por ejemplo: el corte de la hoja ES-200 es el vigente"
            className="w-full rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
          />
          <div className="flex gap-2">
            <Button size="sm" type="submit" disabled={busy || !eleccion.nota.trim()}>
              {busy ? "Recalculando…" : "Decidir y recalcular"}
            </Button>
            <Button size="sm" variant="ghost" type="button" disabled={busy} onClick={onCancelar}>
              Cancelar
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}
