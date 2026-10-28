"use client";

import { useState, type ReactNode } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { LockSimple } from "@phosphor-icons/react";
import { apiMessage, putGate, type TableroNodeKey } from "@/lib/api";
import { canApproveGate } from "@/lib/gates";
import { getBrowserActor } from "@/lib/collab";
import { useTablero } from "@/lib/useProjectReport";
import { quienCerro } from "@/lib/candado";
import { useProjectLive } from "@/components/ProjectLive";
import { Button, Callout, Card, Skeleton } from "@/components/ui";

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
  // A node closed while someone works inside keeps their screen mounted:
  // the lock card is for the next entry, not for unsaved work.
  const [estabaAbierto, setEstabaAbierto] = useState(false);
  if (!estabaAbierto && tablero?.gates?.[node]) setEstabaAbierto(true);
  // Who closed it, from the live gate event (the tablero itself only knows
  // who approved).
  const { latestEvent } = useProjectLive();
  const [cerradoPor, setCerradoPor] = useState<string | null>(null);
  const [ultimoEvento, setUltimoEvento] = useState<number | null>(null);
  if (latestEvent && latestEvent.seq !== ultimoEvento) {
    setUltimoEvento(latestEvent.seq);
    const quien = quienCerro(latestEvent, node);
    if (quien) setCerradoPor(quien);
  }

  const cerradoMientras = !!tablero && !tablero.gates?.[node] && estabaAbierto;
  // One shape on every path that shows the page: a fragment whose children
  // keep their positions, so React never remounts what someone is typing.
  if (cerradoMientras || (error && !tablero) || tablero?.gates?.[node]) {
    return (
      <>
        {cerradoMientras ? (
          <div className="sticky top-0 z-20 px-6 pt-5 lg:px-8">
            <Callout tone="warning">
              {cerradoPor ? `${cerradoPor} cerró este nodo` : "Este nodo se cerró"} mientras
              trabajabas. Lo que guardes se conserva; la próxima vez que entres verás el
              candado.
            </Callout>
          </div>
        ) : null}
        {children}
      </>
    );
  }
  if (!tablero) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-4 h-32 w-full" />
      </div>
    );
  }
  const nodeData = tablero.nodes?.[node];
  const requisitos = (nodeData?.facts ?? []).filter((fact) => fact.tone === "warn");
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
              {canApprove
                ? "Se abre desde aquí o desde el tablero cuando los requisitos estén listos."
                : "Lo abre el propietario del proyecto o un administrador del taller. Pídeselo cuando los requisitos estén listos."}
            </p>
          </div>
        </div>
        {requisitos.length > 0 && (
          <div>
            <div className="microlabel mb-1.5">Antes de abrir</div>
            <ul className="space-y-1 text-sm">
              {requisitos.map((fact, index) => {
                const texto = fact.value ?? fact.label;
                return (
                  <li key={`${fact.label}-${index}`} className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                    {fact.href ? (
                      <Link
                        href={`/proyecto/${id}${fact.href}`}
                        className="underline underline-offset-2"
                      >
                        {texto}
                      </Link>
                    ) : (
                      texto
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {actionError && <p className="text-sm text-danger">{actionError}</p>}
        <div className="flex items-center gap-2">
          {canApprove && (
            <Button onClick={abrir} disabled={busy} data-tour="gate.abrir">
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
