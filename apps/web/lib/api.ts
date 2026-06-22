// Typed client for the Klave Engine FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public path: string, public detail?: unknown) {
    super(`API ${status} on ${path}`);
  }
}

// ---- Types (mirror the backend artifacts) ----

export type ProjectSummary = {
  project_id: string;
  name: string;
  status?: string;
  created_at?: string;
};

export type ProjectStatus = {
  project_id: string;
  state: "queued" | "running" | "processed" | "failed" | "unknown" | string;
  stage: string;
  error?: string | null;
  entity_count?: number;
  detection_count?: number;
};

export type Geometry = {
  extent: [number, number, number, number];
  layers: { name: string; count: number }[];
  shapes: (
    | { t: "path"; layer: string; pts: [number, number][]; closed: boolean }
    | { t: "circle"; layer: string; c: [number, number]; r: number }
    | { t: "box"; layer: string; bbox: [number, number, number, number] }
  )[];
  detections: DetectionOverlay[];
};

export type DetectionOverlay = {
  id: string;
  type: string;
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
};

export type BoqLine = {
  concept_code: string;
  description: string;
  unit: string;
  quantity: number;
  unit_price: number;
  amount: number;
  phase: string;
  confidence: number;
  source_detection_count: number;
  assumptions: string[];
};

export type CostReport = {
  project_id: string;
  currency: string;
  drawing_units: { unit: string; source: string; confidence: number };
  boq: {
    direct_cost_total: number;
    totals_by_phase: Record<string, number>;
    lines: BoqLine[];
    assumptions: string[];
    warnings: string[];
  };
  integration: {
    direct_cost: number;
    sale_price: number;
    contingency: number;
    grand_total: number;
    overcost_factor: number;
    lines: { description: string; percentage: number; amount: number }[];
  };
  schedule: { total_duration_days: number; phases: string[]; activities: ScheduleActivity[] };
  financial: {
    advance_payment: number;
    total_retention: number;
    annual_operating_cost: number;
    periods: unknown[];
  };
};

export type ScheduleActivity = {
  concept_code: string;
  description: string;
  phase: string;
  quantity: number;
  unit: string;
  rendimiento_per_day: number;
  duration_days: number;
  start_day: number;
  end_day: number;
  direct_cost: number;
};

export type Views = {
  is_segmented: boolean;
  npt_levels: number[];
  views: {
    title: string;
    kind: string;
    level_key: string | null;
    detection_counts: Record<string, number>;
  }[];
};

export type Dimensions = {
  dimension_count: number;
  typical_section_cm: [number, number] | null;
  typical_wall_thickness_cm: number | null;
  typical_wall_thickness_source: string | null;
  vigueta_system: string | null;
  measured_dimensions_cm: Record<string, number>;
  block_classes: Record<string, number>;
  notes: string[];
};

// ---- Calls ----

export const listProjects = () =>
  getJSON<{ projects: ProjectSummary[] }>("/projects").then((r) => r.projects);

export const getStatus = (id: string) => getJSON<ProjectStatus>(`/projects/${id}/status`);
export const getGeometry = (id: string) => getJSON<Geometry>(`/projects/${id}/geometry`);
export const getCosts = (id: string) => getJSON<CostReport>(`/projects/${id}/costs`);
export type Insumo = {
  code: string;
  description: string;
  unit: string;
  unit_cost: number;
  resource_type: string;
  is_labor_percentage: boolean;
};

export type CostingConfigFull = {
  currency: string;
  assumptions: Record<string, number>;
  indirects: Record<string, number>;
  schedule: Record<string, number>;
  financial: Record<string, number>;
};

export type CostingConfigResponse = {
  config: CostingConfigFull;
  insumos: Insumo[];
  has_overrides: boolean;
};

export type CostingOverrides = {
  config: CostingConfigFull;
  insumo_prices: Record<string, number>;
};

export const getCostingConfig = (id: string) =>
  getJSON<CostingConfigResponse>(`/projects/${id}/costing-config`);

export async function recompute(id: string, overrides: CostingOverrides): Promise<CostReport> {
  const res = await fetch(`${API_BASE}/projects/${id}/recompute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(overrides),
  });
  if (!res.ok) throw new ApiError(res.status, "/recompute");
  return res.json();
}

export const getViews = (id: string) =>
  getJSON<Views>(`/projects/${id}/views`).catch(() => null);
export const getDimensions = (id: string) =>
  getJSON<Dimensions>(`/projects/${id}/dimensions`).catch(() => null);

export async function uploadProject(file: File): Promise<{ project_id: string; warnings: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/projects/upload`, { method: "POST", body: form });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, "/projects/upload", detail);
  }
  return res.json();
}

export const money = (n: number, currency = "MXN") =>
  new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);

export const money2 = (n: number, currency = "MXN") =>
  new Intl.NumberFormat("es-MX", { style: "currency", currency }).format(n);

export const num = (n: number, digits = 2) =>
  new Intl.NumberFormat("es-MX", { maximumFractionDigits: digits }).format(n);
