import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { safeReturnPath } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "sessionReturn.js"),
);
const origin = "https://app.taller.mx";
for (const candidate of [null, "//outside.example/x", "https://outside.example/x",
  "/\\outside.example/x", "/bienvenida", "/invitacion?token=private",
  "javascript:alert(1)", "https://["]) {
  test("unsafe or looping destination returns home: " + String(candidate), () => {
    assert.equal(safeReturnPath(candidate, origin), "/");
  });
}
test("a project destination keeps query and fragment", () => {
  assert.equal(safeReturnPath("/proyecto/p/resumen?q=1#units", origin),
    "/proyecto/p/resumen?q=1#units");
});
