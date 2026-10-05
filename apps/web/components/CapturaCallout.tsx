"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCaptura, type CapturaState } from "@/lib/api";
import { Button, Callout } from "@/components/ui";

/**
 * «Lo que el plano no dio»: lo que hay que capturar a mano antes de entregar.
 * Sólo existe cuando algo falta; plegado por defecto, con la cuenta a la vista.
 * La misma lista viaja como hoja en cada libro exportado.
 */
export function CapturaCallout({ projectId, reloadKey }: { projectId: string; reloadKey?: number }) {
  const [data, setData] = useState<CapturaState | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      getCaptura(projectId)
        .then((d) => alive && setData(d))
        .catch(() => alive && setData(null));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [projectId, reloadKey]);
  if (!data || data.total === 0) return null;
  const vistos = data.vistos_sin_cantidad.reduce((a, v) => a + v.cantidad, 0);
  const ausentes = data.esperado_y_ausente ?? [];
  const partes = [
    ausentes.length ? `${ausentes.length} ${ausentes.length === 1 ? "partida esperada" : "partidas esperadas"} y ausentes` : "",
    vistos ? `${vistos} elementos vistos sin cantidad` : "",
    data.sin_precio.length ? `${data.sin_precio.length} renglones sin precio` : "",
    data.hojas_sin_lectura.length ? `${data.hojas_sin_lectura.length} hojas sin lectura` : "",
  ].filter(Boolean);
  return (
    <div className="mb-4">
      <Callout
        tone="warning"
        action={
          <Button size="sm" variant="ghost" onClick={() => setOpen((o) => !o)}>
            {open ? "Ocultar" : "Ver la lista"}
          </Button>
        }
      >
        <strong>Lo que el plano no dio:</strong> {partes.join(" · ")}. Captúralo a mano antes de
        entregar; la lista viaja en cada libro exportado.
        {open && ausentes.length > 0 && (
          <div className="mt-3 text-sm">
            <div className="microlabel mb-1">Esperado y ausente</div>
            <ul className="space-y-1">
              {ausentes.map((a) => (
                <li key={a.id}>
                  <strong>{a.partida}</strong>: {a.porque}{" "}
                  <span className="text-xs text-muted">({a.evidencia})</span>{" "}
                  <Link href="/catalogo?tab=conceptos" className="text-xs underline">
                    agregarla desde tu catálogo
                  </Link>
                </li>
              ))}
            </ul>
            <p className="mt-1 text-xs text-faint">
              Si ya está incluida en otro precio, dilo en su renglón («incluye…») y deja de aparecer.
            </p>
          </div>
        )}
        {open && (
          <div className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
            {data.vistos_sin_cantidad.length > 0 && (
              <div>
                <div className="microlabel mb-1">Vistos sin cantidad</div>
                <ul className="space-y-0.5">
                  {data.vistos_sin_cantidad.map((v) => (
                    <li key={v.familia}>
                      {v.familia} <span className="tabular text-muted">· {v.cantidad}</span>
                      {v.marcas.length > 0 && (
                        <span className="text-xs text-faint"> ({v.marcas.slice(0, 4).join(", ")})</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.sin_precio.length > 0 && (
              <div>
                <div className="microlabel mb-1">Sin precio</div>
                <ul className="space-y-0.5">
                  {data.sin_precio.slice(0, 12).map((p) => (
                    <li key={p.descripcion} className="truncate">
                      {p.descripcion}{" "}
                      <span className="tabular text-muted">
                        · {p.cantidad.toLocaleString("es-MX", { maximumFractionDigits: 2 })} {p.unidad}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {data.hojas_sin_lectura.length > 0 && (
              <div>
                <div className="microlabel mb-1">Hojas sin lectura</div>
                <ul className="space-y-0.5">
                  {data.hojas_sin_lectura.map((h) => (
                    <li key={h.hoja} className="truncate">
                      {h.hoja} <span className="text-xs text-faint">· {h.disciplina}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Callout>
    </div>
  );
}
