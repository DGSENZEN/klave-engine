"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowRight, Check, MagnifyingGlass } from "@phosphor-icons/react";
import {
  adoptFromBase,
  browseBase,
  type BaseRow,
  type BaseSource,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { money2 } from "@/lib/format";
import { SelectionBar } from "@/components/SelectionBar";
import { Badge, Button, Callout, Checkbox, Input, Select, Skeleton, Td, Th } from "@/components/ui";

/**
 * La hoja de la base: todas las publicaciones e importaciones en una sola
 * tabla, con filtros por partida, fuente y región. «Traer» es la acción de
 * fila (Enter sobre la fila enfocada) y la de selección; una fila que ya
 * está en el taller lo dice y no se vuelve a traer.
 */
const PARTIDAS: { key: string; label: string }[] = [
  { key: "preliminares", label: "Preliminares" },
  { key: "terracerias", label: "Terracerías" },
  { key: "cimentacion", label: "Cimentación" },
  { key: "estructura", label: "Estructura" },
  { key: "albanileria", label: "Albañilería" },
  { key: "acabados", label: "Acabados" },
  { key: "hidraulica", label: "Hidráulica" },
  { key: "sanitaria", label: "Sanitaria" },
  { key: "electrica", label: "Eléctrica" },
  { key: "canceleria", label: "Cancelería" },
  { key: "herreria", label: "Herrería" },
  { key: "pavimentos", label: "Pavimentos" },
  { key: "urbanizacion", label: "Urbanización" },
];

const PAGE = 50;

export function BaseSheet({
  initialPartida,
  onChanged,
  onError,
  onNotice,
}: {
  initialPartida?: string;
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [partida, setPartida] = useState(initialPartida ?? "");
  const [source, setSource] = useState("");
  const [region, setRegion] = useState("");
  const [offset, setOffset] = useState(0);
  const [rows, setRows] = useState<BaseRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [sources, setSources] = useState<BaseSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(() => new Set());
  const [bringing, setBringing] = useState(false);
  const [focusRef, setFocusRef] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    const handle = window.setTimeout(() => {
      setLoading(true);
      setFailed(false);
      browseBase({ q: query.trim(), partida, source, region, limit: PAGE, offset })
        .then((page) => {
          if (!active) return;
          setRows(page.rows);
          setTotal(page.total);
          setSources(page.sources);
        })
        .catch(() => {
          if (!active) return;
          setRows([]);
          setFailed(true);
        })
        .finally(() => active && setLoading(false));
    }, 200);
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, [query, partida, source, region, offset, attempt]);

  const regions = useMemo(
    () => [...new Set(sources.map((s) => s.region))].sort(),
    [sources],
  );

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  async function bring(refIds: number[]) {
    if (refIds.length === 0) return;
    setBringing(true);
    try {
      const result = await adoptFromBase(refIds, getBrowserActor());
      const skipped = result.skipped.length
        ? ` · ${result.skipped.length} no: ${result.skipped
            .slice(0, 2)
            .map((s) => s.reason)
            .join(" / ")}${result.skipped.length > 2 ? "…" : ""}`
        : "";
      onNotice(
        `${result.created.length} concepto${result.created.length === 1 ? "" : "s"} traído${
          result.created.length === 1 ? "" : "s"
        } al taller${skipped}`,
      );
      clearSelection();
      setAttempt((n) => n + 1);
      onChanged();
    } catch {
      onError("No se pudieron traer los renglones al taller.");
    } finally {
      setBringing(false);
    }
  }

  function toggle(refId: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(refId)) next.delete(refId);
      else next.add(refId);
      return next;
    });
  }

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE, total);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-64 flex-1">
          <MagnifyingGlass
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint"
          />
          <Input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOffset(0);
            }}
            placeholder="Buscar en la base: tabique, concreto f'c=250, tubería de cobre 13 mm…"
            className="w-full pl-9"
            aria-label="Buscar en la base"
          />
        </div>
        <Select
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setOffset(0);
          }}
          aria-label="Fuente"
        >
          <option value="">Todas las fuentes</option>
          {sources.map((s) => (
            <option key={s.source_key} value={s.source_key}>
              {s.name}
            </option>
          ))}
        </Select>
        <Select
          value={region}
          onChange={(e) => {
            setRegion(e.target.value);
            setOffset(0);
          }}
          aria-label="Región"
        >
          <option value="">Toda región</option>
          {regions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Partida">
        <button
          type="button"
          onClick={() => {
            setPartida("");
            setOffset(0);
          }}
          className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
            partida === ""
              ? "border-foreground bg-foreground text-surface"
              : "border-border text-muted hover:text-foreground"
          }`}
        >
          Todas
        </button>
        {PARTIDAS.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => {
              setPartida(partida === p.key ? "" : p.key);
              setOffset(0);
            }}
            className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
              partida === p.key
                ? "border-foreground bg-foreground text-surface"
                : "border-border text-muted hover:text-foreground"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {rows === null ? (
        <div className="mt-3 space-y-2" aria-busy="true">
          <Skeleton className="h-10" />
          <Skeleton className="h-10" />
          <Skeleton className="h-10 w-3/4" />
        </div>
      ) : failed ? (
        <div className="mt-3">
          <Callout
            tone="danger"
            action={
              <Button size="sm" onClick={() => setAttempt((n) => n + 1)}>
                Reintentar
              </Button>
            }
          >
            La base no respondió.
          </Callout>
        </div>
      ) : rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">
          {sources.length === 0
            ? "Todavía no hay publicaciones en la base: descarga e importa las de arriba."
            : "Nada coincide con esos filtros."}
        </p>
      ) : (
        <div className={`mt-3 overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <Th className="w-8 px-3">
                  <Checkbox
                    aria-label="Seleccionar la página"
                    checked={rows.every((r) => selected.has(r.ref_id) || r.in_taller)}
                    onChange={(e) =>
                      setSelected((current) => {
                        const next = new Set(current);
                        for (const r of rows) {
                          if (r.in_taller) continue;
                          if (e.target.checked) next.add(r.ref_id);
                          else next.delete(r.ref_id);
                        }
                        return next;
                      })
                    }
                  />
                </Th>
                <Th>Clave</Th>
                <Th>Concepto</Th>
                <Th>Unidad</Th>
                <Th align="right">Precio</Th>
                <Th className="px-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const regionesRaw = (row.extra as Record<string, unknown> | null)?.regiones;
                const regiones =
                  regionesRaw && typeof regionesRaw === "object"
                    ? Object.keys(regionesRaw as Record<string, number>).length
                    : 0;
                const focused = focusRef === row.ref_id;
                return (
                  <tr
                    key={row.ref_id}
                    tabIndex={0}
                    onFocus={() => setFocusRef(row.ref_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !row.in_taller) {
                        e.preventDefault();
                        void bring([row.ref_id]);
                      }
                      if (e.key === " ") {
                        e.preventDefault();
                        if (!row.in_taller) toggle(row.ref_id);
                      }
                    }}
                    className={`border-b border-border align-top outline-none last:border-0 ${
                      focused ? "bg-accent-soft/40 shadow-[inset_3px_0_0_var(--accent)]" : ""
                    } ${selected.has(row.ref_id) ? "bg-surface-2/60" : ""}`}
                  >
                    <Td className="px-3">
                      {row.in_taller ? (
                        <Check size={14} weight="bold" className="text-success" aria-label="Ya en el taller" />
                      ) : (
                        <Checkbox
                          aria-label={`Seleccionar ${row.clave}`}
                          checked={selected.has(row.ref_id)}
                          onChange={() => toggle(row.ref_id)}
                        />
                      )}
                    </Td>
                    <Td className="font-mono text-xs">{row.clave}</Td>
                    <Td>
                      <div>{row.description}</div>
                      <div className="text-xs text-faint">
                        {row.group_description ? `${row.group_description} · ` : ""}
                        {row.source_name} · {row.source_vigencia}
                        {row.source_kind === "matrices" && (
                          <>
                            {" · "}
                            <Badge tone="accent">con matriz</Badge>
                          </>
                        )}
                      </div>
                    </Td>
                    <Td className="text-muted">{row.unit}</Td>
                    <Td align="right" className="tabular">
                      {money2(row.price)}
                      {regiones > 1 && (
                        <div className="text-[11px] text-faint">{regiones} regiones</div>
                      )}
                    </Td>
                    <Td className="px-3">
                      {row.in_taller ? (
                        <span className="text-xs text-muted">en el taller</span>
                      ) : (
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={bringing}
                          onClick={() => bring([row.ref_id])}
                        >
                          Traer <ArrowRight size={13} />
                        </Button>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="flex items-center justify-between gap-3 px-1 py-2 text-xs text-muted">
            <span className="tabular">
              {pageStart.toLocaleString("es-MX")}–{pageEnd.toLocaleString("es-MX")} de{" "}
              {total.toLocaleString("es-MX")}
            </span>
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}
              >
                Anterior
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Siguiente
              </Button>
            </div>
          </div>
        </div>
      )}

      <SelectionBar count={selected.size} noun="renglones" onClear={clearSelection}>
        <Button
          size="sm"
          variant="primary"
          disabled={bringing}
          onClick={() => bring([...selected])}
        >
          {bringing ? "Trayendo…" : `Traer ${selected.size} al taller`}
        </Button>
      </SelectionBar>
    </div>
  );
}
