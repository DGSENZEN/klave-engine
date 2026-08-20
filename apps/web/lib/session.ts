// Client helpers for the Google session endpoints.

export type AuthStatus = {
  enabled: boolean;
  user: { sub: string; name: string; email: string; picture: string | null } | null;
};

export async function fetchAuthStatus(): Promise<AuthStatus> {
  try {
    const response = await fetch("/api/auth/session", { cache: "no-store" });
    if (!response.ok) return { enabled: false, user: null };
    return (await response.json()) as AuthStatus;
  } catch {
    return { enabled: false, user: null };
  }
}

export async function logout(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {}
}
