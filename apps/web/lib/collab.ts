import { API_BASE, type PresenceViewer, type ProjectEvent } from "@/lib/api";

const ACTOR_KEY = "klave.displayName";
const CLIENT_KEY = "klave.clientId";
const ACTOR_MAX_CHARS = 40;
const DEFAULT_NAMES = ["María", "Diego", "Ana", "Beto", "Carla", "Luis", "Sofía", "Jorge"];

function cleanActor(value: string): string {
  return value.replace(/\s+/g, " ").trim().slice(0, ACTOR_MAX_CHARS);
}

function defaultActor(): string {
  const seed =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : String(Date.now());
  let total = 0;
  for (const char of seed) total += char.charCodeAt(0);
  return DEFAULT_NAMES[total % DEFAULT_NAMES.length];
}

/** Stored display name without creating a default (for onboarding prefill). */
export function peekBrowserActor(): string {
  if (typeof window === "undefined") return "";
  return cleanActor(window.localStorage.getItem(ACTOR_KEY) ?? "");
}

export function getBrowserActor(): string {
  if (typeof window === "undefined") return "Colaborador";
  const existing = cleanActor(window.localStorage.getItem(ACTOR_KEY) ?? "");
  if (existing) return existing;
  const actor = defaultActor();
  window.localStorage.setItem(ACTOR_KEY, actor);
  return actor;
}

export function setBrowserActor(value: string): string {
  const actor = cleanActor(value) || getBrowserActor();
  if (typeof window !== "undefined") window.localStorage.setItem(ACTOR_KEY, actor);
  return actor;
}

export function getBrowserClientId(): string {
  if (typeof window === "undefined") return "server";
  const existing = window.localStorage.getItem(CLIENT_KEY);
  if (existing) return existing;
  const id =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `client-${Date.now().toString(36)}`;
  window.localStorage.setItem(CLIENT_KEY, id);
  return id;
}


export function eventsUrl(): string {
  return `${API_BASE}/events`;
}

export function projectEventsUrl(
  projectId: string,
  actor?: string,
  clientId?: string,
  locationPath?: string,
  locationLabel?: string,
): string {
  const url = new URL(`${API_BASE}/projects/${encodeURIComponent(projectId)}/events`);
  if (actor) url.searchParams.set("actor", actor);
  if (clientId) url.searchParams.set("client_id", clientId);
  if (locationPath) url.searchParams.set("location_path", locationPath);
  if (locationLabel) url.searchParams.set("location_label", locationLabel);
  return url.toString();
}

export function parseProjectEvent(message: MessageEvent): ProjectEvent | null {
  try {
    const value = JSON.parse(String(message.data)) as Partial<ProjectEvent>;
    if (typeof value.seq !== "number" || typeof value.type !== "string") return null;
    return value as ProjectEvent;
  } catch {
    return null;
  }
}

export function parsePresence(value: unknown): PresenceViewer[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is PresenceViewer =>
      item != null &&
      typeof item === "object" &&
      typeof (item as PresenceViewer).client_id === "string" &&
      typeof (item as PresenceViewer).actor === "string" &&
      typeof (item as PresenceViewer).location_path === "string" &&
      typeof (item as PresenceViewer).location_label === "string" &&
      typeof (item as PresenceViewer).joined_at === "string" &&
      typeof (item as PresenceViewer).updated_at === "string",
  );
}

export function parseHelloPresence(message: MessageEvent): PresenceViewer[] {
  try {
    const value = JSON.parse(String(message.data)) as { presence?: unknown };
    return parsePresence(value.presence);
  } catch {
    return [];
  }
}

export function actorLabel(actor: string | null | undefined): string {
  return cleanActor(actor ?? "") || "Alguien";
}
