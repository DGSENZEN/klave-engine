"use client";

import { useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { LockSimple } from "@phosphor-icons/react";
import { apiMessage, putGate, type TableroNodeKey } from "@/lib/api";
import { canApproveGate, quienPuedeAbrir } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { useTablero } from "@/lib/useProjectReport";
import { Button, Card, Skeleton } from "@/components/ui";

/**
 * El candado se respeta: la sección bloqueada no se esconde — dice qué
 * falta y quién puede abrirla. La firma vive en el servidor (con autor y
 * fecha); esto es la cara visible de esa regla. Un error al leer el estado
 * deja pasar: el candado es de proceso, no de seguridad, y una API caída
 * no debe secuestrar la pantalla.
 */
export function GateGuard({ node, children }: { node: TableroNodeKey; children: ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const { tablero, error, refetch } = useTablero(id);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (error && !tablero) return <>{children}</>;
  if (!tablero) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  if (tablero.gates?.[node]) return <>{children}</>;

  const nodeData = tablero.nodes?.[node];
  const requisitos = (nodeData?.chips ?? []).filter((chip) => chip.tone === "warn");
  const canApprove = canApproveGate(tablero.my_role);

  async function abrir() {
    setBusy(true);
    setActionError(null);
    try {
      await putGate(id, node, true, getBrowserActor());
      refetch();
    } catch (err) {
      setActionError(apiMessage(err, "No se pudo abrir el nodo."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <Card className="flex flex-col items-start gap-4 p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-2 text-muted">
            <LockSimple size={20} />
          </span>
          <div>
            <h1 className="text-lg font-semibold">Este nodo tiene candado</h1>
            <p className="text-sm text-muted">
              La sección existe y se puede ver desde el tablero, pero se trabaja hasta que
              alguien con autoridad la abre. Nada se esconde; solo se ordena.
            </p>
          </div>
        </div>
        {requisitos.length > 0 && (
          <div>
            <div className="microlabel mb-1.5">Antes de abrir</div>
            <ul className="space-y-1 text-sm">
              {requisitos.map((chip) => (
                <li key={chip.label} className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                  {chip.href ? (
                    <Link href={`/proyecto/${id}${chip.href}`} className="underline underline-offset-2">
                      {chip.label}
                    </Link>
                  ) : (
                    chip.label
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-sm text-muted">{quienPuedeAbrir(tablero.my_role)}</p>
        {actionError && <p className="text-sm text-danger">{actionError}</p>}
        <div className="flex items-center gap-2">
          {canApprove && (
            <Button onClick={abrir} disabled={busy}>
              {busy ? "Abriendo…" : "Abrir nodo"}
            </Button>
          )}
          <Link href={`/proyecto/${id}`} className="text-sm text-muted underline underline-offset-2">
            Volver al tablero
          </Link>
        </div>
      </Card>
    </div>
  );
}
