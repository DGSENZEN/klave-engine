import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { inicialCostoHorario } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "costoHorario.js"),
);

const DEFAULTS = { vida_util_horas: 10000 };

test("un análisis guardado se muestra como guardado", () => {
  const r = inicialCostoHorario({ ok: true, data: { vida_util_horas: 8000 } }, DEFAULTS);
  assert.deepEqual(r, { params: { vida_util_horas: 8000 }, origen: "guardado" });
});

test("un 404 trae los valores de partida y lo dice", () => {
  const r = inicialCostoHorario({ ok: false, status: 404 }, DEFAULTS);
  assert.deepEqual(r, { params: DEFAULTS, origen: "partida" });
});

test("una respuesta vacía también es partida", () => {
  const r = inicialCostoHorario({ ok: true, data: null }, DEFAULTS);
  assert.deepEqual(r, { params: DEFAULTS, origen: "partida" });
});

test("un 500 o una falla de red no inventan valores", () => {
  assert.deepEqual(inicialCostoHorario({ ok: false, status: 500 }, DEFAULTS), { params: null, origen: "error" });
  assert.deepEqual(inicialCostoHorario({ ok: false }, DEFAULTS), { params: null, origen: "error" });
});
