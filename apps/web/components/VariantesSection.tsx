"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { CaretDown, MagicWand, MagnifyingGlass } from "@phosphor-icons/react";
import {
  apiMessage,
  forgetVariantMapping,
  getCatalog,
  getVariants,
  mapVariants,
  money2,
  searchReference,
  setVariantMapping,
  type BoqVariantDetail,
  type CatalogConcept,
  type VariantLine,
  type VariantsState,
} from "@/lib/api";
import { Badge, Button, Callout, Input, Skeleton, Td, Th } from "@/components/ui";

/**
 * «Tu catálogo»: cada variante del plano junto al concepto de la oficina al
 * que corresponde. La automática se aplica y dice por qué; la propuesta es
 * una duda que espera a una persona; «sin equivalente» se queda con el
 * precio del motor. Lo que se decide aquí vale para el siguiente proyecto.
 */

const LABEL: Record<string, string> = {
  automatica: "Automática",
  propuesta: "Por confirmar",
  confirmada: "Confirmada",
  sin_equivalente: "Sin equivalente",
  "": "Sin mapear",
};
const TONE: Record<string, "success" | "warning" | "default" | "accent"> = {
  automatica: "accent",
  propuesta: "warning",
  confirmada: "success",
  sin_equivalente: "default",
  "": "default",
};

type Candidate =
  | { kind: "concept"; code: string; description: string; unit: string }
  | { kind: "reference"; refId: number; clave: string; description: string; unit: string; source: string; price: number };

const unitKey = (u: string) => u.toUpperCase().replace("²", "2").replace("³", "3").trim();

