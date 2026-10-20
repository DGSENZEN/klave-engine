import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { errorFromResponse, ApiError } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "httpErrors.js"),
);
test("service error retains safe reference and server message", async () => {
  const error = await errorFromResponse(Response.json(
    { detail: { message: "Inténtalo de nuevo." } },
    { status: 503, headers: { "X-Request-Id": "safe-id-123" } },
  ), "/projects/p");
  assert.ok(error instanceof ApiError);
  assert.equal(error.requestId, "safe-id-123");
  assert.equal(error.detail.message, "Inténtalo de nuevo.");
});
test("non-JSON response still yields a typed service error", async () => {
  const error = await errorFromResponse(new Response("Unavailable", { status: 503 }), "/projects");
  assert.equal(error.status, 503);
  assert.equal(error.detail, undefined);
});
test("an invalid reference is discarded", async () => {
  const error = await errorFromResponse(new Response("", {
    status: 500, headers: { "X-Request-Id": "not a safe identifier" },
  }), "/projects");
  assert.equal(error.requestId, undefined);
});
test("public auth rejection does not signal session expiry", async (t) => {
  const target = new EventTarget();
  const previous = globalThis.window;
  globalThis.window = target;
  t.after(() => {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  });
  let events = 0;
  target.addEventListener("klave:session-expired", () => events++);
  await errorFromResponse(new Response("", { status: 401 }), "/auth/login", false);
  assert.equal(events, 0);
  await errorFromResponse(new Response("", { status: 401 }), "/projects", true);
  assert.equal(events, 1);
});
test("invitation token is absent from error text", async () => {
  const error = await errorFromResponse(new Response("", { status: 503 }),
    "/auth/invitations/by-token/private-token/accept", false);
  assert.ok(!error.message.includes("private-token"));
});
