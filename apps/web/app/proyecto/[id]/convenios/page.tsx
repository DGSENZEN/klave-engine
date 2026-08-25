"use client";

/**
 * Convenios modificatorios: el contrato cuando deja de ser el que se firmó.
 *
 * La pantalla se organiza alrededor de un solo número, el porcentaje contra el
 * monto original, porque es el que decide si el convenio se puede firmar. El
 * art. 59 de la LOPSRM limita los convenios **en conjunto** al 25 %, y el error
 * que se comete es contarlos por separado: tres convenios del 10 % no son tres
 * veces «dentro del límite», son un 30 % que ya no cabe. Por eso el medidor
 * está arriba de la lista y no debajo: se ve antes de agregar el que rompe el
 * techo, no después de firmarlo.
 *
 * Lo que la pantalla no hace es escribir el motivo. El motor sabe que una
 * cantidad se excedió, no por qué se excedió, y la ley pide causa justificada:
 * ese campo nace vacío y se queda vacío hasta que una persona lo llene.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { FilePlus, Scales, Trash, Warning } from "@phosphor-icons/react";
import {
  borradorConvenio,
  borrarConvenio,
  getConvenios,
  getEstimaciones,
  guardarConvenio,
  money,
  type Convenio,
  type EstadoContrato,
  type EstimacionConResumen,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

/** Qué tan cerca del techo del art. 59, dicho como barra y como número. */
function Medidor({ estado }: { estado: EstadoContrato }) {
  const pct = estado.monto_pct;
  const lleno = Math.min(Math.abs(pct) / estado.techo_pct, 1) * 100;
  const tono = estado.rebasa_techo
    ? "bg-danger"
    : Math.abs(pct) > estado.techo_pct * 0.8
      ? "bg-warning"
      : "bg-accent";
  return (
    <Card className="p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div className="microlabel">Convenido sobre el monto original</div>
        <div className="font-display text-sm tabular text-muted">
          techo {estado.techo_pct.toFixed(0)} %
        </div>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span
          className={`font-display text-[1.55rem] font-medium leading-none tabular ${
            estado.rebasa_techo ? "text-danger" : "text-foreground"
          }`}
        >
          {pct.toFixed(1)} %
        </span>
        <span className="text-xs text-muted">
          {money(estado.monto_convenido)} sobre {money(estado.monto_original)}
        </span>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
        <div className={`h-full rounded-full ${tono}`} style={{ width: `${lleno}%` }} />
      </div>
      <div className="mt-1.5 text-xs text-muted">
        Contrato vigente {money(estado.monto_vigente)}. El art. 59 de la LOPSRM cuenta
        todos los convenios juntos, no uno por uno.
      </div>
    </Card>
  );
}

function FilasConvenio({ convenio }: { convenio: Convenio }) {
  return (
    <>
      {convenio.renglones.map((r) => {
        const delta = r.quantity - r.quantity_anterior;
        const nuevo = r.quantity_anterior <= 0;
        return (
          <tr key={`${convenio.numero}-${r.clave}`} className="border-t border-border">
            <Td className="font-mono text-xs">{r.clave}</Td>
            <Td>
              {r.description}
              {nuevo && (
                <Badge tone="warning">
                  <span title="No estaba en el catálogo original">concepto nuevo</span>
                </Badge>
              )}
            </Td>
            <Td className="text-muted">{r.unit}</Td>
            <Td className="text-right tabular-nums text-muted">
              {nuevo ? "—" : r.quantity_anterior.toLocaleString("es-MX")}
            </Td>
            <Td className="text-right tabular-nums">{r.quantity.toLocaleString("es-MX")}</Td>
            <Td className="text-right tabular-nums">
              {delta >= 0 ? "+" : ""}
              {delta.toLocaleString("es-MX")}
            </Td>
            <Td className="text-right tabular-nums">
              {money(Math.round(delta * r.unit_price * 100) / 100)}
            </Td>
          </tr>
        );
      })}
    </>
  );
}

