"use client";

import { useEffect, useState } from "react";
import { apiMessage, forgetPerfil, getPerfil, type PerfilEntrada } from "@/lib/api";
import { Badge, Button, Callout, Skeleton, Td, Th } from "@/components/ui";

/**
 * «Lo que tu taller enseñó»: cada bloque o capa que la oficina confirmó o
 * excluyó en Revisión, con cuántas veces. Con tres a favor y ninguna en
 * contra, un bloque de algo que se cuenta por pieza entra a la lectura;
 * lo que se excluye tres veces entra con una duda. Olvidar lo deja de
 * aplicar desde el próximo proceso. Nada de esto sale del taller.
 */

const ACTUA: Record<PerfilEntrada["actua"], { label: string; tone: "accent" | "warning" | "default" }> = {
  agrega: { label: "Entra a la lectura", tone: "accent" },
  duda: { label: "Entra con duda", tone: "warning" },
  "": { label: "Aún no actúa", tone: "default" },
};

export function PerfilTallerSection({
  onError,
  onNotice,
}: {
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
}) {
  const [state, setState] = useState<{ firme: number; entradas: PerfilEntrada[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getPerfil()
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
  }, [version]);

  const olvidar = async (entrada: PerfilEntrada) => {
    try {
      await forgetPerfil(entrada.clave);
      onNotice(`Olvidado: ${entrada.kind} «${entrada.value}». Deja de aplicar desde el próximo proceso.`);
      setVersion((v) => v + 1);
    } catch (err) {
      onError(apiMessage(err, "No se pudo olvidar esa entrada del perfil."));
    }
  };

  return (
    <section className="mt-8 space-y-3">
      <div>
        <h2 className="text-base font-semibold text-foreground">Lo que tu taller enseñó</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Cada vez que alguien confirma, excluye o reasigna un elemento en Revisión, Klave anota el
          bloque y la capa con que estaba dibujado. Con {state?.firme ?? 3} a favor y ninguna en
          contra, un bloque de castillo, columna o pilote entra solo a la lectura del siguiente
          proceso — dicho en el renglón y excluible como cualquier otro. Lo que tu taller excluye
          nunca se quita: entra con una duda. Nada de esto sale de tu taller.
        </p>
      </div>
      {failed ? (
        <Callout tone="warning">No se pudo leer el perfil del taller.</Callout>
      ) : state === null ? (
        <Skeleton className="h-24" />
      ) : state.entradas.length === 0 ? (
        <Callout tone="info">
          Aún no hay nada. Se llena solo conforme tu taller revisa sus planos.
        </Callout>
      ) : (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <Th>Dibujado como</Th>
                <Th>Leído como</Th>
                <Th className="text-right">A favor</Th>
                <Th className="text-right">En contra</Th>
                <Th>Qué hace</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {state.entradas.map((e) => (
                <tr key={e.clave} className="border-t border-border">
                  <Td>
                    <span className="text-muted">{e.kind === "bloque" ? "Bloque" : "Capa"}</span>{" "}
                    <span className="font-mono">{e.value}</span>
                  </Td>
                  <Td>{e.family || e.detection_type}</Td>
                  <Td className="text-right tabular-nums">{e.a_favor}</Td>
                  <Td className="text-right tabular-nums">{e.en_contra}</Td>
                  <Td>
                    <Badge tone={ACTUA[e.actua].tone}>{ACTUA[e.actua].label}</Badge>
                  </Td>
                  <Td className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => olvidar(e)}>
                      Olvidar
                    </Button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
