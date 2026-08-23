"use client";

import { useCallback, useEffect, useState } from "react";
import { Trash } from "@phosphor-icons/react";
import { clearAlias, getAliases, money2, type ConceptAlias } from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { timeAgo } from "@/lib/time";
import { Badge, Button, Callout, Card, SectionTitle, Skeleton, Td, Th } from "@/components/ui";
import { ConfirmDialog } from "@/components/ConfirmDialog";

/**
 * Every "concepto del taller" decided so far: which of our concepts is
 * billed under which clave of the taller, who decided it and from where.
 * Decisions are made in the presupuesto; this is where they are reviewed
 * and undone.
 */
export function AliasesSection({
  onChanged,
  onError,
}: {
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [aliases, setAliases] = useState<ConceptAlias[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [confirm, setConfirm] = useState<ConceptAlias | null>(null);

  const reload = useCallback(() => {
    getAliases()
      .then((r) => {
        setAliases(
          Object.values(r.aliases).sort((a, b) => a.concept_code.localeCompare(b.concept_code)),
        );
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function remove(alias: ConceptAlias) {
    setConfirm(null);
    try {
      await clearAlias(alias.concept_code, alias.project_id, getBrowserActor());
      reload();
      onChanged();
    } catch {
      onError(`No se pudo quitar la clave del taller de ${alias.concept_code}.`);
    }
  }

  return (
    <Card className="p-5">
      <ConfirmDialog
        open={confirm !== null}
        title={confirm ? `Volver al concepto Klave en ${confirm.concept_code}` : ""}
        description="Los próximos cálculos usan otra vez la descripción y el precio de Klave; los presupuestos ya calculados cambian al recalcular."
        confirmLabel="Quitar clave"
        onConfirm={() => confirm && void remove(confirm)}
        onCancel={() => setConfirm(null)}
      />
      <SectionTitle sub="Cada concepto de Klave que se entrega con tu clave, tu descripción y tu precio. Se decide desde el presupuesto (el selector de cada línea) y aplica a todos los proyectos.">
        Claves del taller
      </SectionTitle>
      {loadError && (
        <Callout
          tone="danger"
          action={
            <Button size="sm" onClick={reload}>
              Reintentar
            </Button>
          }
        >
          No se pudieron cargar las claves del taller.
        </Callout>
      )}
      {aliases === null && !loadError && (
        <div className="space-y-2" aria-busy="true">
          <Skeleton className="h-8" />
          <Skeleton className="h-8 w-2/3" />
        </div>
      )}
      {aliases && aliases.length === 0 && (
        <p className="text-xs text-faint">
          Aún no hay claves del taller. En el presupuesto, abre una línea y elige «Concepto del
          taller» para usar tu clave; las sugerencias al 80 % o más aparecen solas.
        </p>
      )}
      {aliases && aliases.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2">
                <Th>Concepto Klave</Th>
                <Th>Clave del taller</Th>
                <Th align="right">Precio</Th>
                <Th>Decidido</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {aliases.map((alias) => (
                <tr key={alias.concept_code} className="border-t border-border">
                  <Td>
                    <span className="font-mono text-xs">{alias.concept_code}</span>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs">{alias.clave}</span>
                      <Badge tone={alias.kind === "concept" ? "accent" : "default"}>
                        {alias.kind === "concept" ? "matriz del taller" : alias.source}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted">
                      {alias.description} · {alias.unit}
                    </div>
                    {alias.note && <div className="text-[11px] text-faint">{alias.note}</div>}
                  </Td>
                  <Td align="right" className="tabular">
                    {alias.price != null ? money2(alias.price) : "sin precio"}
                  </Td>
                  <Td className="text-xs text-muted">
                    {alias.actor || "—"}
                    {alias.created_at && ` · ${timeAgo(alias.created_at)}`}
                  </Td>
                  <Td>
                    <button
                      type="button"
                      aria-label={`Quitar la clave del taller de ${alias.concept_code}`}
                      onClick={() => setConfirm(alias)}
                      className="rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
                    >
                      <Trash size={14} />
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
