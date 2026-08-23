"use client";

import type { CostingConfigFull } from "@/lib/api";
import { Card, Input, SectionTitle } from "@/components/ui";

/** One vocabulary for costing parameters, shared by the project page and
 * the taller defaults so the same field reads the same everywhere. */
export const CONFIG_LABELS: Record<string, string> = {
  // assumptions
  column_section_m2: "Sección de columna sin cuadro (m²)",
  castillo_section_m2: "Sección de castillo sin cuadro (m²)",
  contratrabe_section_m2: "Sección de contratrabe sin cuadro (m²)",
  dala_section_m2: "Sección de dala sin cuadro (m²)",
  slab_thickness_m: "Espesor de losa maciza sin etiqueta (m)",
  mat_thickness_m: "Espesor de losa de cimentación sin etiqueta (m)",
  column_height_m: "Altura de entrepiso sin niveles (m)",
  beam_section_m2: "Sección de trabe sin cuadro (m²)",
  wall_height_m: "Altura de muro sin niveles (m)",
  opening_share_pct: "Vanos supuestos en muros sin puertas/ventanas leídas (%)",
  opening_height_m: "Altura de vano leído (m)",
  footing_depth_m: "Peralte de zapata (m)",
  excavation_depth_m: "Prof. excavación (m)",
  excavation_swell_factor: "Factor abundamiento",
  platform_level_m: "Nivel de plataforma (datum del levantamiento)",
  despalme_thickness_m: "Espesor de despalme (m)",
  area_construida_m2: "Área construida (m², vacío = leída de las losas)",
  // indirects
  field_indirects_pct: "Indirectos de campo (%)",
  office_indirects_pct: "Indirectos de oficina (%)",
  financing_pct: "Financiamiento (%)",
  profit_pct: "Utilidad (%)",
  additional_charges_pct: "Cargos adicionales (%)",
  contingency_pct: "Contingencia (%)",
  // schedule
  workdays_per_month: "Días hábiles por mes",
  intra_phase_overlap_pct: "Traslape entre actividades (%)",
  phase_overlap_pct: "Traslape entre fases (%)",
  crews_per_activity: "Cuadrillas por actividad",
  per_level_cycle_days: "Ciclo por nivel (días)",
  // financial
  advance_payment_pct: "Anticipo (%)",
  retention_pct: "Retención (%)",
  annual_operation_pct: "Operación anual (%)",
  annual_maintenance_pct: "Mantenimiento anual (%)",
  operating_horizon_years: "Horizonte O&M (años)",
};

export const CONFIG_GROUPS: { group: keyof CostingConfigFull; title: string }[] = [
  { group: "assumptions", title: "Supuestos geométricos" },
  { group: "indirects", title: "Indirectos y sobrecosto" },
  { group: "schedule", title: "Programa de obra" },
  { group: "financial", title: "Financiero" },
];

export function ConfigGroup({
  title,
  group,
  config,
  onChange,
}: {
  title: string;
  group: keyof CostingConfigFull;
  config: CostingConfigFull;
  onChange: (g: keyof CostingConfigFull, k: string, v: number | null) => void;
}) {
  const entries = Object.entries(config[group] as Record<string, number | null>);
  return (
    <Card className="p-5">
      <SectionTitle>{title}</SectionTitle>
      <div className="space-y-2.5">
        {entries.map(([key, value]) => (
          <label key={key} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-muted">{CONFIG_LABELS[key] ?? key}</span>
            <Input
              type="number"
              step="any"
              value={value ?? ""}
              placeholder={value === null ? "sin definir" : undefined}
              onChange={(e) =>
                onChange(group, key, e.target.value === "" ? null : Number(e.target.value))
              }
              className="w-28 px-2 py-1 text-right tabular"
            />
          </label>
        ))}
      </div>
    </Card>
  );
}
