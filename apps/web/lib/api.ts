// Typed client for the Klave Engine FastAPI backend.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

/** True when a production build is talking to localhost: the deployment
 * forgot NEXT_PUBLIC_API_URL, and every page would otherwise blame the server. */
export const API_MISCONFIGURED =
  process.env.NODE_ENV === "production" && !process.env.NEXT_PUBLIC_API_URL;

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

/** Subida de archivo. Nunca fija Content-Type: el navegador tiene que poner
 *  el suyo con el boundary del multipart, y ponerlo a mano lo rompe. */
async function postForm<T>(
  path: string,
  body: FormData,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { ...headers },
    body,
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
  // Un DELETE bien hecho responde 204 sin cuerpo, y res.json() truena con eso.
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public path: string, public detail?: unknown) {
    super(`API ${status} on ${path}`);
  }
}

/**
 * The message the server wrote for people, or the fallback. Every error
 * the API raises on purpose carries `{error_type, message}`; a network
 * failure or a 500 carries nothing worth showing.
 */
export function apiMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

/**
 * Download a file the API builds on demand, with the session cookie and a
 * real error: a failed export used to replace the app with a JSON page.
 * The filename comes from Content-Disposition, else the fallback.
 */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "include", cache: "no-store" });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json())?.detail;
    } catch {}
    throw new ApiError(res.status, path, detail);
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
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
  /** "cuadro" when the tag is a row of a cuadro on the sheet, not an element. */
  role?: string;
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
  /** Medidas legibles del elemento (solo con unidad honesta). */
  medidas?: { label: string; value: string }[];
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
  /** Ids of the elements behind the quantity (capped at 200 by the engine). */
  source_detections?: string[];
  assumptions: string[];
  /** Quantity per planta on a segmented sheet (view title → quantity). */
  by_view?: Record<string, number>;
  /** What the engine read before any manual edit; null when untouched. */
  engine_quantity?: number | null;
  /** The taller's own clave when the concept has an alias. */
  taller_clave?: string;
  /** A parametric proposal from the taller's history, not a plan reading. */
  parametric?: boolean;
  /** No matrix nor adopted P.U.: the quantity is real, the amount is unknown (shown as sin precio, never $0). */
  unpriced?: boolean;
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

export type Indicator = {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  low: number | null;
  high: number | null;
  status: "ok" | "alto" | "bajo" | "sin_dato";
  detail: string;
};

export type PhaseShare = {
  phase: string;
  share_pct: number;
  typical_pct: number | null;
  status: "ok" | "alto" | "bajo" | "falta" | "sin_referencia";
};

export type Indicators = {
  indicators: Indicator[];
  phase_shares: PhaseShare[];
  missing_phases: string[];
  reference: string;
  notes: string[];
};

/**
 * Whether a total may be shown as money, resolved once on the server by
 * costing.presentation.resolve_money_state and shipped on every surface
 * that renders a total. Owned here (not in components/MoneyGate.tsx) so
 * that lib/ never has to import from components/ to use it.
 */
export type MoneyGateState = "ok" | "unverified" | "blocked";

/** What the engine read about the drawing's scale, frozen with the run. */
export type MoneyBasis = {
  units_reliable: boolean;
  unit: string;
  source: string;
  confidence: number;
  reasons: string[];
  /** Share of direct cost by confidence band, in percent. */
  confidence_bands: Record<string, number>;
};