export default function ConveniosPage() {
  const { id } = useParams<{ id: string }>();
  const [convenios, setConvenios] = useState<Convenio[]>([]);
  const [estado, setEstado] = useState<EstadoContrato | null>(null);
  const [estimaciones, setEstimaciones] = useState<EstimacionConResumen[]>([]);
  const [cargando, setCargando] = useState(true);
  const [borrador, setBorrador] = useState<Convenio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmar, setConfirmar] = useState<number | null>(null);

  const cargar = useCallback(async () => {
    const [c, e] = await Promise.all([getConvenios(id), getEstimaciones(id)]);
    setConvenios(c.convenios);
    setEstado(c.estado);
    setEstimaciones(e.estimaciones);
    setCargando(false);
  }, [id]);

  useEffect(() => {
    let vivo = true;
    Promise.all([getConvenios(id), getEstimaciones(id)])
      .then(([c, e]) => {
        if (!vivo) return;
        setConvenios(c.convenios);
        setEstado(c.estado);
        setEstimaciones(e.estimaciones);
      })
      .catch(() => vivo && setError("No se pudieron leer los convenios."))
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [id]);

  /** Las estimaciones que rebasaron el catálogo son las que piden convenio. */
  const conExcedente = estimaciones.filter((e) =>
    e.estimacion.renglones.some(
      (r) => r.quantity_contract > 0 &&
        r.quantity_period + r.quantity_previous > r.quantity_contract,
    ),
  );

  async function proponer(numero: number) {
    setError(null);
    try {
      const hoy = new Date().toISOString().slice(0, 10);
      const { convenio } = await borradorConvenio(id, numero, hoy);
      setBorrador(convenio);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo armar el borrador.");
    }
  }

  async function guardar() {
    if (!borrador) return;
    if (!borrador.motivo.trim()) {
      setError("Escribe la causa: la ley pide que el convenio esté justificado.");
      return;
    }
    setError(null);
    await guardarConvenio(id, borrador.numero, borrador, getBrowserActor());
    setBorrador(null);
    await cargar();
  }

  async function eliminar(numero: number) {
    await borrarConvenio(id, numero, getBrowserActor());
    setConfirmar(null);
    await cargar();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Convenios modificatorios"
        sub="Lo que cambió del contrato después de firmarlo, y qué tanto margen queda antes del techo de ley."
      />

      {cargando && <Skeleton className="h-28 w-full" />}

      {!cargando && estado && (
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2">
            <Medidor estado={estado} />
          </div>
          <Metric
            label="Plazo convenido"
            value={`${estado.dias_convenidos} días`}
            hint={
              estado.plazo_original_dias > 0
                ? `${estado.plazo_pct.toFixed(1)} % sobre ${estado.plazo_original_dias} días originales`
                : "Captura el plazo del contrato para medirlo contra el techo."
            }
            icon={<Scales size={18} />}
          />
        </div>
      )}

      {estado?.avisos.map((aviso) => (
        <Callout key={aviso} tone={estado.rebasa_techo ? "danger" : "warning"}>
          {aviso}
        </Callout>
      ))}

      {error && <Callout tone="danger">{error}</Callout>}

      {!cargando && conExcedente.length > 0 && !borrador && (
        <Card className="p-4">
          <SectionTitle>Estimaciones que piden convenio</SectionTitle>
          <p className="mt-1 text-sm text-muted">
            Estas estimaciones midieron más de lo que dice el catálogo contratado. Sin
            convenio, esa obra se ejecuta y no se cobra.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {conExcedente.map((e) => (
              <Button
                key={e.estimacion.numero}
                variant="secondary"
                onClick={() => void proponer(e.estimacion.numero)}
              >
                <FilePlus size={16} />
                Armar convenio de la estimación {e.estimacion.numero}
              </Button>
            ))}
          </div>
        </Card>
      )}

      {borrador && (
        <Card className="p-4">
          <SectionTitle>Borrador del convenio {borrador.numero}</SectionTitle>
          <p className="mt-1 text-sm text-muted">
            Las cantidades vienen de lo que ya se midió en obra. El motivo no: la ley pide
            causa justificada y eso lo escribe quien la conoce.
          </p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto]">
            <label className="block">
              <span className="microlabel">Motivo</span>
              <Input
                className="mt-1 w-full"
                value={borrador.motivo}
                placeholder="Por qué se modifica el contrato"
                onChange={(ev) =>
                  setBorrador({ ...borrador, motivo: ev.target.value })
                }
              />
            </label>
            <label className="block">
              <span className="microlabel">Fecha</span>
              <Input
                type="date"
                className="mt-1"
                value={borrador.fecha}
                onChange={(ev) => setBorrador({ ...borrador, fecha: ev.target.value })}
              />
            </label>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <Th>Clave</Th>
                  <Th>Concepto</Th>
                  <Th>Unidad</Th>
                  <Th className="text-right">Contratado</Th>
                  <Th className="text-right">Nuevo</Th>
                  <Th className="text-right">Diferencia</Th>
                  <Th className="text-right">Importe</Th>
                </tr>
              </thead>
              <tbody>
                <FilasConvenio convenio={borrador} />
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <div className="text-sm text-muted">
              Este convenio agrega{" "}
              <span className="font-medium text-foreground">
                {money(
                  Math.round(
                    borrador.renglones.reduce(
                      (t, r) => t + (r.quantity - r.quantity_anterior) * r.unit_price,
                      0,
                    ) * 100,
                  ) / 100,
                )}
              </span>{" "}
              al contrato.
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setBorrador(null)}>
                Cancelar
              </Button>
              <Button onClick={() => void guardar()}>Guardar convenio</Button>
            </div>
          </div>
        </Card>
      )}

      {!cargando && convenios.length === 0 && !borrador && (
        <EmptyState
          icon={<Scales size={28} />}
          title="El contrato sigue como se firmó"
          hint="Cuando una estimación mida más de lo contratado, aquí se arma el convenio que lo respalda."
        />
      )}

      {convenios.map((c) => (
        <Card key={c.numero} className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <SectionTitle>
                Convenio {c.numero}
                <Badge tone="default">{c.tipo}</Badge>
              </SectionTitle>
              <div className="mt-1 text-sm text-muted">
                {c.fecha}
                {c.motivo ? ` · ${c.motivo}` : ""}
                {c.dias_plazo > 0 ? ` · +${c.dias_plazo} días de plazo` : ""}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="text-right">
                <div className="microlabel">Importe</div>
                <div className="font-display tabular">
                  {money(
                    Math.round(
                      c.renglones.reduce(
                        (t, r) => t + (r.quantity - r.quantity_anterior) * r.unit_price,
                        0,
                      ) * 100,
                    ) / 100,
                  )}
                </div>
              </div>
              {confirmar === c.numero ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted">¿Quitarlo?</span>
                  <Button variant="ghost" onClick={() => setConfirmar(null)}>
                    No
                  </Button>
                  <Button variant="secondary" onClick={() => void eliminar(c.numero)}>
                    Sí, quitar
                  </Button>
                </div>
              ) : (
                <Button variant="ghost" onClick={() => setConfirmar(c.numero)}>
                  <Trash size={16} />
                </Button>
              )}
            </div>
          </div>
          {!c.motivo && (
            <Callout tone="warning">
              <Warning size={16} /> Este convenio no tiene causa escrita. La ley pide que
              esté justificado y una revisión lo va a buscar.
            </Callout>
          )}
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <Th>Clave</Th>
                  <Th>Concepto</Th>
                  <Th>Unidad</Th>
                  <Th className="text-right">Contratado</Th>
                  <Th className="text-right">Nuevo</Th>
                  <Th className="text-right">Diferencia</Th>
                  <Th className="text-right">Importe</Th>
                </tr>
              </thead>
              <tbody>
                <FilasConvenio convenio={c} />
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  );
}
