const AUTH_PAGES = new Set([
  "/bienvenida", "/invitacion", "/recuperar", "/restablecer", "/verificar",
]);
export const SESSION_RETURN_KEY = "klave.session.return";

export function safeReturnPath(candidate: string | null, origin: string): string {
  if (!candidate || candidate.startsWith("//") || candidate.includes("\\")) return "/";
  try {
    const url = new URL(candidate, origin);
    if (url.origin !== origin || AUTH_PAGES.has(url.pathname.replace(/\/$/, ""))) return "/";
    return url.pathname + url.search + url.hash;
  } catch {
    return "/";
  }
}

export function consumeSessionReturn(): string {
  try {
    const path = sessionStorage.getItem(SESSION_RETURN_KEY);
    sessionStorage.removeItem(SESSION_RETURN_KEY);
    return safeReturnPath(path, window.location.origin);
  } catch {
    return "/";
  }
}