export type CostReport = {
  project_id: string;
  currency: string;
  /** Resolved server-side; the client renders this, it does not derive it. */
  money_state?: MoneyGateState;
  money_basis?: MoneyBasis | null;
  /** Sanity ratios and partida shares (empty object on older runs). */
  indicators?: Partial<Indicators>;
  drawing_units: { unit: string; source: string; confidence: number; notes?: string[] };
  boq: {
    direct_cost_total: number;
    totals_by_phase: Record<string, number>;
    lines: BoqLine[];
    assumptions: string[];
    warnings: string[];
    /** False when the drawing unit is not reliable: quantities in drawing units, nothing priced. */
    units_reliable?: boolean;
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
  schedule: {
    total_duration_days: number;
    phases: string[];
    activities: ScheduleActivity[];
    start_date?: string | null;
    end_date?: string | null;
    /** Días naturales corridos — the unit the contract counts in. */
    calendar_days?: number;
    /** The crew assumption in words: frentes and cuadrillas per activity,
     * because nothing in the drawing can say what those should be. */
    assumptions: string[];
  };
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
  /** "matriz" when the rate came from the APU that priced the concept (so the
   * programa and the money cannot disagree), "catálogo" when it fell back. */
  rendimiento_source?: string;
  crews?: number;
  duration_days: number;
  start_day: number;
  end_day: number;
  /** The network, per RLOPSRM art. 224. */
  predecessors?: { predecessor: string; kind: "FS" | "SS"; lag_days: number }[];
  total_float_days?: number;
  free_float_days?: number;
  critical?: boolean;
  /** Calendar dates (ISO) when the obra has a start date; null otherwise. */
  start_date?: string | null;
  end_date?: string | null;
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

/** Create (or reopen) the synthetic sample obra and process it. */
export const createDemoProject = (actor?: string) =>
  postJSON<{ project_id: string; job_id: string; fresh: boolean }>(
    "/projects/demo",
    {},
    actor ? { "X-Actor": actor } : undefined,
  );

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

export type TableroFact = {
  label: string;
  /** El dato en sí («3 de 4», «$40,857.73 MXN»); null cuando la etiqueta basta. */
  value: string | null;
  tone: "ok" | "warn" | "bad" | "muted";
  /** Fragmento de ruta del proyecto (p.ej. «/lectura»); se antepone /proyecto/{id}. */
  href?: string;
};

export type TableroEstado = "ok" | "atencion" | "bloqueado" | "pendiente";

export type TableroNodeKey =
  | "planos"
  | "revision"
  | "catalogo"
  | "presupuesto"
  | "programa"
  | "contrato";

export type TableroNode = { estado: TableroEstado; facts: TableroFact[] };

export type TableroGate = { approved_at: string | null; approved_by: string };

export type Tablero = {
  project_id: string;
  /** null en modo abierto (sin cuentas): todos pueden abrir candados. */
  my_role: "owner" | "editor" | "viewer" | "admin" | null;
  gates: Partial<Record<TableroNodeKey, TableroGate>>;
  nodes: Record<TableroNodeKey, TableroNode>;
};

export const getTablero = (id: string) => getJSON<Tablero>(`/projects/${id}/tablero`);

export const putGate = (id: string, node: TableroNodeKey, approved: boolean, actor?: string) =>
  putJSON<{ gates: Partial<Record<TableroNodeKey, TableroGate>> }>(
    `/projects/${id}/gates/${node}`,
    { approved },
    actor ? { "X-Actor": actor } : undefined,
  );

export type DisciplinePreview = {
  filename: string;
  discipline: string;
  label: string;
  structural: boolean;
  /** Qué datos jala el motor de esta hoja, en frases honestas. */
  jala: string[];
};

export const previewDisciplinas = (filenames: string[]) =>
  postJSON<{ previews: DisciplinePreview[] }>("/disciplines/preview", { filenames }).then(
    (r) => r.previews,
  );

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

/** Un puesto de la plantilla de campo, con su participación en el calendario. */
export type CargoCampo = {
  puesto: string;
  tipo: "tecnico" | "administrativo" | "servicio";
  cantidad: number;
  /** Sueldo nominal mensual. 0 = no capturado: el renglón sale sin importe. */
  salario_mensual: number;
  fsr: number;
  desde_periodo: number;
  hasta_periodo: number | null;
  dedicacion_pct: number;
  razon: string;
};

/** Un renglón del desglose de indirectos de campo: gasto real, categoría
 * contable y si su importe es mensual o único. El personal técnico no vive
 * aquí — nace de la plantilla de campo y se agrega aparte. */
export type RubroIndirecto = {
  concepto: string;
  categoria: string;
  importe: number;
  base: "mensual" | "unico";
};

/** Un cargo adicional declarado (p. ej. impuestos locales), con su base legal. */
export type CargoAdicional = {
  concepto: string;
  base_legal: string;
  pct: number;
};

/** La tasa de financiamiento con su indicador, fuente y fecha — sin los cuatro
 * datos no es un análisis, es un invento (ver indirectos.py). */
export type AnalisisFinanciamiento = {
  tasa_anual: number;
  indicador: string;
  fuente: string;
  fecha_publicacion: string;
};

/** Un componente de la integración con la fuente que lo respalda: "analisis"
 * cuando un desglose/análisis capturado manda, "declarado" cuando es el
 * porcentaje a mano de `indirects`. */
export type ComponenteIntegracion = {
  code: string;
  pct: number | null;
  amount: number | null;
  fuente: "analisis" | "declarado";
  faltantes: string[];
};

export type CostingConfigFull = {
  currency: string;
  /** Nullable: a level the engineer has not set yet (platform_level_m). */
  assumptions: Record<string, number | null>;
  indirects: Record<string, number>;
  schedule: Record<string, number> & { start_date?: string | null };
  financial: Record<string, number>;
  plantilla_campo: CargoCampo[];
  /** null = sin desglose capturado: los indirectos de campo se quedan en el
   * porcentaje declarado. */
  desglose_campo?: { rubros: RubroIndirecto[] } | null;
  cargos_adicionales?: CargoAdicional[];
  /** null = sin análisis de financiamiento: el porcentaje declarado manda. */
  financiamiento?: AnalisisFinanciamiento | null;
  /** Share de oficina central fijado a mano; null = prorrateo derivado. Sólo
   * vale con `oficina_share_motivo` de al menos 15 caracteres. */
  oficina_share_pct?: number | null;
  oficina_share_motivo?: string;
};

export type RenglonPlantilla = {
  puesto: string;
  tipo: CargoCampo["tipo"];
  unidad: string;
  cantidad: number;
  importe: number;
  sin_sueldo: boolean;
  por_periodo: number[];
  importe_por_periodo: number[];
  razon: string;
};

export type PersonalTecnico = {
  programa: {
    renglones: RenglonPlantilla[];
    total: number;
    total_por_periodo: number[];
    cargos_sin_sueldo: number;
    notas: string[];
  };
  plantilla: CargoCampo[];
  sugerida: CargoCampo[];
  periodos: number;
  indirectos_campo: number;
  version: number;
};

export const getPersonalTecnico = (id: string) =>
  getJSON<PersonalTecnico>(`/projects/${id}/personal-tecnico`);

export type CostingConfigResponse = {
  config: CostingConfigFull;
  insumos: Insumo[];
  insumo_prices: Record<string, number>;
  has_overrides: boolean;
  version: number;
  updated_by: string | null;
  updated_at: string | null;
  /** Absent on old cached responses: treat as []. */
  integracion?: ComponenteIntegracion[];
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
  /** Sheet frames tiled in model space (total and plantas); 0 on frameless drawings. */
  frames?: { total: number; plan: number };
  project_id: string;
  project_name: string;
  /** Levantamiento por hoja: símbolos y trazos contados, sin precio. */
  inventory?: Inventory | null;
  /** Capas y bloques de instalaciones que la biblioteca reconoce. Propuestas:
   *  traen la cantidad que producirían y por qué, y nadie las aplica solo. */
  mapeos_sugeridos?: MapeoSugerido[];
  schedules?: LecturaSchedules;
  sheets: LecturaSheet[];
  units: { unit: string; source: string; confidence: number; source_label: string } | null;
  layers: { layer: string; entity_count: number; entity_types: Record<string, number> }[];
  layer_total: number;
  blocks: { block_name: string; insert_count: number }[];
  /** Índice de prefabricados: definiciones de bloque clasificadas una vez. */
  prefabs?: {
    name: string;
    familia: string | null;
    que_es: string | null;
    disciplina: string | null;
    clase: string | null;
    es_anotacion: boolean;
    attdefs: string[];
    instance_count: number;
  }[];
  warning_groups: { type: string; label: string; count: number; samples: string[] }[];
  detection_total: number;
  detections_by_family: Record<string, number>;
  entity_type_labels: Record<string, string>;
};

export type MapeoSugerido = {
  kind: "block" | "layer";
  /** El nombre exacto de la capa o del bloque, no un patrón. */
  pattern: string;
  concept_code: string;
  unit: string;
  quantity: number;
  reason: string;
  discipline: string;
  sheets: string[];
};

export const getLectura = (id: string) => getJSON<Lectura>(`/projects/${id}/lectura`);

/* ------------------------------------------------------------- contrato ---
 * El catálogo de la convocante y las estimaciones: lo que manda sobre qué se
 * cotiza, y lo que se cobra cada mes una vez que la obra arrancó.
 */

export type RenglonConvocante = {
  clave: string;
  description: string;
  unit: string;
  /** La cantidad que catalogó la convocante: es el contrato. */
  quantity: number;
  orden: number;
  group: string;
  concept_code: string;
  match_score: number;
  match_reasons: string[];
  /** La que sostiene el plano, cuando el motor sabe medir ese concepto. */
  quantity_engine: number | null;
  diferencia_pct: number | null;
  unit_price: number | null;
  amount: number | null;
};

export type CatalogoConvocante = {
  nombre: string;
  renglones: RenglonConvocante[];
  notas: string[];
  avisos: string[];
  total: number;
  sin_precio?: string[];
  sin_atar?: string[];
};

export const getCatalogoConvocante = (id: string) =>
  getJSON<CatalogoConvocante>(`/projects/${id}/catalogo-convocante`);

export async function subirCatalogoConvocante(
  id: string,
  file: File,
  nombre: string,
  actor?: string,
): Promise<CatalogoConvocante> {
  const form = new FormData();
  form.append("file", file);
  return postForm<CatalogoConvocante>(
    `/projects/${id}/catalogo-convocante?nombre=${encodeURIComponent(nombre)}`,
    form,
    actor ? { "X-Actor": actor } : {},
  );
}

export type RenglonEstimado = {
  clave: string;
  description: string;
  unit: string;
  unit_price: number;
  quantity_contract: number;
  quantity_period: number;
  quantity_previous: number;
  generador: LineaGenerador[];
};

/**
 * Una medición de campo. `medida_directa` es para lo que no se calcula
 * multiplicando —kilos de una lista de habilitado, piezas contadas—: si viene,
 * manda sobre las dimensiones.
 */
export type LineaGenerador = {
  ubicacion: string;
  veces: number;
  largo: number | null;
  ancho: number | null;
  alto: number | null;
  medida_directa: number | null;
  nota: string;
};

/**
 * Qué dimensiones multiplica cada unidad. Se pide a la API en vez de escribirse
 * aquí: tener la tabla dos veces es tenerla distinta el día que cambie. La
 * multiplicación puede vivir en cualquier lado; qué se multiplica, no.
 */
/** La estimación como se entrega: carátula, conceptos y generadores en un archivo. */
export const descargarEstimacion = (id: string, numero: number) =>
  downloadFile(
    `/projects/${id}/estimaciones/${numero}/export.xlsx`,
    `estimacion_${numero}.xlsx`,
  );

export const getUnidadesGenerador = () =>
  getJSON<{ unidades: Record<string, string[]> }>("/medidas/unidades-generador");

/** El resultado de una línea, o la razón por la que no se puede calcular. */
export type LineaCalculada = {
  medida: number | null;
  formula: string;
  falta: string[];
};

/**
 * Calcula una línea con la tabla que sirve la API.
 *
 * Lo que nunca hace es rellenar con 1.00 la dimensión que falta: un dato
 * faltante convertido en uno neutro da un número plausible y equivocado, y ése
 * es peor que un hueco — el hueco se ve, el número se cobra.
 */
export function calcularLinea(
  linea: LineaGenerador,
  unidad: string,
  unidades: Record<string, string[]>,
): LineaCalculada {
  const veces = Number.isFinite(linea.veces) ? linea.veces : 1;
  if (linea.medida_directa !== null && linea.medida_directa !== undefined) {
    return {
      medida: Math.round(linea.medida_directa * veces * 10000) / 10000,
      formula: veces !== 1 ? `${veces} × ${linea.medida_directa}` : `${linea.medida_directa}`,
      falta: [],
    };
  }
  const dims = unidades[unidad.trim().toLowerCase()];
  if (dims === undefined) return { medida: null, formula: "", falta: ["medida_directa"] };
  if (dims.length === 0) {
    return { medida: Math.round(veces * 10000) / 10000, formula: `${veces}`, falta: [] };
  }
  const falta = dims.filter(
    (d) => (linea as unknown as Record<string, number | null>)[d] == null,
  );
  if (falta.length > 0) return { medida: null, formula: "", falta };

  let producto = veces;
  const partes: string[] = [];
  for (const d of dims) {
    const v = Number((linea as unknown as Record<string, number>)[d]);
    producto *= v;
    partes.push(String(v));
  }
  if (veces !== 1) partes.unshift(String(veces));
  return {
    medida: Math.round(producto * 10000) / 10000,
    formula: partes.join(" × "),
    falta: [],
  };
}

/** Debajo de esto la diferencia es redondeo de cinta métrica, no un error. */
export const TOLERANCIA_GENERADOR = 0.005;

export const lineaGeneradorVacia = (): LineaGenerador => ({
  ubicacion: "",
  veces: 1,
  largo: null,
  ancho: null,
  alto: null,
  medida_directa: null,
  nota: "",
});

export type Deductiva = { concepto: string; importe: number; razon: string };

export type Estimacion = {
  numero: number;
  periodo_inicio: string;
  periodo_fin: string;
  renglones: RenglonEstimado[];
  deductivas: Deductiva[];
  anticipo_pct: number;
  retencion_pct: number;
  amortizado_previo: number;
  monto_contrato: number;
  notas: string[];
};

export type ResumenEstimacion = {
  numero: number;
  periodo: string;
  importe: number;
  amortizacion: number;
  retencion: number;
  deductivas: number;
  liquido: number;
  acumulado: number;
  avance_pct: number;
  avisos: string[];
};

export type EstimacionConResumen = {
  estimacion: Estimacion;
  resumen: ResumenEstimacion;
};

export const getEstimaciones = (id: string) =>
  getJSON<{ estimaciones: EstimacionConResumen[] }>(`/projects/${id}/estimaciones`);

export const guardarEstimacion = (
  id: string,
  numero: number,
  estimacion: Estimacion,
  actor?: string,
) =>
  putJSON<EstimacionConResumen>(
    `/projects/${id}/estimaciones/${numero}`,
    { estimacion },
    actor ? { "X-Actor": actor } : {},
  );

export const siguienteEstimacion = (id: string, inicio: string, fin: string) =>
  postJSON<EstimacionConResumen>(
    `/projects/${id}/estimaciones/siguiente?inicio=${inicio}&fin=${fin}`,
    {},
  );

/**
 * Convenios modificatorios y finiquito: el contrato cuando cambia y cuando
 * termina.
 *
 * El techo del art. 59 de la LOPSRM (25 % del monto o del plazo, en conjunto)
 * lo calcula la API, no la pantalla: es una regla legal, no una decoración.
 */
export type RenglonConvenio = {
  clave: string;
  description: string;
  unit: string;
  unit_price: number;
  quantity: number;
  /** Lo que decía el contrato antes; 0 si el concepto no existía. */
  quantity_anterior: number;
};

export type Convenio = {
  numero: number;
  fecha: string;
  tipo: "monto" | "plazo" | "ambos";
  motivo: string;
  renglones: RenglonConvenio[];
  dias_plazo: number;
};

export type EstadoContrato = {
  monto_original: number;
  monto_convenido: number;
  monto_vigente: number;
  monto_pct: number;
  plazo_original_dias: number;
  dias_convenidos: number;
  plazo_vigente_dias: number;
  plazo_pct: number;
  rebasa_techo: boolean;
  techo_pct: number;
  avisos: string[];
};

export const getConvenios = (id: string, plazoDias = 0) =>
  getJSON<{ convenios: Convenio[]; estado: EstadoContrato }>(
    `/projects/${id}/convenios?plazo_dias=${plazoDias}`,
  );

export const guardarConvenio = (
  id: string,
  numero: number,
  convenio: Convenio,
  actor?: string,
) =>
  putJSON<{ convenio: Convenio }>(
    `/projects/${id}/convenios/${numero}`,
    { convenio },
    actor ? { "X-Actor": actor } : {},
  );

export const borrarConvenio = (id: string, numero: number, actor?: string) =>
  deleteJSON<void>(
    `/projects/${id}/convenios/${numero}`,
    actor ? { "X-Actor": actor } : {},
  );

/** El borrador que resuelve lo que una estimación no pudo cobrar. No se guarda. */
export const borradorConvenio = (id: string, numero: number, fecha: string) =>
  postJSON<{ convenio: Convenio }>(
    `/projects/${id}/convenios/desde-estimacion/${numero}?fecha=${fecha}`,
    {},
  );

/**
 * Ajuste de costos (LOPSRM art. 57–58). Los índices no se precargan ni se
 * estiman: los trae quien consulta la publicación del INEGI. Sin los dos
 * valores el factor es null y la pantalla pide el dato en vez de aproximarlo.
 */
export type IndicePrecios = {
  nombre: string;
  fuente: string;
  publicacion: string;
  /** Periodo ISO ("2026-03") → valor publicado. */
  valores: Record<string, number>;
};

export type RenglonAjuste = {
  clave: string;
  description: string;
  unit: string;
  unit_price: number;
  quantity_contract: number;
  quantity_executed: number;
  quantity_programada: number | null;
};

export type SolicitudAjuste = {
  numero: number;
  /** Del acto de presentación y apertura de proposiciones, no de la firma. */
  periodo_base: string;
  periodo_ajuste: string;
  indice: IndicePrecios | null;
  renglones: RenglonAjuste[];
  atraso_imputable_al_contratista: boolean;
};

export type ResumenAjuste = {
  numero: number;
  periodo_base: string;
  periodo_ajuste: string;
  indice_base: number | null;
  indice_ajuste: number | null;
  factor: number | null;
  calculable: boolean;
  importe_pendiente: number;
  importe_ajustable: number;
  importe_ajuste: number;
  avisos: string[];
};

export type AjusteConResumen = { solicitud: SolicitudAjuste; resumen: ResumenAjuste };

export const getAjustes = (id: string) =>
  getJSON<{ ajustes: AjusteConResumen[] }>(`/projects/${id}/ajustes`);

export const prepararAjuste = (id: string, base = "", ajuste = "") =>
  postJSON<AjusteConResumen>(
    `/projects/${id}/ajustes/preparar?periodo_base=${base}&periodo_ajuste=${ajuste}`,
    {},
  );

export const guardarAjuste = (
  id: string,
  numero: number,
  solicitud: SolicitudAjuste,
  actor?: string,
) =>
  putJSON<AjusteConResumen>(
    `/projects/${id}/ajustes/${numero}`,
    { solicitud },
    actor ? { "X-Actor": actor } : {},
  );

export const borrarAjuste = (id: string, numero: number, actor?: string) =>
  deleteJSON<void>(
    `/projects/${id}/ajustes/${numero}`,
    actor ? { "X-Actor": actor } : {},
  );

/**
 * Bitácora de obra (RLOPSRM art. 123–125). No hay `editarNota` ni `borrarNota`
 * y no es un olvido: una bitácora que se puede corregir no prueba nada. Una
 * nota mal asentada se aclara con otra que la referencia, y las dos se quedan.
 */
export type NotaBitacora = {
  numero: number;
  fecha: string;
  tipo: "apertura" | "ordinaria" | "extraordinaria" | "cierre";
  parte: "contratante" | "contratista" | "supervision";
  autor: string;
  cargo: string;
  texto: string;
  /** La nota que ésta aclara. La aclarada se queda. */
  referencia: number | null;
  /** La pone el servidor al asentar, no el navegador. */
  asentada_en: string;
};

export type EstadoBitacora = {
  abierta: boolean;
  cerrada: boolean;
  siguiente_numero: number;
  por_parte: Record<string, number>;
  avisos: string[];
};

export const getBitacora = (id: string) =>
  getJSON<{ notas: NotaBitacora[]; estado: EstadoBitacora }>(
    `/projects/${id}/bitacora`,
  );

export const asentarNota = (id: string, nota: NotaBitacora, actor?: string) =>
  postJSON<{ nota: NotaBitacora }>(
    `/projects/${id}/bitacora`,
    { nota },
    actor ? { "X-Actor": actor } : undefined,
  );

export type SaldoFiniquito = {
  concepto: string;
  importe: number;
  razon: string;
  a_favor: string;
};

export type Finiquito = {
  fecha: string;
  monto_contrato: number;
  ejecutado: number;
  pagado: number;
  anticipo_otorgado: number;
  anticipo_amortizado: number;
  retenciones_aplicadas: number;
  retencion_sustituida_por_fianza: boolean;
  dias_atraso: number;
  pena_pct_diario: number;
  otros: SaldoFiniquito[];
};

export type ResumenFiniquito = {
  fecha: string;
  ejecutado: number;
  pagado: number;
  saldos: SaldoFiniquito[];
  saldo_final: number;
  /** "contratista" | "contratante" | "nadie" — lo decide la API, no la pantalla. */
  a_favor_de: string;
  avisos: string[];
};

export type FiniquitoConResumen = {
  finiquito: Finiquito;
  resumen: ResumenFiniquito;
  /** false = precargado de las estimaciones, todavía no lo guarda nadie. */
  guardado: boolean;
};

export const getFiniquito = (id: string) =>
  getJSON<FiniquitoConResumen>(`/projects/${id}/finiquito`);

export const guardarFiniquito = (id: string, finiquito: Finiquito, actor?: string) =>
  putJSON<FiniquitoConResumen>(
    `/projects/${id}/finiquito`,
    { finiquito },
    actor ? { "X-Actor": actor } : {},
  );

/** What a vision model read from one sheet image — a suggestion with provenance. */
export type AiElementRead = {
  mark: string;
  family: string;
  section_cm: string | null;
  rebar: string | null;
  stirrups: string | null;
  length_m: number | null;
  note: string | null;
  confidence: number;
};
export type AiSheetRead = {
  sheet_code: string | null;
  title: string | null;
  level: string | null;
  scale: string | null;
  concrete_fc: Record<string, number>;
  steel_fy: number | null;
  cover_cm: Record<string, number>;
  desplante_m: number | null;
  slab_system: string | null;
  elements: AiElementRead[];
  conteo?: { family: string; drawn_count: number; note?: string | null }[];
  notes: string[];
  uncertainties: string[];
};

/** One coverage-audit discrepancy: the model counts N, the engine detected M. */
export type CoverageFlag = {
  frame_code: string;
  family: string;
  ai_count: number;
  engine_count: number;
  kind: "faltante" | "sobrante";
};
export type AiSheetReading = {
  frame_code: string;
  frame_title: string;
  model: string;
  read: AiSheetRead;
  input_tokens: number;
  output_tokens: number;
};
export type AiReads = {
  status: "idle" | "running" | "done" | "cancelled" | "failed" | "unavailable";
  started_at: string | null;
  finished_at: string | null;
  run_id: string | null;
  /** Frames the job set out to read; `readings` grows one by one while it runs. */
  total_frames: number;
  readings: AiSheetReading[];
  input_tokens: number;
  output_tokens: number;
  error: string | null;
  notes: string[];
  available: boolean;
  running: boolean;
  model: string;
  cobertura: CoverageFlag[];
  /** Sheets whose reading failed: a retry asks only for these. */
  failed: string[];
};

export const getAiReads = (id: string) => getJSON<AiReads>(`/projects/${id}/ai-reads`);
/** Stop after the sheet being read; what was already read stays. */
export const cancelAiRead = (id: string) =>
  postJSON<{ project_id: string; status: string }>(`/projects/${id}/ai-read/cancel`, {});
/** `onlyFailed` resumes: sheets already read are kept, only failures re-asked. */
export const startAiRead = (id: string, actor?: string, onlyFailed = false) =>
  postJSON<{ project_id: string; status: string }>(
    `/projects/${id}/ai-read${onlyFailed ? "?only_failed=true" : ""}`,
    {},
    actor ? { "X-Actor": actor } : undefined,
  );
/** The crop of the sheet where a mark is written — what makes an AI reading
 * checkable against the drawing instead of merely plausible. */
export const aiEvidenceUrl = (id: string, code: string, mark: string) =>
  `${API_BASE}/projects/${id}/ai-reads/${encodeURIComponent(code)}/${encodeURIComponent(mark)}.png`;

export const frameRenderUrl = (id: string, code: string) =>
  `${API_BASE}/projects/${id}/renders/${encodeURIComponent(code)}.png`;

// ---- Bitácora del taller: gasto de IA y lo que se rompió ----

export type GastoIA = {
  llamadas: number;
  tokens_entrada: number;
  tokens_salida: number;
  /** Estimado con tarifas declaradas por el operador, nunca un cargo real. */
  costo_estimado_usd: number;
  tope_usd: number | null;
  porcentaje: number | null;
  excedido: boolean;
  /** Llamadas cuyo modelo no tiene tarifa declarada: cuestan «no sé», no cero. */
  sin_tarifar: number;
  por_proyecto: { project_id: string; llamadas: number; usd: number }[];
  por_tipo: Record<string, number>;
};

export type ErroresRecientes = {
  total: number;
  grupos: {
    ruta: string;
    tipo: string;
    veces: number;
    ultimo: string;
    mensaje: string;
    request_id: string;
  }[];
  donde: Record<string, string>;
};

export const getGastoIA = () => getJSON<GastoIA>(`/workspace/gasto-ia`);
export const getErrores = () => getJSON<ErroresRecientes>(`/workspace/errores`);

// ---- Copiloto: respuestas con fuente, o ninguna ----

export type CopilotCita = {
  titulo: string;
  fuente: string;
  url?: string;
  vigencia?: string;
  tipo?: string;
};

export type CopilotRespuesta = {
  texto: string;
  citas: CopilotCita[];
  /** False when the server could not back the answer with its own material. */
  fundamentada: boolean;
  aviso: string;
  con_contexto: boolean;
};

export type CopilotCambio = {
  concepto: string;
  de: string;
  a: string;
  monto_actual: number | null;
};

export type CopilotAccion = {
  tipo: string;
  titulo: string;
  descripcion: string;
  endpoint: string;
  vista_previa: CopilotCambio[];
  /** What is still missing before it can run (a price, a decision). */
  requiere: string;
  reversible: string;
  hallazgo_id: string;
  /** False when it needs something only the engineer can supply. */
  aplicable: boolean;
};

export const getAcciones = (projectId: string) =>
  getJSON<{ acciones: CopilotAccion[] }>(`/copilot/acciones/${projectId}`);

export const aplicarAccion = (
  projectId: string,
  tipo: string,
  hallazgoId: string,
  actor?: string,
) =>
  postJSON<{
    aplicadas: string[];
    total_antes: number | null;
    // Null when the verdict withholds money (copilot.py resolves it before
    // answering). Typed as a bare number, `money(null)` rendered "$0" — an
    // invented zero, in the one place the gate had already done its job.
    total_despues: number | null;
    accion: string;
  }>(
    `/copilot/aplicar`,
    { project_id: projectId, tipo, hallazgo_id: hallazgoId },
    actor ? { "X-Actor": actor } : undefined,
  );

export const copilotStatus = () =>
  getJSON<{ available: boolean; model: string }>(`/copilot/status`);

export const askCopilot = (pregunta: string, projectId?: string) =>
  postJSON<CopilotRespuesta>(`/copilot/ask`, {
    pregunta,
    project_id: projectId ?? null,
  });

// ---- Diagnóstico: hallazgos ranked by consequence ----

/** Three actionable tiers. A deliberate engine choice is not an alarm at
 * all — it lives in `criterios`, the assumptions register. */
export type Severity = "bloqueante" | "dinero" | "revisar";

export type Hallazgo = {
  id: string;
  severity: Severity;
  title: string;
  detail: string;
  action: string;
  /** Route to act on it: bare = project subroute, "/x" = workspace, "" = resumen. */
  target: string | null;
  /** Pesos already counted that depend on this finding. */
  monto_afectado: number | null;
  /** How to confirm the finding against the drawing itself. */
  verificar: string;
  /** The last responsible moment: after this, fixing it costs money. */
  momento: "entregar" | "cotizar" | "contratar" | "sin_urgencia";
  /** What is at stake when the money is honestly unknowable ("23.00 PZA"). */
  exposicion: string | null;
  concept_code: string | null;
};

/** Findings that differ only in which concept they name, collapsed to one
 * card with a count — nineteen repeats of the same four lines is not
 * nineteen warnings, it is one warning and eighteen distractions. */
export type HallazgoGrupo = {
  rule_id: string;
  titulo: string;
  severity: Severity;
  momento: Hallazgo["momento"];
  count: number;
  miembros: Hallazgo[];
  monto_afectado: number | null;
  /** What is at stake across the group when pesos are honestly unknowable. */
  exposicion_total: string;
};

export type Diagnostico = {
  hallazgos: Hallazgo[];
  /** Findings collapsed by rule; the renderer walks these, not `hallazgos` —
   * two code paths reading the same findings is how they drift apart. */
  grupos: HallazgoGrupo[];
  /** Deliberate engine choices — recorded, not alarmed. */
  criterios: string[];
  by_severity: Partial<Record<Severity, number>>;
  monto_en_duda: number;
  conceptos_sin_precio: number;
  entregable: boolean;
  resumen: string;
};

export const getDiagnostico = (id: string) =>
  getJSON<Diagnostico>(`/projects/${id}/diagnostico`);

// ---- Correction loop & verification ----

export type ReviewStatus = "confirmed" | "excluded";

export type ManualAdjustment = {
  adjustment_id: string;
  concept_code: string;
  quantity_delta: number;
  /** An in-place edit: the quantity replaces the engine's figure. */
  quantity_set?: number | null;
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

export type OmittedElement = {
  element_id: string;
  family: string;
  mark: string;
  count: number;
  length_m?: number | null;
  area_m2?: number | null;
  section_cm: string;
  sheet: string;
  note: string;
  actor: string;
  created_at: string;
};

export type ProjectReviews = {
  detections: Record<
    string,
    { status: ReviewStatus; note: string; actor: string; updated_at: string }
  >;
  adjustments: ManualAdjustment[];
  omitted: OmittedElement[];
  verification: VerificationState;
  summary: { confirmed: number; excluded: number; adjustments: number; omitted: number };
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
  adjustment: {
    concept_code: string;
    quantity_delta?: number;
    quantity_set?: number;
    note: string;
  },
  actor?: string,
  clientId?: string | null,
) =>
  postJSON<ProjectReviews>(
    `/projects/${id}/reviews/adjustments`,
    adjustment,
    actorClientHeaders(actor, clientId),
  );

export const addOmittedElement = (
  id: string,
  element: {
    family: string;
    mark?: string;
    count?: number;
    length_m?: number;
    area_m2?: number;
    section_cm?: string;
    sheet?: string;
    note?: string;
  },
  actor?: string,
  clientId?: string | null,
) =>
  postJSON<ProjectReviews>(
    `/projects/${id}/reviews/omitted`,
    element,
    actorClientHeaders(actor, clientId),
  );

export const removeOmittedElement = (
  id: string,
  elementId: string,
  actor?: string,
  clientId?: string | null,
) =>
  deleteJSON<ProjectReviews>(
    `/projects/${id}/reviews/omitted/${encodeURIComponent(elementId)}`,
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

// ---- Review at scale ----

export type RevisionRow = {
  key: string;
  detection_id: string;
  label: string;
  mark: string;
  family: string;
  family_label: string;
  concept_code: string;
  concept_unit: string;
  view_id: string | null;
  view_title: string;
  sheet: string;
  measure: string;
  confidence: number;
  status: "confirmed" | "excluded" | "";
  note: string;
  actor: string;
  doubts: string[];
  bbox: [number, number, number, number];
};

export type RevisionTable = {
  rows: RevisionRow[];
  concepts: { code: string; description: string; unit: string; count: number }[];
  views: { view_id: string; title: string; count: number }[];
  total: number;
  with_doubts: number;
  confirmed: number;
  excluded: number;
};

export const getRevisionTable = (id: string) =>
  getJSON<RevisionTable>(`/projects/${id}/revision`);

export const setDetectionReviews = (
  id: string,
  keys: string[],
  status: ReviewStatus | "none",
  note = "",
  actor?: string,
  clientId?: string | null,
  recompute = true,
) =>
  putJSON<ProjectReviews>(
    `/projects/${id}/reviews/detections`,
    { keys, status, note, recompute },
    actorClientHeaders(actor, clientId),
  );

// ---- Conteos: lo que una persona contó sobre el plano ----
//
// El motor se compara contra sí mismo en cada otra prueba; esto es lo único
// que compara contra el plano. No recomputa nada (ver put_conteos en
// reviews.py) — es evidencia sobre el motor, no un insumo para el costeo.

export type ConteoHoja = {
  hoja: string;
  familia: string;
  dibujados: number;
  detectados: number;
  nota: string;
};

export type ConteosDeProyecto = {
  contado_por: string;
  contado_en: string;
  hojas: ConteoHoja[];
};

export const getConteos = (id: string) =>
  getJSON<ConteosDeProyecto>(`/projects/${id}/conteos`);

export const putConteos = (id: string, body: ConteosDeProyecto, actor?: string) =>
  putJSON<ConteosDeProyecto>(
    `/projects/${id}/conteos`,
    body,
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Croquis for the generadores ----

export type CroquisItem = { view_id: string; title: string; count: number; url: string };

export const getCroquis = (id: string, conceptCode: string) =>
  getJSON<{ concept_code: string; croquis: CroquisItem[] }>(
    `/projects/${id}/croquis/${encodeURIComponent(conceptCode)}`,
  );

export const croquisUrl = (item: CroquisItem) => `${API_BASE}${item.url}`;

// ---- Vigencia de precios, cotización e índices ----

export type PriceAge = {
  code: string;
  description: string;
  unit: string;
  unit_cost: number;
  source: string;
  source_type: string;
  vigencia: string;
  months: number | null;
  status: "vigente" | "revisar" | "vencido";
};

export const getVigencia = () =>
  getJSON<{
    insumos: PriceAge[];
    counts: Record<"vigente" | "revisar" | "vencido", number>;
    fresh_months: number;
    stale_months: number;
  }>("/catalog/vigencia");

export const cotizacionPath = (status: "vencido" | "revisar" | "all" = "vencido") =>
  `/catalog/cotizacion.xlsx?status=${status}`;

export type PriceIndices = { source: string; values: Record<string, number> };

export const getIndices = () => getJSON<PriceIndices>("/catalog/indices");

export const putIndices = (body: PriceIndices, actor?: string) =>
  putJSON<PriceIndices>("/catalog/indices", body, actor ? { "X-Actor": actor } : undefined);

export type RollForwardResult = {
  updated: {
    code: string;
    description: string;
    from: number;
    to: number;
    factor: number;
    vigencia_from: string;
  }[];
  skipped: string[];
  to_month: string;
  dry_run: boolean;
};

/** With `dry_run` nothing is written: the result is the preview of what the same call would change. */
export const rollForwardPrices = (
  body: {
    status?: "vencido" | "revisar" | "all";
    codes?: string[];
    to_month?: string;
    dry_run?: boolean;
  },
  actor?: string,
) =>
  postJSON<RollForwardResult>(
    "/catalog/indices/roll-forward",
    body,
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Integración del precio (oficina central y financiamiento del taller) ----

/** Los dos análisis a nivel taller que alimentan la integración de cada
 * obra: los rubros de oficina central (con su volumen anual para el
 * prorrateo) y la tasa de financiamiento con su indicador, fuente y fecha.
 * Ver packages/klave_engine/costing/indirectos.py. */
export type IntegracionTaller = {
  oficina: { rubros: RubroIndirecto[]; volumen_anual_contratado: number };
  financiamiento: AnalisisFinanciamiento;
};

const OFICINA_VACIA: IntegracionTaller["oficina"] = { rubros: [], volumen_anual_contratado: 0 };
const FINANCIAMIENTO_VACIO: AnalisisFinanciamiento = {
  tasa_anual: 0,
  indicador: "",
  fuente: "",
  fecha_publicacion: "",
};

/** El GET manda `{}` en la mitad que nunca se ha guardado; se normaliza aquí
 * para que el resto del código no repita el fallback. */
export const getIntegracionTaller = () =>
  getJSON<{
    oficina: Partial<IntegracionTaller["oficina"]>;
    financiamiento: Partial<AnalisisFinanciamiento>;
  }>("/catalog/integracion").then((r) => ({
    oficina: { ...OFICINA_VACIA, ...r.oficina },
    financiamiento: { ...FINANCIAMIENTO_VACIO, ...r.financiamiento },
  }));

/** El PUT siempre manda las dos mitades juntas — el endpoint las guarda como un solo objeto. */
export const putIntegracionTaller = (body: IntegracionTaller, actor?: string) =>
  putJSON<IntegracionTaller>(
    "/catalog/integracion",
    body,
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Plantillas & paramétricos (the taller's history) ----

export type Plantilla = {
  key: string;
  name: string;
  tipologia: string;
  area_m2: number;
  source_key: string;
  rows: number;
  actor: string;
  created_at: string;
};

export type ParametricRule = {
  id: number;
  concept_code: string;
  basis: string;
  factor: number;
  source: string;
  plantilla_key: string;
  note: string;
  engine_read: number;
  active: number;
  created_at: string;
};

export type PlantillaImportResult = {
  plantilla_key: string;
  rows: number;
  priced_rows: number;
  rules: number;
  comparison_rules: number;
  concepts_created: number;
  problems: string[];
};

export const getPlantillas = () =>
  getJSON<{ plantillas: Plantilla[]; rules: ParametricRule[] }>("/catalog/plantillas");

export async function importPlantilla(
  file: File,
  meta: { name: string; tipologia: string; area_m2: number },
  actor?: string,
) {
  const body = new FormData();
  body.append("file", file);
  const params = new URLSearchParams({
    name: meta.name,
    tipologia: meta.tipologia,
    area_m2: String(meta.area_m2),
  });
  const res = await fetch(`${API_BASE}/catalog/plantillas?${params.toString()}`, {
    method: "POST",
    body,
    credentials: "include",
    headers: actor ? { "X-Actor": actor } : {},
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = null;
    }
    throw new ApiError(res.status, "/catalog/plantillas", detail);
  }
  return (await res.json()) as PlantillaImportResult;
}

export const deletePlantilla = (key: string, actor?: string) =>
  deleteJSON<{ deleted: string }>(
    `/catalog/plantillas/${encodeURIComponent(key)}`,
    actor ? { "X-Actor": actor } : undefined,
  );

export const addParametricRule = (
  body: { concept_code: string; basis: string; factor: number; source?: string; note?: string },
  actor?: string,
) => postJSON<ParametricRule>("/catalog/parametrics", body, actor ? { "X-Actor": actor } : undefined);

export const updateParametricRule = (
  id: number,
  body: { factor?: number; active?: boolean; note?: string },
  actor?: string,
) =>
  putJSON<ParametricRule>(
    `/catalog/parametrics/${id}`,
    body,
    actor ? { "X-Actor": actor } : undefined,
  );

export const deleteParametricRule = (id: number, actor?: string) =>
  deleteJSON<{ deleted: number }>(
    `/catalog/parametrics/${id}`,
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Concept aliases & matching (the taller's own vocabulary) ----

export type ConceptMatch = {
  kind: "reference" | "concept";
  key: string;
  ref_id: number | null;
  target_code: string | null;
  clave: string;
  description: string;
  unit: string;
  price: number | null;
  source: string;
  vigencia: string;
  score: number;
  reasons: string[];
};

export type ConceptAlias = {
  concept_code: string;
  kind: "reference" | "concept";
  ref_id: number | null;
  target_code: string | null;
  clave: string;
  description: string;
  unit: string;
  price: number | null;
  source: string;
  vigencia: string;
  actor: string;
  note: string;
  project_id: string;
  created_at: string;
};

export const getConceptMatches = (code: string, sourceKey?: string) =>
  getJSON<{ concept_code: string; matches: ConceptMatch[] }>(
    `/catalog/concepts/${encodeURIComponent(code)}/matches${sourceKey ? `?source_key=${encodeURIComponent(sourceKey)}` : ""}`,
  );

export const getAllMatches = (minScore = 0.8) =>
  getJSON<{
    matches: { concept_code: string; description: string; unit: string; match: ConceptMatch }[];
    aliases: number;
    candidates: number;
  }>(`/catalog/matches?min_score=${minScore}`);

export const getAliases = () =>
  getJSON<{ aliases: Record<string, ConceptAlias> }>("/catalog/aliases");

export type AliasInput = {
  concept_code: string;
  kind: "reference" | "concept";
  ref_id?: number | null;
  target_code?: string | null;
  note?: string;
  project_id?: string;
  /** Adopt across units on purpose; the server demands a note saying why. */
  force?: boolean;
};

/** The 422 the API raises when a price's unit is not the concept's. */
export type UnitMismatchDetail = {
  error_type: "unit_mismatch";
  message: string;
  code: string;
  unit: string;
  reference_unit: string;
};

export function unitMismatch(error: unknown): UnitMismatchDetail | null {
  if (error instanceof ApiError && error.status === 422 && error.detail && typeof error.detail === "object") {
    const detail = error.detail as { error_type?: string };
    if (detail.error_type === "unit_mismatch") return error.detail as UnitMismatchDetail;
  }
  return null;
}

export const setAlias = (body: AliasInput, actor?: string) =>
  postJSON<ConceptAlias>("/catalog/aliases", body, actor ? { "X-Actor": actor } : undefined);

export const setAliasesBulk = (items: AliasInput[], projectId: string, actor?: string) =>
  postJSON<{ aliases: ConceptAlias[] }>(
    "/catalog/aliases/bulk",
    { items, project_id: projectId },
    actor ? { "X-Actor": actor } : undefined,
  );

export const clearAlias = (code: string, projectId: string, actor?: string) =>
  deleteJSON<{ cleared: string }>(
    `/catalog/aliases/${encodeURIComponent(code)}?project_id=${encodeURIComponent(projectId)}`,
    actor ? { "X-Actor": actor } : undefined,
  );

// ---- Presupuesto versions ----

export type VersionSummary = {
  version_id: string;
  number: number;
  label: string;
  note: string;
  actor: string;
  created_at: string;
  run_id: string | null;
  overrides_version: number;
  direct_cost: number;
  grand_total: number;
  line_count: number;
  adjustments: number;
  excluded: number;
};

export type LineChange = {
  concept_code: string;
  description: string;
  unit: string;
  status: "added" | "removed" | "changed" | "same";
  quantity_before: number | null;
  quantity_after: number | null;
  unit_price_before: number | null;
  unit_price_after: number | null;
  amount_before: number;
  amount_after: number;
};

export type VersionDiff = {
  before_label: string;
  after_label: string;
  lines: LineChange[];
  direct_cost_before: number;
  direct_cost_after: number;
  grand_total_before: number;
  grand_total_after: number;
  changed: number;
  added: number;
  removed: number;
  notes: string[];
};

export const getVersions = (id: string) =>
  getJSON<{ versions: VersionSummary[]; active_run_id: string | null }>(
    `/projects/${id}/versions`,
  );

export const saveVersion = (
  id: string,
  body: { label: string; note: string },
  actor?: string,
  clientId?: string | null,
) =>
  postJSON<VersionSummary>(
    `/projects/${id}/versions`,
    body,
    actorClientHeaders(actor, clientId),
  );

export const getVersionDiff = (id: string, versionId: string, against = "current") =>
  getJSON<VersionDiff>(
    `/projects/${id}/versions/${encodeURIComponent(versionId)}/diff?against=${encodeURIComponent(against)}`,
  );

export const restoreVersion = (
  id: string,
  versionId: string,
  actor?: string,
  clientId?: string | null,
) =>
  postJSON<{ restored: VersionSummary; grand_total: number; same_run: boolean }>(
    `/projects/${id}/versions/${encodeURIComponent(versionId)}/restore`,
    {},
    actorClientHeaders(actor, clientId),
  );

export const deleteVersion = (id: string, versionId: string, actor?: string) =>
  deleteJSON<{ deleted: string }>(
    `/projects/${id}/versions/${encodeURIComponent(versionId)}`,
    actorClientHeaders(actor),
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
  /** Características extraídas del texto (f'c, t.m.a., acabado, elemento…). */
  ficha?: { campo: string; valor: string }[];
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

/** With `purge`, the drawings, runs, reviews and versions on disk go too. */
export const removeProject = (id: string, actor?: string, purge = false) =>
  deleteJSON<{ project_id: string; removed: boolean; purged: boolean }>(
    `/projects/${id}${purge ? "?purge=true" : ""}`,
    actor ? { "X-Actor": actor } : undefined,
  );

// Formatting lives in lib/format.ts; re-exported so existing imports keep working.
export { money, money2, num } from "./format";

// ---- Workspace (home overview, taller defaults) ----

export type ProjectOverview = ProjectSummary & {
  verified: boolean;
  verification: { units: boolean; detections: boolean; assumptions: boolean };
  excluded_count: number;
  adjustment_count: number;
  grand_total: number | null;
  money_state?: MoneyGateState;
  currency: string;
  last_activity: string | null;
  job_error: string | null;
  engine_stale: boolean;
  exported: boolean;
};

export type OnboardingState = {
  sample_explored: boolean;
  first_project: boolean;
  any_verified: boolean;
  aliases: number;
  any_exported: boolean;
};

export type WorkspaceOverview = {
  projects: ProjectOverview[];
  onboarding?: OnboardingState;
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

export const adoptConceptReference = (
  code: string,
  refId: number,
  actor?: string,
  options?: { force?: boolean; note?: string },
) =>
  postJSON<CatalogConcept>(
    `/catalog/concepts/${encodeURIComponent(code)}/adopt`,
    { ref_id: refId, ...options },
    actor ? { "X-Actor": actor } : undefined,
  );

export const clearConceptPrice = (code: string, actor?: string) =>
  deleteJSON<CatalogConcept>(
    `/catalog/concepts/${encodeURIComponent(code)}/price`,
    actor ? { "X-Actor": actor } : undefined,
  );

export const adoptReference = (
  code: string,
  refId: number,
  actor?: string,
  options?: { force?: boolean; note?: string },
) =>
  postJSON<CatalogInsumo>(
    `/catalog/insumos/${encodeURIComponent(code)}/adopt`,
    { ref_id: refId, ...options },
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

export type RegionPreset = {
  key: string;
  label: string;
  salario_minimo: number;
  isn_pct: number;
  zone: "general" | "frontera";
  source: string;
};

export const getLaborPresets = () =>
  getJSON<{ presets: RegionPreset[] }>("/catalog/labor/presets");

export const applyLaborPreset = (key: string, actor?: string) =>
  postJSON<LaborState & { preset: RegionPreset }>(
    `/catalog/labor/presets/${encodeURIComponent(key)}`,
    {},
    actor ? { "X-Actor": actor } : {},
  );

export type MatricesImportResult = {
  concepts_created: number;
  concepts_updated: number;
  insumos_upserted: number;
  problems: string[];
  source: string;
};

export async function importMatrices(file: File, source: string, actor?: string) {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(
    `${API_BASE}/catalog/import-matrices?source=${encodeURIComponent(source)}`,
    {
      method: "POST",
      body,
      credentials: "include",
      headers: actor ? { "X-Actor": actor } : {},
    },
  );
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = null;
    }
    throw new ApiError(res.status, "/catalog/import-matrices", detail);
  }
  return (await res.json()) as MatricesImportResult;
}

/** Un catálogo de destajos por bloques: sus matrices y sus cuadrillas. Es la
 *  forma en que se escribe un catálogo mexicano de destajo, y trae lo que
 *  ninguna publicación oficial da suelto: el costo real de cada cuadrilla. */
export const importDestajos = (file: File, source: string, actor?: string) => {
  const body = new FormData();
  body.append("file", file);
  return postForm<MatricesImportResult>(
    `/catalog/import-destajos?source=${encodeURIComponent(source)}`,
    body,
    actor ? { "X-Actor": actor } : {},
  );
};

export type CatalogImport = { source: string; concepts: number; with_price: number };

/** Qué importaciones de matrices se pueden deshacer. */
export const listImports = () =>
  getJSON<{ imports: CatalogImport[] }>("/catalog/imports");

/** Deshacer una importación de matrices: quita los conceptos que creó y deja
 *  los del motor, los escritos a mano y los que ya tengan precio adoptado. */
export const undoImport = (source: string, actor?: string) =>
  deleteJSON<{ source: string; removed: number; kept_with_price: string[] }>(
    `/catalog/imports/${encodeURIComponent(source)}`,
    actor ? { "X-Actor": actor } : undefined,
  );

/** Quitar una fuente de referencia y sus renglones. Se niega mientras algún
 *  concepto tenga precio adoptado de ella. */
export const deleteSource = (sourceKey: string, actor?: string) =>
  deleteJSON<{ source_key: string; name: string; rows: number }>(
    `/catalog/sources/${encodeURIComponent(sourceKey)}`,
    actor ? { "X-Actor": actor } : undefined,
  );

export type LaborPreviewRow = {
  code: string;
  description: string;
  salario_nominal: number;
  fsr: number;
  from: number | null;
  to: number;
};

/** What "Aplicar salario real" would write, next to today's catalog price. Nothing is saved. */
export const previewLabor = (params: FsrParameters, categories: LaborCategory[]) =>
  postJSON<{ rows: LaborPreviewRow[]; vigencia: string }>("/catalog/labor/preview", {
    params,
    categories,
  });

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
