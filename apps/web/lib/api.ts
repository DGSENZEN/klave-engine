// Typed client for the Klave Engine FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    credentials: "include",
  });
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

async function postJSON<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

async function putJSON<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

async function patchJSON<T>(
  path: string,
  body: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

async function deleteJSON<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    credentials: "include",
    headers,
  });
  if (!res.ok) {
    let detail: unknown;
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
  client?: string | null;
  archived?: boolean;
  sheet_count?: number;
};

export type ProjectStatus = {
  project_id: string;
  job_id?: string;
  run_id?: string;
  state: "queued" | "running" | "processed" | "failed" | "unknown" | string;
  stage: string;
  error?: string | null;
  entity_count?: number;
  detection_count?: number;
  artifacts_available?: boolean;
};

export type ProjectEvent = {
  seq: number;
  ts: string;
  type:
    | "project_created"
    | "project_updated"
    | "job_updated"
    | "run_published"
    | "costing_updated"
    | "presence_updated"
    | "collaborator_activity"
    | string;
  project_id: string | null;
  actor: string | null;
  data: Record<string, unknown>;
};

export type PresenceViewer = {
  client_id: string;
  actor: string;
  location_path: string;
  location_label: string;
  joined_at: string;
  updated_at: string;
};

export type SheetInfo = { name: string; sheet_number: string | null; count: number };

export type Geometry = {
  extent: [number, number, number, number];
  layers: { name: string; count: number }[];
  shapes: (
    | { t: "path"; layer: string; pts: [number, number][]; closed: boolean; sheet?: number }
    | { t: "hatch"; layer: string; pts: [number, number][]; sheet?: number }
    | { t: "circle"; layer: string; c: [number, number]; r: number; sheet?: number }
    | {
        t: "arc";
        layer: string;
        c: [number, number];
        r: number;
        a0: number;
        a1: number;
        sheet?: number;
      }
    | { t: "box"; layer: string; bbox: [number, number, number, number]; sheet?: number }
    | {
        t: "text";
        layer: string;
        p: [number, number];
        h: number;
        rot: number;
        s: string;
        multi: boolean;
        sheet?: number;
      }
    | { t: "dim"; layer: string; pts: [number, number][]; label: string; sheet?: number }
  )[];
  /** Sheet frames found on the drawing (plantas and detalles), for navigation. */
  frames?: {
    code: string;
    title: string;
    kind: string;
    bbox: [number, number, number, number];
    source_file: string;
  }[];
  detections: DetectionOverlay[];
  sheets: SheetInfo[];
  units: { unit: string; to_meters: number | null } | null;
};

export type DetectionOverlay = {
  id: string;
  type: string;
  label: string;
  confidence: number;
  bbox: [number, number, number, number];
  /** Real outline in drawing units when the element is a region (tableros). */
  polygon?: [number, number][] | null;
  /** Tag read from the plano (e.g. "K-5"); empty for untagged elements. */
  mark: string;
  /** Canonical family (castillo, columna, trabe, …); empty on old runs. */
  family: string;
  family_label: string;
  /** Stable system name (e.g. "CAS-05"). */
  display_label: string;
  /** Spanish evidence sentence composed by the engine. */
  description: string;
  /** Correction loop: stable key for review calls + current human verdict. */
  review_key: string;
  review: "confirmed" | "excluded" | "";
  review_note: string;
  /** Sheet index into Geometry.sheets; null when unmapped (old runs). */
  sheet: number | null;
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
  /** Quantity per planta on a segmented sheet (view title → quantity). */
  by_view?: Record<string, number>;
};

export type ApuLine = {
  resource_code: string;
  description: string;
  unit: string;
  quantity: number;
  unit_cost: number;
  amount: number;
  resource_type: string;
};

export type Apu = {
  concept_code: string;
  concept_description: string;
  unit: string;
  lines: ApuLine[];
  /** Direct unit cost broken down by resource type. */
  breakdown: Record<string, number>;
  direct_unit_cost: number;
  /** Set when the P.U. was adopted from a reference row instead of priced from lines. */
  price_source?: string | null;
};

