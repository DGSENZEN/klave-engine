"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  CheckCircle,
  Prohibit,
  ArrowCounterClockwise,
  MapTrifold,
  PlusCircle,
} from "@phosphor-icons/react";
import {
  ApiError,
  getAiReads,
  getConteos,
  getRevisionTable,
  putConteos,
  setDetectionReviews,
  type ConteoHoja,
  type ConteosDeProyecto,
  type CoverageFlag,
  type RevisionRow,
  type RevisionTable,
} from "@/lib/api";
import {
  Badge,
  Button,
  buttonClasses,
  Callout,
  Card,
  Checkbox,
  ConfidenceBadge,
  Input,
  Metric,
  PageHeader,
  SectionTitle,
  Select,
  SkeletonHeader,
  SkeletonMetrics,
  SkeletonTable,
  TableCard,
  Td,
  Th,
} from "@/components/ui";
import { FAMILIES, FAMILY_LABELS } from "@/lib/families";
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
              <Link href={`/proyecto/${id}/resumen`} className={buttonClasses("secondary", "sm")}>
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

      <ConteoSection
        projectId={id}
        detections={table.rows}
        actorName={actorName}
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
    >
      {label}
      <span className="text-[10px]">{active ? (sort.dir === 1 ? "▲" : "▼") : ""}</span>
    </button>
  );
}

/* ---- Conteos: cuánto hay dibujado, contado por una persona ----
 *
 * Every other test in this codebase compares the engine to itself; this is
 * the one number that compares it to the drawing. Rows join, per hoja, the
 * families the engine detected there with anything a person already saved.
 * `dibujados` only ever pre-fills from the AI sheet-read's independent count
 * (coverage_flags) — never from the engine's own `detectados`, which would
 * quietly turn this into the engine grading itself. */

// conteos.py's per-familia fold has no dedup of its own — every
// ConteoHoja.dibujados gets summed verbatim across every hoja string, by
// design (a family legitimately spans several sheets). That means two
// spellings of the *same* sheet ("e-02" vs "E-02") silently double-counts
// it. Free-text entry (the "familia que el motor no detectó" control) is
// the only place a hoja doesn't already come from the engine's own
// normalized frame code, so case-fold + collapse whitespace there — and
// everywhere a hoja is compared or keyed — so a variant always resolves to
// the one existing row instead of a new one.
function normalizarHoja(raw: string): string {
  return raw.trim().replace(/\s+/g, " ").toLocaleUpperCase("es");
}

// A visible separator; hoja/familia are never decoded back out of this
// key (see engineInfo/filas below), so it only has to be collision-free
// in practice, not literally unsplittable. Keys on the normalized hoja so
// a variant spelling always joins the same row instead of forking a new one.
const filaKey = (hoja: string, familia: string) => `${normalizarHoja(hoja)}::${familia}`;
const familyLabel = (familia: string) => FAMILY_LABELS[familia] ?? familia;
const FAMILIAS_ORDENADAS = [...FAMILIES].sort((a, b) =>
  familyLabel(a).localeCompare(familyLabel(b), "es"),
);

// A view's title is "E-02 · Planta baja" when the sheet has a cajetín
// (views.py: f"{frame.code} · {frame.title}"); this is the physical hoja, a
// finer grain than `sheet` (the source file, shared by every frame on a
// multi-sheet DXF). Falls back to `sheet` for plans with no cajetín, where
// the file is the closest thing to a hoja.
const SHEET_CODE_RE = /^([A-Z]{1,3}-\d{2,4}[A-Z]?)\s*·\s*/;
function hojaOf(row: RevisionRow): string {
  const m = SHEET_CODE_RE.exec(row.view_title);
  return normalizarHoja(m ? m[1] : row.sheet);
}

type Fila = {
  hoja: string;
  familia: string;
  detectados: number;
  dibujados: number | null; // null: nadie lo ha contado — nunca se guarda como 0.
  nota: string;
};

const CONTEOS_VACIOS: ConteosDeProyecto = { contado_por: "", contado_en: "", hojas: [] };

