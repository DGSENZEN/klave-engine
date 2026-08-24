"use client";

import { useEffect, useState } from "react";
import { Bug, CurrencyDollar } from "@phosphor-icons/react";
import { getErrores, getGastoIA, type ErroresRecientes, type GastoIA } from "@/lib/api";
import { Card, SectionTitle } from "@/components/ui";

/**
 * Lo que el taller gasta en IA y lo que se le rompe, para quien administra.
 *
 * Las dos cifras se presentan por lo que son: el gasto es una **estimación**
 * con tarifas que el operador declaró, no un cargo leído del proveedor, y se
 * dice con esas palabras. Los errores se quedan en la máquina del taller —
 * mandar trazas a un tercero significaría mandarle nombres de obra y de
 * cliente.
 */

function usd(v: number): string {
  return new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: v < 10 ? 2 : 0,
  }).format(v);
}

export function GastoIACard() {
  const [gasto, setGasto] = useState<GastoIA | null>(null);
  const [falla, setFalla] = useState(false);

  useEffect(() => {
    getGastoIA()
      .then(setGasto)
      .catch(() => setFalla(true));
  }, []);

  if (falla) return null;

  return (
    <Card className="p-5">
      <SectionTitle sub="Estimado con las tarifas que declaró quien administra este servidor, no un cargo leído del proveedor. Sirve para ver tendencia y frenar a tiempo, no para conciliar una factura.">
        <span className="inline-flex items-center gap-2">
          <CurrencyDollar size={17} weight="duotone" /> Gasto de IA este mes
        </span>
      </SectionTitle>
      {!gasto ? (
        <p className="text-sm text-muted">Cargando…</p>
      ) : gasto.llamadas === 0 ? (
        <p className="text-sm text-muted">
          Todavía no se ha usado la IA este mes en este taller.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-display text-2xl font-semibold tabular">
              ~{usd(gasto.costo_estimado_usd)}
            </span>
            <span className="text-sm text-muted">
              {gasto.llamadas.toLocaleString("es-MX")} llamadas ·{" "}
              {(gasto.tokens_entrada / 1000).toFixed(0)}k tokens de entrada
            </span>
          </div>
          {gasto.tope_usd ? (
            <div className="mt-2">
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                <div
                  className={`h-full rounded-full ${
                    gasto.excedido ? "bg-danger" : "bg-accent"
                  }`}
                  style={{ width: `${Math.min(gasto.porcentaje ?? 0, 100)}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-muted">
                {gasto.porcentaje}% del tope de {usd(gasto.tope_usd)}.{" "}
                {gasto.excedido
                  ? "La lectura y el copiloto están pausados hasta el mes que entra o hasta subir el tope."
                  : "Al llegar al tope, la lectura y el copiloto se pausan."}
              </p>
            </div>
          ) : (
            <p className="mt-1.5 text-xs text-muted">
              Sin tope configurado: nada frena el gasto. Se pone con{" "}
              <code className="font-mono">KLAVE_AI_BUDGET_USD</code>.
            </p>
          )}
          {gasto.sin_tarifar > 0 && (
            <p className="mt-1.5 text-xs text-warning">
              {gasto.sin_tarifar} llamada(s) usaron un modelo sin tarifa declarada: su
              costo no está en este número, no es que fueran gratis.
            </p>
          )}
          {gasto.por_proyecto.length > 0 && (
            <ul className="mt-3 space-y-1">
              {gasto.por_proyecto.slice(0, 5).map((p) => (
                <li key={p.project_id} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-muted">{p.project_id}</span>
                  <span className="tabular shrink-0">~{usd(p.usd)}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

export function ErroresCard() {
  const [errores, setErrores] = useState<ErroresRecientes | null>(null);
  const [falla, setFalla] = useState(false);

  useEffect(() => {
    getErrores()
      .then(setErrores)
      .catch(() => setFalla(true));
  }, []);

  if (falla) return null;

  return (
    <Card className="p-5">
      <SectionTitle sub="Los últimos siete días, agrupados. Se guarda aquí y no se manda a ningún tercero: en una traza viajan nombres de obra y de cliente.">
        <span className="inline-flex items-center gap-2">
          <Bug size={17} weight="duotone" /> Qué se ha roto
        </span>
      </SectionTitle>
      {!errores ? (
        <p className="text-sm text-muted">Cargando…</p>
      ) : errores.total === 0 ? (
        <p className="text-sm text-muted">
          Nada se rompió en la última semana. Si un usuario reporta algo y aquí no
          aparece, no llegó al servidor.
        </p>
      ) : (
        <>
          <p className="text-sm">
            <span className="font-medium">{errores.total}</span> incidente(s) en 7 días,
            en {errores.grupos.length} punto(s) distintos.
          </p>
          <ul className="mt-2 space-y-1.5">
            {errores.grupos.slice(0, 6).map((g) => (
              <li key={`${g.ruta}-${g.tipo}`} className="text-sm">
                <span className="tabular font-semibold">{g.veces}×</span>{" "}
                <span className="font-mono text-xs">{g.tipo}</span>{" "}
                <span className="text-muted">en {g.ruta}</span>
                {g.mensaje && (
                  <div className="truncate text-xs text-faint" title={g.mensaje}>
                    {g.mensaje}
                  </div>
                )}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-faint">
            Detalle completo en {errores.donde.errores}
          </p>
        </>
      )}
    </Card>
  );
}
