// Client for the workspace accounts API (FastAPI, dedicated users database).
// Sessions ride an HttpOnly cookie on the API origin, so every call sends
// credentials. The workspace has three modes: "open" (no accounts yet),
// "protected" (accounts + roles enforced), "unavailable" (users DB down).

import { API_BASE, ApiError } from "@/lib/api";

export type AuthUser = {
  user_id: string;
  email: string;
  name: string;
  picture: string | null;
  role: "admin" | "member";
  status: "pending" | "active" | "disabled";
};

export type AuthStatus = {
  mode: "open" | "protected" | "unavailable";
  user: AuthUser | null;
  google_enabled: boolean;
};

export type WorkspaceUser = AuthUser & { created_at: string };

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

export async function fetchAuthStatus(): Promise<AuthStatus> {
  try {
    return await authFetch<AuthStatus>("/auth/session", { cache: "no-store" });
  } catch {
    return { mode: "unavailable", user: null, google_enabled: false };
  }
}

export const googleLoginUrl = () => `${API_BASE}/auth/google`;

export const register = (email: string, name: string, password: string) =>
  authFetch<AuthUser>("/auth/register", { json: { email, name, password } });

export const login = (email: string, password: string) =>
  authFetch<AuthUser>("/auth/login", { json: { email, password } });

export async function logout(): Promise<void> {
  try {
    await authFetch("/auth/logout", { method: "POST" });
  } catch {}
}

export async function logoutAll(): Promise<void> {
  try {
    await authFetch("/auth/logout-all", { method: "POST" });
  } catch {}
}

export const changePassword = (currentPassword: string, newPassword: string) =>
  authFetch("/auth/password", {
    json: { current_password: currentPassword, new_password: newPassword },
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
