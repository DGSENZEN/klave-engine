"use client";

/**
 * Finiquito: la cuenta que cierra el contrato.
 *
 * La pantalla enseña la resta completa, no el resultado. Un finiquito que sólo
 * dice «saldo a favor del contratista: $X» es un finiquito que nadie puede
 * revisar, y revisarlo es exactamente para lo que existe: la retención vuelve,
 * el anticipo tiene que quedar en ceros y las penas se aplican, y cada uno de
 * esos tres es una discusión distinta con una razón distinta.
 *
 * Por eso los saldos no se compensan antes de mostrarse. Cada renglón sale con
 * su signo y su razón, y la suma se hace al final y a la vista.
 *
 * Los campos que el motor sí sabe vienen precargados de las estimaciones que ya
 * se capturaron. Los que no —los días de atraso, el porcentaje de pena que fija
 * el contrato y no la ley— nacen en cero y se quedan en cero hasta que alguien
 * los escriba: una pena inventada es dinero que se le quita a alguien.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Flag, FloppyDisk } from "@phosphor-icons/react";
import {
  getFiniquito,
  guardarFiniquito,
  money,
  type Finiquito,
  type ResumenFiniquito,
  type SaldoFiniquito,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
} from "@/components/ui";

function Campo({
  label,
  hint,
  value,
  onChange,
  step = "0.01",
}: {
  label: string;
  hint?: string;
  value: number;
  onChange: (v: number) => void;
  step?: string;
}) {
  return (
    <label className="block">
      <span className="microlabel">{label}</span>
      <Input
        type="number"
        step={step}
        className="mt-1 w-full text-right tabular-nums"
        value={Number.isFinite(value) ? value : 0}
        onChange={(ev) => onChange(Number(ev.target.value))}
      />
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

/** Un renglón de la cuenta, con su signo intacto. */
function Saldo({ saldo }: { saldo: SaldoFiniquito }) {
  const aFavorContratista = saldo.importe >= 0;
  return (
    <div className="flex items-start justify-between gap-4 border-t border-border py-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{saldo.concepto}</span>
          <Badge tone={aFavorContratista ? "success" : "warning"}>
            a favor {aFavorContratista ? "del contratista" : "de la contratante"}
          </Badge>
        </div>
        {saldo.razon && <p className="mt-1 text-sm text-muted">{saldo.razon}</p>}
      </div>
      <div
        className={`shrink-0 font-display tabular ${
          aFavorContratista ? "text-success" : "text-warning"
        }`}
      >
        {saldo.importe >= 0 ? "+" : "−"}
        {money(Math.abs(saldo.importe))}
      </div>
    </div>
  );
}

