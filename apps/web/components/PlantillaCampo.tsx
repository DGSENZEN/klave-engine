"use client";

/**
 * El quinto programa: personal técnico, administrativo y de servicio.
 *
 * Los otros tres programas de erogaciones salen solos del presupuesto porque
 * la mano de obra, la maquinaria y los materiales viven dentro de las
 * matrices. Éste no puede: el superintendente y el velador son costo
 * indirecto de campo. Antes se exportaba vacío y el licitante se enteraba al
 * abrir el Excel — o peor, en la apertura de propuestas.
 *
 * Aquí se captura. Dos honestidades sostienen la pantalla:
 *
 * - Un puesto sin sueldo capturado se ve, con su participación en el
 *   calendario, y dice «sin sueldo» en la columna del importe. Nunca $0.
 * - La suma de la plantilla se compara contra los indirectos de campo que
 *   declara la integración del precio. Es la comparación que hace un revisor
 *   bajo el art. 64-A-I, y sale en pantalla antes que en su escritorio.
 */

import { useEffect, useState } from "react";
import { Plus, Trash, UsersThree, Warning } from "@phosphor-icons/react";
import {
  getCostingConfig,
  getPersonalTecnico,
  money,
  recompute,
  type CargoCampo,
  type PersonalTecnico,
} from "@/lib/api";
import { useProjectLive } from "@/components/ProjectLive";
import { Button, Callout, Card, Input, SectionTitle, Select, Skeleton, Td, Th } from "@/components/ui";

const TIPO_LABEL: Record<CargoCampo["tipo"], string> = {
  tecnico: "Técnico",
  administrativo: "Administrativo",
  servicio: "Servicio",
};

const CARGO_NUEVO: CargoCampo = {
  puesto: "",
  tipo: "tecnico",
  cantidad: 1,
  salario_mensual: 0,
  fsr: 1.6,
  desde_periodo: 1,
  hasta_periodo: null,
  dedicacion_pct: 100,
  razon: "",
};

/** Una nota que trae "64-A-I" es una incongruencia; el resto es informativa. */
function notaTone(nota: string): "danger" | "warning" | "info" {
  if (nota.includes("64-A-I")) return "danger";
  if (nota.includes("45-A-XI-d") || nota.includes("sin sueldo capturado")) return "warning";
  return "info";
}