export type PeriodCashflow = {
  period: number;
  label: string;
  direct_spend: number;
  billing: number;
  advance_amortization: number;
  retention: number;
  net_cashflow: number;
  accumulated_billing: number;
  progress_pct: number;
};

export type OperatingYear = {
  year: number;
  operation: number;
  maintenance: number;
  total: number;
  accumulated: number;
};

export type CostReport = {
  project_id: string;
  currency: string;
  drawing_units: { unit: string; source: string; confidence: number; notes?: string[] };
  boq: {
    direct_cost_total: number;
    totals_by_phase: Record<string, number>;
    lines: BoqLine[];
    assumptions: string[];
    warnings: string[];
  };
  apus?: Apu[];
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
    advance_payment_pct?: number;
    retention_pct?: number;
    advance_payment: number;
    total_retention: number;
    annual_operating_cost: number;
    periods: PeriodCashflow[];
    operating_projection?: OperatingYear[];
  };
};

export type ScheduleActivity = {
  concept_code: string;
  description: string;
  phase: string;
  quantity: number;
  unit: string;
  rendimiento_per_day: number;
  crews?: number;
  duration_days: number;
  start_day: number;
  end_day: number;
  direct_cost: number;
};

export type RiskFinding = {
  risk_id: string;
  risk_type: string;
  severity: "low" | "medium" | "high" | string;
  message: string;
  source_entities: string[];
  related_detections: string[];
  bbox: [number, number, number, number] | null;
  evidence: {
    source: string;
    method: string;
    entity_ids: string[];
    bbox: [number, number, number, number] | null;
    confidence: number;
    notes: string[];
  };
  recommended_human_action: string;
};

export type RiskReport = {
  project_id: string;
  generated_at: string;
  findings: RiskFinding[];
  counts_by_severity: Record<string, number>;
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

export type ProjectInfo = {
  project_id: string;
  project_name: string;
  client: string | null;
  archived: boolean;
  processing_status: string;
  engine?: {
    fingerprint: string | null;
    processed_at: string | null;
    current: string;
    stale: boolean;
  };
  source_files: {
    file_id: string;
    path: string;
    file_type: string;
    sheet_number: string | null;
    discipline: string | null;
  }[];
};

export const getProject = (id: string) => getJSON<ProjectInfo>(`/projects/${id}`);
export const getStatus = (id: string) => getJSON<ProjectStatus>(`/projects/${id}/status`);
export const getEventsHistory = (id: string) =>
  getJSON<{ events: ProjectEvent[] }>(`/projects/${id}/events/history`).then(
    (r) => r.events,
  );
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
  insumo_prices: Record<string, number>;
  has_overrides: boolean;
  version: number;
  updated_by: string | null;
  updated_at: string | null;
};

export type CostingOverrides = {
  config: CostingConfigFull;
  insumo_prices: Record<string, number>;
  version: number;
};

export type ProjectActivity = {
  client_id?: string | null;
  action: string;
  label?: string;
  location_path?: string;
  location_label?: string;
};

export const getCostingConfig = (id: string) =>
  getJSON<CostingConfigResponse>(`/projects/${id}/costing-config`);

export function recompute(
  id: string,
  overrides: CostingOverrides,
  actor?: string,
  clientId?: string | null,
): Promise<CostReport> {
  return postJSON<CostReport>(`/projects/${id}/recompute`, overrides, {
    ...(actor ? { "X-Actor": actor } : {}),
    ...(clientId ? { "X-Client-Id": clientId } : {}),
  });
}

export async function publishActivity(
  id: string,
  activity: ProjectActivity,
  actor?: string,
): Promise<void> {
  await postJSON(`/projects/${id}/activity`, activity, actor ? { "X-Actor": actor } : undefined);
}

export async function publishPresence(
  id: string,
  update: { client_id: string; location_path?: string; location_label?: string },
  actor?: string,
): Promise<void> {
  await postJSON(`/projects/${id}/presence`, update, actor ? { "X-Actor": actor } : undefined);
}

