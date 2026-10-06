"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  apiMessage,
  confirmPropuesta,
  getPropuestas,
  rejectPropuesta,
  type Propuesta,
} from "@/lib/api";
import { Button, Callout, Select, Skeleton, Td, Th } from "@/components/ui";

/**
 * «Propuestas del lector»: figuras que ninguna regla tomó y se parecen a lo
 * que las reglas sí leen. Punteadas en el plano, sin contar. Decir qué son
 * las agrega como elemento omitido con la medida del recuadro; decir que no
 * son elemento las quita. Las dos decisiones enseñan al lector.
 */

const NOMBRE: Record<string, string> = {
  castillo: "Castillo",
  columna: "Columna",
  pilote: "Pilote",
  zapata: "Zapata",
};

const hojaCorta = (hoja: string) => hoja.replace(/\.(dxf|dwg)$/i, "");

export function PropuestasSection({
  projectId,
  actorName,
  clientId,
  reloadKey,
}: {
  projectId: string;
  actorName: string;
  clientId: string | null;
  reloadKey?: unknown;
}) {
  const [state, setState] = useState<{ familias: string[]; propuestas: Propuesta[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [familia, setFamilia] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getPropuestas(projectId)
        .then((s) => {
          if (!alive) return;
          setState(s);
          setFailed(false);
        })
        .catch(() => alive && setFailed(true));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [projectId, reloadKey, version]);

  const decidir = async (p: Propuesta, que: "confirmar" | "descartar") => {
    setBusy(p.key);
    setError(null);
    try {
      if (que === "confirmar") {
        const fam = familia[p.key] ?? "castillo";
        await confirmPropuesta(projectId, p.key, fam, actorName, clientId);
        setNotice(
          `Agregado como ${NOMBRE[fam] ?? fam} en «Lo que Klave no vio», con la medida del recuadro.`,
        );
      } else {
        await rejectPropuesta(projectId, p.key, actorName);
        setNotice("Anotado: no es elemento. No se volverá a proponer.");
      }
      setVersion((v) => v + 1);
    } catch (err) {
      setError(apiMessage(err, "No se pudo guardar la decisión."));
    } finally {
      setBusy(null);
    }
  };

  const propuestas = state?.propuestas ?? [];
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-semibold text-foreground">Propuestas del lector</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Figuras que ninguna regla tomó y que se parecen a los elementos que sí se leen. Están
          punteadas en el plano y no cuentan en ninguna cantidad hasta que alguien diga qué son.
          Cada decisión, de un lado o del otro, le enseña al lector.
        </p>
      </div>
      {notice && <Callout tone="info">{notice}</Callout>}
      {error && <Callout tone="danger">{error}</Callout>}
      {failed ? (
        <Callout tone="warning">No se pudieron leer las propuestas.</Callout>
      ) : state === null ? (
        <Skeleton className="h-24" />
      ) : propuestas.length === 0 ? (
        <Callout tone="info">
          No hay propuestas: el lector no vio nada con forma de elemento fuera de lo que las reglas
          ya leen, o todo lo que propuso ya se decidió.
        </Callout>
      ) : (
        <>
          <Link
            href={`/proyecto/${projectId}/plano?propuestas=1`}
            className="text-sm text-accent hover:underline"
          >
            Ver las {propuestas.length} en el plano
          </Link>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <Th>Lo que se ve</Th>
                  <Th>Dibujado en</Th>
                  <Th>Qué es</Th>
                </tr>
              </thead>
              <tbody>
                {propuestas.map((p) => (
                  <tr key={p.key} className="border-t border-border align-top">
                    <Td>
                      <div className="text-foreground first-letter:uppercase">{p.razon}</div>
                      <Link
                        href={`/proyecto/${projectId}/plano?propuestas=1&bbox=${p.bbox.map((v) => v.toFixed(3)).join(",")}`}
                        className="mt-0.5 block text-xs text-accent hover:underline"
                      >
                        Ver en {hojaCorta(p.hoja)}
                      </Link>
                    </Td>
                    <Td className="font-mono text-xs text-muted">
                      {p.capa}
                      {p.bloque ? ` · ${p.bloque}` : ""}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap items-center gap-2">
                        <Select
                          size="sm"
                          aria-label="Qué elemento es"
                          value={familia[p.key] ?? "castillo"}
                          onChange={(e) => setFamilia((f) => ({ ...f, [p.key]: e.target.value }))}
                        >
                          {state.familias.map((f) => (
                            <option key={f} value={f}>
                              {NOMBRE[f] ?? f}
                            </option>
                          ))}
                        </Select>
                        <Button
                          size="sm"
                          disabled={busy === p.key}
                          onClick={() => decidir(p, "confirmar")}
                        >
                          Es un elemento
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy === p.key}
                          onClick={() => decidir(p, "descartar")}
                        >
                          No es elemento
                        </Button>
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
