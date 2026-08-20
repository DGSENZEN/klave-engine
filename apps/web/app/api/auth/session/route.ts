import { NextRequest, NextResponse } from "next/server";
import {
  decodeSession,
  googleAuthConfigured,
  SESSION_COOKIE,
} from "@/lib/server/session";

/** Reports whether Google sign-in is configured and who is signed in. */
export function GET(request: NextRequest): NextResponse {
  const user = decodeSession(request.cookies.get(SESSION_COOKIE)?.value);
  return NextResponse.json({ enabled: googleAuthConfigured(), user });
}
