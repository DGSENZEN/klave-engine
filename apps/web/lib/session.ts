// Client for the workspace accounts API (FastAPI, dedicated users database).
// Sessions ride an HttpOnly cookie on the API origin, so every call sends
// credentials. The deployment has three modes: "open" (no accounts yet),
// "protected" (accounts + roles enforced), "unavailable" (users DB down).

import { API_BASE, ApiError } from "@/lib/api";

export type AuthUser = {
  user_id: string;
  email: string;
  name: string;
  picture: string | null;
  role: "admin" | "member";
  status: "pending" | "active" | "disabled";
  email_verified: boolean;
  pending_email: string | null;
  has_password: boolean;
  has_google: boolean;
};

export type Workspace = { slug: string; name: string };

export type AuthStatus = {
  mode: "open" | "protected" | "unavailable";
  user: AuthUser | null;
  workspace: Workspace | null;
  google_enabled: boolean;
  /** Whether a mail provider is configured; otherwise links are handed over by admins. */
  mail_enabled: boolean;
};

export type WorkspaceUser = AuthUser & { created_at: string; approved_at: string | null };

async function authFetch<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...(json !== undefined
      ? {
          method: rest.method ?? "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(json),
        }
      : {}),
    ...rest,
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

/** Server-provided Spanish message from an ApiError, else the fallback. */
export function apiMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.detail && typeof error.detail === "object") {
    const message = (error.detail as { message?: string }).message;
    if (message) return message;
  }
  return fallback;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  try {
    return await authFetch<AuthStatus>("/auth/session", { cache: "no-store" });
  } catch {
    return {
      mode: "unavailable",
      user: null,
      workspace: null,
      google_enabled: false,
      mail_enabled: false,
    };
  }
}

export const googleLoginUrl = (invite?: string) =>
  `${API_BASE}/auth/google${invite ? `?invite=${encodeURIComponent(invite)}` : ""}`;

/** With `workspaceName`, the account founds that taller and is its admin at once. */
export const register = (email: string, name: string, password: string, workspaceName?: string) =>
  authFetch<AuthUser>("/auth/register", {
    json: { email, name, password, workspace_name: workspaceName || undefined },
  });

export const login = (email: string, password: string, remember = false) =>
  authFetch<AuthUser>("/auth/login", { json: { email, password, remember } });

export async function logout(): Promise<void> {
  try {
    await authFetch("/auth/logout", { method: "POST" });
  } catch {}
}

// ---- Own account ----

export type SessionInfo = {
  session_id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  ip: string | null;
  remember: boolean;
  current: boolean;
};

export const getMe = () =>
  authFetch<AuthUser & { workspace: Workspace | null; created_at: string }>("/auth/me", {
    cache: "no-store",
  });

export const updateMe = (name: string) =>
  authFetch<AuthUser>("/auth/me", { method: "PUT", json: { name } });

export const changePassword = (currentPassword: string, newPassword: string) =>
  authFetch<{ ok: true; sessions_revoked: number }>("/auth/password", {
    json: { current_password: currentPassword, new_password: newPassword },
  });

export const listSessions = () =>
  authFetch<{ sessions: SessionInfo[] }>("/auth/sessions", { cache: "no-store" }).then(
    (r) => r.sessions,
  );

export const revokeSession = (sessionId: string) =>
  authFetch(`/auth/sessions/${sessionId}`, { method: "DELETE" });

export const logoutOthers = () =>
  authFetch<{ ok: true; sessions_revoked: number }>("/auth/logout-all", { method: "POST" });

export const unlinkGoogle = () => authFetch("/auth/google/unlink", { method: "POST" });

export const sendVerification = () =>
  authFetch<{ delivered: boolean; mail_enabled: boolean; already_verified?: boolean }>(
    "/auth/verify/send",
    { method: "POST" },
  );

export const confirmVerification = (token: string) =>
  authFetch<{ ok: true; email: string; changed: boolean }>(
    `/auth/verify/${encodeURIComponent(token)}`,
    { method: "POST" },
  );

export const changeEmail = (newEmail: string, currentPassword: string) =>
  authFetch<{ ok: true; delivered: boolean; pending_email: string }>("/auth/email", {
    json: { new_email: newEmail, current_password: currentPassword },
  });

// ---- Recovery ----

