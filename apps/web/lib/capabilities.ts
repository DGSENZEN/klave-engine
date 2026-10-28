/**
 * What the person in front of the screen may do, from their taller role and
 * their role on the project. One rule for every screen: a control the role
 * can't use is hidden, never offered and then refused. The server stays the
 * authority (docs/superpowers/specs/2026-10-23-role-enforcement-design.md).
 */

export type ProjectRole = "admin" | "owner" | "editor" | "viewer" | null;

/**
 * The project payload came from an API older than role enforcement (no
 * `my_role` field): screens behave as they did before it and the server,
 * which still enforces project roles, decides. Lets the frontend ship
 * before the API is released.
 */
export type LegacyRole = "legacy";

export type Capabilities = {
  /** Change the taller catálogo (prices, matrices, imports, mappings already decided). */
  editCatalog: boolean;
  /** Review, quantify and edit this project's own data. */
  editProject: boolean;
  /** Rename, delete, files and sharing of this project. */
  manageProject: boolean;
  /** Open a node's lock on the tablero. */
  approveGate: boolean;
};

const ALL: Capabilities = { editCatalog: true, editProject: true, manageProject: true, approveGate: true };
const NONE: Capabilities = { editCatalog: false, editProject: false, manageProject: false, approveGate: false };

export function capabilities(input: {
  mode: "open" | "protected" | "unavailable";
  tallerRole: "admin" | "member" | null;
  projectRole?: ProjectRole | LegacyRole;
}): Capabilities {
  if (input.mode === "open") return ALL;
  if (input.mode === "unavailable") return NONE;
  if (input.tallerRole === "admin") return ALL;
  if (input.projectRole === "legacy") return { ...ALL, editCatalog: false };
  const role = input.projectRole ?? null;
  const manage = role === "owner" || role === "admin";
  return {
    editCatalog: false,
    editProject: manage || role === "editor",
    manageProject: manage,
    approveGate: manage,
  };
}

/**
 * A variant mapping a person decided — the server's rule
 * (``auth.shared_mappings.is_human_decision``). Engine proposals stay open to
 * editors; changing a person's decision in the taller catálogo is the admin's.
 */
export function isHumanDecision(row: { status: string; actor?: string | null } | null | undefined): boolean {
  if (!row) return false;
  if (row.status === "confirmada") return true;
  return row.status === "sin_equivalente" && Boolean(row.actor) && row.actor !== "motor";
}

/** The example obra keeps its own sandbox catálogo (server: es_obra_de_ejemplo). */
export function isSampleProject(projectId: string): boolean {
  return projectId.startsWith("obra_de_ejemplo");
}

/**
 * Change or remove an alias / variant mapping the taller already has: the
 * administrator's, except in the example obra where its owner decides.
 * Adding a new one only needs `editProject`.
 */
export function mayChangeSharedMapping(caps: Capabilities, projectId: string): boolean {
  return caps.editCatalog || (isSampleProject(projectId) && caps.editProject);
}

/**
 * The server refused because of the caller's role (it changed mid-session,
 * or a screen offered too much). Screens use it to refresh what they offer.
 */
export function isRoleRefusal(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const { status, detail } = error as { status?: number; detail?: { error_type?: string } };
  return (
    status === 403 &&
    (detail?.error_type === "admin_required" || detail?.error_type === "forbidden_project")
  );
}

/** A session status worth keeping for the page's life: never a momentary outage. */
export function keepStatus(status: { mode: string }): boolean {
  return status.mode !== "unavailable";
}
