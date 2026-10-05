"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DownloadSimple, GitDiff, MapTrifold } from "@phosphor-icons/react";
import {
  apiMessage,
  cambiosQuery,
  downloadFile,
  getCambios,
  getRevisiones,
  labelRevision,
  money2,
  type CambioElemento,
  type CambiosState,
  type Revision,
} from "@/lib/api";
import { useProjectLive } from "@/components/ProjectLive";
import {
  Badge,
  Button,
  Callout,
  EmptyState,
  Input,
  Metric,
  PageHeader,
  Select,
  Skeleton,
  Td,
  Th,
  type BadgeTone,
} from "@/components/ui";

const TIPO_LABEL: Record<CambioElemento["tipo"], string> = {
  agregado: "Agregado",
  eliminado: "Eliminado",
  movido: "Movido",
  modificado: "Modificado",
};
const TIPO_TONE: Record<CambioElemento["tipo"], BadgeTone> = {
  agregado: "success",
  eliminado: "danger",
  movido: "accent",
  modificado: "warning",
};

/**
 * Qué cambió entre dos revisiones del plano: por concepto en cantidades y
 * pesos, por elemento con su liga al visor, y el libro de aditivas y
 * deductivas. Si los planos son los mismos, lo dice: entonces cambió la
 * lectura, no el proyecto.
 */
