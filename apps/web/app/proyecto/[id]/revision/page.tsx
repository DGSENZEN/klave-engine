"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CheckCircle, Prohibit, ArrowCounterClockwise, MapTrifold } from "@phosphor-icons/react";
import {
  ApiError,
  getRevisionTable,
  setDetectionReviews,
  type RevisionRow,
  type RevisionTable,
} from "@/lib/api";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  Checkbox,
  ConfidenceBadge,
  Input,
  Metric,
  PageHeader,
  Select,
  SkeletonHeader,
  SkeletonMetrics,
  SkeletonTable,
  TableCard,
  Td,
  Th,
} from "@/components/ui";
import { isDoubtful, LoteDeRevision } from "@/components/LoteDeRevision";
import { OmittedSection } from "@/components/OmittedSection";
import { useProjectLive } from "@/components/ProjectLive";

/**
 * Review at scale: every element behind the presupuesto as a row, doubts
 * first; filter by concept/planta/doubt, select many, one verdict, one
 * recompute. The visor stays the place to look at one element; this is
 * where a firm signs off hundreds.
 */
export default function RevisionPage() {
  const { id } = useParams<{ id: string }>();
  const { latestEvent, connectionEpoch, actorName, clientId } = useProjectLive();
  const [table, setTable] = useState<RevisionTable | null>(null);
  const [error, setError] = useState<"none" | "not_processed" | "failed">("none");
  const [concept, setConcept] = useState("");
  const [view, setView] = useState("");
  const [onlyDoubts, setOnlyDoubts] = useState(false);
  const [lote, setLote] = useState(false);
  const [onlyPending, setOnlyPending] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [lastIndex, setLastIndex] = useState<number | null>(null);
  const [excluding, setExcluding] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const reload = useCallback(() => {
    getRevisionTable(id)
      .then((t) => {
        setTable(t);
        setError("none");
      })
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? "not_processed" : "failed"));
  }, [id]);

  useEffect(() => {
    reload();
  }, [reload, connectionEpoch]);

  useEffect(() => {
    const type = latestEvent?.type ?? "";
    if (type === "review_updated" || type === "run_published") reload();
  }, [latestEvent, reload]);

  function clearFilters() {
    setOnlyDoubts(false);
    setOnlyPending(false);
    setLote(false);
  }

  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "doubts", dir: 1 });
  function sortBy(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  }
  const rows = useMemo(() => {
    if (!table) return [];
    const q = query.trim().toLowerCase();
    const cmp = (a: RevisionRow, b: RevisionRow): number => {
      switch (sort.key) {
        case "label":
          return a.label.localeCompare(b.label, "es");
        case "concept":
          return a.concept_code.localeCompare(b.concept_code) || a.label.localeCompare(b.label, "es");
        case "view":
          return a.view_title.localeCompare(b.view_title, "es") || a.label.localeCompare(b.label, "es");
        case "confidence":
          return a.confidence - b.confidence;
        case "status":
          return a.status.localeCompare(b.status) || a.label.localeCompare(b.label, "es");
        default:
          return (
            (b.doubts.length > 0 ? 1 : 0) - (a.doubts.length > 0 ? 1 : 0) ||
            a.concept_code.localeCompare(b.concept_code) ||
            a.label.localeCompare(b.label, "es")
          );
      }
    };
    return [...table.rows].sort((a, b) => cmp(a, b) * sort.dir).filter(
      (r) =>
        (!concept || r.concept_code === concept) &&
        (!view || r.view_id === view) &&
        (!onlyDoubts || r.doubts.length > 0) &&
        (!lote || (r.status === "" && isDoubtful(r))) &&
        (!onlyPending || r.status === "") &&
        (!q || r.label.toLowerCase().includes(q) || r.mark.toLowerCase().includes(q)),
    );
  }, [table, concept, view, onlyDoubts, onlyPending, lote, query, sort]);

  // Long sets render in pages of 500; filters and "seleccionar todo" always
  // work over the whole filtered set, never just the page.
  const [shown, setShown] = useState(PAGE_SIZE);
  const pagedRows = rows.length > shown ? rows.slice(0, shown) : rows;

  // Selection only ever holds visible keys: a filter change drops the rest.
  const visibleKeys = useMemo(() => new Set(rows.map((r) => r.key)), [rows]);
  const selectedVisible = useMemo(
    () => [...selected].filter((k) => visibleKeys.has(k)),
    [selected, visibleKeys],
  );
  const allSelected = rows.length > 0 && selectedVisible.length === rows.length;

  function toggle(row: RevisionRow, index: number, shift: boolean) {
    setSelected((current) => {
      const next = new Set(current);
      if (shift && lastIndex !== null) {
        const [a, b] = [Math.min(lastIndex, index), Math.max(lastIndex, index)];
        const turnOn = !current.has(row.key);
        for (let i = a; i <= b; i++) {
          if (turnOn) next.add(rows[i].key);
          else next.delete(rows[i].key);
        }
      } else if (next.has(row.key)) {
        next.delete(row.key);
      } else {
        next.add(row.key);
      }
      return next;
    });
    setLastIndex(index);
  }

  function toggleAll() {
    setSelected((current) => {
      const next = new Set(current);
      if (allSelected) rows.forEach((r) => next.delete(r.key));
      else rows.forEach((r) => next.add(r.key));
      return next;
    });
  }

  async function apply(status: "confirmed" | "excluded" | "none") {
    if (selectedVisible.length === 0) return;
    if (status === "excluded" && !reason.trim()) {
      setActionError("Excluir requiere un motivo.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      // The API takes up to 2,000 keys per call; send batches and let only
      // the last one recompute the presupuesto.
      const BATCH = 500;
      for (let start = 0; start < selectedVisible.length; start += BATCH) {
        const batch = selectedVisible.slice(start, start + BATCH);
        const last = start + BATCH >= selectedVisible.length;
        await setDetectionReviews(
          id,
          batch,
          status,
          status === "excluded" ? reason.trim() : "",
          actorName,
          clientId,
          last,
        );
      }
      setSelected(new Set());
      setExcluding(false);
      setReason("");
      reload();
    } catch {
      setActionError("No se pudo guardar la revisión.");
    } finally {
      setBusy(false);
    }
  }

  if (error !== "none") {
    return (
      <div className="p-6">
        <Callout
          tone={error === "not_processed" ? "info" : "danger"}
          action={
            error === "not_processed" ? (
              <Link href={`/proyecto/${id}`} className={buttonClasses("secondary", "sm")}>
                Ir al resumen
              </Link>
            ) : (
              <Button size="sm" onClick={reload}>
                Reintentar
              </Button>
            )
          }
        >
          {error === "not_processed"
            ? "No hay presupuesto que revisar todavía: procesa el proyecto primero."
            : "No se pudo cargar la revisión; el servidor no respondió."}
        </Callout>
      </div>
    );
  }
  if (!table) {
    return (
      <div className="p-6">
        <SkeletonHeader />
        <SkeletonMetrics />
        <SkeletonTable rows={10} />
      </div>
    );
  }

  const pending = table.total - table.confirmed - table.excluded;
  return (
    <div className="p-6">
      <PageHeader
        title="Revisión del presupuesto"
        sub="Cada elemento que alimenta una cantidad. Empieza por las dudas; confirma o excluye en lote, con motivo."
      />

      {/* The overview is the filter, not a caption above it: clicking a figure
          takes you to exactly the rows it counts (Shneiderman 1996). */}
      <div className="mb-6 grid gap-4 sm:grid-cols-5">
        {(
          [
            {
              label: "Elementos", value: table.total, accent: undefined,
              active: !onlyDoubts && !onlyPending && !lote,
              on: () => clearFilters(),
            },
            {
              label: "Con dudas", value: table.with_doubts,
              accent: table.with_doubts === 0 ? "success" : undefined,
              active: onlyDoubts,
              on: () => { clearFilters(); setOnlyDoubts(true); },
            },
            { label: "Confirmados", value: table.confirmed, accent: "success", active: false },
            { label: "Excluidos", value: table.excluded, accent: undefined, active: false },
            {
              label: "Sin revisar", value: pending, accent: undefined, active: onlyPending,
              on: () => { clearFilters(); setOnlyPending(true); },
            },
          ] as { label: string; value: number; accent?: "accent" | "danger" | "success" | "primary"; active: boolean;
                 on?: () => void }[]
        ).map((card) =>
          card.on ? (
            <button
              key={card.label}
              type="button"
              onClick={card.on}
              className={`rounded-xl text-left transition ${
                card.active ? "ring-2 ring-accent" : "hover:brightness-105"
              }`}
              aria-pressed={card.active}
              title={`Ver solo: ${card.label.toLowerCase()}`}
            >
              <Metric label={card.label} value={card.value} accent={card.accent} />
            </button>
          ) : (
            <Metric key={card.label} label={card.label} value={card.value} accent={card.accent} />
          ),
        )}
      </div>

      <LoteDeRevision
        rows={table.rows}
        active={lote}
        onFocus={() => setLote(true)}
        onShowAll={() => setLote(false)}
      />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
          aria-label="Concepto"
        >
          <option value="">Todos los conceptos</option>
          {table.concepts.map((c) => (
            <option key={c.code || "none"} value={c.code}>
              {c.code ? `${c.code} · ${c.description.slice(0, 40)}` : "Sin concepto"} ({c.count})
            </option>
          ))}
        </Select>
        {table.views.length > 1 && (
          <Select
            value={view}
            onChange={(e) => setView(e.target.value)}
            aria-label="Planta"
          >
            <option value="">Todas las plantas</option>
            {table.views.map((v) => (
              <option key={v.view_id} value={v.view_id}>
                {v.title} ({v.count})
              </option>
            ))}
          </Select>
        )}
        <label className="flex items-center gap-1.5 text-sm">
          <Checkbox checked={onlyDoubts} onChange={(e) => setOnlyDoubts(e.target.checked)} />
          solo con dudas
        </label>
        <label className="flex items-center gap-1.5 text-sm">
          <Checkbox checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} />
          sin revisar
        </label>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar etiqueta o marca"
          className="w-48 px-2 py-1.5"
          aria-label="Buscar"
        />
        <span className="ml-auto text-xs text-muted">
          {rows.length} de {table.total}
        </span>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-2/60 px-3 py-2">
        <span className="text-sm font-medium tabular">
          {selectedVisible.length} seleccionado{selectedVisible.length === 1 ? "" : "s"}
        </span>
        <Button
          size="sm"
          variant="primary"
          onClick={() => apply("confirmed")}
          disabled={busy || selectedVisible.length === 0}
        >
          <CheckCircle size={14} weight="bold" /> Confirmar
        </Button>
        {excluding ? (
          <>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Motivo de la exclusión (obligatorio)"
              maxLength={300}
              autoFocus
              className="min-w-64 px-2 py-1"
              aria-label="Motivo"
              onKeyDown={(e) => {
                if (e.key === "Enter") void apply("excluded");
                if (e.key === "Escape") setExcluding(false);
              }}
            />
            <Button size="sm" onClick={() => apply("excluded")} disabled={busy}>
              <Prohibit size={14} weight="bold" /> Excluir
            </Button>
            <Button size="sm" onClick={() => setExcluding(false)} disabled={busy}>
              Cancelar
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            onClick={() => setExcluding(true)}
            disabled={busy || selectedVisible.length === 0}
          >
            <Prohibit size={14} weight="bold" /> Excluir…
          </Button>
        )}
        <Button
          size="sm"
          onClick={() => apply("none")}
          disabled={busy || selectedVisible.length === 0}
          title="Quita la revisión: el elemento vuelve a contar como lo leyó el motor"
        >
          <ArrowCounterClockwise size={14} weight="bold" /> Quitar revisión
        </Button>
        {actionError && <span className="text-sm text-danger">{actionError}</span>}
        <span className="ml-auto text-xs text-faint">Shift+clic selecciona un rango</span>
      </div>

      <TableCard>
        <thead>
          <tr className="border-b border-border bg-surface-2">
            <Th>
              <Checkbox
                checked={allSelected}
                onChange={toggleAll}
                aria-label="Seleccionar todos los visibles"
              />
            </Th>
            <Th><SortButton label="Elemento" k="label" sort={sort} onSort={sortBy} /></Th>
            <Th><SortButton label="Concepto" k="concept" sort={sort} onSort={sortBy} /></Th>
            <Th><SortButton label="Planta" k="view" sort={sort} onSort={sortBy} /></Th>
            <Th>Medida</Th>
            <Th align="center"><SortButton label="Conf." k="confidence" sort={sort} onSort={sortBy} /></Th>
            <Th><SortButton label="Dudas" k="doubts" sort={sort} onSort={sortBy} /></Th>
            <Th><SortButton label="Estado" k="status" sort={sort} onSort={sortBy} /></Th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} className="px-4 py-6 text-center text-sm text-muted">
                Nada que mostrar con estos filtros.
              </td>
            </tr>
          )}
          {pagedRows.map((r, index) => {
            const on = selected.has(r.key);
            return (
              <tr
                key={r.key}
                className={`border-b border-border transition-colors hover:bg-surface-2/60 ${
                  on ? "bg-accent-soft/50" : ""
                }`}
                onClick={(e) => toggle(r, index, e.shiftKey)}
              >
                <Td>
                  <Checkbox
                    checked={on}
                    onChange={() => undefined}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggle(r, index, (e as React.MouseEvent).shiftKey);
                    }}
                    aria-label={`Seleccionar ${r.label}`}
                  />
                </Td>
                <Td>
                  <span className="font-medium">{r.label}</span>
                  {r.mark && r.mark !== r.label && (
                    <span className="ml-1.5 font-mono text-xs text-muted">{r.mark}</span>
                  )}
                  <div className="text-[11px] text-faint">{r.family_label}</div>
                </Td>
                <Td className="font-mono text-xs text-muted">{r.concept_code || "—"}</Td>
                <Td className="text-xs text-muted">
                  {r.view_title.replace(/^[A-Z]{1,3}-\d{2,4}[A-Z]?\s*·\s*/, "") || r.sheet}
                </Td>
                <Td className="whitespace-nowrap tabular text-xs">{r.measure || "—"}</Td>
                <Td align="center">
                  <ConfidenceBadge value={r.confidence} />
                </Td>
                <Td>
                  <div className="flex flex-wrap gap-1">
                    {r.doubts.map((d) => (
                      <Badge key={d} tone="warning">
                        {d}
                      </Badge>
                    ))}
                  </div>
                </Td>
                <Td>
                  {r.status === "confirmed" && <Badge tone="success">confirmado</Badge>}
                  {r.status === "excluded" && <Badge tone="danger">excluido</Badge>}
                  {r.status === "" && <span className="text-xs text-faint">—</span>}
                  {(r.note || r.actor) && (
                    <div className="text-[11px] text-faint">
                      {r.note}
                      {r.actor && ` — ${r.actor}`}
                    </div>
                  )}
                  {r.concept_code && (
                    <Link
                      href={`/proyecto/${id}/plano?concept=${encodeURIComponent(r.concept_code)}`}
                      className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-muted underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MapTrifold size={11} /> plano
                    </Link>
                  )}
                </Td>
              </tr>
            );
          })}
          {rows.length > shown && (
            <tr>
              <td colSpan={8} className="px-4 py-3 text-center">
                <Button size="sm" onClick={() => setShown((n) => n + PAGE_SIZE)}>
                  Mostrar {Math.min(PAGE_SIZE, rows.length - shown).toLocaleString("es-MX")} más
                  ({(rows.length - shown).toLocaleString("es-MX")} restantes)
                </Button>
              </td>
            </tr>
          )}
        </tbody>
      </TableCard>

      <OmittedSection
        projectId={id}
        actorName={actorName}
        clientId={clientId}
        reloadKey={latestEvent?.seq}
      />
    </div>
  );
}


const PAGE_SIZE = 500;

type SortKey = "doubts" | "label" | "concept" | "view" | "confidence" | "status";

function SortButton({
  label,
  k,
  sort,
  onSort,
}: {
  label: string;
  k: SortKey;
  sort: { key: SortKey; dir: 1 | -1 };
  onSort: (key: SortKey) => void;
}) {
  const active = sort.key === k;
  return (
    <button
      type="button"
      onClick={() => onSort(k)}
      className={`inline-flex items-center gap-1 uppercase tracking-wide ${active ? "text-foreground" : ""}`}
      title={`Ordenar por ${label.toLowerCase()}`}
    >
      {label}
      <span className="text-[10px]">{active ? (sort.dir === 1 ? "▲" : "▼") : ""}</span>
    </button>
  );
}