export function PlantillaCampo({ id }: { id: string }) {
  const { actorName, clientId, latestEvent, connectionEpoch } = useProjectLive();
  const [data, setData] = useState<PersonalTecnico | null>(null);
  const [borrador, setBorrador] = useState<CargoCampo[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El programa se recalcula con el presupuesto: cuando otro cliente recompone
  // los indirectos, la congruencia de abajo cambia sin que nadie toque esta
  // pantalla, así que se vuelve a leer.
  const recalculado =
    latestEvent?.type === "costing_updated" || latestEvent?.type === "run_published";

  useEffect(() => {
    let active = true;
    getPersonalTecnico(id)
      .then((d) => {
        if (!active) return;
        setData(d);
        setError(null);
      })
      .catch(() => {
        if (active) setError("No se pudo cargar el programa de personal.");
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch, recalculado, latestEvent]);

  async function guardar(cargos: CargoCampo[]) {
    setBusy(true);
    setError(null);
    try {
      const actual = await getCostingConfig(id);
      actual.config.plantilla_campo = cargos.filter((c) => c.puesto.trim());
      await recompute(
        id,
        { config: actual.config, insumo_prices: actual.insumo_prices, version: actual.version },
        actorName,
        clientId,
      );
      setBorrador(null);
      setData(await getPersonalTecnico(id));
    } catch {
      setError("No se pudo guardar la plantilla; inténtalo de nuevo.");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <Card className="p-5">
        <Skeleton className="h-4 w-56" />
        <div className="mt-5 space-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      </Card>
    );
  }

  const editando = borrador !== null;
  const cargos = borrador ?? data.plantilla;
  const { programa } = data;
  const periodos = Math.max(data.periodos, 1);

  function set(index: number, patch: Partial<CargoCampo>) {
    setBorrador(cargos.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <SectionTitle sub="RLOPSRM art. 45-A-XI-d. Es costo indirecto de campo: no sale del presupuesto, se captura y se calendariza sobre el mismo programa.">
          Personal técnico, administrativo y de servicio
        </SectionTitle>
        <div className="flex shrink-0 gap-2">
          {editando ? (
            <>
              <Button variant="ghost" onClick={() => setBorrador(null)} disabled={busy}>
                Descartar
              </Button>
              <Button onClick={() => void guardar(cargos)} disabled={busy}>
                {busy ? "Guardando…" : "Guardar plantilla"}
              </Button>
            </>
          ) : (
            <Button variant="ghost" onClick={() => setBorrador([...data.plantilla])}>
              {data.plantilla.length ? "Editar plantilla" : "Capturar plantilla"}
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {!cargos.length && !editando && (
        <div className="space-y-4">
          <Callout
            tone="warning"
            action={
              <Button
                onClick={() => setBorrador(data.sugerida.map((c) => ({ ...c })))}
                disabled={busy}
              >
                Partir de la sugerida
              </Button>
            }
          >
            Falta este programa. Una propuesta sin él está incompleta ante el art. 45-A
            y se desecha en la apertura.
          </Callout>
          <p className="text-sm text-muted">
            El motor puede proponer <strong>qué puestos</strong> lleva una obra de esta
            duración y con estos frentes — un residente por frente, un velador siempre, un
            topógrafo mientras se traza. No propone sueldos: eso es dinero de tu taller y
            lo capturas tú.
          </p>
          <ul className="grid gap-1.5 text-sm sm:grid-cols-2">
            {data.sugerida.map((c) => (
              <li key={c.puesto} className="flex gap-2">
                <UsersThree size={15} weight="duotone" className="mt-0.5 shrink-0 text-muted" />
                <span>
                  <span className="font-medium">
                    {c.cantidad > 1 ? `${c.cantidad}× ` : ""}
                    {c.puesto}
                  </span>
                  <span className="block text-xs text-muted">{c.razon}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {editando && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="border-b border-border">
              <tr>
                <Th>Puesto</Th>
                <Th>Tipo</Th>
                <Th align="right">Cant.</Th>
                <Th align="right">Sueldo mensual</Th>
                <Th align="right">FSR</Th>
                <Th align="right">Desde</Th>
                <Th align="right">Hasta</Th>
                <Th align="right">Dedic. %</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {cargos.map((cargo, index) => (
                <tr key={index} className="border-b border-border/60">
                  <Td className="min-w-[200px]">
                    <Input
                      value={cargo.puesto}
                      onChange={(e) => set(index, { puesto: e.target.value })}
                      placeholder="Residente de obra"
                      className="w-full px-2 py-1 text-sm"
                      aria-label={`Puesto ${index + 1}`}
                    />
                    {cargo.razon && (
                      <span className="mt-1 block text-xs text-muted">{cargo.razon}</span>
                    )}
                  </Td>
                  <Td>
                    <Select
                      size="sm"
                      value={cargo.tipo}
                      onChange={(e) =>
                        set(index, { tipo: e.target.value as CargoCampo["tipo"] })
                      }
                      aria-label={`Tipo de ${cargo.puesto || index + 1}`}
                    >
                      {Object.entries(TIPO_LABEL).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </Select>
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={0}
                      step={1}
                      value={cargo.cantidad}
                      onChange={(e) => set(index, { cantidad: Number(e.target.value) })}
                      className="w-16 px-2 py-1 text-right text-sm"
                      aria-label={`Cantidad de ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={0}
                      step={500}
                      value={cargo.salario_mensual || ""}
                      onChange={(e) => set(index, { salario_mensual: Number(e.target.value) })}
                      placeholder="sin capturar"
                      className="w-32 px-2 py-1 text-right text-sm"
                      aria-label={`Sueldo mensual de ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={1}
                      step={0.01}
                      value={cargo.fsr}
                      onChange={(e) => set(index, { fsr: Number(e.target.value) })}
                      className="w-20 px-2 py-1 text-right text-sm"
                      aria-label={`Factor de salario real de ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={1}
                      max={periodos}
                      value={cargo.desde_periodo}
                      onChange={(e) => set(index, { desde_periodo: Number(e.target.value) })}
                      className="w-16 px-2 py-1 text-right text-sm"
                      aria-label={`Desde qué periodo participa ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={1}
                      max={periodos}
                      value={cargo.hasta_periodo ?? ""}
                      onChange={(e) =>
                        set(index, {
                          hasta_periodo: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                      placeholder="fin"
                      className="w-16 px-2 py-1 text-right text-sm"
                      aria-label={`Hasta qué periodo participa ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step={5}
                      value={cargo.dedicacion_pct}
                      onChange={(e) => set(index, { dedicacion_pct: Number(e.target.value) })}
                      className="w-16 px-2 py-1 text-right text-sm"
                      aria-label={`Dedicación de ${cargo.puesto || index + 1}`}
                    />
                  </Td>
                  <Td align="right">
                    <button
                      type="button"
                      onClick={() => setBorrador(cargos.filter((_, i) => i !== index))}
                      className="text-muted transition hover:text-danger"
                      aria-label={`Quitar ${cargo.puesto || `renglón ${index + 1}`}`}
                    >
                      <Trash size={15} weight="duotone" />
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button
              variant="ghost"
              onClick={() => setBorrador([...cargos, { ...CARGO_NUEVO }])}
            >
              <Plus size={14} weight="bold" /> Agregar puesto
            </Button>
            {!data.plantilla.length && (
              <Button
                variant="ghost"
                onClick={() => setBorrador(data.sugerida.map((c) => ({ ...c })))}
              >
                Cargar la sugerida
              </Button>
            )}
            <span className="text-xs text-muted">
              Periodos 1–{periodos} ({programa.renglones[0]?.unidad.split("-")[0] ?? "mes"}).
              «Hasta» vacío = hasta el final de la obra.
            </span>
          </div>
        </div>
      )}

      {!editando && programa.renglones.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="border-b border-border">
                <tr>
                  <Th>Puesto</Th>
                  <Th>Tipo</Th>
                  <Th align="right">{programa.renglones[0].unidad}</Th>
                  <Th>Participación</Th>
                  <Th align="right">Importe</Th>
                </tr>
              </thead>
              <tbody>
                {programa.renglones.map((r) => {
                  const pico = Math.max(...r.por_periodo, 1);
                  return (
                    <tr key={r.puesto} className="border-b border-border/60">
                      <Td>
                        <span className="font-medium">{r.puesto}</span>
                        {r.razon && (
                          <span className="mt-0.5 block text-xs text-muted">{r.razon}</span>
                        )}
                      </Td>
                      <Td className="text-muted">{TIPO_LABEL[r.tipo]}</Td>
                      <Td align="right" className="tabular-nums">
                        {r.cantidad.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                      </Td>
                      <Td>
                        <div className="flex h-4 min-w-[120px] items-stretch gap-px">
                          {r.por_periodo.map((v, i) => (
                            <div
                              key={i}
                              className="flex-1 rounded-[2px] bg-accent"
                              style={{ opacity: v > 0 ? 0.25 + 0.75 * (v / pico) : 0.08 }}
                              title={`Periodo ${i + 1}: ${v.toLocaleString("es-MX", {
                                maximumFractionDigits: 2,
                              })}`}
                            />
                          ))}
                        </div>
                      </Td>
                      <Td align="right" className="tabular-nums">
                        {r.sin_sueldo ? (
                          <span className="inline-flex items-center gap-1 text-warning">
                            <Warning size={13} weight="bold" /> sin sueldo
                          </span>
                        ) : (
                          money(r.importe)
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="font-medium">
                  <Td colSpan={4}>
                    Total de la plantilla
                    {programa.cargos_sin_sueldo > 0 && (
                      <span className="ml-2 text-xs font-normal text-warning">
                        incompleto: {programa.cargos_sin_sueldo}{" "}
                        {programa.cargos_sin_sueldo === 1 ? "puesto" : "puestos"} sin sueldo
                      </span>
                    )}
                  </Td>
                  <Td align="right" className="tabular-nums">
                    {money(programa.total)}
                  </Td>
                </tr>
                {data.indirectos_campo > 0 && (
                  <tr className="text-muted">
                    <Td colSpan={4} className="text-xs">
                      Indirectos de campo que declara la integración del precio
                    </Td>
                    <Td align="right" className="text-xs tabular-nums">
                      {money(data.indirectos_campo)}
                    </Td>
                  </tr>
                )}
              </tfoot>
            </table>
          </div>
          <div className="mt-4 space-y-2">
            {programa.notas.map((nota) => (
              <Callout key={nota} tone={notaTone(nota)}>
                {nota}
              </Callout>
            ))}
          </div>
        </>
      )}
    </Card>
  );
}
