"use client";

/**
 * El catálogo de la convocante: el documento que manda en una licitación.
 *
 * Aquí la pantalla no propone nada. Las claves, el orden y las cantidades son
 * de la convocante y se muestran tal cual, porque eso es lo que hay que
 * devolver. Lo único que Klave pone al lado es la cantidad que sostiene el
 * plano, y esa columna es la razón de ser de la pantalla: una diferencia entre
 * las dos es dinero, en un sentido o en el otro, y sólo sirve verla antes de
 * firmar.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { FileArrowUp, Scales, Warning } from "@phosphor-icons/react";
import {
  getCatalogoConvocante,
  money,
  subirCatalogoConvocante,
  type CatalogoConvocante,
  type RenglonConvocante,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  Metric,
  PageHeader,
  SectionTitle,
  Skeleton,
  Td,
  Th,
} from "@/components/ui";

/** Una diferencia de cantidad, dicha en la dirección en que duele. */
function Diferencia({ renglon }: { renglon: RenglonConvocante }) {
  if (renglon.quantity_engine === null || renglon.diferencia_pct === null) {
    return <span className="text-faint">—</span>;
  }
  const pct = renglon.diferencia_pct;
  if (Math.abs(pct) <= 5) {
    return <span className="text-muted tabular-nums">{pct >= 0 ? "+" : ""}{pct.toFixed(0)} %</span>;
  }
  // Positivo = el plano tiene más que el catálogo: obra que se ejecuta y no se
  // cobra. Negativo = el catálogo tiene más que el plano: monto sin obra.
  return (
    <Badge tone={pct > 0 ? "danger" : "warning"}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(0)} %
    </Badge>
  );
}

