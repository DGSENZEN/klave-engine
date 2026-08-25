"use client";

/**
 * El generador de una estimación: dónde se midió cada cantidad que se cobra.
 *
 * La tabla se lee en la dirección en que se trabaja —ubicación, cuántas veces,
 * medidas, resultado— y el total va abajo confrontado contra lo que el renglón
 * dice cobrar. Cuando las dos cifras no coinciden, la que está mal es la
 * cobrada: la cantidad sale del generador, no al revés. Por eso el botón dice
 * «usar el total del generador» y no existe el inverso.
 *
 * Las columnas que se muestran dependen de la unidad. Un concepto en m² no
 * tiene altura y enseñar una casilla de altura invita a llenarla; una casilla
 * llena que no participa en la cuenta es una discusión de media hora en una
 * revisión.
 *
 * Lo que falta se queda faltando. Una dimensión vacía deja la línea sin
 * resultado y lo dice en su lugar, en vez de valer 1.00 y producir un número
 * que parece bien.
 */

import { Plus, Trash } from "@phosphor-icons/react";
import {
  TOLERANCIA_GENERADOR,
  calcularLinea,
  lineaGeneradorVacia,
  type LineaGenerador,
} from "@/lib/api";
import { Button, IconButton, Input } from "@/components/ui";

const ETIQUETA: Record<string, string> = {
  largo: "Largo",
  ancho: "Ancho",
  alto: "Alto",
};

export function GeneradorEditor({
  lineas,
  unidad,
  unidades,
  cantidad,
  onChange,
  onUsarTotal,
}: {
  lineas: LineaGenerador[];
  unidad: string;
  unidades: Record<string, string[]>;
  cantidad: number;
  onChange: (lineas: LineaGenerador[]) => void;
  onUsarTotal: (total: number) => void;
}) {
  const dims = unidades[unidad.trim().toLowerCase()];
  const conocida = dims !== undefined;
  const calculadas = lineas.map((l) => calcularLinea(l, unidad, unidades));
  const total = Math.round(calculadas.reduce((s, c) => s + (c.medida ?? 0), 0) * 10000) / 10000;
  const incompletas = calculadas.filter((c) => c.medida === null).length;
  const diferencia = Math.round((total - cantidad) * 10000) / 10000;
  const cuadra = incompletas === 0 && Math.abs(diferencia) <= TOLERANCIA_GENERADOR;

  function set(i: number, campo: keyof LineaGenerador, valor: string) {
    const siguiente = lineas.map((l, j) => {
      if (j !== i) return l;
      if (campo === "ubicacion" || campo === "nota") return { ...l, [campo]: valor };
      // Vacío es vacío, no cero: un cero se multiplica, un vacío se ve.
      const n = valor.trim() === "" ? null : Number(valor);
      if (campo === "veces") return { ...l, veces: n ?? 1 };
      return { ...l, [campo]: n };
    });
    onChange(siguiente);
  }

  return (
    <div className="rounded-lg border border-border bg-surface-2/40 p-3">
      {!conocida && (
        <p className="mb-2 text-xs text-warning">
          La unidad «{unidad}» no tiene una fórmula conocida: captura la medida de cada
          línea a mano. El motor no va a suponer cómo se multiplica.
        </p>
      )}

      {lineas.length === 0 ? (
        <p className="text-xs text-muted">
          Sin líneas de generador. Una estimación sin respaldo de medición se regresa.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs">
            <thead className="text-muted">
              <tr>
                <th className="px-1 pb-1 text-left font-medium">Ubicación</th>
                <th className="px-1 pb-1 text-right font-medium">Veces</th>
                {conocida &&
                  dims.map((d) => (
                    <th key={d} className="px-1 pb-1 text-right font-medium">
                      {ETIQUETA[d] ?? d}
                    </th>
                  ))}
                {(!conocida || dims.length === 0) && (
                  <th className="px-1 pb-1 text-right font-medium">Medida</th>
                )}
                <th className="px-1 pb-1 text-right font-medium">Resultado</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {lineas.map((l, i) => {
                const c = calculadas[i];
                return (
                  <tr key={i} className="border-t border-border/50">
                    <td className="px-1 py-1">
                      <Input
                        value={l.ubicacion}
                        placeholder="Eje A-3, nivel 2"
                        onChange={(e) => set(i, "ubicacion", e.target.value)}
                        className="w-full px-2 py-1 text-xs"
                        aria-label={`Ubicación de la línea ${i + 1}`}
                      />
                    </td>
                    <td className="px-1 py-1">
                      <Input
                        type="number"
                        step="any"
                        value={l.veces}
                        onChange={(e) => set(i, "veces", e.target.value)}
                        className="w-16 px-2 py-1 text-right text-xs"
                        aria-label={`Veces en la línea ${i + 1}`}
                      />
                    </td>
                    {conocida &&
                      dims.map((d) => (
                        <td key={d} className="px-1 py-1">
                          <Input
                            type="number"
                            step="any"
                            value={
                              (l as unknown as Record<string, number | null>)[d] ?? ""
                            }
                            onChange={(e) => set(i, d as keyof LineaGenerador, e.target.value)}
                            className={`w-20 px-2 py-1 text-right text-xs ${
                              c.falta.includes(d) ? "border-warning" : ""
                            }`}
                            aria-label={`${ETIQUETA[d] ?? d} en la línea ${i + 1}`}
                          />
                        </td>
                      ))}
                    {(!conocida || dims.length === 0) && (
                      <td className="px-1 py-1">
                        <Input
                          type="number"
                          step="any"
                          value={l.medida_directa ?? ""}
                          onChange={(e) => set(i, "medida_directa", e.target.value)}
                          className="w-24 px-2 py-1 text-right text-xs"
                          aria-label={`Medida de la línea ${i + 1}`}
                        />
                      </td>
                    )}
                    <td className="px-1 py-1 text-right tabular-nums">
                      {c.medida === null ? (
                        <span className="text-warning" title={`Falta ${c.falta.join(", ")}`}>
                          falta {c.falta.join(", ")}
                        </span>
                      ) : (
                        <span title={c.formula}>
                          {c.medida.toLocaleString("es-MX", { maximumFractionDigits: 4 })}
                        </span>
                      )}
                    </td>
                    <td className="px-1 py-1 text-right">
                      <IconButton
                        onClick={() => onChange(lineas.filter((_, j) => j !== i))}
                        aria-label={`Quitar la línea ${i + 1}`}
                      >
                        <Trash size={14} />
                      </IconButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <Button
          variant="ghost"
          onClick={() => onChange([...lineas, lineaGeneradorVacia()])}
          className="text-xs"
        >
          <Plus size={14} /> Agregar línea
        </Button>

        {lineas.length > 0 && (
          <div className="flex items-center gap-3 text-xs">
            <span className={cuadra ? "text-success" : "text-warning"}>
              Generador: {total.toLocaleString("es-MX", { maximumFractionDigits: 4 })}{" "}
              {unidad}
              {incompletas > 0 && ` · ${incompletas} sin calcular`}
              {incompletas === 0 && !cuadra && (
                <> · se cobran {cantidad.toLocaleString("es-MX", { maximumFractionDigits: 4 })}</>
              )}
            </span>
            {incompletas === 0 && !cuadra && (
              <Button variant="secondary" onClick={() => onUsarTotal(total)} className="text-xs">
                Usar el total del generador
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
