"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ArrowsClockwise,
  FileText,
  Ruler,
  Scan,
  Stack,
  Warning,
} from "@phosphor-icons/react";
import { getLectura, num, type Lectura, type LecturaSheet } from "@/lib/api";
import { FAMILY_LABELS } from "@/components/PlanoCanvas";
import { useProjectLive } from "@/components/ProjectLive";
import {
  Badge,
  Callout,
  Card,
  Metric,
  PageHeader,
  SectionTitle,
  SkeletonCards,
  SkeletonHeader,
  SkeletonMetrics,
} from "@/components/ui";

export default function LecturaPage() {
  const { id } = useParams<{ id: string }>();
  const [lectura, setLectura] = useState<Lectura | null>(null);
  const [error, setError] = useState(false);
  const { latestEvent, connectionEpoch } = useProjectLive();

  useEffect(() => {
    let active = true;
    getLectura(id)
      .then((data) => {
        if (active) {
          setLectura(data);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [id, connectionEpoch]);

  useEffect(() => {
    if (latestEvent?.type !== "run_published") return;
    getLectura(id).then(setLectura).catch(() => {});
  }, [id, latestEvent]);

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Lectura del plano" />
        <Callout tone="danger">
          No se pudo cargar la lectura. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!lectura) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <SkeletonMetrics count={4} />
        <SkeletonCards count={2} />
      </div>
    );
  }

  const totalEntities = lectura.sheets.reduce(
    (sum, sheet) => sum + (sheet.parse?.entity_count ?? 0),
    0,
  );
  const maxLayerCount = Math.max(...lectura.layers.map((l) => l.entity_count), 1);

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Lectura del plano"
        sub="Qué leyó Klave de tus archivos: conversión, entidades, capas, bloques y lo que se omitió. Aquí se decide si puedes confiar en lo demás."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Unidades"
          value={lectura.units?.unit ?? "—"}
          hint={
            lectura.units
              ? `${Math.round(lectura.units.confidence * 100)}% · ${lectura.units.source_label}`
              : undefined
          }
          icon={<Ruler size={16} weight="duotone" />}
          accent={lectura.units && lectura.units.confidence >= 0.7 ? "success" : undefined}
        />
        <Metric
          label="Hojas"
          value={lectura.sheets.length}
          icon={<FileText size={16} weight="duotone" />}
        />
        <Metric
          label="Entidades leídas"
          value={num(totalEntities, 0)}
          icon={<Stack size={16} weight="duotone" />}
        />
        <Metric
          label="Detecciones"
          value={lectura.detection_total}
          icon={<Scan size={16} weight="duotone" />}
        />
      </div>

      <div className="mb-6 space-y-3">
        {lectura.sheets.map((sheet) => (
          <SheetCard key={sheet.name} sheet={sheet} labels={lectura.entity_type_labels} />
        ))}
      </div>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <SectionTitle
            sub={
              lectura.layer_total > lectura.layers.length
                ? `Las ${lectura.layers.length} capas con más entidades de ${lectura.layer_total}.`
                : "Todas las capas del dibujo."
            }
          >
            Capas
          </SectionTitle>
          <div className="space-y-2">
            {lectura.layers.map((layer) => (
              <div key={layer.layer}>
                <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
                  <span className="truncate font-mono text-xs">{layer.layer}</span>
                  <span className="tabular text-xs text-muted">{layer.entity_count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full bg-chart-2"
                    style={{ width: `${(layer.entity_count / maxLayerCount) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <SectionTitle sub="Familias estructurales que la detección encontró.">
              Detecciones por familia
            </SectionTitle>
            {lectura.detection_total === 0 ? (
              <p className="text-sm text-muted">
                Sin detecciones: el visor y las herramientas de medición siguen
                disponibles.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {Object.entries(lectura.detections_by_family).map(([family, count]) => (
                  <span
                    key={family}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 text-xs"
                  >
                    {FAMILY_LABELS[family] ?? family}
                    <span className="tabular font-semibold">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </Card>

          {lectura.blocks.length > 0 && (
            <Card className="p-5">
              <SectionTitle sub="Definiciones de bloque más usadas; su geometría interna se expande para la detección.">
                Bloques
              </SectionTitle>
              <div className="flex flex-wrap gap-2">
                {lectura.blocks.map((block) => (
                  <span
                    key={block.block_name}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface-2/60 px-2.5 py-1.5 font-mono text-xs"
                  >
                    {block.block_name}
                    <span className="tabular font-semibold">×{block.insert_count}</span>
                  </span>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {lectura.warning_groups.length > 0 && (
        <Card className="p-5">
          <SectionTitle sub="Nada se omite en silencio: esto es lo que no se pudo leer o se ajustó.">
            Avisos de lectura
          </SectionTitle>
          <ul className="space-y-3">
            {lectura.warning_groups.map((group) => (
              <li key={group.type} className="text-sm">
                <div className="flex items-center gap-2">
                  <Warning size={15} weight="bold" className="shrink-0 text-warning" />
                  <span className="font-medium">{group.label}</span>
                  <span className="tabular text-xs text-muted">×{group.count}</span>
                </div>
                {group.samples[0] && (
                  <p className="ml-6 mt-0.5 text-xs text-faint">{group.samples[0]}</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function SheetCard({
  sheet,
  labels,
}: {
  sheet: LecturaSheet;
  labels: Record<string, string>;
}) {
  const parse = sheet.parse;
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <FileText size={16} weight="duotone" className="text-muted" />
        <span className="font-medium">{sheet.sheet_number ?? sheet.name}</span>
        <span className="text-xs text-faint">{sheet.name}</span>
        <span className="uppercase text-xs text-faint">{sheet.file_type}</span>
        {sheet.conversion && (
          <Badge tone={sheet.conversion.status === "success" ? "success" : "warning"}>
            {sheet.conversion.status === "success" ? "Convertido" : "Conversión con avisos"}
          </Badge>
        )}
        {parse?.recovered && (
          <Badge tone="warning" dot>
            <ArrowsClockwise size={11} weight="bold" /> Leído en recuperación
          </Badge>
        )}
      </div>
      {parse ? (
        <>
          <div className="flex flex-wrap gap-2">
            {Object.entries(parse.entities_by_type).map(([type, count]) => (
              <span
                key={type}
                className="inline-flex items-center gap-1.5 rounded-lg bg-surface-2/70 px-2.5 py-1.5 text-xs"
              >
                {labels[type] ?? type}
                <span className="tabular font-semibold">{count}</span>
              </span>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
            {parse.from_block_count > 0 && (
              <span>{parse.from_block_count} entidades expandidas de bloques</span>
            )}
            {Object.entries(parse.derived_by_type).map(([type, count]) => (
              <span key={type}>
                {count} de {type}
              </span>
            ))}
            {Object.entries(parse.dropped_by_type).length > 0 && (
              <span className="text-warning">
                Omitidas:{" "}
                {Object.entries(parse.dropped_by_type)
                  .map(([type, count]) => `${type}×${count}`)
                  .join(", ")}
              </span>
            )}
          </div>
        </>
      ) : (
        <p className="text-sm text-muted">
          Sin resumen de lectura para esta hoja (procesamiento anterior a esta versión;
          vuelve a procesar el proyecto).
        </p>
      )}
    </Card>
  );
}
