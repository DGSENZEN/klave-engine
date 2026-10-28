import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { proxyAPI } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "apiProxy.js"),
);

function binding(t, value = "https://app.internal/bound/") {
  const previous = process.env.KLAVE_APP_URL;
  if (value === null) delete process.env.KLAVE_APP_URL;
  else process.env.KLAVE_APP_URL = value;
  t.after(() => {
    if (previous === undefined) delete process.env.KLAVE_APP_URL;
    else process.env.KLAVE_APP_URL = previous;
  });
}

test("the runtime binding receives the stripped path, query, session and origin", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const headers = new Headers(init.headers);
    return Response.json({ url: String(url), cookie: headers.get("cookie"),
      origin: headers.get("origin"), host: headers.get("host"),
      spoofed: headers.get("x-forwarded-host"), cache: init.cache });
  });
  const res = await proxyAPI(new Request("https://pilot.example/api/projects?q=one%20two", {
    headers: { cookie: "klave_session=synthetic", origin: "https://pilot.example",
      host: "pilot.example", "x-forwarded-host": "attacker.example" },
  }));
  assert.deepEqual(await res.json(), { url: "https://app.internal/bound/projects?q=one%20two",
    cookie: "klave_session=synthetic", origin: "https://pilot.example", host: null,
    spoofed: null, cache: "no-store" });
});

test("a binding is read at request time, without a build-time upstream", async (t) => {
  binding(t, null);
  assert.equal((await proxyAPI(new Request("https://pilot.example/api/health"))).status, 503);
  process.env.KLAVE_APP_URL = "https://second.internal/";
  t.mock.method(globalThis, "fetch", async (url) => Response.json({ target: String(url) }));
  const res = await proxyAPI(new Request("https://pilot.example/api/health"));
  assert.deepEqual(await res.json(), { target: "https://second.internal/health" });
});

test("multipart upload bytes reach the backend without JSON conversion", async (t) => {
  binding(t);
  const form = new FormData();
  form.append("files", new File(["DXF bytes"], "plano.dxf"));
  t.mock.method(globalThis, "fetch", async (url, init) => {
    const forwarded = new Request(url, init);
    const received = await forwarded.formData();
    const file = received.get("files");
    return Response.json({ name: file.name, content: await file.text(), method: init.method },
      { status: 201 });
  });
  const res = await proxyAPI(new Request("https://pilot.example/api/projects/upload", {
    method: "POST", body: form,
  }));
  assert.equal(res.status, 201);
  assert.deepEqual(await res.json(), { name: "plano.dxf", content: "DXF bytes", method: "POST" });
});

test("SSE is returned as a stream before the upstream finishes", async (t) => {
  binding(t);
  let controller;
  const stream = new ReadableStream({ start(value) { controller = value; } });
  t.mock.method(globalThis, "fetch", async () => new Response(stream, {
    headers: { "content-type": "text/event-stream", "x-request-id": "pilot-id" },
  }));
  const res = await proxyAPI(new Request("https://pilot.example/api/events"));
  controller.enqueue(new TextEncoder().encode("data: live\n\n"));
  const reader = res.body.getReader();
  assert.equal(new TextDecoder().decode((await reader.read()).value), "data: live\n\n");
  assert.equal(res.headers.get("content-type"), "text/event-stream");
  assert.equal(res.headers.get("x-request-id"), "pilot-id");
  controller.close();
  reader.releaseLock();
});

test("all Set-Cookie headers and backend errors survive the proxy", async (t) => {
  binding(t);
  const headers = new Headers({ "cache-control": "public, max-age=3600", "x-request-id": "ref-1" });
  headers.append("set-cookie", "klave_session=value; Path=/; HttpOnly; Secure");
  headers.append("set-cookie", "state=value; Path=/api/auth; HttpOnly; SameSite=Lax");
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { error_type: "denied" } },
    { status: 403, headers }));
  const res = await proxyAPI(new Request("https://pilot.example/api/auth/login"));
  assert.equal(res.status, 403);
  assert.equal(res.headers.getSetCookie().length, 2);
  assert.equal(res.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(await res.json(), { detail: { error_type: "denied" } });
});

test("redirects stay manual and internal redirect URLs map to the public prefix", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async (_url, init) => {
    assert.equal(init.redirect, "manual");
    return new Response(null, { status: 307,
      headers: { location: "https://app.internal/bound/projects/?page=2" } });
  });
  const res = await proxyAPI(new Request("https://pilot.example/api/projects"));
  assert.equal(res.status, 307);
  assert.equal(res.headers.get("location"), "/api/projects/?page=2");
});

test("external redirects are returned to the browser rather than followed internally", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 307,
    headers: { location: "https://elsewhere.example/landing?state=synthetic" } }));
  const res = await proxyAPI(new Request("https://pilot.example/api/projects"));
  assert.equal(res.headers.get("location"), "https://elsewhere.example/landing?state=synthetic");
});

test("export bytes, filenames and empty 204 responses survive forwarding", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async () => new Response(new Uint8Array([80, 75, 0, 255]), {
    headers: { "content-disposition": "attachment; filename=budget.xlsx",
      "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  }));
  const download = await proxyAPI(new Request("https://pilot.example/api/projects/p/export"));
  assert.deepEqual([...new Uint8Array(await download.arrayBuffer())], [80, 75, 0, 255]);
  assert.equal(download.headers.get("content-disposition"), "attachment; filename=budget.xlsx");
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 204 }));
  const empty = await proxyAPI(new Request("https://pilot.example/api/projects/p", { method: "DELETE" }));
  assert.equal(empty.status, 204);
  assert.equal(await empty.text(), "");
});

test("upstream failures return a coarse error without internal URLs or secrets", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async () => { throw Error("secret at https://app.internal"); });
  const res = await proxyAPI(new Request("https://pilot.example/api/auth/invitations/by-token/private"));
  assert.equal(res.status, 502);
  const body = await res.text();
  assert.ok(!body.includes("secret") && !body.includes("internal") && !body.includes("private"));
});

test("encoded path separators cannot escape the bound service base", async (t) => {
  binding(t);
  t.mock.method(globalThis, "fetch", async () => { throw Error("must not fetch"); });
  const res = await proxyAPI(new Request("https://pilot.example/api/%2f%2fattacker.example/health"));
  assert.equal(res.status, 400);
});

for (const [path, expected] of [
  ["http:attacker.example", "https://app.internal/bound/http:attacker.example"],
  ["https://attacker.example/steal", "https://app.internal/bound/https://attacker.example/steal"],
  ["//attacker.example/steal", "https://app.internal/bound///attacker.example/steal"],
]) {
  test("a URL-looking API path cannot forward sessions outside the binding: " + path, async (t) => {
    binding(t);
    t.mock.method(globalThis, "fetch", async (url) => Response.json({ target: String(url) }));
    const res = await proxyAPI(new Request("https://pilot.example/api/" + path, {
      headers: { cookie: "klave_session=synthetic" },
    }));
    assert.deepEqual(await res.json(), { target: expected });
  });
}
