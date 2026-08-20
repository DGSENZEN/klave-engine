import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/server/session";

export function POST(): NextResponse {
  const response = NextResponse.json({ ok: true });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