export function VariantesSection({
  projectId,
  actorName,
  reloadKey,
}: {
  projectId: string;
  actorName: string;
  reloadKey?: number;
}) {
  const [state, setState] = useState<VariantsState | null>(null);
  const [failed, setFailed] = useState(false);
  const [concepts, setConcepts] = useState<CatalogConcept[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"dudas" | "todas">("dudas");
  const [open, setOpen] = useState<Set<string>>(() => new Set());
  const [picking, setPicking] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getVariants(projectId)
        .then((s) => {
          if (!alive) return;
          setState(s);
          setFailed(false);
        })
        .catch(() => alive && setFailed(true));
      getCatalog()
        .then((c) => alive && setConcepts(c.concepts.filter((x) => !x.detection_backed)))
        .catch(() => alive && setConcepts([]));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [projectId, reloadKey, version]);

  const lines = useMemo(() => {
    if (!state) return [];
    if (filter === "todas") return state.lines;
    return state.lines.filter((l) =>
      l.variants.some((v) => v.mapping === "propuesta" || v.mapping === ""),
    );
  }, [state, filter]);

  async function run(fn: () => Promise<string | void>) {
    setBusy(true);
    setError(null);
    try {
      const message = await fn();
      if (message) setNotice(message);
      setVersion((n) => n + 1);
    } catch (e) {
      setError(apiMessage(e, "No se pudo guardar el mapeo."));
    } finally {
      setBusy(false);
    }
  }

  function autoMap(rematch: boolean) {
    void run(async () => {
      const r = await mapVariants(projectId, rematch, actorName);
      if (r.sin_catalogo) {
        return "Tu catálogo todavía no tiene conceptos propios: importa tu base de OPUS o Neodata y vuelve a intentarlo";
      }
      return `${r.automatica} se mapearon solas, ${r.propuesta} esperan tu confirmación, ${r.sin_equivalente} sin equivalente en tu catálogo`;
    });
  }

  if (failed) {
    return (
      <Callout tone="info">
        Las variantes aparecen cuando el proyecto ya se procesó y tiene presupuesto.
      </Callout>
    );
  }
  if (!state) return <Skeleton className="h-40 w-full" />;

  const c = state.counts;
  const pendientes = (c.sin_mapear ?? 0) + (c.propuesta ?? 0);
  const total = Object.values(c).reduce((a, b) => a + b, 0);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="text-muted">
          {total} variantes del plano ·{" "}
          <Badge tone="success">{(c.confirmada ?? 0) + (c.automatica ?? 0)} en tu catálogo</Badge>{" "}
          <Badge tone="warning">{c.propuesta ?? 0} por confirmar</Badge>{" "}
          <Badge tone="default">{c.sin_equivalente ?? 0} sin equivalente</Badge>{" "}
          <Badge tone="default">{c.sin_mapear ?? 0} sin mapear</Badge>
        </span>
        <span className="flex-1" />
        <div className="flex items-center gap-1 text-xs">
          <button
            type="button"
            onClick={() => setFilter("dudas")}
            className={`rounded-md px-2 py-1 ${filter === "dudas" ? "bg-surface-2 font-medium" : "text-muted"}`}
          >
            Pendientes
          </button>
          <button
            type="button"
            onClick={() => setFilter("todas")}
            className={`rounded-md px-2 py-1 ${filter === "todas" ? "bg-surface-2 font-medium" : "text-muted"}`}
          >
            Todas
          </button>
        </div>
      </div>

      {(c.sin_mapear ?? 0) > 0 && (
        <div className="mb-4">
          <Callout
            tone="info"
            action={
              <Button size="sm" variant="primary" disabled={busy} onClick={() => autoMap(false)}>
                <MagicWand size={14} weight="bold" /> Buscar en mi catálogo
              </Button>
            }
          >
            {c.sin_mapear} variantes todavía no tienen concepto de tu catálogo. Klave busca el más
            parecido en tus conceptos y en las bases que importaste: lo seguro se aplica solo y lo
            dudoso queda aquí para que lo confirmes.
          </Callout>
        </div>
      )}
      {notice && (
        <div className="mb-4">
          <Callout tone="info" action={<Button size="sm" variant="ghost" onClick={() => setNotice(null)}>Entendido</Button>}>
            {notice}.
          </Callout>
        </div>
      )}
      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {lines.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted">
          {pendientes === 0
            ? "Todas las variantes del plano tienen decisión. Lo que confirmaste se usará en el siguiente proyecto."
            : "Nada que mostrar con este filtro."}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border bg-surface">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-surface-2">
                <Th className="px-4">Lo que dice el plano</Th>
                <Th align="right">Cantidad</Th>
                <Th>Tu catálogo</Th>
                <Th align="right" className="px-4">P.U.</Th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <LineRows
                  key={line.concept_code}
                  line={line}
                  open={open.has(line.concept_code) || filter === "dudas"}
                  onToggle={() =>
                    setOpen((cur) => {
                      const next = new Set(cur);
                      if (next.has(line.concept_code)) next.delete(line.concept_code);
                      else next.add(line.concept_code);
                      return next;
                    })
                  }
                  picking={picking}
                  onPick={setPicking}
                  busy={busy}
                  concepts={concepts}
                  onConfirm={(v, cand) =>
                    void run(async () => {
                      await setVariantMapping(
                        projectId,
                        v.key,
                        cand.kind === "concept"
                          ? { status: "confirmada", target_kind: "concept", target_code: cand.code }
                          : { status: "confirmada", target_kind: "reference", ref_id: cand.refId },
                        actorName,
                      );
                      setPicking(null);
                      return `${v.description.slice(0, 60)} → ${cand.kind === "concept" ? cand.code : cand.clave}`;
                    })
                  }
                  onAccept={(v) =>
                    void run(async () => {
                      // Confirmar la propuesta tal cual: el servidor ya sabe su destino.
                      await setVariantMapping(projectId, v.key, { status: "confirmada" }, actorName);
                    })
                  }
                  onNone={(v) =>
                    void run(async () => {
                      await setVariantMapping(projectId, v.key, { status: "sin_equivalente" }, actorName);
                    })
                  }
                  onForget={(v) =>
                    void run(async () => {
                      await forgetVariantMapping(projectId, v.key, actorName);
                    })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function LineRows({
  line,
  open,
  onToggle,
  picking,
  onPick,
  busy,
  concepts,
  onConfirm,
  onAccept,
  onNone,
  onForget,
}: {
  line: VariantLine;
  open: boolean;
  onToggle: () => void;
  picking: string | null;
  onPick: (key: string | null) => void;
  busy: boolean;
  concepts: CatalogConcept[];
  onConfirm: (v: BoqVariantDetail, c: Candidate) => void;
  onAccept: (v: BoqVariantDetail) => void;
  onNone: (v: BoqVariantDetail) => void;
  onForget: (v: BoqVariantDetail) => void;
}) {
  const shown =
    open ? line.variants : [];
  return (
    <>
      <tr className="cursor-pointer border-b border-border bg-surface-2/50" onClick={onToggle}>
        <td colSpan={4} className="px-4 py-1.5">
          <span className="flex items-center gap-2">
            <CaretDown size={12} weight="bold" className={`text-faint transition-transform ${open ? "" : "-rotate-90"}`} />
            <span className="microlabel">{line.phase}</span>
            <span className="font-medium">{line.description}</span>
            <span className="text-xs text-muted">
              · {line.variants.length} {line.variants.length === 1 ? "variante" : "variantes"}
            </span>
          </span>
        </td>
      </tr>
      {shown.map((v) => (
        <Fragment key={v.key}>
          <tr className="group border-b border-border">
            <Td className="px-4">
              <div className="pl-5">
                <div>{v.description}</div>
                <div className="text-[11px] text-faint">
                  {v.source_detection_count} {v.source_detection_count === 1 ? "elemento" : "elementos"}
                  {v.mapping_reason ? ` · ${v.mapping_reason}` : ""}
                </div>
              </div>
            </Td>
            <Td align="right" className="tabular whitespace-nowrap">
              {v.quantity.toLocaleString("es-MX", { maximumFractionDigits: 2 })} {line.unit}
            </Td>
            <Td>
              <div className="flex flex-wrap items-center gap-2">
                <span title={v.mapping_reason || undefined}>
                  <Badge tone={TONE[v.mapping]}>{LABEL[v.mapping]}</Badge>
                </span>
                {v.clave && (
                  <span className="min-w-0">
                    <span className="font-mono text-xs">{v.clave}</span>{" "}
                    <span className="text-xs text-muted">{v.mapped_description.slice(0, 70)}</span>
                  </span>
                )}
                <span className="ml-auto flex gap-1 opacity-70 group-hover:opacity-100">
                  {v.mapping === "propuesta" && (
                    <Button size="sm" variant="primary" disabled={busy} onClick={() => onAccept(v)}>
                      Confirmar
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => onPick(picking === v.key ? null : v.key)}>
                    {v.clave ? "Cambiar…" : "Elegir…"}
                  </Button>
                  {v.mapping !== "sin_equivalente" && (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => onNone(v)}>
                      Sin equivalente
                    </Button>
                  )}
                  {v.mapping && (
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => onForget(v)} title="Olvidar la decisión; vuelve a «sin mapear»">
                      Olvidar
                    </Button>
                  )}
                </span>
              </div>
            </Td>
            <Td align="right" className="tabular px-4 whitespace-nowrap">
              {v.unit_price == null ? <span className="text-muted">sin precio</span> : money2(v.unit_price)}
              {v.price_source && <div className="text-[11px] text-faint">{v.price_source}</div>}
            </Td>
          </tr>
          {picking === v.key && (
            <tr className="border-b border-border bg-surface-2/30">
              <td colSpan={4} className="px-4 py-3">
                <Picker
                  unit={line.unit}
                  description={v.description}
                  concepts={concepts}
                  busy={busy}
                  onPick={(c) => onConfirm(v, c)}
                  onCancel={() => onPick(null)}
                />
              </td>
            </tr>
          )}
        </Fragment>
      ))}
    </>
  );
}

function Picker({
  unit,
  description,
  concepts,
  busy,
  onPick,
  onCancel,
}: {
  unit: string;
  description: string;
  concepts: CatalogConcept[];
  busy: boolean;
  onPick: (c: Candidate) => void;
  onCancel: () => void;
}) {
  const [query, setQuery] = useState(() => description.split(",")[0].slice(0, 40));
  const [refs, setRefs] = useState<Candidate[]>([]);
  const own = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter((w) => w.length > 2);
    return concepts
      .filter((c) => unitKey(c.unit) === unitKey(unit))
      .map((c) => {
        const text = `${c.code} ${c.description}`.toLowerCase();
        return { c, hits: words.filter((w) => text.includes(w)).length };
      })
      .filter((x) => x.hits > 0 || words.length === 0)
      .sort((a, b) => b.hits - a.hits)
      .slice(0, 8)
      .map(({ c }) => ({ kind: "concept" as const, code: c.code, description: c.description, unit: c.unit }));
  }, [concepts, query, unit]);

  useEffect(() => {
    const q = query.trim();
    let alive = true;
    const handle = window.setTimeout(() => {
      if (q.length < 3) {
        if (alive) setRefs([]);
        return;
      }
      searchReference(q)
        .then((rows) => {
          if (!alive) return;
          setRefs(
            rows
              .filter((r) => unitKey(r.unit) === unitKey(unit))
              .slice(0, 8)
              .map((r) => ({
                kind: "reference" as const,
                refId: r.ref_id,
                clave: r.clave,
                description: r.description,
                unit: r.unit,
                source: r.source_name,
                price: r.price,
              })),
          );
        })
        .catch(() => alive && setRefs([]));
    }, 250);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [query, unit]);

  const all: Candidate[] = [...own, ...refs];
  return (
    <div>
      <div className="relative mb-2 max-w-xl">
        <MagnifyingGlass size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
        <Input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") onCancel();
            if (e.key === "Enter" && all[0]) onPick(all[0]);
          }}
          placeholder={`Buscar en tu catálogo (${unit})…`}
          className="w-full pl-9"
          aria-label="Buscar concepto de tu catálogo"
        />
      </div>
      {all.length === 0 ? (
        <p className="text-xs text-muted">Nada en tu catálogo con esa unidad y esas palabras.</p>
      ) : (
        <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-md border border-border bg-surface">
          {all.map((c) => (
            <li key={c.kind === "concept" ? `c:${c.code}` : `r:${c.refId}`}>
              <button
                type="button"
                disabled={busy}
                onClick={() => onPick(c)}
                className="flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-sm hover:bg-surface-2"
              >
                <span className="font-mono text-xs">{c.kind === "concept" ? c.code : c.clave}</span>
                <span className="min-w-0 flex-1 truncate">{c.description}</span>
                <span className="text-[11px] text-faint">
                  {c.kind === "concept" ? "tu catálogo" : `${c.source} · ${money2(c.price)}`}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-1.5 text-[11px] text-faint">Enter toma el primero · Esc cierra</p>
    </div>
  );
}