export const requestRecovery = (email: string) =>
  authFetch<{ ok: true; mail_enabled: boolean }>("/auth/recover", { json: { email } });

export const resetInfo = (token: string) =>
  authFetch<{ valid: boolean; email?: string; name?: string }>(
    `/auth/reset/${encodeURIComponent(token)}`,
    { cache: "no-store" },
  );

export const resetPassword = (token: string, password: string) =>
  authFetch<{ ok: true; status: string }>(`/auth/reset/${encodeURIComponent(token)}`, {
    json: { password },
  });

// ---- Invitations ----

export type ProjectGrant = { project_id: string; role: "viewer" | "editor" | "owner" };

export type Invitation = {
  invite_id: string;
  email: string;
  role: "admin" | "member";
  project_grants: ProjectGrant[];
  state: "open" | "accepted" | "revoked" | "expired";
  inviter_name: string | null;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
};

export type InvitationResult = Invitation & {
  link: string;
  delivered: boolean;
  mail_enabled: boolean;
};

export const createInvitation = (
  email: string,
  role: "admin" | "member",
  projectGrants: ProjectGrant[],
) =>
  authFetch<InvitationResult>("/auth/invitations", {
    json: { email, role, project_grants: projectGrants },
  });

export const listInvitations = () =>
  authFetch<{ invitations: Invitation[] }>("/auth/invitations", { cache: "no-store" }).then(
    (r) => r.invitations,
  );

export const revokeInvitation = (inviteId: string) =>
  authFetch(`/auth/invitations/${inviteId}`, { method: "DELETE" });

export const resendInvitation = (inviteId: string) =>
  authFetch<{ link: string; delivered: boolean; mail_enabled: boolean }>(
    `/auth/invitations/${inviteId}/resend`,
    { method: "POST" },
  );

export type InvitationInfo = {
  state: Invitation["state"];
  email: string;
  role: "admin" | "member";
  workspace_name: string;
  inviter_name: string | null;
  project_count: number;
  expires_at: string;
  google_enabled: boolean;
};

export const invitationInfo = (token: string) =>
  authFetch<InvitationInfo>(`/auth/invitations/by-token/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });

export const acceptInvitation = (token: string, name: string, password: string) =>
  authFetch<AuthUser>(`/auth/invitations/by-token/${encodeURIComponent(token)}/accept`, {
    json: { name, password },
  });

// ---- Admin confirmation loop ----

export const listWorkspaceUsers = () =>
  authFetch<{ users: WorkspaceUser[] }>("/auth/users", { cache: "no-store" }).then(
    (r) => r.users,
  );

export const setUserStatus = (userId: string, status: "active" | "disabled") =>
  authFetch(`/auth/users/${userId}/status`, { method: "PUT", json: { status } });

export const setUserRole = (userId: string, role: "admin" | "member") =>
  authFetch(`/auth/users/${userId}/role`, { method: "PUT", json: { role } });

export const issueRecoveryLink = (userId: string) =>
  authFetch<{ link: string; expires_in_hours: number; email: string }>(
    `/auth/users/${userId}/recovery-link`,
    { method: "POST" },
  );

export type AuditEntry = {
  audit_id: number;
  actor_id: string | null;
  actor_name: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown>;
  created_at: string;
};

export const listAudit = (limit = 100) =>
  authFetch<{ entries: AuditEntry[] }>(`/auth/audit?limit=${limit}`, { cache: "no-store" }).then(
    (r) => r.entries,
  );

// ---- Project sharing ----

export type ProjectMember = {
  user_id: string;
  email: string;
  name: string;
  picture: string | null;
  status: string;
  project_role: "viewer" | "editor" | "owner";
};

export type ProjectAccess = {
  members: ProjectMember[];
  invitable: AuthUser[];
};

export const getProjectAccess = (projectId: string) =>
  authFetch<ProjectAccess>(`/projects/${projectId}/access`, { cache: "no-store" });

export const grantProjectAccess = (
  projectId: string,
  email: string,
  role: "viewer" | "editor" | "owner",
) => authFetch(`/projects/${projectId}/access`, { json: { email, role } });

export const revokeProjectAccess = (projectId: string, userId: string) =>
  authFetch(`/projects/${projectId}/access/${userId}`, { method: "DELETE" });
