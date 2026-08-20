"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ShieldCheck, TriangleAlert } from "lucide-react";
import type { RiskFinding } from "@/lib/api";
import { useRiskReport } from "@/lib/useProjectReport";
import {
  Badge,
  Callout,
  Card,
  EmptyState,
  Metric,
  PageHeader,
  Skeleton,
  type BadgeTone,
} from "@/components/ui";

const SEVERITY_LABELS: Record<string, string> = {
  high: "Alto",
  medium: "Medio",
  low: "Bajo",
};

const SEVERITY_TONES: Record<string, BadgeTone> = {
  high: "danger",
  medium: "warning",
  low: "default",
};

const RISK_TYPE_LABELS: Record<string, string> = {
  unresolved_detail_reference: "Referencia de detalle sin resolver",
  column_tag_without_grid: "Columna sin eje cercano",
  footing_without_column: "Zapata sin columna asociada",
  duplicate_column_tag: "Etiqueta de columna duplicada",
  low_confidence_detection_in_takeoff: "Baja confianza en cuantificación",
  unknown_drawing_units: "Unidades de dibujo inciertas",
  unknown_layer_entities: "Capas no reconocidas",
  empty_drawing_after_parsing: "Plano vacío tras la lectura",
};

const FILTERS = ["all", "high", "medium", "low"] as const;

export default function RiesgosPage() {
  const { id } = useParams<{ id: string }>();
  const { risks, error } = useRiskReport(id);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");

  const filtered = useMemo(() => {
    if (!risks) return [];
    const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
    return risks.findings
      .filter((f) => filter === "all" || f.severity === filter)
      .sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
  }, [risks, filter]);

  if (error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Riesgos" />
        <Callout tone="danger">
          No se pudo cargar el reporte de riesgos. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!risks) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <Skeleton className="mb-6 h-14 w-80" />
        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
          <Skeleton className="h-[104px]" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      </div>
    );
  }

  const counts = risks.counts_by_severity;

  return (
    <div className="rise-in px-6 py-7 lg:px-8">
      <PageHeader
        title="Riesgos"
        sub="Hallazgos deterministas sobre el plano y la cuantificación; cada uno indica su evidencia y la acción humana recomendada."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Metric
          label="Severidad alta"
          value={counts.high ?? 0}
          accent={(counts.high ?? 0) > 0 ? "danger" : undefined}
        />
        <Metric label="Severidad media" value={counts.medium ?? 0} />
        <Metric label="Severidad baja" value={counts.low ?? 0} />
      </div>

      {risks.findings.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {FILTERS.map((key) => {
            const active = filter === key;
            const label =
              key === "all" ? `Todos (${risks.findings.length})` : SEVERITY_LABELS[key];
            return (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  active
                    ? "bg-primary text-primary-fg"
                    : "border border-border bg-surface text-muted hover:bg-surface-2 hover:text-foreground"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {risks.findings.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck size={22} />}
          title="Sin riesgos detectados"
          hint="El análisis determinista no encontró hallazgos en este procesamiento. Revisa igualmente las advertencias del presupuesto."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<TriangleAlert size={22} />}
          title="Sin hallazgos con este filtro"
          hint="Cambia el filtro de severidad para ver el resto de los hallazgos."
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((finding) => (
            <RiskCard key={finding.risk_id} finding={finding} />
          ))}
        </div>
      )}
    </div>
  );
}

function RiskCard({ finding }: { finding: RiskFinding }) {
  const relatedCount = finding.related_detections.length + finding.source_entities.length;
  return (
    <Card className="p-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge dot tone={SEVERITY_TONES[finding.severity] ?? "default"}>
          {SEVERITY_LABELS[finding.severity] ?? finding.severity}
        </Badge>
        <span className="text-sm font-semibold">
          {RISK_TYPE_LABELS[finding.risk_type] ?? finding.risk_type}
        </span>
      </div>
      <p className="text-sm leading-relaxed">{finding.message}</p>
      <div className="mt-3 rounded-lg bg-primary-soft px-3.5 py-2.5 text-sm text-primary">
        <span className="font-medium">Acción recomendada:</span>{" "}
        {finding.recommended_human_action}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        <span>
          Método: <span className="font-mono">{finding.evidence.method}</span>
        </span>
        <span className="tabular">
          Confianza {(finding.evidence.confidence * 100).toFixed(0)}%
        </span>
        {relatedCount > 0 && (
          <span className="tabular">
            {relatedCount} {relatedCount === 1 ? "elemento relacionado" : "elementos relacionados"}
          </span>
        )}
      </div>
      {finding.evidence.notes.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-faint">
          {finding.evidence.notes.slice(0, 3).map((note, i) => (
            <li key={i}>· {note}</li>
          ))}
        </ul>
      )}
    </Card>
  );
}
