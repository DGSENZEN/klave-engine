import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { vista } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "procesando.js"),
);

test("procesado abre el proyecto", () => {
  assert.equal(vista("processed", false, false), "shell");
});

test("reprocesar con una lectura legible deja el proyecto abierto con aviso", () => {
  assert.equal(vista("queued", true, false), "shell-reprocesando");
  assert.equal(vista("running", true, false), "shell-reprocesando");
});

test("reprocesar desde dentro: ya abierta aunque el evento no traiga artefactos", () => {
  assert.equal(vista("running", false, true), "shell-reprocesando");
});

test("la primera lectura muestra la pantalla de procesamiento", () => {
  assert.equal(vista("queued", false, false), "procesando");
  assert.equal(vista("running", false, false), "procesando");
});

test("un fallo con lectura legible abre el proyecto; sin ella, la pantalla de fallo", () => {
  assert.equal(vista("failed", true, false), "shell");
  assert.equal(vista("failed", false, false), "fallo");
});
