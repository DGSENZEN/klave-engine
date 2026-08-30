"use client";

/**
 * El desglose de indirectos de campo: un renglón por gasto real, no un
 * porcentaje desnudo. Ver packages/klave_engine/costing/indirectos.py — un
 * documento se arma renglón por renglón, con importe y categoría contable;
 * eso es lo que se captura aquí.
 *
 * **El personal no se vuelve a teclear.** La plantilla de campo (más abajo
 * en Programa de obra) ya tiene los sueldos, puesto por puesto. El primer
 * renglón de esta tabla lo recuerda, fijo y sin poderse editar, para que
 * nadie lo capture dos veces por accidente.
 *
 * **Un renglón en $0 no es un renglón.** Se ve vacío a propósito — mismo
 * idioma que el sueldo sin capturar de PlantillaCampo — y no suma: hay que
 * captúralo o borrarlo.
 *
 * **La fila fantasma.** Al final de la tabla siempre hay un renglón vacío;
 * en cuanto se teclea algo en él (concepto, categoría, lo que sea) se vuelve
 * un renglón real y aparece un fantasma nuevo debajo, listo para el
 * siguiente. Es el mismo idioma que la matriz de precio unitario del
 * catálogo, con las llaves alineadas por posición para que el cursor no
 * salte al materializar.
 *
 * El share de oficina central es aparte: normalmente es un cociente
 * derivado (costo anual de oficina entre volumen anual de obra en cartera),
 * y aquí se puede fijar a mano — pero sólo con un motivo escrito, porque un
 * número sin motivo es un decreto, no un criterio.
 */

import type { ReactNode } from "react";
import { Trash } from "@phosphor-icons/react";
import type { RubroIndirecto } from "@/lib/api";
import { Card, Input, SectionTitle, Select, Td, Th } from "@/components/ui";

export const CATEGORIAS: Record<string, string> = {
  honorarios_prestaciones: "Honorarios, sueldos y prestaciones",
  depreciacion_mantenimiento_rentas: "Depreciación, mantenimiento y rentas",
  servicios: "Servicios",
  fletes_acarreos: "Fletes y acarreos",
  gastos_oficina: "Gastos de oficina",
  capacitacion: "Capacitación y adiestramiento",
  seguridad_higiene: "Seguridad e higiene",
  seguros_fianzas: "Seguros y fianzas",
  trabajos_previos_auxiliares: "Trabajos previos y auxiliares",
};

const BASE_LABEL: Record<RubroIndirecto["base"], string> = {
  mensual: "Mensual",
  unico: "Único",
};

const RUBRO_VACIO: RubroIndirecto = {
  concepto: "",
  categoria: "servicios",
  importe: 0,
  base: "mensual",
};

/**
 * El renglón-por-renglón de un desglose: concepto, categoría e importe, con
 * la fila fantasma al final. Se usa tal cual para indirectos de campo
 * (`DesgloseCampoCard`, con `base` mensual/único) y para los rubros de
 * oficina central (`IntegracionSection`, con `baseAnual` — los importes ya
 * son anuales y la columna Base no aplica). `children` deja inyectar filas
 * fijas antes de las editables (p. ej. el renglón de personal de campo) sin
 * romper la tabla en dos.
 */
