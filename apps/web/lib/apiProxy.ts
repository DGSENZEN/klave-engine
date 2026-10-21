// Server-only consumer: app/api/[[...path]]/route.ts. Never import this from
// a client component or next.config: service bindings exist at runtime only.
const HOP_HEADERS = [
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailer", "transfer-encoding", "upgrade",
];

function transportHeaders(source: Headers): Headers {
  const headers = new Headers(source);
  // Connection may nominate additional headers that are local to one hop.
  for (const name of (headers.get("connection") ?? "").split(",")) {
    if (name.trim()) headers.delete(name.trim());
  }
  for (const name of HOP_HEADERS) headers.delete(name);
  headers.delete("content-length");
  return headers;
}

function unavailable(status: number): Response {
  return Response.json({ detail: {
    error_type: "api_unavailable",
    message: "El servidor no está disponible. Inténtalo de nuevo.",
  } }, { status, headers: { "cache-control": "private, no-store" } });
}

/** Forward public /api requests to the private FastAPI service. Preserve
 * bodies as streams: multipart uploads, SSE and binary exports use this too. */
export async function proxyAPI(request: Request): Promise<Response> {
  const binding = process.env.KLAVE_APP_URL;
  if (!binding) return unavailable(503);

  const incoming = new URL(request.url);
  if (incoming.pathname !== "/api" && !incoming.pathname.startsWith("/api/")) {
    return new Response(null, { status: 404 });
  }
  const path = incoming.pathname.slice(4).replace(/^\//, "");
  try {
    // Do not let encoded separators or dot segments escape a binding's base
    // path. Query parameters are forwarded separately and remain untouched.
    for (const part of path.split("/")) {
      const decoded = decodeURIComponent(part);
      if (decoded === "." || decoded === ".." || /[\\/\x00-\x1f]/.test(decoded)) {
        return new Response(null, { status: 400 });
      }
    }
  } catch {
    return new Response(null, { status: 400 });
  }

  let base: URL;
  try {
    base = new URL(binding);
    if (base.protocol !== "https:" && base.protocol !== "http:") return unavailable(503);
    if (!base.pathname.endsWith("/")) base.pathname += "/";
  } catch {
    return unavailable(503);
  }
  // A path like "http:example.com" is a URL to new URL(path, base), not a
  // relative path. Assign pathname so user input can never change the origin.
  const target = new URL(base);
  target.pathname = base.pathname + path;
  target.search = incoming.search;

  const headers = transportHeaders(request.headers);
  headers.delete("host");
  headers.delete("forwarded");
  for (const name of [...headers.keys()]) {
    if (name.startsWith("x-forwarded-")) headers.delete(name);
  }
  // Node fetch decodes compressed responses. Request identity and also remove
  // encoding/length on the way back if the upstream chose compression anyway.
  headers.set("accept-encoding", "identity");
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method, headers, cache: "no-store", redirect: "manual",
    signal: request.signal,
  };
  if (request.method !== "GET" && request.method !== "HEAD" && request.body) {
    init.body = request.body;
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    // Never expose a binding URL, invitation token or transport exception.
    return unavailable(502);
  }
  const responseHeaders = transportHeaders(upstream.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.set("cache-control", "private, no-store");
  responseHeaders.delete("set-cookie");
  for (const cookie of upstream.headers.getSetCookie()) {
    responseHeaders.append("set-cookie", cookie);
  }

  const location = responseHeaders.get("location");
  if (location) {
    const redirect = new URL(location, target);
    if (redirect.origin === base.origin && redirect.pathname.startsWith(base.pathname)) {
      responseHeaders.set("location", "/api/" + redirect.pathname.slice(base.pathname.length)
        + redirect.search + redirect.hash);
    }
  }
  return new Response(upstream.body, {
    status: upstream.status, statusText: upstream.statusText, headers: responseHeaders,
  });
}
