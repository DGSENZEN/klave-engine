import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { alCargar, puedeGuardar } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "conteos.js"),
);

test("un fallo sin carga previa deja la base vacía y no se puede guardar", () => {
  const c = alCargar({ base: null, error: false }, { ok: false });
  assert.equal(c.base, null);
  assert.equal(c.error, true);
  assert.equal(puedeGuardar(c), false);
});

test("un fallo en una recarga conserva lo ya cargado y se puede guardar", () => {
  const base = { hojas: [{ hoja: "E-01", familia: "column", contado: 12 }] };
  const c = alCargar({ base, error: false }, { ok: false });
  assert.deepEqual(c.base, base);
  assert.equal(c.error, true);
  assert.equal(puedeGuardar(c), true);
});

test("una carga buena limpia el error", () => {
  const c = alCargar({ base: null, error: true }, { ok: true, data: { hojas: [] } });
  assert.equal(c.error, false);
  assert.equal(puedeGuardar(c), true);
});
