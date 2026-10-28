import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { accionDeTecla } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "teclasVisor.js"),
);

const base = { enCampo: false, seleccionado: true, motivoAbierto: false, midiendo: false };

test("X pide el motivo en vez de excluir", () => {
  assert.equal(accionDeTecla("x", base), "pedir-motivo");
  assert.equal(accionDeTecla("X", base), "pedir-motivo");
});

test("C confirma y Q quita, de una tecla", () => {
  assert.equal(accionDeTecla("c", base), "confirmar");
  assert.equal(accionDeTecla("q", base), "quitar");
});

test("escribiendo en un campo, ninguna tecla actúa", () => {
  for (const k of ["x", "c", "q", "ArrowRight", "Escape"]) {
    assert.equal(accionDeTecla(k, { ...base, enCampo: true }), null, k);
  }
});

test("con el motivo abierto, la X es una letra del motivo", () => {
  assert.equal(accionDeTecla("x", { ...base, motivoAbierto: true }), null);
  assert.equal(accionDeTecla("c", { ...base, motivoAbierto: true }), null);
});

test("las flechas recorren aunque no haya nada elegido", () => {
  assert.equal(accionDeTecla("ArrowRight", { ...base, seleccionado: false }), "siguiente");
  assert.equal(accionDeTecla("ArrowLeft", base), "anterior");
});

test("sin elemento elegido, C, X y Q no hacen nada", () => {
  for (const k of ["c", "x", "q"]) {
    assert.equal(accionDeTecla(k, { ...base, seleccionado: false }), null, k);
  }
});

test("Escape cancela; midiendo, sólo Escape cuenta", () => {
  assert.equal(accionDeTecla("Escape", base), "cancelar");
  assert.equal(accionDeTecla("x", { ...base, midiendo: true }), null);
  assert.equal(accionDeTecla("Escape", { ...base, midiendo: true }), "cancelar");
});
