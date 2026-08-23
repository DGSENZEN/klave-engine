"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkle } from "@phosphor-icons/react";
import { getAllMatches, setAliasesBulk, type ConceptMatch } from "@/lib/api";
import { Badge, Button, Callout, Skeleton } from "@/components/ui";
import { useProjectLive } from "@/components/ProjectLive";

type Suggestion = { concept_code: string; description: string; unit: string; match: ConceptMatch };

/**
 * "Tu catálogo ya tiene estos conceptos": concepts without an alias whose
 * best match in the taller's catálogo scores ≥ 80 %. Review one by one or
 * adopt them all; either way each alias is remembered for every project.
 */
export function SuggestionsBar({
  projectId,
  actorName,
  conceptCodes,
}: {
  projectId: string;
  actorName: string;
  /** Concept codes with a line in this presupuesto: suggestions for anything else are noise here. */
  conceptCodes: Set<string>;
}) {
  const { latestEvent } = useProjectLive();
  const [items, setItems] = useState<Suggestion[] | null>(null);
  const [open, setOpen] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(() => new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  const reload = useCallback(() => {
    getAllMatches(0.8)
      .then((r) => {
        setItems(r.matches);
        setLoadError(false);
      })
      .catch(() => {
        setItems([]);
        setLoadError(true);
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    if (latestEvent?.type === "catalog_updated") reload();
  }, [latestEvent, reload]);

  const pending = (items ?? []).filter(
    (s) => !skipped.has(s.concept_code) && conceptCodes.has(s.concept_code),
  );
  // Reserve the bar's height while the matches load so the table below does
  // not jump when suggestions appear.
  if (!items) {
    return (
      <div className="mb-4" aria-busy="true">
        <Skeleton className="h-11 w-full" />
      </div>
    );
  }
  if (loadError) {
    return (
      <div className="mb-4">
        <Callout
          tone="warning"
          action={
            <Button size="sm" onClick={reload}>
              Reintentar
            </Button>
          }
        >
          No se pudieron buscar coincidencias con tu catálogo.
        </Callout>
      </div>
    );
  }
  if (pending.length === 0) return null;

  async function adopt(list: Suggestion[]) {
    setBusy(true);
    setError(null);
    try {
      await setAliasesBulk(
        list.map((s) => ({
          concept_code: s.concept_code,
          kind: s.match.kind,
          ref_id: s.match.ref_id,
          target_code: s.match.target_code,
          note: `sugerido (${(s.match.score * 100).toFixed(0)} %)`,
        })),
        projectId,
        actorName,
      );
      reload();
    } catch {
      setError("No se pudieron guardar los conceptos del taller.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4">
      <Callout
        tone="info"
        action={
          <span className="flex items-center gap-1">
            <Button size="sm" onClick={() => setOpen((v) => !v)} disabled={busy}>
              {open ? "Ocultar" : "Revisar"}
            </Button>
            <Button size="sm" variant="primary" onClick={() => adopt(pending)} disabled={busy}>
              {pending.length === 1 ? "Usar mi clave" : `Usar mis claves (${pending.length})`}
            </Button>
          </span>
        }
      >
        <span className="inline-flex items-center gap-1.5">
          <Sparkle size={15} weight="fill" />
          {pending.length === 1
            ? "1 concepto coincide con tu catálogo al 80 % o más. Usar tu clave pone tu descripción y tu precio en este y en los próximos proyectos."
            : `${pending.length} conceptos coinciden con tu catálogo al 80 % o más. Usar tus claves pone tu descripción y tu precio en este y en los próximos proyectos.`}
        </span>
      </Callout>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      {open && (
        <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface">
          {pending.map((s) => (
            <li key={s.concept_code} className="flex items-start gap-3 px-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <div className="text-xs text-muted">
                  <span className="font-mono">{s.concept_code}</span> {s.description.slice(0, 60)}
                </div>
                <div>
                  <span className="font-mono text-xs">{s.match.clave}</span> {s.match.description}
                </div>
                <div className="text-[11px] text-faint">{s.match.reasons.join(" · ")}</div>
              </div>
              <Badge tone="success">{(s.match.score * 100).toFixed(0)}%</Badge>
              <Button size="sm" variant="primary" onClick={() => adopt([s])} disabled={busy}>
                Usar esta clave
              </Button>
              <Button
                size="sm"
                onClick={() => setSkipped((current) => new Set(current).add(s.concept_code))}
                disabled={busy}
              >
                Omitir
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
