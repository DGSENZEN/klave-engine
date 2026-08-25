"use client";

/**
 * Estimaciones: lo que se cobra cada mes.
 *
 * La pantalla se organiza alrededor de una sola cifra —el líquido a pagar— y
 * del camino aritmético que lleva hasta ella, porque es exactamente lo que un
 * residente rehace a mano y lo que una contratante revisa antes de pagar. Cada
 * descuento se ve con su nombre y su porcentaje; ninguno aparece como un
 * número suelto.
 *
 * La cantidad de cada renglón se teclea: es lo que alguien midió en obra. No
 * hay barra de «avance %» que reparta importes, y esa ausencia es deliberada
 * — un avance inventado se paga y luego se descuenta.
 */

import { Fragment, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { DownloadSimple, Plus, Receipt, Ruler, TrendUp } from "@phosphor-icons/react";
import {
  descargarEstimacion,
  getEstimaciones,
  getUnidadesGenerador,
  guardarEstimacion,
  money,
  siguienteEstimacion,
  type Estimacion,
  type EstimacionConResumen,
  type LineaGenerador,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { GeneradorEditor } from "@/components/GeneradorEditor";
import {
  Button,
  Callout,
  Card,
  EmptyState,
  IconButton,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

function hoy(): string {
  return new Date().toISOString().slice(0, 10);
}

function finDeMes(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return new Date(d.getFullYear(), d.getMonth() + 1, 0).toISOString().slice(0, 10);
}

export default function EstimacionesPage() {
  const { id } = useParams<{ id: string }>();
  const [lista, setLista] = useState<EstimacionConResumen[] | null>(null);
  const [abierta, setAbierta] = useState<number | null>(null);
  const [borrador, setBorrador] = useState<Estimacion | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const leer = useCallback(async () => {
    const r = await getEstimaciones(id);
    setLista(r.estimaciones);
    return r.estimaciones;
  }, [id]);

  useEffect(() => {
    let vivo = true;
    getEstimaciones(id)
      .then((r) => vivo && setLista(r.estimaciones))
      .catch(() => vivo && setError("No se pudieron leer las estimaciones."));
    return () => {
      vivo = false;
    };
  }, [id]);

  async function crearSiguiente() {
    setBusy(true);
    setError(null);
    try {
      const inicio = hoy();
      const r = await siguienteEstimacion(id, inicio, finDeMes(inicio));
      setBorrador(r.estimacion);
      setAbierta(r.estimacion.numero);
    } catch {
      setError(
        "No hay una estimación anterior de la cual continuar. La primera se captura con " +
        "el catálogo contratado.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function guardar(est: Estimacion) {
    setBusy(true);
    setError(null);
    try {
      await guardarEstimacion(id, est.numero, est, getBrowserActor());
      await leer();
      setBorrador(null);
      setAbierta(est.numero);
    } catch {
      setError("No se pudo guardar la estimación.");
    } finally {
      setBusy(false);
    }
  }

  if (!lista) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Estimaciones" />
        <Card className="p-5">
          <Skeleton className="h-4 w-48" />
          <div className="mt-5 space-y-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        </Card>
      </div>
    );
  }

  const ultima = lista.at(-1);
  const editando = borrador ?? (
    abierta !== null ? lista.find((e) => e.estimacion.numero === abierta)?.estimacion : undefined
  );

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Estimaciones"
        sub="Lo ejecutado en el periodo, menos la amortización del anticipo y la retención del fondo de garantía (RLOPSRM art. 130–132)."
      />

      {error && (
        <div className="mb-5">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {ultima && (
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Metric
            label="Avance del contrato"
            value={`${ultima.resumen.avance_pct.toFixed(2)} %`}
            hint={`${money(ultima.resumen.acumulado)} estimados de ${money(
              ultima.estimacion.monto_contrato,
            )}`}
            icon={<TrendUp size={16} weight="duotone" />}
            accent="accent"
          />
          <Metric
            label={`Última estimación (#${ultima.resumen.numero})`}
            value={money(ultima.resumen.liquido)}
            hint={`líquido a pagar · ${ultima.resumen.periodo}`}
            icon={<Receipt size={16} weight="duotone" />}
          />
          <Metric
            label="Anticipo amortizado"
            value={money(
              ultima.estimacion.amortizado_previo + ultima.resumen.amortizacion,
            )}
            hint={`de ${money(
              (ultima.estimacion.monto_contrato * ultima.estimacion.anticipo_pct) / 100,
            )} recibidos`}
          />
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Button onClick={() => void crearSiguiente()} disabled={busy}>
          <Plus size={14} weight="bold" /> Nueva estimación
        </Button>
        <span className="text-xs text-muted">
          Se genera con lo acumulado y lo amortizado ya cargados: encadenar a mano es como
          se cobra dos veces el mismo metro.
        </span>
      </div>

      {lista.length === 0 && !borrador && (
        <EmptyState
          icon={<Receipt size={22} weight="duotone" />}
          title="Sin estimaciones todavía"
          hint="La primera se captura con el catálogo contratado, sus precios y lo medido en el periodo. Klave calcula la amortización, la retención y el líquido."
        />
      )}

      {lista.length > 0 && (
        <Card className="mb-6 p-5">
          <SectionTitle sub="Cada una con su carátula: de lo ejecutado al líquido, descuento por descuento.">
            Estimaciones del contrato
          </SectionTitle>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b border-border">
                <tr>
                  <Th>#</Th>
                  <Th>Periodo</Th>
                  <Th align="right">Ejecutado</Th>
                  <Th align="right">Amortización</Th>
                  <Th align="right">Retención</Th>
                  <Th align="right">Deductivas</Th>
                  <Th align="right">Líquido</Th>
                  <Th align="right">Avance</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {lista.map(({ resumen }) => (
                  <tr
                    key={resumen.numero}
                    className={`border-b border-border/60 ${
                      abierta === resumen.numero ? "bg-surface-2/50" : ""
                    }`}
                  >
                    <Td>
                      <button
                        type="button"
                        className="font-medium underline-offset-2 hover:underline"
                        onClick={() => {
                          setBorrador(null);
                          setAbierta(abierta === resumen.numero ? null : resumen.numero);
                        }}
                      >
                        {resumen.numero}
                      </button>
                    </Td>
                    <Td className="whitespace-nowrap text-muted">{resumen.periodo}</Td>
                    <Td align="right" className="tabular-nums">{money(resumen.importe)}</Td>
                    <Td align="right" className="tabular-nums text-muted">
                      −{money(resumen.amortizacion)}
                    </Td>
                    <Td align="right" className="tabular-nums text-muted">
                      −{money(resumen.retencion)}
                    </Td>
                    <Td align="right" className="tabular-nums text-muted">
                      {resumen.deductivas ? `−${money(resumen.deductivas)}` : "—"}
                    </Td>
                    <Td
                      align="right"
                      className={`tabular-nums font-medium ${
                        resumen.liquido < 0 ? "text-danger" : ""
                      }`}
                    >
                      {money(resumen.liquido)}
                    </Td>
                    <Td align="right" className="tabular-nums text-muted">
                      {resumen.avance_pct.toFixed(2)} %
                    </Td>
                    <Td align="right">
                      <IconButton
                        onClick={() => void descargarEstimacion(id, resumen.numero)}
                        title="Descargar la estimación con sus generadores"
                        aria-label={`Descargar la estimación ${resumen.numero}`}
                      >
                        <DownloadSimple size={16} />
                      </IconButton>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {lista.flatMap((e) => e.resumen.avisos).length > 0 && (
            <div className="mt-4 space-y-2">
              {lista.flatMap(({ resumen }) =>
                resumen.avisos.map((a) => (
                  <Callout key={`${resumen.numero}-${a}`} tone="danger">
                    Estimación {resumen.numero}: {a}
                  </Callout>
                )),
              )}
            </div>
          )}
        </Card>
      )}

      {editando && (
        <EditorEstimacion
          key={`${editando.numero}-${borrador ? "nueva" : "guardada"}`}
          estimacion={editando}
          busy={busy}
          onGuardar={guardar}
          onCancelar={() => {
            setBorrador(null);
            setAbierta(null);
          }}
        />
      )}
    </div>
  );
}

function EditorEstimacion({
  estimacion,
  busy,
  onGuardar,
  onCancelar,
}: {
  estimacion: Estimacion;
  busy: boolean;
  onGuardar: (e: Estimacion) => void;
  onCancelar: () => void;
}) {
  // La estimación que se edita se identifica por su número: cambiar de
  // estimación monta otro editor en vez de reiniciar éste, que es lo que pedía
  // un efecto y lo que React 19 desaconseja.
  const [local, setLocal] = useState<Estimacion>(estimacion);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [unidades, setUnidades] = useState<Record<string, string[]>>({});

  useEffect(() => {
    let vivo = true;
    getUnidadesGenerador()
      .then((r) => vivo && setUnidades(r.unidades))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  function medir(indice: number, cantidad: number) {
    setLocal({
      ...local,
      renglones: local.renglones.map((r, i) =>
        i === indice ? { ...r, quantity_period: cantidad } : r,
      ),
    });
  }

  function generar(indice: number, lineas: LineaGenerador[]) {
    setLocal({
      ...local,
      renglones: local.renglones.map((r, i) =>
        i === indice ? { ...r, generador: lineas } : r,
      ),
    });
  }

  const importe = local.renglones.reduce(
    (s, r) => s + r.quantity_period * r.unit_price,
    0,
  );

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <SectionTitle sub="Cada renglón lleva la cantidad que alguien midió en obra, con su generador detrás. Lo que no se midió no entra.">
          Estimación {local.numero}
        </SectionTitle>
        <div className="flex shrink-0 gap-2">
          <Button variant="ghost" onClick={onCancelar} disabled={busy}>
            Cerrar
          </Button>
          <Button onClick={() => onGuardar(local)} disabled={busy}>
            {busy ? "Guardando…" : "Guardar estimación"}
          </Button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-muted">Del</span>
          <Input
            type="date"
            value={local.periodo_inicio}
            onChange={(e) => setLocal({ ...local, periodo_inicio: e.target.value })}
            className="px-2 py-1"
            aria-label="Inicio del periodo"
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="text-muted">al</span>
          <Input
            type="date"
            value={local.periodo_fin}
            onChange={(e) => setLocal({ ...local, periodo_fin: e.target.value })}
            className="px-2 py-1"
            aria-label="Fin del periodo"
          />
        </label>
        <span className="text-xs text-muted">
          Anticipo {local.anticipo_pct} % · retención {local.retencion_pct} %
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="border-b border-border">
            <tr>
              <Th>Clave</Th>
              <Th>Concepto</Th>
              <Th align="right">P.U.</Th>
              <Th align="right">Contratado</Th>
              <Th align="right">Anterior</Th>
              <Th align="right">Este periodo</Th>
              <Th align="right">Acumulado</Th>
              <Th align="right">Importe</Th>
            </tr>
          </thead>
          <tbody>
            {local.renglones.map((r, i) => {
              const acumulado = r.quantity_previous + r.quantity_period;
              const excede = r.quantity_contract > 0 && acumulado > r.quantity_contract;
              const respaldo = r.generador?.length ?? 0;
              return (
                <Fragment key={r.clave}>
                <tr className="border-b border-border/60">
                  <Td className="whitespace-nowrap font-mono text-xs">{r.clave}</Td>
                  <Td className="min-w-[200px]">
                    {r.description}
                    <button
                      type="button"
                      onClick={() => setAbierto(abierto === r.clave ? null : r.clave)}
                      className="mt-0.5 flex items-center gap-1 text-[11px] text-muted underline-offset-2 hover:text-foreground hover:underline"
                    >
                      <Ruler size={12} />
                      {respaldo > 0
                        ? `Generador · ${respaldo} ${respaldo === 1 ? "línea" : "líneas"}`
                        : "Sin generador"}
                    </button>
                  </Td>
                  <Td align="right" className="tabular-nums">{money(r.unit_price)}</Td>
                  <Td align="right" className="tabular-nums text-muted">
                    {r.quantity_contract.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                  </Td>
                  <Td align="right" className="tabular-nums text-muted">
                    {r.quantity_previous.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={0}
                      step="any"
                      value={r.quantity_period || ""}
                      onChange={(e) => medir(i, Number(e.target.value))}
                      className="w-24 px-2 py-1 text-right text-sm"
                      aria-label={`Medido este periodo en ${r.clave}`}
                    />
                  </Td>
                  <Td
                    align="right"
                    className={`tabular-nums ${excede ? "text-danger" : ""}`}
                  >
                    {acumulado.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                    {excede && (
                      <span className="mt-0.5 block text-[11px]">
                        rebasa el catálogo: necesita convenio
                      </span>
                    )}
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {money(r.quantity_period * r.unit_price)}
                  </Td>
                </tr>
                {abierto === r.clave && (
                  <tr className="border-b border-border/60">
                    <td colSpan={8} className="px-2 pb-3">
                      <GeneradorEditor
                        lineas={r.generador ?? []}
                        unidad={r.unit}
                        unidades={unidades}
                        cantidad={r.quantity_period}
                        onChange={(lineas) => generar(i, lineas)}
                        onUsarTotal={(total) => medir(i, total)}
                      />
                    </td>
                  </tr>
                )}
                </Fragment>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="font-medium">
              <Td colSpan={7}>Ejecutado en el periodo</Td>
              <Td align="right" className="tabular-nums">{money(importe)}</Td>
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}
