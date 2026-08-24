"use client";

import { Target } from "@phosphor-icons/react";
import type { RevisionRow } from "@/lib/api";
import { Card, buttonClasses } from "@/components/ui";

/**
 * Why this exists, because it is not obvious and it changes the screen.
 *
 * Wolfe, Horowitz and Kenner measured how people search when the thing they
 * are looking for is rare (*Nature* 435:439, 2005). At 50 % prevalence
 * observers miss 7 % of targets; at 10 % they miss 16 %; at 1 % they miss
 * 30 %. Mixing frequencies makes it worse — the rarest targets were missed
 * 52 % of the time. The cause is that a search with nothing to find ends too
 * soon, and telling people about it beforehand does not fix it.
 *
 * A detector that is 95 % right puts Klave squarely in that regime: about
 * one row in twenty is wrong, sprinkled through two thousand. Asking an
 * engineer to review all of them evenly means roughly half the real errors
 * go unseen — not through carelessness, but through how human visual search
 * works. So the screen offers a batch where the doubtful rows are dense
 * instead of scattered, and says plainly why.
 *
 * It offers; it does not impose. Moderators surveyed by Bajpai and
 * Chandrasekharan (2025) preferred inline signals over filters that hide
 * things, and 94 of 106 wanted to see everything by default. Nothing here
 * is hidden — the full list is one click away, always.
 */

/** A row worth concentrating on: the engine itself is unsure, the reading is
 * weak, or the quantity was proposed from history rather than read. */
export function isDoubtful(row: RevisionRow): boolean {
  return row.doubts.length > 0 || row.confidence < 0.7;
}

export function LoteDeRevision({
  rows,
  active,
  onFocus,
  onShowAll,
}: {
  rows: RevisionRow[];
  active: boolean;
  onFocus: () => void;
  onShowAll: () => void;
}) {
  const pending = rows.filter((r) => r.status === "");
  const doubtful = pending.filter(isDoubtful);
  // Below a few hundred rows an even sweep is still tractable, and above
  // ~40 % density the batch is not concentrating anything.
  const density = pending.length > 0 ? doubtful.length / pending.length : 0;
  if (pending.length < 200 || doubtful.length === 0 || density > 0.4) return null;

  return (
    <Card className="mb-4 p-4">
      <div className="flex flex-wrap items-start gap-3">
        <Target size={20} weight="duotone" className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">
            Revisar {pending.length.toLocaleString("es-MX")} elementos parejo no funciona
          </div>
          <p className="mt-0.5 text-sm text-muted">
            Cuando lo que falla es raro, la vista se rinde antes de encontrarlo: en las
            mediciones clásicas de búsqueda visual, con 1 % de objetivos se pasa por alto
            el 30 %, y avisarlo de antemano no lo corrige.{" "}
            <span className="text-foreground">
              Estos {doubtful.length.toLocaleString("es-MX")} concentran la duda
            </span>{" "}
            ({(density * 100).toFixed(0)} % de lo pendiente): el motor no está seguro, la
            lectura es débil, o la cantidad vino de tu historia y no del plano.
          </p>
          <p className="mt-1 text-xs text-faint">
            No se te esconde nada: la lista completa sigue a un clic.
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {active ? (
            <button type="button" onClick={onShowAll} className={buttonClasses("secondary", "sm")}>
              Ver los {pending.length.toLocaleString("es-MX")}
            </button>
          ) : (
            <button type="button" onClick={onFocus} className={buttonClasses("primary", "sm")}>
              Revisar esos {doubtful.length.toLocaleString("es-MX")} primero
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}
