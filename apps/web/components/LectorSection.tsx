"use client";

import { useEffect, useState } from "react";
import { apiMessage, getLector, resumeLector, type LectorEstado } from "@/lib/api";
import { Button, Callout, Skeleton } from "@/components/ui";

/**
 * «El lector»: cuántas de sus propuestas confirmó y descartó este taller. Si
 * descarta casi todo, el lector se pausa solo para no cargar la revisión;
 * reanudarlo empieza la cuenta de nuevo.
 */
export function LectorSection({
  onError,
  onNotice,
}: {
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
}) {
  const [estado, setEstado] = useState<LectorEstado | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getLector()
        .then((s) => {
          if (!alive) return;
          setEstado(s);
          setFailed(false);
        })
        .catch(() => alive && setFailed(true));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, []);

  const reanudar = async () => {
    try {
      setEstado(await resumeLector());
      onNotice("El lector vuelve a proponer desde el próximo proceso; la cuenta empieza de nuevo.");
    } catch (err) {
      onError(apiMessage(err, "No se pudo reanudar el lector."));
    }
  };

  return (
    <section className="mt-8 space-y-3">
      <div>
        <h2 className="text-base font-semibold text-foreground">El lector</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Propone figuras que ninguna regla tomó; nunca cuentan hasta que alguien diga qué son. Si
          tu taller descarta casi todo lo que propone, se pausa solo para no cargarte la revisión.
        </p>
      </div>
      {failed ? (
        <Callout tone="warning">No se pudo leer el estado del lector.</Callout>
      ) : estado === null ? (
        <Skeleton className="h-16" />
      ) : (
        <>
          <dl className="grid max-w-xl grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted">Versión</dt>
              <dd className="font-mono text-foreground">{estado.version ?? "sin modelo"}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Confirmadas</dt>
              <dd className="tabular-nums text-foreground">{estado.confirmadas}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Descartadas</dt>
              <dd className="tabular-nums text-foreground">{estado.descartadas}</dd>
            </div>
          </dl>
          {estado.pausado ? (
            <Callout
              tone="warning"
              action={
                <Button size="sm" onClick={reanudar}>
                  Reanudar
                </Button>
              }
            >
              En pausa: de las últimas {estado.decisiones} propuestas tu taller confirmó{" "}
              {estado.confirmadas}. Menos de {Math.round(estado.aceptacion_minima * 100)} de cada
              100 eran elementos.
            </Callout>
          ) : estado.decisiones < estado.minimo ? (
            <p className="text-xs text-muted">
              Con {estado.minimo} decisiones se sabe si le sirve a tu taller; van {estado.decisiones}.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