export function RubrosEditor({
  rubros,
  onChange,
  baseAnual,
  children,
}: {
  rubros: RubroIndirecto[];
  onChange: (r: RubroIndirecto[]) => void;
  baseAnual?: boolean;
  children?: ReactNode;
}) {
  const hayCero = rubros.some((r) => r.importe === 0);
  const importeLabel = baseAnual ? "Importe anual" : "Importe";

  // El renglón `rubros.length` es la fila fantasma: no existe todavía en
  // `rubros`, así que tocarla no reemplaza un renglón — lo crea. La llave de
  // React es el mismo índice antes y después de materializar, así que el
  // input no se desmonta y el cursor no salta.
  function set(index: number, patch: Partial<RubroIndirecto>) {
    if (index === rubros.length) {
      onChange([...rubros, { ...RUBRO_VACIO, ...patch }]);
      return;
    }
    onChange(rubros.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function remove(index: number) {
    onChange(rubros.filter((_, i) => i !== index));
  }

  const filas = [...rubros, RUBRO_VACIO];

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="border-b border-border">
            <tr>
              <Th>Concepto</Th>
              <Th>Categoría</Th>
              <Th align="right">{importeLabel}</Th>
              {!baseAnual && <Th>Base</Th>}
              <Th />
            </tr>
          </thead>
          <tbody>
            {children}
            {filas.map((rubro, index) => {
              const fantasma = index === rubros.length;
              return (
                <tr key={index} className="border-b border-border/60 last:border-0">
                  <Td className="min-w-[200px]">
                    <Input
                      value={rubro.concepto}
                      onChange={(e) => set(index, { concepto: e.target.value })}
                      placeholder={fantasma ? "Nuevo renglón — p. ej. Renta de oficina de campo" : "Concepto"}
                      className="w-full px-2 py-1 text-sm"
                      aria-label={fantasma ? "Concepto de nuevo renglón" : `Concepto ${index + 1}`}
                    />
                  </Td>
                  <Td>
                    <Select
                      size="sm"
                      value={rubro.categoria}
                      onChange={(e) => set(index, { categoria: e.target.value })}
                      aria-label={
                        fantasma ? "Categoría de nuevo renglón" : `Categoría de ${rubro.concepto || index + 1}`
                      }
                    >
                      {Object.entries(CATEGORIAS).map(([val, label]) => (
                        <option key={val} value={val}>
                          {label}
                        </option>
                      ))}
                    </Select>
                  </Td>
                  <Td align="right">
                    <Input
                      type="number"
                      min={0}
                      step="any"
                      value={rubro.importe || ""}
                      onChange={(e) => set(index, { importe: Number(e.target.value) })}
                      placeholder="sin capturar"
                      className="w-32 px-2 py-1 text-right text-sm tabular"
                      aria-label={
                        fantasma
                          ? `${importeLabel} de nuevo renglón`
                          : `${importeLabel} de ${rubro.concepto || index + 1}`
                      }
                    />
                  </Td>
                  {!baseAnual && (
                    <Td>
                      <Select
                        size="sm"
                        value={rubro.base}
                        onChange={(e) =>
                          set(index, { base: e.target.value as RubroIndirecto["base"] })
                        }
                        aria-label={fantasma ? "Base de nuevo renglón" : `Base de ${rubro.concepto || index + 1}`}
                      >
                        {Object.entries(BASE_LABEL).map(([val, label]) => (
                          <option key={val} value={val}>
                            {label}
                          </option>
                        ))}
                      </Select>
                    </Td>
                  )}
                  <Td align="right">
                    {!fantasma && (
                      <button
                        type="button"
                        onClick={() => remove(index)}
                        className="text-muted transition hover:text-danger"
                        aria-label={`Quitar ${rubro.concepto || `renglón ${index + 1}`}`}
                      >
                        <Trash size={15} weight="duotone" />
                      </button>
                    )}
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hayCero && (
        <p className="mt-3 text-xs text-warning">
          Renglones en $0 se muestran vacíos y no suman: captúralos o bórralos.
        </p>
      )}
    </>
  );
}

export function DesgloseCampoCard({
  value,
  onChange,
}: {
  value: { rubros: RubroIndirecto[] } | null;
  onChange: (v: { rubros: RubroIndirecto[] }) => void;
}) {
  const rubros = value?.rubros ?? [];

  return (
    <Card className="p-5">
      <SectionTitle sub="RLOPSRM arts. 211-220. Cada renglón es un gasto real de la obra, con su importe y su categoría contable — un porcentaje desnudo no es un desglose.">
        Desglose de indirectos de campo
      </SectionTitle>
      <RubrosEditor rubros={rubros} onChange={(r) => onChange({ rubros: r })}>
        <tr className="border-b border-border/60">
          <Td colSpan={5} className="text-xs italic text-muted">
            Personal técnico, administrativo y de servicio — se calcula de la plantilla de
            campo (abajo)
          </Td>
        </tr>
      </RubrosEditor>
    </Card>
  );
}

/** El share de oficina central de esta obra: normalmente sale del prorrateo
 * (costo anual de oficina entre volumen anual de obra en cartera). Se puede
 * fijar a mano, pero un porcentaje sin motivo escrito es un decreto — el
 * backend lo ignora y usa el prorrateo derivado. */
export function OficinaShareCard({
  pct,
  motivo,
  onPctChange,
  onMotivoChange,
}: {
  pct: number | null;
  motivo: string;
  onPctChange: (v: number | null) => void;
  onMotivoChange: (v: string) => void;
}) {
  return (
    <Card className="p-5">
      <SectionTitle sub="Sin motivo escrito de al menos 15 caracteres se usa el prorrateo derivado del volumen anual de obra.">
        Oficina central en esta obra
      </SectionTitle>
      <div className="space-y-3">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span className="text-muted">Share de oficina central (%)</span>
          <Input
            type="number"
            min={0}
            max={100}
            step="any"
            value={pct ?? ""}
            placeholder="derivado"
            onChange={(e) => onPctChange(e.target.value === "" ? null : Number(e.target.value))}
            className="w-24 px-2 py-1 text-right tabular"
            aria-label="Share de oficina central"
          />
        </label>
        <div>
          <label htmlFor="oficina-share-motivo" className="mb-1 block text-sm text-muted">
            Motivo del share
          </label>
          <Input
            id="oficina-share-motivo"
            value={motivo}
            onChange={(e) => onMotivoChange(e.target.value)}
            placeholder="Por qué este porcentaje y no el derivado…"
            className="w-full px-3 py-2 text-sm"
          />
          <p className="mt-1 text-xs text-muted">
            Obligatorio, mínimo 15 caracteres — sin motivo escrito se usa el prorrateo
            derivado.
          </p>
        </div>
      </div>
    </Card>
  );
}
