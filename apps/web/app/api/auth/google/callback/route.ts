import { NextRequest, NextResponse } from "next/server";
import {
  encodeSession,
  googleAuthConfigured,
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  STATE_COOKIE,
  type SessionUser,
} from "@/lib/server/session";

const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";

function failure(request: NextRequest): NextResponse {
  return NextResponse.redirect(new URL("/bienvenida?error=google", request.nextUrl.origin));
}

/**
 * Completes the code flow. The id_token payload is trusted without local
 * signature verification because it is received directly from Google's token
 * endpoint over TLS in the same request (per Google's OpenID guidance).
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!googleAuthConfigured()) return failure(request);

  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get(STATE_COOKIE)?.value;
  if (!code || !state || !expectedState || state !== expectedState) {
    return failure(request);
  }

  const redirectUri = new URL("/api/auth/google/callback", request.nextUrl.origin);
  let tokenBody: { id_token?: string };
  try {
    const tokenResponse = await fetch(GOOGLE_TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: process.env.AUTH_GOOGLE_ID!,
        client_secret: process.env.AUTH_GOOGLE_SECRET!,
        redirect_uri: redirectUri.toString(),
        grant_type: "authorization_code",
      }),
    });
    if (!tokenResponse.ok) return failure(request);
    tokenBody = (await tokenResponse.json()) as { id_token?: string };
  } catch {
    return failure(request);
  }

  const idToken = tokenBody.id_token;
  if (!idToken) return failure(request);
  let user: SessionUser;
  try {
    const claims = JSON.parse(
      Buffer.from(idToken.split(".")[1], "base64url").toString(),
    ) as Record<string, unknown>;
    if (typeof claims.sub !== "string") return failure(request);
    user = {
      sub: claims.sub,
      name: typeof claims.name === "string" ? claims.name : "",
      email: typeof claims.email === "string" ? claims.email : "",
      picture: typeof claims.picture === "string" ? claims.picture : null,
    };
    if (!user.name) user.name = user.email.split("@")[0] || "Colaborador";
  } catch {
    return failure(request);
  }

  const response = NextResponse.redirect(new URL("/bienvenida", request.nextUrl.origin));
  response.cookies.set(SESSION_COOKIE, encodeSession(user), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
  });
  response.cookies.delete(STATE_COOKIE);
  return response;
}
