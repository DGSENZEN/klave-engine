"use client";

import { useEffect, useState } from "react";
import { Check, MagnifyingGlass, X } from "@phosphor-icons/react";
import {
  clearAlias,
  getConceptMatches,
  money2,
  searchReference,
  setAlias,
  type ConceptMatch,
} from "@/lib/api";
import { Badge, Button, Input, Skeleton } from "@/components/ui";

/**
 * "El concepto del taller": pick the taller's own clave for one of ours.
 * Top matches come ranked with their reasons; a search box covers the
 * rest of the catálogo. The choice is workspace-wide (every project from
 * now on) and remembered with who decided it and where.
 */
export function ConceptPicker({
  conceptCode,
  conceptDescription,
  unit,
  currentClave,
  projectId,
  actorName,
  onDone,
}: {
  conceptCode: string;
  conceptDescription: string;
  unit: string;
  currentClave: string;
  projectId: string;
  actorName: string;
  onDone: () => void;
}) {
  const [matches, setMatches] = useState<ConceptMatch[] | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ConceptMatch[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getConceptMatches(conceptCode)
      .then((r) => {
        if (active) setMatches(r.matches);
      })
      .catch(() => {
        if (active) setMatches([]);
      });
    return () => {
      active = false;
    };
  }, [conceptCode]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) return;
    let active = true;
    const handle = setTimeout(() => {
      searchReference(q)
        .then((rows) => {
          if (!active) return;
          setResults(
            rows
              .filter((row) => row.unit.toUpperCase().replace("²", "2").replace("³", "3") === unit)
              .slice(0, 12)
              .map((row) => ({
                kind: "reference" as const,
                key: String(row.ref_id),
                ref_id: row.ref_id,
                target_code: null,
                clave: row.clave,
                description: row.description,
                unit: row.unit,
                price: row.price,
                source: row.source_name ?? row.source_key,
                vigencia: "",
                score: 0,
                reasons: [],
              })),
          );
        })
        .catch(() => {});
    }, 250);
    return () => {
      active = false;
      clearTimeout(handle);
    };
  }, [query, unit]);

  async function choose(match: ConceptMatch) {
    setBusy(true);
    setError(null);
    try {
      await setAlias(
        {
          concept_code: conceptCode,
          kind: match.kind,
          ref_id: match.ref_id,
          target_code: match.target_code,
          note: note.trim(),
          project_id: projectId,
        },
        actorName,
      );
      onDone();
    } catch {
      setError("No se pudo guardar el concepto del taller.");
      setBusy(false);
    }
  }

  async function clear() {
    setBusy(true);
    try {
      await clearAlias(conceptCode, projectId, actorName);
      onDone();
    } catch {
      setError("No se pudo quitar el alias.");
      setBusy(false);
    }
  }

  const list = query.trim().length >= 2 ? results : (matches ?? []);
  return (
    <div className="rounded-lg border border-border bg-surface p-3 text-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-medium">Concepto del taller para {conceptCode}</span>
        <span className="text-xs text-muted">
          {conceptDescription.slice(0, 60)} · {unit}
        </span>
        {currentClave && (
          <Badge tone="accent">actual: {currentClave}</Badge>
        )}
        <span className="ml-auto flex items-center gap-1">
          {currentClave && (
            <Button size="sm" onClick={clear} disabled={busy}>
              Volver al concepto Klave
            </Button>
          )}
          <Button size="sm" onClick={onDone} disabled={busy} aria-label="Cerrar">
            <X size={13} weight="bold" />
          </Button>
        </span>
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="relative">
          <MagnifyingGlass size={13} className="absolute left-2 top-2 text-faint" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar en tu catálogo…"
            className="w-64 py-1 pl-7 pr-2"
            aria-label="Buscar concepto del taller"
          />
        </span>
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Nota (opcional)"
          maxLength={300}
          className="min-w-48 flex-1 px-2 py-1"
          aria-label="Nota del alias"
        />
      </div>
      {error && <p className="mb-2 text-xs text-danger">{error}</p>}
      {matches === null && query.trim().length < 2 ? (
        <div className="space-y-2" aria-busy="true">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12 w-2/3" />
        </div>
      ) : list.length === 0 ? (
        <p className="text-xs text-faint">
          {query.trim().length >= 2
            ? `Nada con unidad ${unit} para «${query.trim()}».`
            : "Sin coincidencias claras; busca por palabras de tu catálogo."}
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {list.map((m) => (
            <li key={`${m.kind}-${m.key}`} className="flex items-start gap-3 py-2">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{m.clave}</span>
                  {m.score > 0 && (
                    <Badge tone={m.score >= 0.8 ? "success" : m.score >= 0.5 ? "warning" : "default"}>
                      {(m.score * 100).toFixed(0)}%
                    </Badge>
                  )}
                  <span className="text-xs text-muted">
                    {m.kind === "concept" ? "matriz del taller" : m.source}
                    {m.vigencia && ` · ${m.vigencia}`}
                  </span>
                </div>
                <div className="text-sm">{m.description}</div>
                {m.reasons.length > 0 && (
                  <div className="text-[11px] text-faint">{m.reasons.join(" · ")}</div>
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className="tabular text-sm">
                  {m.price != null ? `${money2(m.price)} / ${m.unit}` : "sin precio"}
                </span>
                <Button size="sm" variant="primary" onClick={() => choose(m)} disabled={busy}>
                  <Check size={13} weight="bold" /> Usar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
