"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { apiMessage, getPiloto, putPiloto, type Piloto } from "@/lib/api";
import { useProjectLive } from "@/components/ProjectLive";
import {
  Button,
  Callout,
  Card,
  Input,
  Metric,
  PageHeader,
  Select,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

/**
 * La medición del piloto: la puerta del v1 es «horas ahorradas, generadores
 * aceptados, export importado». Las horas salen de lo que el proyecto ya
 * guarda (estimadas, y se dice cómo); lo demás lo declara la oficina — Klave
 * no inventa la base contra la que se compara.
 */

const FORMATOS: Record<string, string> = {
  klave: "Excel de Klave",
  opus: "OPUS",
  neodata: "Neodata",
  licitacion: "Formato de licitación",
  licitacion_larga: "Licitación (largo)",
  explosion: "Explosión de insumos",
  apus: "Análisis de precios",
  generadores_compartidos: "Generadores por liga",
};

function horas(min: number | null | undefined): string {
  if (min == null) return "—";
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

const siNo = (v: boolean | null) => (v === true ? "si" : v === false ? "no" : "");
const deSiNo = (v: string) => (v === "si" ? true : v === "no" ? false : null);

export default function PilotoPage() {
  const { id } = useParams<{ id: string }>();
  const { latestEvent, actorName } = useProjectLive();
  const [data, setData] = useState<Piloto | null>(null);
  const [failed, setFailed] = useState(false);
  const [form, setForm] = useState<{ horas: string; aceptados: string; importado: string; notas: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getPiloto(id)
        .then((d) => {
          if (!alive) return;
          setData(d);
          setFailed(false);
          setForm((f) =>
            f ?? {
              horas: d.metodo_anterior.horas != null ? String(d.metodo_anterior.horas) : "",
              aceptados: siNo(d.puerta.generadores_aceptados),
              importado: siNo(d.puerta.export_importado),
              notas: d.puerta.notas,
            },
          );
        })
        .catch(() => alive && setFailed(true));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [id, latestEvent?.seq]);

  const guardar = async () => {
    if (!form) return;
    setSaving(true);
    setError(null);
    try {
      const h = form.horas.trim() ? Number(form.horas.replace(",", ".")) : null;
      setData(
        await putPiloto(
          id,
          {
            horas_metodo_anterior: h != null && Number.isFinite(h) ? h : null,
            generadores_aceptados: deSiNo(form.aceptados),
            export_importado: deSiNo(form.importado),
            notas: form.notas,
          },
          actorName,
        ),
      );
      setNotice("Guardado.");
    } catch (err) {
      setError(apiMessage(err, "No se pudo guardar."));
    } finally {
      setSaving(false);
    }
  };

  if (failed) return <Callout tone="warning">No se pudo leer la medición del piloto.</Callout>;
  if (!data || !form) return <Skeleton className="h-64" />;

  const resumen = [
    `Piloto — tiempo de una persona en Klave: ${horas(data.revision.minutos_activos)} en ${data.revision.sesiones} sesiones, ${data.revision.decisiones} decisiones.`,
    `Proceso del motor: ${horas(data.procesamiento.ultima_min)} (última corrida).`,
    data.entrega.minutos_desde_inicio != null
      ? `Primera entrega a ${horas(data.entrega.minutos_desde_inicio)} de subir el plano, en ${data.entrega.formatos.map((f) => FORMATOS[f] ?? f).join(", ")}.`
      : "Sin entrega todavía.",
    data.minutos_por_hoja != null ? `Minutos de revisión por hoja: ${data.minutos_por_hoja}.` : "",
    data.metodo_anterior.horas != null
      ? `Método anterior (declarado): ${data.metodo_anterior.horas} h. Ahorro: ${data.metodo_anterior.ahorro_horas} h.`
      : "Horas del método anterior: sin declarar.",
    `Generadores aceptados: ${siNo(data.puerta.generadores_aceptados) || "sin decir"}. Export importado: ${siNo(data.puerta.export_importado) || "sin decir"}.`,
    data.como_se_mide,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Medición del piloto"
        sub="Cuánto le tomó a tu oficina ir del plano a los generadores con Klave, junto a lo que le toma a su modo. Las horas se estiman de lo que el proyecto guarda; la base la declaras tú."
      />

      {!data.inicio && (
        <Callout tone="info">
          Este proyecto no tiene actividad guardada: la medición se registra desde que se activó.
          Para el piloto, sube el plano de la licitación como proyecto nuevo y trabájalo aquí
          de principio a fin.
        </Callout>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Tiempo de una persona"
          value={data.revision.sesiones ? horas(data.revision.minutos_activos) : "—"}
          hint={
            data.revision.sesiones
              ? `${data.revision.sesiones} sesiones · ${data.revision.decisiones} decisiones`
              : "sin actividad registrada"
          }
        />
        <Metric label="Proceso del motor" value={horas(data.procesamiento.ultima_min)} hint={`${data.procesamiento.corridas} corridas`} />
        <Metric label="Hasta la primera entrega" value={horas(data.entrega.minutos_desde_inicio)} hint={data.entrega.formatos.map((f) => FORMATOS[f] ?? f).join(", ") || "sin entrega"} />
        <Metric label="Revisión por hoja" value={data.minutos_por_hoja != null ? `${data.minutos_por_hoja} min` : "—"} hint="promedio, por decisiones" />
      </div>

      <Card className="space-y-4 p-5">
        <h2 className="text-base font-semibold">Contra el método anterior</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            <span className="text-muted">Horas que le toma a tu oficina sin Klave</span>
            <Input
              inputMode="decimal"
              value={form.horas}
              placeholder="p. ej. 16"
              onChange={(e) => setForm({ ...form, horas: e.target.value })}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted">¿Se aceptaron los generadores?</span>
            <Select value={form.aceptados} onChange={(e) => setForm({ ...form, aceptados: e.target.value })}>
              <option value="">Sin decir</option>
              <option value="si">Sí</option>
              <option value="no">No</option>
            </Select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted">¿El export entró a OPUS o Neodata?</span>
            <Select value={form.importado} onChange={(e) => setForm({ ...form, importado: e.target.value })}>
              <option value="">Sin decir</option>
              <option value="si">Sí</option>
              <option value="no">No</option>
            </Select>
          </label>
        </div>
        <label className="block space-y-1 text-sm">
          <span className="text-muted">Notas (qué faltó, qué se corrigió a mano)</span>
          <textarea
            className="w-full rounded-lg border border-border bg-surface p-2.5 text-sm text-foreground outline-none focus:border-border-strong focus:ring-2 focus:ring-accent/20"
            rows={3}
            value={form.notas}
            onChange={(e) => setForm({ ...form, notas: e.target.value })}
          />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={guardar} disabled={saving}>
            Guardar
          </Button>
          {data.metodo_anterior.ahorro_horas != null && (
            <span className="text-sm text-foreground">
              Klave: {data.metodo_anterior.horas_klave} h de una persona · Antes:{" "}
              {data.metodo_anterior.horas} h ·{" "}
              <strong className={data.metodo_anterior.ahorro_horas >= 0 ? "text-success" : "text-danger"}>
                {data.metodo_anterior.ahorro_horas >= 0 ? "Ahorro" : "Exceso"}{" "}
                {Math.abs(data.metodo_anterior.ahorro_horas)} h
              </strong>
            </span>
          )}
        </div>
        {notice && <Callout tone="info">{notice}</Callout>}
        {error && <Callout tone="danger">{error}</Callout>}
      </Card>

      {data.por_hoja.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 text-base font-semibold">Por hoja</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <Th>Hoja</Th>
                  <Th className="text-right">Decisiones</Th>
                  <Th className="text-right">Minutos (estimados)</Th>
                </tr>
              </thead>
              <tbody>
                {data.por_hoja.map((h) => (
                  <tr key={h.hoja} className="border-t border-border">
                    <Td>{h.hoja.replace(/\.(dxf|dwg)$/i, "")}</Td>
                    <Td className="text-right tabular-nums">{h.decisiones}</Td>
                    <Td className="text-right tabular-nums">{h.minutos_estimados}</Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="space-y-3 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Resumen</h2>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              void navigator.clipboard?.writeText(resumen);
              setNotice("Resumen copiado.");
            }}
          >
            Copiar resumen
          </Button>
        </div>
        <pre className="whitespace-pre-wrap text-sm text-muted">{resumen}</pre>
      </Card>
    </div>
  );
}