export const getRisks = (id: string) => getJSON<RiskReport>(`/projects/${id}/risks`);

export type RunDiff = {
  available: boolean;
  families?: Record<string, { prev: number; new: number }>;
  added_labels?: string[];
  removed_labels?: string[];
  prev_detection_count?: number;
  new_detection_count?: number;
  prev_grand_total?: number | null;
  new_grand_total?: number;
};

export const getRunDiff = (id: string) => getJSON<RunDiff>(`/projects/${id}/diff`);

// ---- Lectura del plano ----

export type LecturaParse = {
  entity_count: number;
  entities_by_type: Record<string, number>;
  from_block_count: number;
  derived_by_type: Record<string, number>;
  dropped_by_type: Record<string, number>;
  text_count: number;
  recovered: boolean;
  warning_count: number;
  insunits: number | null;
  layer_count: number;
  block_count: number;
  layouts?: LecturaLayout[];
  xrefs?: LecturaXref[];
};

export type LecturaViewport = {
  scale_factor: number;
  scale_label: string | null;
  model_bbox: [number, number, number, number];
};

export type LecturaLayout = {
  name: string;
  viewports: LecturaViewport[];
  texts: string[];
  attributes: Record<string, string>;
};

export type LecturaXref = {
  name: string;
  path: string;
  resolved_path: string | null;
  status: "embedded" | "missing" | "failed";
};

export type LecturaSheet = {
  name: string;
  sheet_number: string | null;
  discipline: string | null;
  file_type: string;
  conversion: { status: string; message: string; duration_seconds?: number } | null;
  parse: LecturaParse | null;
};

export type ElementSpec = {
  mark: string;
  family: string;
  section_cm: [number, number] | null;
  rebar: string | null;
  stirrups: string | null;
  source: "cuadro" | "detalle" | "nota";
  source_text: string;
  confidence: number;
};

export type LecturaSchedules = {
  by_mark: ElementSpec[];
  by_family: (ElementSpec & { family: string })[];
  tables_found: number;
  concrete_fc?: Record<string, number>;
  notes: string[];
};

export type InventoryBlock = {
  block_name: string;
  layer: string;
  count: number;
  by_view: Record<string, number>;
};
export type InventoryRun = {
  layer: string;
  length_m: number | null;
  length_du: number;
  segments: number;
  by_view: Record<string, number>;
};
export type InventoryTag = { tag: string; count: number; by_view: Record<string, number> };
export type InventoryArea = {
  layer: string;
  area_m2: number | null;
  area_du2: number;
  count: number;
  by_view: Record<string, number>;
};
export type SheetInventory = {
  sheet: string;
  label?: string;
  discipline: string | null;
  blocks: InventoryBlock[];
  runs: InventoryRun[];
  /** Repeated marks (V-1, P-3…): element types of cancelería, carpintería, plafones. */
  tags?: InventoryTag[];
  /** Closed shapes and hatches by layer: pisos, plafones, acabados (m²). */
  areas?: InventoryArea[];
  specs: string[];
  notes: string[];
};
export type Inventory = { sheets: SheetInventory[]; unit: string | null; notes: string[] };

/** A symbol or layer of the levantamiento mapped to a concept (workspace-wide). */
export type InventoryMapping = {
  id: number;
  kind: "block" | "layer" | "tag" | "area";
  pattern: string;
  concept_code: string;
  factor: number;
  created_at: string;
};

export const listInventoryMappings = () =>
  getJSON<{ mappings: InventoryMapping[] }>("/catalog/inventory-mappings").then((r) => r.mappings);

export const addInventoryMapping = (
  body: {
    kind: "block" | "layer" | "tag" | "area";
    pattern: string;
    concept_code: string;
    factor?: number;
  },
  actor?: string,
) =>
  postJSON<InventoryMapping>(
    "/catalog/inventory-mappings",
    body,
    actor ? { "X-Actor": actor } : undefined,
  );

export const deleteInventoryMapping = (id: number, actor?: string) =>
  deleteJSON<{ deleted: number }>(
    `/catalog/inventory-mappings/${id}`,
    actor ? { "X-Actor": actor } : undefined,
  );

