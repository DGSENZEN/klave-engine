import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { pideConfirmarQuitarEnLote } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "confirmar.js"),
);

test("quitar la revisión de 50 elementos no pregunta; de 51, sí", () => {
  assert.equal(pideConfirmarQuitarEnLote(50), false);
  assert.equal(pideConfirmarQuitarEnLote(51), true);
});
