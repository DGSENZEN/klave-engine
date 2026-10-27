import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { colocarTarjeta } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "colocar.js"),
);
const vista = { w: 1280, h: 800 };
const tarjeta = { w: 320, h: 160 };

test("abajo por defecto", () => {
  const c = colocarTarjeta({ top: 100, left: 400, width: 200, height: 40 }, tarjeta, vista);
  assert.equal(c.lado, "abajo");
  assert.equal(c.top, 152);
  assert.equal(c.left, 340);
});

test("arriba si no cabe abajo", () => {
  const c = colocarTarjeta({ top: 700, left: 400, width: 200, height: 40 }, tarjeta, vista);
  assert.equal(c.lado, "arriba");
  assert.equal(c.top, 700 - 12 - 160);
});

test("nunca fuera de la vista", () => {
  const c = colocarTarjeta({ top: 100, left: 1250, width: 20, height: 20 }, tarjeta, vista);
  assert.ok(c.left >= 12 && c.left + tarjeta.w <= vista.w - 12);
  assert.ok(c.top >= 12 && c.top + tarjeta.h <= vista.h - 12);
});

test("un ancla que llena la vista deja la tarjeta en la esquina", () => {
  const c = colocarTarjeta({ top: 0, left: 0, width: 1280, height: 800 }, tarjeta, vista);
  assert.equal(c.lado, "centro");
  assert.equal(c.left, 1280 - 320 - 12);
  assert.equal(c.top, 800 - 160 - 12);
});

test("sin ancla va al centro", () => {
  const c = colocarTarjeta(null, tarjeta, vista);
  assert.deepEqual(c, { top: 320, left: 480, lado: "centro" });
});

test("respeta el lado que pide el paso cuando cabe (un menú se abre abajo)", () => {
  const ancla = { top: 80, left: 1100, width: 120, height: 36 };
  const c = colocarTarjeta(ancla, tarjeta, vista, 12, "izquierda");
  assert.equal(c.lado, "izquierda");
  assert.equal(c.left, 1100 - 12 - 320);
  // Si no cabe donde pide, vuelve al orden normal.
  const pegado = colocarTarjeta({ top: 80, left: 20, width: 120, height: 36 }, tarjeta, vista, 12, "izquierda");
  assert.equal(pegado.lado, "abajo");
});

test("«esquina» deja la tarjeta abajo a la izquierda, lejos de menús y diálogos", () => {
  const c = colocarTarjeta({ top: 80, left: 1100, width: 120, height: 36 }, tarjeta, vista, 12, "esquina");
  assert.deepEqual(c, { top: 800 - 160 - 12, left: 12, lado: "esquina" });
});
