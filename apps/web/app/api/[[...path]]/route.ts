import { proxyAPI } from "@/lib/apiProxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = proxyAPI;
export const HEAD = proxyAPI;
export const POST = proxyAPI;
export const PUT = proxyAPI;
export const PATCH = proxyAPI;
export const DELETE = proxyAPI;
export const OPTIONS = proxyAPI;
