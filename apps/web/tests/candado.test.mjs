import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { quienCerro } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "candado.js"),
);

const cierre = { type: "gate_updated", data: { node: "contrato", approved: false, by: "Ana" } };

test("el cierre de este nodo dice quién lo cerró", () => {
  assert.equal(quienCerro(cierre, "contrato"), "Ana");
});

test("otro nodo, una apertura u otro evento no cuentan", () => {
  assert.equal(quienCerro(cierre, "programa"), null);
  assert.equal(quienCerro({ ...cierre, data: { ...cierre.data, approved: true } }, "contrato"), null);
  assert.equal(quienCerro({ type: "review_updated", data: {} }, "contrato"), null);
  assert.equal(quienCerro(null, "contrato"), null);
});

test("un cierre sin nombre no inventa uno", () => {
  assert.equal(quienCerro({ ...cierre, data: { node: "contrato", approved: false, by: "" } }, "contrato"), null);
});
