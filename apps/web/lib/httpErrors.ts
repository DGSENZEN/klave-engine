export class ApiError extends Error {
  constructor(
    public status: number,
    public path: string,
    public detail?: unknown,
    public requestId?: string,
  ) {
    super("API " + status + " on " + path.replace(/(\/by-token\/)[^/]+/g, "$1[redacted]"));
  }
}

export async function errorFromResponse(
  response: Response,
  path: string,
  notifySession = true,
  parsedDetail?: unknown,
): Promise<ApiError> {
  let detail = parsedDetail;
  if (!response.bodyUsed) {
    try { detail = (await response.json())?.detail; } catch {}
  }
  const reference = response.headers.get("X-Request-Id") ?? "";
  const requestId = /^[A-Za-z0-9._-]{4,64}$/.test(reference) ? reference : undefined;
  if (response.status === 401 && notifySession && typeof window !== "undefined") {
    window.dispatchEvent(new Event("klave:session-expired"));
  }
  return new ApiError(response.status, path, detail, requestId);
}