export default function CambiosPage() {
  const { id } = useParams<{ id: string }>();
  const { latestEvent } = useProjectLive();
  const [revs, setRevs] = useState<Revision[] | null>(null);
  const [antes, setAntes] = useState<string>("");
  const [despues, setDespues] = useState<string>("");
  const [data, setData] = useState<CambiosState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<CambioElemento["tipo"] | "">("");
  const [nombre, setNombre] = useState<{ run: string; label: string } | null>(null);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getRevisiones(id)
        .then((r) => alive && setRevs(r))
        .catch(() => alive && setRevs([]));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [id, latestEvent?.seq]);

  useEffect(() => {
    if (!revs || revs.length < 2) return;
    let alive = true;
    const handle = window.setTimeout(() => {
      getCambios(id, antes || undefined, despues || undefined)
        .then((d) => {
          if (!alive) return;
          setData(d);
          setError(null);
        })
        .catch((e) => alive && setError(apiMessage(e, "No se pudieron comparar las lecturas.")));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [id, revs, antes, despues]);

  const elementos = useMemo(
    () => (data?.elementos ?? []).filter((e) => !filtro || e.tipo === filtro),
    [data, filtro],
  );

  async function guardarNombre() {
    if (!nombre || !nombre.label.trim()) return;
    try {
      await labelRevision(id, nombre.run, nombre.label.trim());
      setNombre(null);
      setRevs(await getRevisiones(id));
    } catch (e) {
      setError(apiMessage(e, "No se pudo nombrar la revisión."));
    }
  }

  if (!revs) return <Skeleton className="m-6 h-64" />;

  if (revs.length < 2) {
    return (
      <div className="p-6">
        <PageHeader title="Cambios entre revisiones" sub="Qué cambió entre una revisión del plano y otra." />
        <EmptyState
          icon={<GitDiff size={22} weight="duotone" />}
          title="Hace falta una segunda lectura"
          hint="Cuando llegue la siguiente revisión del plano, súbela en el Resumen y reprocesa: aquí verás qué cambió, en cantidades y en pesos, elemento por elemento."
          action={
            <Link href={`/proyecto/${id}/resumen`} className="underline">
              Ir al resumen
            </Link>
          }
        />
      </div>
    );
  }

  const opciones = revs.map((r) => ({ value: r.run_id, label: r.label }));
  const r = data?.resumen ?? {};

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Cambios entre revisiones"
        sub="Por concepto en cantidades y pesos, por elemento con su lugar en el plano."
        actions={
          data && (
            <Button
              onClick={() =>
                void downloadFile(
                  `/projects/${id}/cambios.xlsx${cambiosQuery(data.antes, data.despues)}`,
                  "aditivas_deductivas.xlsx",
                )
              }
            >
              <DownloadSimple size={15} weight="bold" /> Aditivas y deductivas (Excel)
            </Button>
          )
        }
      />

      <div className="mb-5 flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted">
          Antes
          <Select
            value={antes || data?.antes || ""}
            onChange={(e) => setAntes(e.target.value)}
            className="mt-1 block min-w-56"
          >
            {opciones.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </label>
        <label className="text-xs text-muted">
          Después
          <Select
            value={despues || data?.despues || ""}
            onChange={(e) => setDespues(e.target.value)}
            className="mt-1 block min-w-56"
          >
            {opciones.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </label>
        {nombre ? (
          <span className="flex items-end gap-1">
            <Input
              autoFocus
              value={nombre.label}
              onChange={(e) => setNombre({ ...nombre, label: e.target.value })}
              onKeyDown={(e) => {
                if (e.key === "Enter") void guardarNombre();
                if (e.key === "Escape") setNombre(null);
              }}
              aria-label="Nombre de la revisión"
              className="w-40"
            />
            <Button size="sm" variant="primary" onClick={() => void guardarNombre()}>
              Guardar
            </Button>
          </span>
        ) : (
          data && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                const run = data.despues;
                setNombre({ run, label: revs.find((x) => x.run_id === run)?.label ?? "" });
              }}
            >
              Nombrar «después» (Rev C, ejecutivo…)
            </Button>
          )
        )}
      </div>

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {data && data.mismo_plano === true && (
        <div className="mb-4">
          <Callout tone="info">
            Las dos lecturas leyeron <strong>los mismos planos</strong>: estos cambios son de
            Klave (una versión que lee distinto), no del proyecto. No son aditivas ni deductivas.
          </Callout>
        </div>
      )}
      {data && data.mismo_plano === null && (
        <div className="mb-4">
          <Callout tone="warning">
            {data.misma_version === false
              ? "Entre estas lecturas cambió la versión de Klave y la lectura anterior no guardó qué planos leyó: no se sabe si estos cambios son del plano o de la lectura. "
              : "La lectura anterior no guardó qué planos leyó: no se sabe si cambió el plano. "}
            Las lecturas nuevas ya lo guardan.
          </Callout>
        </div>
      )}

      {!data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-5">
            <Metric label="Diferencia a precio de hoy" value={money2(data.importe_diferencia)}
              hint={data.importe_sin_precio ? `${data.importe_sin_precio} conceptos cambiaron sin precio: no están en la suma.` : undefined} />
            {(["agregado", "eliminado", "movido", "modificado"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setFiltro(filtro === t ? "" : t)} className="text-left">
                <Metric label={TIPO_LABEL[t] + "s"} value={String(r[t] ?? 0)} />
              </button>
            ))}
          </div>

          <h3 className="mb-2 text-sm font-semibold">Por concepto</h3>
          {data.conceptos.length === 0 ? (
            <p className="mb-6 text-sm text-muted">Ninguna cantidad cambió.</p>
          ) : (
            <div className="mb-8 overflow-x-auto rounded-lg border border-border bg-surface">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-surface-2">
                    <Th className="px-4">Concepto</Th>
                    <Th align="right">Antes</Th>
                    <Th align="right">Después</Th>
                    <Th align="right">Diferencia</Th>
                    <Th align="right" className="px-4">Importe</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.conceptos.map((c) => (
                    <tr key={c.concept_code} className="border-b border-border last:border-0">
                      <Td className="px-4">
                        <div>{c.descripcion}</div>
                        <div className="text-[11px] text-faint">
                          {Object.entries(c.elementos)
                            .map(([t, n]) => `${n} ${TIPO_LABEL[t as CambioElemento["tipo"]].toLowerCase()}${n === 1 ? "" : "s"}`)
                            .join(" · ")}
                          {" · "}
                          <Link
                            href={`/proyecto/${id}/plano?concept=${encodeURIComponent(c.concept_code)}&cambios=${encodeURIComponent(data.antes)}`}
                            className="underline"
                          >
                            ver en el plano
                          </Link>
                        </div>
                      </Td>
                      <Td align="right" className="tabular whitespace-nowrap">{c.cantidad_antes.toLocaleString("es-MX", { maximumFractionDigits: 2 })} {c.unidad}</Td>
                      <Td align="right" className="tabular whitespace-nowrap">{c.cantidad_despues.toLocaleString("es-MX", { maximumFractionDigits: 2 })} {c.unidad}</Td>
                      <Td align="right" className={`tabular whitespace-nowrap font-medium ${c.diferencia > 0 ? "text-success" : c.diferencia < 0 ? "text-danger" : ""}`}>
                        {c.diferencia > 0 ? "+" : ""}
                        {c.diferencia.toLocaleString("es-MX", { maximumFractionDigits: 2 })}
                      </Td>
                      <Td align="right" className="tabular px-4 whitespace-nowrap">
                        {c.importe_diferencia == null ? <span className="text-muted">sin precio</span> : money2(c.importe_diferencia)}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 className="mb-2 text-sm font-semibold">
            Por elemento{filtro ? ` · ${TIPO_LABEL[filtro].toLowerCase()}s` : ""}
            {filtro && (
              <button type="button" onClick={() => setFiltro("")} className="ml-2 text-xs font-normal text-muted underline">
                ver todos
              </button>
            )}
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <table className="w-full text-sm">
              <tbody>
                {elementos.slice(0, 500).map((e, i) => {
                  const bbox = e.bbox_despues ?? e.bbox_antes;
                  return (
                    <tr key={`${e.antes_id}-${e.despues_id}-${i}`} className="border-b border-border last:border-0">
                      <Td className="px-4"><Badge tone={TIPO_TONE[e.tipo]}>{TIPO_LABEL[e.tipo]}</Badge></Td>
                      <Td>{e.familia} {e.marca && <span className="font-mono text-xs text-muted">{e.marca}</span>}</Td>
                      <Td className="text-xs text-muted">{e.hoja}</Td>
                      <Td className="text-xs">
                        {e.tipo === "movido"
                          ? `se movió ${e.movido_m.toFixed(2)} m`
                          : e.campos.map((f) => `${f.campo}: ${f.antes} → ${f.despues}`).join(" · ")}
                      </Td>
                      <Td align="right" className="px-4">
                        {bbox && (
                          <Link
                            href={`/proyecto/${id}/plano?bbox=${bbox.map((v) => v.toFixed(3)).join(",")}&cambios=${encodeURIComponent(data.antes)}`}
                            className="inline-flex items-center gap-1 text-xs text-muted underline"
                          >
                            <MapTrifold size={12} /> plano
                          </Link>
                        )}
                      </Td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {elementos.length > 500 && (
              <p className="px-4 py-2 text-xs text-muted">
                Se muestran 500 de {elementos.length}; el Excel los trae todos.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
