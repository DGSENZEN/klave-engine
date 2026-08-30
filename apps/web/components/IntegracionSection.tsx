"use client";

/**
 * Integración del precio a nivel taller: los rubros de oficina central con
 * su volumen anual contratado (de ahí sale el prorrateo — costo anual entre
 * volumen, ver packages/klave_engine/costing/indirectos.py) y la tasa de
 * financiamiento con su indicador, fuente y fecha. Sin estos dos análisis,
 * la integración de cada obra se queda en los porcentajes declarados de
 * `indirects` y `financial`; capturarlos aquí es lo que activa el análisis.
 *
 * Cada tarjeta guarda con su propio botón, pero el PUT siempre manda las dos
 * mitades juntas — el backend las guarda como un solo objeto — así que el
 * "Guardar" de una tarjeta también sube lo que esté tecleado en la otra.
 */

import { useCallback, useEffect, useState } from "react";
import {
  apiMessage,
  getIntegracionTaller,
  money2,
  putIntegracionTaller,
  type AnalisisFinanciamiento,
  type RubroIndirecto,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { RubrosEditor } from "@/components/DesgloseCampo";
import { Button, Callout, Card, Input, SectionTitle, Skeleton } from "@/components/ui";

export function IntegracionSection({
  onChanged,
  onError,
  onNotice,
}: {
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [rubros, setRubros] = useState<RubroIndirecto[]>([]);
  const [volumen, setVolumen] = useState(0);
  const [financiamiento, setFinanciamiento] = useState<AnalisisFinanciamiento>({
    tasa_anual: 0,
    indicador: "",
    fuente: "",
    fecha_publicacion: "",
  });
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [oficinaBusy, setOficinaBusy] = useState(false);
  const [financiamientoBusy, setFinanciamientoBusy] = useState(false);

  const reload = useCallback(() => {
    getIntegracionTaller()
      .then((r) => {
        setRubros(r.oficina.rubros);
        setVolumen(r.oficina.volumen_anual_contratado);
        setFinanciamiento(r.financiamiento);
        setLoaded(true);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function save(busySetter: (v: boolean) => void, notice: string) {
    busySetter(true);
    try {
      const saved = await putIntegracionTaller(
        { oficina: { rubros, volumen_anual_contratado: volumen }, financiamiento },
        getBrowserActor(),
      );
      setRubros(saved.oficina.rubros);
      setVolumen(saved.oficina.volumen_anual_contratado);
      setFinanciamiento(saved.financiamiento);
      onNotice(notice);
      onChanged();
    } catch (e) {
      onError(apiMessage(e, "No se pudo guardar la integración del precio."));
    } finally {
      busySetter(false);
    }
  }

  const costoAnual = rubros.reduce((sum, r) => sum + (r.importe || 0), 0);
  const pctDerivado = costoAnual > 0 && volumen > 0 ? (costoAnual / volumen) * 100 : null;

  return (
    <div className="mb-8 space-y-6">
      <h2 className="text-[0.95rem] font-semibold">Integración del precio</h2>

      {loadError && (
        <Callout
          tone="danger"
          action={
            <Button size="sm" onClick={reload}>
              Reintentar
            </Button>
          }
        >
          No se pudo cargar la integración del precio.
        </Callout>
      )}

      <Card className="p-5">
        <SectionTitle sub="Los rubros de oficina central son costos ANUALES de la empresa; divididos entre el volumen anual de obra en cartera dan el prorrateo que le toca a cada obra.">
          Oficina central
        </SectionTitle>
        {!loaded && !loadError && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
            <Skeleton className="h-8 w-3/4" />
          </div>
        )}
        {loaded && (
          <>
            <RubrosEditor rubros={rubros} onChange={setRubros} baseAnual />
            <label className="mt-4 flex items-center justify-between gap-3 text-sm">
              <span className="text-muted">Volumen anual contratado (MXN)</span>
              <Input
                type="number"
                min={0}
                step="any"
                value={volumen || ""}
                onChange={(e) => setVolumen(Number(e.target.value))}
                placeholder="sin capturar"
                className="w-40 px-2 py-1 text-right tabular"
                aria-label="Volumen anual contratado (MXN)"
              />
            </label>
            {pctDerivado !== null && (
              <p className="mt-3 text-xs text-muted">
                {money2(costoAnual)} ÷ {money2(volumen)} = {pctDerivado.toFixed(4)} %
              </p>
            )}
            <Button
              size="sm"
              variant="primary"
              className="mt-4"
              disabled={oficinaBusy}
              onClick={() => save(setOficinaBusy, "Oficina central guardada.")}
            >
              {oficinaBusy ? "Guardando…" : "Guardar oficina central"}
            </Button>
          </>
        )}
      </Card>

      <Card className="p-5">
        <SectionTitle sub="RLOPSRM art. 195. Una tasa sin indicador, fuente y fecha de publicación no es un análisis: es un invento.">
          Financiamiento
        </SectionTitle>
        {!loaded && !loadError && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-8" />
            <Skeleton className="h-8" />
          </div>
        )}
        {loaded && (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="microlabel">Tasa anual (%)</span>
                <Input
                  type="number"
                  min={0}
                  step="any"
                  value={financiamiento.tasa_anual || ""}
                  onChange={(e) =>
                    setFinanciamiento({ ...financiamiento, tasa_anual: Number(e.target.value) })
                  }
                  className="mt-1 w-full px-2 py-1.5 text-sm tabular"
                  aria-label="Tasa anual (%)"
                />
              </label>
              <label className="block">
                <span className="microlabel">Indicador</span>
                <Input
                  value={financiamiento.indicador}
                  onChange={(e) =>
                    setFinanciamiento({ ...financiamiento, indicador: e.target.value })
                  }
                  placeholder="TIIE 28 días"
                  className="mt-1 w-full px-2 py-1.5 text-sm"
                  aria-label="Indicador"
                />
              </label>
              <label className="block">
                <span className="microlabel">Fuente</span>
                <Input
                  value={financiamiento.fuente}
                  onChange={(e) => setFinanciamiento({ ...financiamiento, fuente: e.target.value })}
                  placeholder="Banxico SF43783"
                  className="mt-1 w-full px-2 py-1.5 text-sm"
                  aria-label="Fuente"
                />
              </label>
              <label className="block">
                <span className="microlabel">Fecha de publicación</span>
                <Input
                  type="date"
                  value={financiamiento.fecha_publicacion}
                  onChange={(e) =>
                    setFinanciamiento({ ...financiamiento, fecha_publicacion: e.target.value })
                  }
                  className="mt-1 w-full px-2 py-1.5 text-sm"
                  aria-label="Fecha de publicación"
                />
              </label>
            </div>
            <p className="mt-3 text-xs text-muted">
              Sin los cuatro datos no hay análisis: el financiamiento se queda en porcentaje
              declarado.
            </p>
            <Button
              size="sm"
              variant="primary"
              className="mt-4"
              disabled={financiamientoBusy}
              onClick={() => save(setFinanciamientoBusy, "Financiamiento guardado.")}
            >
              {financiamientoBusy ? "Guardando…" : "Guardar financiamiento"}
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
