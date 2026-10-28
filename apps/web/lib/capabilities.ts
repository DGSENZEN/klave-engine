/**
 * What the person in front of the screen may do, from their taller role and
 * their role on the project. One rule for every screen: a control the role
 * can't use is hidden, never offered and then refused. The server stays the
 * authority (docs/superpowers/specs/2026-10-23-role-enforcement-design.md).
 */

export type ProjectRole = "admin" | "owner" | "editor" | "viewer" | null;

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
  projectRole?: ProjectRole;
}): Capabilities {
  if (input.mode === "open") return ALL;
  if (input.mode === "unavailable") return NONE;
  if (input.tallerRole === "admin") return ALL;
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
