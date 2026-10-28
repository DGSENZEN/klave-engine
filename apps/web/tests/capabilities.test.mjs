import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { capabilities, isHumanDecision, isRoleRefusal, keepStatus } = createRequire(import.meta.url)(
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

test("una decisión es de una persona: confirmada, o sin equivalente que no puso el motor", () => {
  assert.equal(isHumanDecision({ status: "confirmada", actor: "motor" }), true);
  assert.equal(isHumanDecision({ status: "sin_equivalente", actor: "Ana" }), true);
  assert.equal(isHumanDecision({ status: "sin_equivalente", actor: "motor" }), false);
  assert.equal(isHumanDecision({ status: "sin_equivalente", actor: "" }), false);
  assert.equal(isHumanDecision({ status: "propuesta", actor: "Ana" }), false);
  assert.equal(isHumanDecision({ status: "automatica", actor: "motor" }), false);
  assert.equal(isHumanDecision(null), false);
});

test("una negativa por rol se reconoce para refrescar la sesión", () => {
  assert.equal(isRoleRefusal({ status: 403, detail: { error_type: "admin_required" } }), true);
  assert.equal(isRoleRefusal({ status: 403, detail: { error_type: "forbidden_project" } }), true);
  assert.equal(isRoleRefusal({ status: 403, detail: { error_type: "origin_not_allowed" } }), false);
  assert.equal(isRoleRefusal({ status: 500 }), false);
  assert.equal(isRoleRefusal(new Error("red")), false);
});

test("una caída momentánea no se queda guardada como la sesión", () => {
  assert.equal(keepStatus({ mode: "unavailable" }), false);
  assert.equal(keepStatus({ mode: "protected" }), true);
  assert.equal(keepStatus({ mode: "open" }), true);
});
