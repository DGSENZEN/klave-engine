"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { DownloadSimple, Eye } from "@phosphor-icons/react";
import { PlanoCanvas } from "@/components/PlanoCanvas";
import { familyOf, HIDDEN_BY_DEFAULT } from "@/lib/families";
import { getShared, sharedGeneradoresUrl, type DetectionOverlay, type Geometry } from "@/lib/api";
import { Callout, Skeleton } from "@/components/ui";

/**
 * Lo que ve quien abre una liga de Klave: el plano con sus elementos y los
 * generadores para descargar. Sin cuenta, de sólo lectura, sin dinero.
 * «?bbox=» encuadra el elemento al que apuntaba la liga del generador.
 */
export default function CompartidoPage() {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-96" />}>
      <Compartido />
    </Suspense>
  );
}

function Compartido() {
  const { token } = useParams<{ token: string }>();
  const searchParams = useSearchParams();
  const [meta, setMeta] = useState<{ project_name: string } | null>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<DetectionOverlay | null>(null);

  useEffect(() => {
    let alive = true;
    const handle = window.setTimeout(() => {
      Promise.all([
        getShared<{ project_name: string }>(token),
        getShared<Geometry>(token, "/geometry"),
      ])
        .then(([m, g]) => {
          if (!alive) return;
          setMeta(m);
          setGeometry(g);
        })
        .catch(() => alive && setFailed(true));
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(handle);
    };
  }, [token]);

  const layers = useMemo(
    () => new Set((geometry?.layers ?? []).slice(0, 14).map((l) => l.name)),
    [geometry],
  );
  const families = useMemo(
    () =>
      new Set(
        (geometry?.detections ?? []).map(familyOf).filter((f) => !HIDDEN_BY_DEFAULT.has(f)),
      ),
    [geometry],
  );
  const focus = useMemo(() => {
    const parts = (searchParams.get("bbox") ?? "").split(",").map(Number);
    if (parts.length !== 4 || parts.some((v) => !Number.isFinite(v))) return null;
    const [x0, y0, x1, y1] = parts;
    const pad = Math.max(x1 - x0, y1 - y0, 1) * 2;
    return { bbox: [x0 - pad, y0 - pad, x1 + pad, y1 + pad] as [number, number, number, number], nonce: 1 };
  }, [searchParams]);

  if (failed) {
    return (
      <main className="mx-auto max-w-xl px-6 py-16">
        <Callout tone="warning">
          Esta liga no existe, caducó o la revocaron. Pide una nueva a quien te la compartió.
        </Callout>
      </main>
    );
  }
  if (!meta || !geometry) return <Skeleton className="m-6 h-96" />;

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-5 py-3">
        <Eye size={18} className="text-muted" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold">{meta.project_name}</div>
          <div className="text-xs text-muted">
            Liga de sólo lectura de Klave · el plano con sus elementos y los generadores
          </div>
        </div>
        <a
          href={sharedGeneradoresUrl(token)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-surface-2"
        >
          <DownloadSimple size={15} weight="bold" /> Generadores (Excel)
        </a>
      </header>
      <div className="relative min-h-0 flex-1">
        <PlanoCanvas
          geometry={geometry}
          visibleLayers={layers}
          visibleFamilies={families}
          minConfidence={0}
          selectedId={selected?.id ?? null}
          onSelect={setSelected}
          focus={focus}
        />
        {selected && (
          <div className="absolute bottom-4 left-4 max-w-sm rounded-lg border border-border bg-surface p-3 text-sm shadow-lg">
            <div className="font-medium">{selected.display_label || selected.label}</div>
            {selected.description && <div className="text-xs text-muted">{selected.description}</div>}
            {(selected.medidas ?? []).length > 0 && (
              <div className="mt-1 text-xs text-muted">
                {(selected.medidas ?? []).map((m) => `${m.label}: ${m.value}`).join(" · ")}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
