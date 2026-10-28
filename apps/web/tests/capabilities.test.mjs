import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { capabilities } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "capabilities.js"),
);

const ALL = { editCatalog: true, editProject: true, manageProject: true, approveGate: true };
const NONE = { editCatalog: false, editProject: false, manageProject: false, approveGate: false };

test("modo abierto: todos pueden todo", () => {
  assert.deepEqual(capabilities({ mode: "open", tallerRole: null, projectRole: null }), ALL);
});

test("sin servicio de cuentas: nada se ofrece", () => {
  assert.deepEqual(capabilities({ mode: "unavailable", tallerRole: null }), NONE);
});

test("admin del taller: todo, en cualquier proyecto", () => {
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "admin", projectRole: "admin" }), ALL);
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "admin" }), ALL);
});

test("propietario: su proyecto entero, el catálogo solo lo lee", () => {
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "member", projectRole: "owner" }), {
    editCatalog: false, editProject: true, manageProject: true, approveGate: true,
  });
});

test("editor: revisa y cuantifica, sin controles de propietario", () => {
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "member", projectRole: "editor" }), {
    editCatalog: false, editProject: true, manageProject: false, approveGate: false,
  });
});

test("lector: solo lee", () => {
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "member", projectRole: "viewer" }), NONE);
});

test("miembro fuera de un proyecto: el catálogo solo lo lee", () => {
  assert.deepEqual(capabilities({ mode: "protected", tallerRole: "member" }), NONE);
});