export type Lectura = {
  project_id: string;
  project_name: string;
  /** Levantamiento por hoja: símbolos y trazos contados, sin precio. */
  inventory?: Inventory | null;
  schedules?: LecturaSchedules;
  sheets: LecturaSheet[];
  units: { unit: string; source: string; confidence: number; source_label: string } | null;
  layers: { layer: string; entity_count: number; entity_types: Record<string, number> }[];
  layer_total: number;
  blocks: { block_name: string; insert_count: number }[];
  warning_groups: { type: string; label: string; count: number; samples: string[] }[];
  detection_total: number;
  detections_by_family: Record<string, number>;
  entity_type_labels: Record<string, string>;
};

export const getLectura = (id: string) => getJSON<Lectura>(`/projects/${id}/lectura`);

// ---- Correction loop & verification ----

export type ReviewStatus = "confirmed" | "excluded";

export type ManualAdjustment = {
  adjustment_id: string;
  concept_code: string;
  quantity_delta: number;
  note: string;
  actor: string;
  created_at: string;
};

export type VerificationState = {
  units_confirmed_at: string | null;
  units_confirmed_by: string;
  units_override: string | null;
  detections_confirmed_at: string | null;
  detections_confirmed_by: string;
  assumptions_confirmed_at: string | null;
  assumptions_confirmed_by: string;
};

export type ProjectReviews = {
  detections: Record<
    string,
    { status: ReviewStatus; note: string; actor: string; updated_at: string }
  >;
  adjustments: ManualAdjustment[];
  verification: VerificationState;
  summary: { confirmed: number; excluded: number; adjustments: number };
};

function actorClientHeaders(actor?: string, clientId?: string | null) {
  return {
    ...(actor ? { "X-Actor": actor } : {}),
    ...(clientId ? { "X-Client-Id": clientId } : {}),
  };
}

export const getProjectReviews = (id: string) =>
  getJSON<ProjectReviews>(`/projects/${id}/reviews`);

export const setDetectionReview = (
  id: string,
  key: string,
  status: ReviewStatus | "none",
  note = "",
  actor?: string,
  clientId?: string | null,
) =>
  putJSON<ProjectReviews>(
    `/projects/${id}/reviews/detections/${encodeURIComponent(key)}`,
    { status, note },
    actorClientHeaders(actor, clientId),
  );

export const addAdjustment = (
  id: string,
  adjustment: { concept_code: string; quantity_delta: number; note: string },
  actor?: string,
  clientId?: string | null,
) =>
  postJSON<ProjectReviews>(
    `/projects/${id}/reviews/adjustments`,
    adjustment,
    actorClientHeaders(actor, clientId),
  );

export const removeAdjustment = (
  id: string,
  adjustmentId: string,
  actor?: string,
  clientId?: string | null,
) =>
  deleteJSON<ProjectReviews>(
    `/projects/${id}/reviews/adjustments/${encodeURIComponent(adjustmentId)}`,
    actorClientHeaders(actor, clientId),
  );