function ConteoSection({
  projectId,
  detections,
  actorName,
  reloadKey,
}: {
  projectId: string;
  detections: RevisionRow[];
  actorName: string;
  reloadKey?: unknown;
}) {
  const [conteos, setConteosState] = useState<ConteosDeProyecto | null>(null);
  const [cobertura, setCobertura] = useState<CoverageFlag[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // null: the person hasn't chosen a hoja yet, so the field displays the
  // first known one as a convenience default (computed at render time
  // below, not synced in via an effect). Once they've typed anything —
  // even clearing it back to "" — it's a real string, and the default
  // never overrides it again (an empty string is not nullish).
  const [nuevaHoja, setNuevaHoja] = useState<string | null>(null);
  const [nuevaFamilia, setNuevaFamilia] = useState(FAMILIAS_ORDENADAS[0] ?? "");
  const [nuevaCuenta, setNuevaCuenta] = useState("");

  // A blur-triggered save must build its PUT body from the latest known
  // state, not from a stale render closure: two fields blurred before the
  // first PUT resolves would otherwise race, the second undoing the first.
  // The ref is updated synchronously (state alone lags a render behind).
  const conteosRef = useRef<ConteosDeProyecto | null>(null);
  const setConteos = useCallback((next: ConteosDeProyecto) => {
    conteosRef.current = next;
    setConteosState(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getConteos(projectId)
      .then((c) => !cancelled && setConteos(c))
      .catch(() => {
        if (cancelled) return;
        // Still render with what the engine detected — but say so: a
        // silent empty table here would look identical to "nadie ha
        // contado nada", and someone could re-enter counts that already
        // exist and just failed to load.
        setConteos(CONTEOS_VACIOS);
        setError("No se pudieron cargar los conteos guardados; lo que se ve aquí puede estar incompleto.");
      });
    // The AI coverage comparison is only ever a pre-fill hint, never the
    // primary data: failing to load it just means no suggestions, silently.
    getAiReads(projectId)
      .then((r) => !cancelled && setCobertura(r.cobertura ?? []))
      .catch(() => !cancelled && setCobertura([]));
    return () => {
      cancelled = true;
    };
  }, [projectId, reloadKey, setConteos]);

  // Live engine counts, per hoja + familia — always the current run, never
  // the possibly-stale snapshot a ConteoHoja happened to save last time.
  // `pares` carries hoja/familia alongside each key so nothing ever has to
  // decode one back out of a composite string.
  const engineInfo = useMemo(() => {
    const counts = new Map<string, number>();
    const pares = new Map<string, { hoja: string; familia: string }>();
    for (const row of detections) {
      if (!row.family) continue;
      const hoja = hojaOf(row);
      const key = filaKey(hoja, row.family);
      counts.set(key, (counts.get(key) ?? 0) + 1);
      if (!pares.has(key)) pares.set(key, { hoja, familia: row.family });
    }
    return { counts, pares };
  }, [detections]);

  const filas = useMemo<Fila[]>(() => {
    if (!conteos) return [];
    const saved = new Map(conteos.hojas.map((h) => [filaKey(h.hoja, h.familia), h]));
    const aiCount = new Map<string, number>();
    for (const flag of cobertura) {
      aiCount.set(filaKey(flag.frame_code, flag.family), flag.ai_count);
    }
    const pares = new Map(engineInfo.pares);
    for (const h of conteos.hojas) {
      // Store the normalized form, not whatever happens to be on disk: a
      // row saved before this fix (or by hand) shows and re-saves in
      // canonical form from here on, healing itself on the next edit.
      const hoja = normalizarHoja(h.hoja);
      pares.set(filaKey(hoja, h.familia), { hoja, familia: h.familia });
    }
    const out: Fila[] = [];
    for (const [key, { hoja, familia }] of pares) {
      const row = saved.get(key);
      out.push({
        hoja,
        familia,
        detectados: engineInfo.counts.get(key) ?? 0,
        dibujados: row ? row.dibujados : (aiCount.get(key) ?? null),
        nota: row?.nota ?? "",
      });
    }
    out.sort(
      (a, b) =>
        a.hoja.localeCompare(b.hoja, "es") ||
        familyLabel(a.familia).localeCompare(familyLabel(b.familia), "es"),
    );
    return out;
  }, [conteos, cobertura, engineInfo]);

  const hojasConocidas = useMemo(
    () => [...new Set(filas.map((f) => f.hoja))].sort((a, b) => a.localeCompare(b, "es")),
    [filas],
  );

  // Convenience default once the sheet list loads, computed at render time
  // (not synced into state through an effect — nothing here is an external
  // value to mirror, just a pure function of hojasConocidas/nuevaHoja that
  // was already available this render). The field stays free text (not a
  // closed picker) so a plan the engine read nothing from — no rows, no
  // known hojas — can still be counted by hand.
  const nuevaHojaEfectiva = nuevaHoja ?? hojasConocidas[0] ?? "";

  async function guardarFila(fila: ConteoHoja): Promise<boolean> {
    // The single choke point where a row is actually persisted: normalize
    // here too (not just at the call sites) so this invariant — everything
    // in conteos.hojas is already canonical — holds no matter what a future
    // caller passes in, and matching a pre-existing non-normalized row
    // (saved before this fix, or by hand) still finds it as the same row.
    const row = { ...fila, hoja: normalizarHoja(fila.hoja) };
    const current = conteosRef.current ?? CONTEOS_VACIOS;
    const resto = current.hojas.filter(
      (h) => !(normalizarHoja(h.hoja) === row.hoja && h.familia === row.familia),
    );
    const next = { ...current, hojas: [...resto, row] };
    setConteos(next);
    setBusy(true);
    setError(null);
    try {
      const saved = await putConteos(projectId, next, actorName);
      setConteos(saved);
      return true;
    } catch {
      setError("No se pudo guardar el conteo.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  // Saves only a genuine, deliberate entry: a blank blur (never touched)
  // stays absent rather than becoming an invented zero, and blurring past
  // an unedited AI pre-fill without changing it does not silently confirm
  // it — "dibujados" only ever means a person actually counted.
  function commitDibujados(fila: Fila, raw: string) {
    const trimmed = raw.trim();
    if (trimmed === "") return;
    const value = Number(trimmed);
    if (!Number.isFinite(value) || value < 0) return;
    const dibujados = Math.round(value);
    if (dibujados === fila.dibujados) return;
    void guardarFila({
      hoja: fila.hoja,
      familia: fila.familia,
      dibujados,
      detectados: fila.detectados,
      nota: fila.nota,
    });
  }

  const cuentaNueva = Number(nuevaCuenta.trim());
  const puedeAgregar =
    nuevaHojaEfectiva.trim() !== "" &&
    nuevaFamilia !== "" &&
    nuevaCuenta.trim() !== "" &&
    Number.isFinite(cuentaNueva) &&
    cuentaNueva >= 0;

  async function agregar() {
    if (!puedeAgregar) return;
    const hoja = normalizarHoja(nuevaHojaEfectiva);
    const ok = await guardarFila({
      hoja,
      familia: nuevaFamilia,
      dibujados: Math.round(cuentaNueva),
      detectados: engineInfo.counts.get(filaKey(hoja, nuevaFamilia)) ?? 0,
      nota: "",
    });
    if (ok) setNuevaCuenta("");
  }

  return (
    <Card className="mt-6 p-5">
      <SectionTitle sub="El motor se compara contra sí mismo en todo lo demás. Esto es lo único que dice cuánto de lo dibujado encuentra, y sólo lo puede contestar alguien contando.">
        Cuántos hay dibujados
      </SectionTitle>

      {error && (
        <div className="mb-3">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      <TableCard>
        <thead>
          <tr className="border-b border-border bg-surface-2">
            <Th>Hoja</Th>
            <Th>Familia</Th>
            <Th align="right">Detectados</Th>
            <Th align="right">Dibujados</Th>
          </tr>
        </thead>
        <tbody>
          {conteos === null && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-sm text-muted">
                Cargando conteos…
              </td>
            </tr>
          )}
          {conteos !== null && filas.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-sm text-muted">
                El motor no detectó nada todavía en este proyecto.
              </td>
            </tr>
          )}
          {filas.map((fila) => (
            <tr key={filaKey(fila.hoja, fila.familia)} className="border-b border-border">
              <Td className="text-xs">{fila.hoja}</Td>
              <Td>{familyLabel(fila.familia)}</Td>
              <Td align="right" className="tabular text-muted">
                {fila.detectados}
              </Td>
              <Td align="right">
                <Input
                  key={`${filaKey(fila.hoja, fila.familia)}:${fila.dibujados ?? "vacio"}`}
                  type="number"
                  min={0}
                  defaultValue={fila.dibujados ?? undefined}
                  onBlur={(e) => commitDibujados(fila, e.target.value)}
                  className="w-20 px-2 py-1 text-right tabular"
                  aria-label={`Dibujados en ${fila.hoja}, ${familyLabel(fila.familia)}`}
                />
              </Td>
            </tr>
          ))}
        </tbody>
      </TableCard>

      <div className="mt-4 border-t border-border pt-3">
        <p className="text-sm text-muted">
          Lo más importante son las familias que no aparecen arriba. Si el plano
          tiene escaleras y el motor no detectó ninguna, ese renglón lo escribes tú:
          es el que cuesta más caro descubrir tarde.
        </p>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Hoja</span>
            <Input
              list={`hojas-conocidas-${projectId}`}
              value={nuevaHojaEfectiva}
              onChange={(e) => setNuevaHoja(e.target.value)}
              placeholder="E-02"
              className="w-24 px-2 py-1"
              aria-label="Hoja"
            />
            <datalist id={`hojas-conocidas-${projectId}`}>
              {hojasConocidas.map((h) => (
                <option key={h} value={h} />
              ))}
            </datalist>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Familia</span>
            <Select value={nuevaFamilia} onChange={(e) => setNuevaFamilia(e.target.value)}>
              {FAMILIAS_ORDENADAS.map((f) => (
                <option key={f} value={f}>
                  {familyLabel(f)}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-xs text-muted">Dibujados</span>
            <Input
              type="number"
              min={0}
              value={nuevaCuenta}
              onChange={(e) => setNuevaCuenta(e.target.value)}
              className="w-20 px-2 py-1 text-right tabular"
              aria-label="Cantidad dibujada"
            />
          </label>
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || !puedeAgregar}
            onClick={() => void agregar()}
          >
            <PlusCircle size={14} weight="bold" /> Agregar
          </Button>
        </div>
      </div>
    </Card>
  );
}