export default function ContratoPage() {
  const { id } = useParams<{ id: string }>();
  const [catalogo, setCatalogo] = useState<CatalogoConvocante | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const archivo = useRef<HTMLInputElement>(null);

  const leer = useCallback(async () => {
    try {
      setCatalogo(await getCatalogoConvocante(id));
    } catch {
      setError("No se pudo leer el catálogo del contrato.");
    }
  }, [id]);

  useEffect(() => {
    let vivo = true;
    getCatalogoConvocante(id)
      .then((c) => vivo && setCatalogo(c))
      .catch(() => vivo && setError("No se pudo leer el catálogo del contrato."));
    return () => {
      vivo = false;
    };
  }, [id]);

  async function subir(file: File) {
    setCargando(true);
    setError(null);
    try {
      setCatalogo(await subirCatalogoConvocante(id, file, file.name.replace(/\.\w+$/, ""),
        getBrowserActor()));
    } catch {
      setError(
        "No se pudo leer el archivo. Necesita un encabezado con clave, descripción, " +
        "unidad y cantidad.",
      );
      await leer();
    } finally {
      setCargando(false);
      if (archivo.current) archivo.current.value = "";
    }
  }

  const renglones = catalogo?.renglones ?? [];
  const comparables = renglones.filter((r) => r.quantity_engine !== null);
  const discrepantes = comparables.filter(
    (r) => r.diferencia_pct !== null && Math.abs(r.diferencia_pct) > 5,
  );

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Catálogo del contrato"
        sub="El catálogo que manda la convocante: sus claves, su orden y sus cantidades. Klave le pone al lado la cantidad que sostiene el plano, y no lo modifica."
      />

      {error && (
        <div className="mb-5">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <input
          ref={archivo}
          type="file"
          accept=".xlsx,.xls,.csv"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void subir(f);
          }}
        />
        <Button onClick={() => archivo.current?.click()} disabled={cargando}>
          <FileArrowUp size={15} weight="bold" />
          {cargando
            ? "Leyendo…"
            : renglones.length
              ? "Reemplazar catálogo"
              : "Cargar catálogo de la convocante"}
        </Button>
        <span className="text-xs text-muted">
          XLSX o CSV con clave, descripción, unidad y cantidad. Los precios los pones tú.
        </span>
      </div>

      {!catalogo && !error && (
        <Card className="p-5">
          <Skeleton className="h-4 w-56" />
          <div className="mt-5 space-y-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        </Card>
      )}

      {catalogo && renglones.length === 0 && (
        <EmptyState
          icon={<Scales size={22} weight="duotone" />}
          title="Sin catálogo del contrato"
          hint="En obra pública la convocante manda el catálogo y tú devuelves ese mismo documento con precios. Cárgalo y Klave comparará sus cantidades contra las que leyó del plano."
        />
      )}

      {catalogo && renglones.length > 0 && (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            <Metric
              label="Renglones del catálogo"
              value={renglones.length}
              hint={`${comparables.length} los mide Klave del plano`}
              icon={<Scales size={16} weight="duotone" />}
            />
            <Metric
              label="Cantidades que no cuadran"
              value={discrepantes.length}
              hint={
                discrepantes.length
                  ? "Más de 5 % de diferencia contra el plano"
                  : "Ninguna se aparta más de 5 % del plano"
              }
              accent={discrepantes.length ? "danger" : undefined}
              icon={<Warning size={16} weight="duotone" />}
            />
            <Metric
              label="Importe con tus precios"
              value={money(catalogo.total)}
              hint={
                catalogo.sin_precio?.length
                  ? `${catalogo.sin_precio.length} renglones sin precio: el total va corto`
                  : "Todos los renglones tienen precio"
              }
              /* Sin acento a propósito: la que grita es la discrepancia de
                 cantidades, que es la razón de ser de esta pantalla. Dos
                 alarmas juntas no son dos avisos, son ninguno. */
            />
          </div>

          {catalogo.avisos.length > 0 && (
            <div className="mb-6 space-y-2">
              {catalogo.avisos.map((a) => (
                <Callout key={a} tone={a.includes("menos cantidad") ? "danger" : "warning"}>
                  {a}
                </Callout>
              ))}
            </div>
          )}

          <Card className="p-5">
            <SectionTitle sub="En el orden de la convocante. La columna «plano» es lo que Klave midió; la del catálogo no se toca.">
              {catalogo.nombre || "Catálogo del contrato"}
            </SectionTitle>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[860px] text-sm">
                <thead className="border-b border-border">
                  <tr>
                    <Th>Clave</Th>
                    <Th>Concepto</Th>
                    <Th>Unidad</Th>
                    <Th align="right">Catálogo</Th>
                    <Th align="right">Plano</Th>
                    <Th align="right">Δ</Th>
                    <Th align="right">P.U.</Th>
                    <Th align="right">Importe</Th>
                  </tr>
                </thead>
                <tbody>
                  {renglones.map((r) => (
                    <tr key={`${r.orden}-${r.clave}`} className="border-b border-border/60">
                      <Td className="whitespace-nowrap font-mono text-xs">{r.clave}</Td>
                      <Td className="min-w-[240px]">
                        {r.description}
                        <span className="mt-0.5 block text-xs text-muted">
                          {r.concept_code ? (
                            <>
                              Klave lo mide como {r.concept_code}
                              {r.match_score > 0 && ` · ${(r.match_score * 100).toFixed(0)} %`}
                            </>
                          ) : (
                            "Sin concepto equivalente en Klave: cotízalo aparte."
                          )}
                        </span>
                      </Td>
                      <Td className="text-muted">{r.unit}</Td>
                      <Td align="right" className="tabular-nums">
                        {r.quantity.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                      </Td>
                      <Td align="right" className="tabular-nums text-muted">
                        {r.quantity_engine === null
                          ? "—"
                          : r.quantity_engine.toLocaleString("es-MX", {
                              maximumFractionDigits: 2,
                            })}
                      </Td>
                      <Td align="right">
                        <Diferencia renglon={r} />
                      </Td>
                      <Td align="right" className="tabular-nums">
                        {r.unit_price === null ? (
                          <span className="text-warning">sin precio</span>
                        ) : (
                          money(r.unit_price)
                        )}
                      </Td>
                      <Td align="right" className="tabular-nums">
                        {r.amount === null ? (
                          <span className="text-faint">—</span>
                        ) : (
                          money(r.amount)
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 space-y-1 text-xs text-muted">
              {catalogo.notas.map((n) => (
                <p key={n}>{n}</p>
              ))}
              <p>
                Las cantidades de la convocante son el contrato: Klave no las corrige.
                Una diferencia se aclara en junta y se firma, o no.
              </p>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