export const setVerification = (
  id: string,
  step: "units" | "detections" | "assumptions",
  confirmed: boolean,
  actor?: string,
  unit?: "m" | "cm" | "mm" | "ft" | "in",
) =>
  putJSON<ProjectReviews & { reprocessing?: boolean }>(
    `/projects/${id}/reviews/verification`,
    { step, confirmed, unit },
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Workspace catalog ----

export type CatalogInsumo = {
  code: string;
  description: string;
  unit: string;
  resource_type: string;
  unit_cost: number;
  is_labor_percentage: number;
  source: string;
  source_type: "referencia" | "cotizacion" | "publicacion" | "calculado";
  region: string;
  vigencia: string;
  updated_at: string;
};

export type CatalogConcept = {
  code: string;
  description: string;
  unit: string;
  phase: string;
  production_rate_per_day: number;
  detection_backed: boolean;
  /** P.U. adopted from a reference row (catálogo propio or publication); replaces the matrix. */
  price_override?: number | null;
  price_source?: string | null;
  price_clave?: string | null;
  price_vigencia?: string | null;
};

export type ApuComponent = { resource_code: string; quantity: number };

export type CatalogState = {
  insumos: CatalogInsumo[];
  concepts: CatalogConcept[];
  apus: Record<string, ApuComponent[]>;
  phase_order: string[];
};

export const getCatalog = () => getJSON<CatalogState>("/catalog");

export const updateInsumo = (
  code: string,
  patch: Partial<
    Pick<
      CatalogInsumo,
      "description" | "unit" | "unit_cost" | "source" | "source_type" | "vigencia" | "region"
    >
  >,
  actor?: string,
) =>
  putJSON<CatalogInsumo>(`/catalog/insumos/${encodeURIComponent(code)}`, patch, {
    ...(actor ? { "X-Actor": actor } : {}),
  });

export const createInsumo = (
  insumo: Pick<
    CatalogInsumo,
    "code" | "description" | "unit" | "resource_type" | "unit_cost" | "source"
  >,
  actor?: string,
) =>
  postJSON<CatalogInsumo>("/catalog/insumos", insumo, {
    ...(actor ? { "X-Actor": actor } : {}),
  });

export const createConcept = (
  concept: {
    code: string;
    description: string;
    unit: string;
    phase: string;
    production_rate_per_day: number;
    components: ApuComponent[];
  },
  actor?: string,
) =>
  postJSON<CatalogConcept>("/catalog/concepts", concept, {
    ...(actor ? { "X-Actor": actor } : {}),
  });

export const updateApu = (conceptCode: string, components: ApuComponent[], actor?: string) =>
  putJSON<{ concept_code: string }>(
    `/catalog/apus/${encodeURIComponent(conceptCode)}`,
    { components },
    { ...(actor ? { "X-Actor": actor } : {}) },
  );

export const updateRendimiento = (conceptCode: string, rate: number, actor?: string) =>
  putJSON<{ concept_code: string }>(
    `/catalog/rendimientos/${encodeURIComponent(conceptCode)}`,
    { production_rate_per_day: rate },
    { ...(actor ? { "X-Actor": actor } : {}) },
  );

export async function importCatalogPrices(
  file: File,
  source: string,
  actor?: string,
): Promise<{ updated: number; skipped: string[] }> {
  const form = new FormData();
  form.append("file", file);
  const url = new URL(`${API_BASE}/catalog/import-prices`);
  if (source) url.searchParams.set("source", source);
  const res = await fetch(url.toString(), {
    method: "POST",
    credentials: "include",
    headers: actor ? { "X-Actor": actor } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, "/catalog/import-prices", detail);
  }
  return res.json();
}

export const getViews = (id: string) =>
  getJSON<Views>(`/projects/${id}/views`).catch(() => null);
export const getDimensions = (id: string) =>
  getJSON<Dimensions>(`/projects/${id}/dimensions`).catch(() => null);

async function postFiles<T>(
  path: string,
  files: File[],
  actor?: string,
  fields?: Record<string, string | undefined>,
): Promise<T> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  for (const [key, value] of Object.entries(fields ?? {})) {
    if (value) form.append(key, value);
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: actor ? { "X-Actor": actor } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  return res.json() as Promise<T>;
}

export const uploadProject = (
  files: File[],
  actor?: string,
  meta?: { project_name?: string; client?: string },
) =>
  postFiles<{ project_id: string; warnings: string[] }>("/projects/upload", files, actor, {
    project_name: meta?.project_name,
    client: meta?.client,
  });

export const addProjectFiles = (id: string, files: File[], actor?: string) =>
  postFiles<{ project_id: string; sheet_count: number; warnings: string[] }>(
    `/projects/${id}/files`,
    files,
    actor,
  );

export const patchProject = (
  id: string,
  patch: { name?: string; client?: string; archived?: boolean },
  actor?: string,
) =>
  patchJSON<{ project_id: string; name: string; client: string | null; archived: boolean }>(
    `/projects/${id}`,
    patch,
    actor ? { "X-Actor": actor } : undefined,
  );

export const removeProject = (id: string, actor?: string) =>
  deleteJSON<{ project_id: string; removed: boolean }>(
    `/projects/${id}`,
    actor ? { "X-Actor": actor } : undefined,
  );

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

// ---- Workspace (home overview, taller defaults) ----

export type ProjectOverview = ProjectSummary & {
  verified: boolean;
  verification: { units: boolean; detections: boolean; assumptions: boolean };
  excluded_count: number;
  adjustment_count: number;
  grand_total: number | null;
  currency: string;
  last_activity: string | null;
  job_error: string | null;
  engine_stale: boolean;
};

export type WorkspaceOverview = {
  projects: ProjectOverview[];
  attention: {
    processing: number;
    failed: number;
    unverified: number;
    stale_runs: number;
    pending_users: number | null;
    stale_insumos: number;
    stale_threshold_months: number;
  };
  workspace: { slug: string; name: string };
  mode: "open" | "protected";
  is_admin: boolean;
};

export const getWorkspaceOverview = () => getJSON<WorkspaceOverview>("/workspace/overview");

export type WorkspaceDefaults = {
  config: CostingConfigFull;
  customized: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export const getWorkspaceDefaults = () => getJSON<WorkspaceDefaults>("/workspace/defaults");

export const saveWorkspaceDefaults = (config: CostingConfigFull, actor?: string) =>
  putJSON<WorkspaceDefaults>(
    "/workspace/defaults",
    { config },
    actor ? { "X-Actor": actor } : undefined,
  );

export const resetWorkspaceDefaults = (actor?: string) =>
  fetch(`${API_BASE}/workspace/defaults`, {
    method: "DELETE",
    credentials: "include",
    headers: actor ? { "X-Actor": actor } : undefined,
  }).then(async (res) => {
    if (!res.ok) throw new ApiError(res.status, "/workspace/defaults", undefined);
    return res.json() as Promise<WorkspaceDefaults>;
  });

export const renameWorkspace = (name: string) =>
  putJSON<{ slug: string; name: string }>("/workspace", { name });

// ---- Reference library, salario real, costo horario ----

export type ReferenceSource = {
  /** Uploaded by the taller (not a publication). */
  custom?: boolean;
  key: string;
  name: string;
  publisher: string;
  region: string;
  vigencia: string;
  kind: "precios_unitarios" | "costo_horario";
  filename: string;
  url: string;
  available: boolean;
  bytes: number | null;
  sha256: string | null;
  fetched_at: string | null;
  imported: { imported_at: string; row_count: number } | null;
};

export type ReferenceRow = {
  ref_id: number;
  source_key: string;
  clave: string;
  description: string;
  unit: string;
  price: number;
  group_clave: string;
  group_description: string;
  extra: Record<string, number> | null;
  page: number | null;
  source_name: string;
  source_vigencia: string;
  source_region: string;
};

export const listReferenceSources = () =>
  getJSON<{ sources: ReferenceSource[] }>("/catalog/sources").then((r) => r.sources);

export const importReferenceSource = (key: string, actor?: string) =>
  postJSON<{ source_key: string; rows: number }>(
    `/catalog/sources/${encodeURIComponent(key)}/import`,
    {},
    actor ? { "X-Actor": actor } : undefined,
  );

export async function importCustomSource(
  file: File,
  name: string,
  vigencia: string,
  actor?: string,
): Promise<{ source_key: string; rows: number; name: string }> {
  const form = new FormData();
  form.append("file", file);
  const url = new URL(`${API_BASE}/catalog/sources/custom`);
  if (name) url.searchParams.set("name", name);
  if (vigencia) url.searchParams.set("vigencia", vigencia);
  const res = await fetch(url.toString(), {
    method: "POST",
    credentials: "include",
    headers: actor ? { "X-Actor": actor } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, "/catalog/sources/custom", detail);
  }
  return res.json();
}

export const searchReference = (q: string, source?: string) =>
  getJSON<{ rows: ReferenceRow[] }>(
    `/catalog/reference?q=${encodeURIComponent(q)}${source ? `&source=${encodeURIComponent(source)}` : ""}`,
  ).then((r) => r.rows);

export const adoptConceptReference = (code: string, refId: number, actor?: string) =>
  postJSON<CatalogConcept>(
    `/catalog/concepts/${encodeURIComponent(code)}/adopt`,
    { ref_id: refId },
    actor ? { "X-Actor": actor } : undefined,
  );

export const clearConceptPrice = (code: string, actor?: string) =>
  deleteJSON<CatalogConcept>(
    `/catalog/concepts/${encodeURIComponent(code)}/price`,
    actor ? { "X-Actor": actor } : undefined,
  );

export const adoptReference = (code: string, refId: number, actor?: string) =>
  postJSON<CatalogInsumo>(
    `/catalog/insumos/${encodeURIComponent(code)}/adopt`,
    { ref_id: refId },
    actor ? { "X-Actor": actor } : undefined,
  );

export type FsrParameters = {
  year: number;
  uma: number;
  aguinaldo_days: number;
  vacation_days: number;
  prima_vacacional_pct: number;
  sundays: number;
  holidays: number;
  customary_days: number;
  riesgo_trabajo_pct: number;
  eym_cuota_fija_pct_uma: number;
  eym_excedente_pct: number;
  eym_prestaciones_dinero_pct: number;
  eym_gastos_medicos_pensionados_pct: number;
  invalidez_vida_pct: number;
  guarderias_pct: number;
  retiro_pct: number;
  infonavit_pct: number;
  ceyv_bands: [number, number][];
  isn_pct: number;
  isn_in_fsr: boolean;
};

export type FsrBreakdown = {
  salario_nominal: number;
  factor_integracion: number;
  salario_base_cotizacion: number;
  sbc_in_uma: number;
  employer_daily: Record<string, number>;
  employer_daily_total: number;
  ps: number;
  tp: number;
  tl: number;
  fsr: number;
  salario_real: number;
  notes: string[];
};

export type LaborCategory = { code: string; description: string; salario_nominal: number };

export type LaborState = {
  params: FsrParameters;
  categories: (LaborCategory & { breakdown: FsrBreakdown })[];
  applied_at: string | null;
};

export const getLabor = () => getJSON<LaborState>("/catalog/labor");

export const putLabor = (params: FsrParameters, categories: LaborCategory[], actor?: string) =>
  putJSON<LaborState & { applied: unknown[] }>(
    "/catalog/labor",
    { params, categories },
    actor ? { "X-Actor": actor } : undefined,
  );

export type EquipmentParameters = {
  vm: number; vr: number; ve: number; hea: number; i: number; s: number; ko: number;
  gh: number; pc: number; ah: number; ga: number; pa: number; pn: number; vn: number;
  pa_e: number; va: number; sr: number; ht: number; other_energy: number;
};

export type EquipmentBreakdown = {
  depreciacion: number; inversion: number; seguros: number; mantenimiento: number;
  cargos_fijos: number; combustible: number; otras_energias: number; lubricantes: number;
  llantas: number; piezas_especiales: number; consumos: number; operacion: number;
  costo_horario: number; notes: string[];
};

export const getEquipment = (code: string) =>
  getJSON<{ code: string; params: EquipmentParameters | null; breakdown: EquipmentBreakdown | null; saved: boolean }>(
    `/catalog/equipment/${encodeURIComponent(code)}`,
  );

export const putEquipment = (
  code: string,
  params: EquipmentParameters,
  description?: string,
  actor?: string,
) =>
  putJSON<CatalogInsumo & { breakdown: EquipmentBreakdown }>(
    `/catalog/equipment/${encodeURIComponent(code)}`,
    { params, description },
    actor ? { "X-Actor": actor } : undefined,
  );

/** Re-run the whole pipeline on the project's current files. */
export const processProject = (id: string) =>
  postJSON<{ project_id: string; job_id: string; state: string }>(`/projects/${id}/process`, {});
