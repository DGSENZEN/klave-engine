"use client";

/**
 * Las instalaciones que el levantamiento ya leyó y el presupuesto no cobra.
 *
 * Una capa llamada `00-SANITARIA` en una hoja que el motor clasificó como
 * sanitaria es casi seguramente tubería sanitaria — casi. Por eso esto es una
 * lista de propuestas y no un resultado: cada renglón trae la cantidad que
 * produciría, la hoja de la que salió y la razón por la que se propone, y
 * nadie lo aplica hasta que alguien lo palomea.
 *
 * Las casillas empiezan vacías a propósito. Marcar es un acto; desmarcar
 * quince cosas que ya venían marcadas no lo es, y ese es exactamente el
 * mecanismo por el que la gente aprueba lo que no leyó.
 */

import { useState } from "react";
import { Link, Plugs } from "@phosphor-icons/react";
import type { MapeoSugerido } from "@/lib/api";
import { Button, Callout, Card, Checkbox, SectionTitle, Td, Th } from "@/components/ui";

const DISCIPLINA_LABEL: Record<string, string> = {
  hidraulica: "Hidráulica",
  sanitaria: "Sanitaria",
  electrica: "Eléctrica",
  gas: "Gas",
  aire: "Aire acondicionado",
};

function clave(s: MapeoSugerido): string {
  return `${s.kind}:${s.pattern}:${s.concept_code}`;
}

export function MapeosSugeridos({
  sugerencias,
  busy,
  onAssign,
}: {
  sugerencias: MapeoSugerido[];
  busy: boolean;
  onAssign: (elegidas: MapeoSugerido[]) => void;
}) {
  const [elegidas, setElegidas] = useState<Set<string>>(new Set());
  if (!sugerencias.length) return null;

  const seleccion = sugerencias.filter((s) => elegidas.has(clave(s)));

  function alternar(s: MapeoSugerido) {
    const key = clave(s);
    const siguiente = new Set(elegidas);
    if (siguiente.has(key)) siguiente.delete(key);
    else siguiente.add(key);
    setElegidas(siguiente);
  }

  return (
    <Card className="p-5">
      <SectionTitle sub="Capas y bloques de instalaciones que reconoce la biblioteca del motor. Son propuestas: revisa la razón, palomea las que apliquen y asígnalas.">
        Instalaciones sin asignar
      </SectionTitle>

      <div className="mb-4">
        <Callout tone="info">
          {sugerencias.length}{" "}
          {sugerencias.length === 1 ? "capa o bloque" : "capas y bloques"} de
          instalaciones ya medidos que hoy no entran al presupuesto. Las instalaciones
          suelen ser entre el 15 y el 25 % del costo de un edificio.
        </Callout>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b border-border">
            <tr>
              <Th className="w-8" />
              <Th>Capa o bloque</Th>
              <Th>Disciplina</Th>
              <Th align="right">Cantidad</Th>
              <Th>Concepto propuesto</Th>
            </tr>
          </thead>
          <tbody>
            {sugerencias.map((s) => {
              const key = clave(s);
              return (
                <tr key={key} className="border-b border-border/60 align-top">
                  <Td>
                    <Checkbox
                      checked={elegidas.has(key)}
                      onChange={() => alternar(s)}
                      disabled={busy}
                      aria-label={`Asignar ${s.pattern} a ${s.concept_code}`}
                    />
                  </Td>
                  <Td>
                    <span className="font-mono text-xs">{s.pattern}</span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {s.kind === "block" ? "bloque" : "capa"}
                      {s.sheets.length > 0 && ` · ${s.sheets.join(", ")}`}
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap text-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <Plugs size={13} weight="duotone" />
                      {DISCIPLINA_LABEL[s.discipline] ?? s.discipline}
                    </span>
                  </Td>
                  <Td align="right" className="whitespace-nowrap tabular-nums">
                    {s.quantity.toLocaleString("es-MX", { maximumFractionDigits: 2 })}{" "}
                    <span className="text-muted">{s.unit}</span>
                  </Td>
                  <Td>
                    <span className="inline-flex items-center gap-1.5 font-medium">
                      <Link size={13} weight="bold" className="text-muted" />
                      {s.concept_code}
                    </span>
                    <span className="mt-0.5 block max-w-[38ch] text-xs text-muted">
                      {s.reason}
                    </span>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button onClick={() => onAssign(seleccion)} disabled={busy || !seleccion.length}>
          {busy
            ? "Asignando…"
            : seleccion.length === 1
              ? "Asignar la seleccionada"
              : seleccion.length
                ? `Asignar las ${seleccion.length} seleccionadas`
                : "Palomea las que apliquen"}
        </Button>
        <span className="text-xs text-muted">
          Entran como cantidad sin precio hasta que el concepto tenga matriz o un P.U.
          adoptado. La asignación vale para todo el taller y se puede quitar.
        </span>
      </div>
    </Card>
  );
}
