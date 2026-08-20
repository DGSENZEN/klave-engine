// Server-side session for Google sign-in.
//
// The session is a compact HMAC-SHA256-signed payload in an HTTP-only cookie:
// no database tables, no third-party auth dependency. The Docker PostgreSQL
// belongs to the cost-data platform's schema; persisting accounts there is a
// deliberate later step once that branch lands.

import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "klave_session";
export const STATE_COOKIE = "klave_oauth_state";
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

export type SessionUser = {
  sub: string;
  name: string;
  email: string;
  picture: string | null;
};

type SessionPayload = SessionUser & { exp: number };

export function googleAuthConfigured(): boolean {
  return Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET);
}

function secret(): string {
  const value = process.env.AUTH_SECRET;
  if (value) return value;
  if (process.env.NODE_ENV === "production") {
    throw new Error("AUTH_SECRET must be set outside development.");
  }
  // Stable well-known development fallback; never valid in production.
  return "klave-dev-only-secret";
}

function b64url(data: Buffer | string): string {
  return Buffer.from(data).toString("base64url");
}

function sign(data: string): string {
  return createHmac("sha256", secret()).update(data).digest("base64url");
}

export function encodeSession(user: SessionUser): string {
  const payload: SessionPayload = {
    ...user,
    exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE_SECONDS,
  };
  const body = b64url(JSON.stringify(payload));
  return `${body}.${sign(body)}`;
}

export function decodeSession(token: string | undefined): SessionUser | null {
  if (!token) return null;
  const dot = token.lastIndexOf(".");
  if (dot <= 0) return null;
  const body = token.slice(0, dot);
  const signature = token.slice(dot + 1);
  const expected = sign(body);
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const payload = JSON.parse(Buffer.from(body, "base64url").toString()) as SessionPayload;
    if (typeof payload.exp !== "number" || payload.exp * 1000 < Date.now()) return null;
    if (typeof payload.sub !== "string" || typeof payload.name !== "string") return null;
    return {
      sub: payload.sub,
      name: payload.name,
      email: typeof payload.email === "string" ? payload.email : "",
      picture: typeof payload.picture === "string" ? payload.picture : null,
    };
  } catch {
    return null;
  }
}
