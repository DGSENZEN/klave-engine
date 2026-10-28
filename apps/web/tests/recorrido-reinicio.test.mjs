import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const { empezarDeCero } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "reinicio.js"),
);

test("si el servidor rechaza el reinicio, el progreso se queda y se dice por qué", async () => {
  let borrado = false;
  const resultado = await empezarDeCero("obra_1", {
    reiniciar: async () => { throw Object.assign(new Error("busy"), { detail: { message: "La obra de ejemplo se está procesando; espera a que termine." } }); },
    borrar: async () => { borrado = true; },
  });
  assert.equal(resultado.ok, false);
  assert.match(resultado.mensaje, /procesando/);
  assert.equal(borrado, false);
});

test("con el reinicio hecho, se borra el progreso", async () => {
  let borrado = false;
  const resultado = await empezarDeCero("obra_1", {
    reiniciar: async () => ({}),
    borrar: async () => { borrado = true; },
  });
  assert.deepEqual(resultado, { ok: true });
  assert.equal(borrado, true);
});

test("sin obra conocida sólo se borra el progreso", async () => {
  let llamado = false;
  const resultado = await empezarDeCero(null, {
    reiniciar: async () => { llamado = true; },
    borrar: async () => {},
  });
  assert.deepEqual(resultado, { ok: true });
  assert.equal(llamado, false);
});
