import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { googleAuthConfigured, STATE_COOKIE } from "@/lib/server/session";

const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

/** Starts the Google OAuth code flow. */
export function GET(request: NextRequest): NextResponse {
  if (!googleAuthConfigured()) {
    return NextResponse.json(
      { error: "google_auth_not_configured" },
      { status: 404 },
    );
  }
  const state = randomUUID();
  const redirectUri = new URL("/api/auth/google/callback", request.nextUrl.origin);
  const url = new URL(GOOGLE_AUTH_URL);
  url.searchParams.set("client_id", process.env.AUTH_GOOGLE_ID!);
  url.searchParams.set("redirect_uri", redirectUri.toString());
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("state", state);

  const response = NextResponse.redirect(url);
  response.cookies.set(STATE_COOKIE, state, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 600,
    path: "/api/auth",
  });
  return response;
}
