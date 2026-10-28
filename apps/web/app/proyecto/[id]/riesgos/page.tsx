"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { CaretDown, MapTrifold, ShieldCheck, Warning } from "@phosphor-icons/react";
import type { RiskFinding } from "@/lib/api";
import { useRiskReport } from "@/lib/useProjectReport";
import {
  Badge,
  Callout,
  EmptyState,
  PageHeader,
  SkeletonCards,
  SkeletonHeader,
  SkeletonMetrics,
  StatStrip,
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
  sparse_grid: "Malla de ejes incompleta",
  unresolved_detail_reference: "Referencia de detalle sin resolver",
  column_tag_without_grid: "Columna sin eje cercano",
  footing_without_column: "Zapata sin columna asociada",
  duplicate_column_tag: "Etiqueta de columna duplicada",
  low_confidence_detection_in_takeoff: "Baja confianza en cuantificación",
  unknown_drawing_units: "Unidades de dibujo inciertas",
  unknown_layer_entities: "Capas no reconocidas",
  empty_drawing_after_parsing: "Plano vacío tras la lectura",
};

type Filter = "all" | "high" | "medium" | "low";

export default function RiesgosPage() {
  const { id } = useParams<{ id: string }>();
  const { risks, error } = useRiskReport(id);
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    if (!risks) return [];
    const order: Record<string, number> = { high: 0, medium: 1, low: 2 };
    return risks.findings
      .filter((f) => filter === "all" || f.severity === filter)
      .sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));
  }, [risks, filter]);

  if (error) {
    return (
      <div className="px-4 py-5 sm:px-6">
        <PageHeader title="Riesgos" />
        <Callout tone="danger">
          No se pudo cargar el reporte de riesgos. Revisa que el servidor esté activo.
        </Callout>
      </div>
    );
  }

  if (!risks) {
    return (
      <div className="px-4 py-5 sm:px-6">
        <SkeletonHeader />
        <SkeletonMetrics count={3} />
        <SkeletonCards count={3} />
      </div>
    );
  }

  const counts = risks.counts_by_severity;

  return (
    <div className="px-4 py-5 sm:px-6">
      <PageHeader
        title="Riesgos"
        sub="Hallazgos deterministas sobre el plano y la cuantificación; cada uno indica su evidencia y la acción humana recomendada."
      />

      {/* The counts are the filter: clicking one shows exactly what it counts. */}
      <StatStrip
        className="mb-4"
        stats={[
          {
            // Same unit as the severities beside it (elements, not groups).
            label: "Todos",
            value: (counts.high ?? 0) + (counts.medium ?? 0) + (counts.low ?? 0),
            hint:
              risks.findings.length === 1
                ? "en 1 hallazgo"
                : `en ${risks.findings.length} hallazgos`,
            active: filter === "all",
            onClick: () => setFilter("all"),
          },
          {
            label: "Severidad alta",
            value: counts.high ?? 0,
            tone: (counts.high ?? 0) > 0 ? "danger" : undefined,
            active: filter === "high",
            onClick: () => setFilter("high"),
          },
          {
            label: "Severidad media",
            value: counts.medium ?? 0,
            active: filter === "medium",
            onClick: () => setFilter("medium"),
          },
          {
            label: "Severidad baja",
            value: counts.low ?? 0,
            active: filter === "low",
            onClick: () => setFilter("low"),
          },
        ]}
      />

      {risks.findings.length === 0 ? (
        <EmptyState
          icon={<ShieldCheck size={20} weight="duotone" />}
          title="Sin riesgos detectados"
          hint="El análisis determinista no encontró hallazgos en este procesamiento. Revisa igualmente las advertencias del presupuesto."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Warning size={20} weight="duotone" />}
          title="Sin hallazgos con este filtro"
          hint="Cambia el filtro de severidad para ver el resto de los hallazgos."
        />
      ) : (
        <ul className="card divide-y divide-border overflow-clip">
          {filtered.map((finding) => (
            <RiskCard key={finding.risk_id} finding={finding} projectId={id} />
          ))}
        </ul>
      )}
    </div>
  );
}

function RiskCard({ finding, projectId }: { finding: RiskFinding; projectId: string }) {
  // La tarjeta agrupada abre su lista de miembros; una tarjeta suelta no
  // tiene nada que abrir. Sin nombres de método ni porcentajes estampados:
  // el título del oficio, la cuenta y la acción — lo que se decide con.
  const [open, setOpen] = useState(false);
  const members = finding.members ?? [];
  const grouped = (finding.member_count ?? 0) > 1 && members.length > 0;
  return (
    <li className="px-4 py-3">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <Badge dot tone={SEVERITY_TONES[finding.severity] ?? "default"}>
          {SEVERITY_LABELS[finding.severity] ?? finding.severity}
        </Badge>
        <span className="text-sm font-semibold">
          {finding.titulo || RISK_TYPE_LABELS[finding.risk_type] || finding.risk_type}
        </span>
        {grouped && (
          <span className="tabular text-xs text-muted">
            {finding.member_count} elementos
          </span>
        )}
      </div>
      <p className="text-[13px] leading-relaxed">{finding.message}</p>
      {finding.bbox && (
        <Link
          href={`/proyecto/${projectId}/plano?bbox=${finding.bbox.map((v) => v.toFixed(2)).join(",")}`}
          className="mt-1 inline-flex items-center gap-1 text-xs text-accent underline"
        >
          <MapTrifold size={14} /> ver en el plano
        </Link>
      )}
      <p className="mt-1.5 text-[13px]">
        <span className="text-muted">Acción recomendada:</span>{" "}
        {finding.recommended_human_action}
      </p>
      {grouped && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-foreground"
          >
            <CaretDown
              size={12}
              className={`transition-transform ${open ? "" : "-rotate-90"}`}
            />
            {open ? "Ocultar los elementos" : `Ver los ${finding.member_count} elementos`}
          </button>
          {open && (
            <ul className="mt-2 space-y-1.5 border-l border-border pl-3">
              {members.map((member, i) => (
                <li key={i} className="text-xs text-muted">
                  {member.message}{" "}
                  {member.bbox && (
                    <Link
                      href={`/proyecto/${projectId}/plano?bbox=${member.bbox
                        .map((v) => v.toFixed(2))
                        .join(",")}`}
                      className="inline-flex items-center gap-1 text-accent underline"
                    >
                      <MapTrifold size={14} /> ver
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {finding.evidence.notes.length > 0 && (
        <ul className="mt-1.5 space-y-0.5 text-xs text-muted">
          {finding.evidence.notes.slice(0, 3).map((note, i) => (
            <li key={i}>· {note}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
