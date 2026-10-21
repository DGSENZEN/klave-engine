import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

// A missing public override must produce same-origin browser requests, not
// localhost requests from a customer's machine.
delete process.env.NEXT_PUBLIC_API_URL;
const api = createRequire(import.meta.url)(join(process.env.KLAVE_TEST_LIB_DIR, "api.js"));
const { projectEventsUrl } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "collab.js"),
);

test("the default browser client uses the public API prefix", async (t) => {
  let target;
  t.mock.method(globalThis, "fetch", async (url) => {
    target = String(url);
    return Response.json({ projects: [] });
  });
  await api.listProjects();
  assert.equal(target, "/api/projects");
  assert.equal(api.API_MISCONFIGURED, false);
});

test("catalog uploads support a relative API prefix and encode query values", async (t) => {
  let target;
  t.mock.method(globalThis, "fetch", async (url) => {
    target = String(url);
    return Response.json({ updated: 1, skipped: [] });
  });
  await api.importCatalogPrices(new File(["price"], "prices.xlsx"), "pilot & team");
  assert.equal(target, "/api/catalog/import-prices?source=pilot+%26+team");
  await api.importCustomSource(new File(["price"], "source.xlsx"), "A & B", "2026");
  assert.equal(target, "/api/catalog/sources/custom?name=A+%26+B&vigencia=2026");
});

test("project event streams support the same relative prefix", () => {
  assert.equal(projectEventsUrl("pilot project", "A & B", "client", "/proyecto/p/plano", "Plano"),
    "/api/projects/pilot%20project/events?actor=A+%26+B&client_id=client&location_path=%2Fproyecto%2Fp%2Fplano&location_label=Plano");
});