export default function FiniquitoPage() {
  const { id } = useParams<{ id: string }>();
  const [fin, setFin] = useState<Finiquito | null>(null);
  const [resumen, setResumen] = useState<ResumenFiniquito | null>(null);
  const [guardado, setGuardado] = useState(false);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let vivo = true;
    getFiniquito(id)
      .then((cuerpo) => {
        if (!vivo) return;
        setFin(cuerpo.finiquito);
        setResumen(cuerpo.resumen);
        setGuardado(cuerpo.guardado);
      })
      .finally(() => vivo && setCargando(false));
    return () => {
      vivo = false;
    };
  }, [id]);

  async function guardar() {
    if (!fin) return;
    setGuardando(true);
    try {
      const cuerpo = await guardarFiniquito(id, fin, getBrowserActor());
      setFin(cuerpo.finiquito);
      setResumen(cuerpo.resumen);
      setGuardado(true);
    } finally {
      setGuardando(false);
    }
  }

  function set<K extends keyof Finiquito>(campo: K, valor: Finiquito[K]) {
    setFin((prev) => (prev ? { ...prev, [campo]: valor } : prev));
  }

  if (cargando || !fin || !resumen) {
    return (
      <div className="space-y-6">
        <PageHeader title="Finiquito" sub="La cuenta que cierra el contrato." />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const aFavor = resumen.saldo_final;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Finiquito"
        sub="Todo lo que pasó en la obra contra todo lo que se pagó, con cada saldo por su nombre."
        actions={
          <Button onClick={() => void guardar()} disabled={guardando}>
            <FloppyDisk size={16} />
            {guardando ? "Guardando…" : "Guardar finiquito"}
          </Button>
        }
      />

      {!guardado && (
        <Callout tone="info">
          Este finiquito está precargado con lo que suman las estimaciones capturadas y
          todavía no lo guarda nadie. Revisa los importes contra tus papeles antes de
          cerrarlo.
        </Callout>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Metric
          label="Ejecutado"
          value={money(resumen.ejecutado)}
          hint="Suma de las estimaciones autorizadas."
        />
        <Metric
          label="Pagado"
          value={money(resumen.pagado)}
          hint="Suma de los líquidos que efectivamente se cobraron."
        />
        <Metric
          label="Saldo final"
          value={`${aFavor >= 0 ? "" : "−"}${money(Math.abs(aFavor))}`}
          accent={Math.abs(aFavor) < 0.01 ? undefined : aFavor > 0 ? "success" : "danger"}
          hint={
            resumen.a_favor_de === "nadie"
              ? "El contrato cierra en ceros."
              : `A favor ${resumen.a_favor_de === "contratista" ? "del contratista" : "de la contratante"}.`
          }
          icon={<Flag size={18} />}
        />
      </div>

      {resumen.avisos.map((aviso) => (
        <Callout key={aviso} tone="warning">
          {aviso}
        </Callout>
      ))}

      <Card className="p-4">
        <SectionTitle>La cuenta</SectionTitle>
        <p className="mt-1 text-sm text-muted">
          Nada se compensa antes de mostrarse: cada saldo con su signo, y la resta al
          final.
        </p>
        <div className="mt-3">
          {resumen.saldos.length === 0 ? (
            <p className="border-t border-border py-4 text-sm text-muted">
              No hay saldos pendientes: lo ejecutado, lo pagado y el anticipo cuadran, y
              no hay retención por devolver.
            </p>
          ) : (
            resumen.saldos.map((s) => <Saldo key={s.concepto} saldo={s} />)
          )}
          <div className="flex items-center justify-between border-t-2 border-border-strong pt-3">
            <span className="font-medium">Saldo final</span>
            <span
              className={`font-display text-lg tabular ${
                Math.abs(aFavor) < 0.01
                  ? "text-foreground"
                  : aFavor > 0
                    ? "text-success"
                    : "text-danger"
              }`}
            >
              {aFavor >= 0 ? "+" : "−"}
              {money(Math.abs(aFavor))}
            </span>
          </div>
        </div>
      </Card>

      <Card className="p-4">
        <SectionTitle>Los datos de la cuenta</SectionTitle>
        <p className="mt-1 text-sm text-muted">
          Lo que sale de las estimaciones viene precargado. Lo que sólo está en el
          contrato lo escribes tú.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="block">
            <span className="microlabel">Fecha del finiquito</span>
            <Input
              type="date"
              className="mt-1 w-full"
              value={fin.fecha}
              onChange={(ev) => set("fecha", ev.target.value)}
            />
          </label>
          <Campo
            label="Monto del contrato"
            hint="Incluye los convenios firmados."
            value={fin.monto_contrato}
            onChange={(v) => set("monto_contrato", v)}
          />
          <Campo
            label="Ejecutado"
            value={fin.ejecutado}
            onChange={(v) => set("ejecutado", v)}
          />
          <Campo label="Pagado" value={fin.pagado} onChange={(v) => set("pagado", v)} />
          <Campo
            label="Anticipo otorgado"
            value={fin.anticipo_otorgado}
            onChange={(v) => set("anticipo_otorgado", v)}
          />
          <Campo
            label="Anticipo amortizado"
            hint="Si quedó de menos, el resto lo reintegra el contratista."
            value={fin.anticipo_amortizado}
            onChange={(v) => set("anticipo_amortizado", v)}
          />
          <Campo
            label="Retenciones aplicadas"
            hint="El fondo de garantía que se descontó en cada estimación."
            value={fin.retenciones_aplicadas}
            onChange={(v) => set("retenciones_aplicadas", v)}
          />
          <Campo
            label="Días de atraso"
            step="1"
            hint="Contra la fecha pactada de terminación."
            value={fin.dias_atraso}
            onChange={(v) => set("dias_atraso", Math.max(0, Math.round(v)))}
          />
          <Campo
            label="Pena diaria (%)"
            step="0.01"
            hint="La fija el contrato, no la ley: sin este dato no se calcula."
            value={fin.pena_pct_diario}
            onChange={(v) => set("pena_pct_diario", v)}
          />
        </div>
        <label className="mt-4 flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={fin.retencion_sustituida_por_fianza}
            onChange={(ev) => set("retencion_sustituida_por_fianza", ev.target.checked)}
          />
          <span>
            La retención se sustituyó por fianza
            <span className="block text-xs text-muted">
              Si se sustituyó, no se devuelve en el finiquito.
            </span>
          </span>
        </label>
      </Card>
    </div>
  );
}
