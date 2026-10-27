import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

// El recorrido no se pudre en silencio: cada ancla que un paso señala tiene
// que existir, como literal, en alguna pantalla (data-tour="…", tour="…" o
// ancla="…"). Si alguien renombra o borra el elemento, esta prueba falla.

const { CAPITULOS } = createRequire(import.meta.url)(
  join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "capitulos", "index.js"),
);

function archivos(dir) {
  return readdirSync(dir).flatMap((nombre) => {
    const ruta = join(dir, nombre);
    if (statSync(ruta).isDirectory()) return archivos(ruta);
    return ruta.endsWith(".tsx") ? [ruta] : [];
  });
}
const fuente = [...archivos("app"), ...archivos("components")]
  .map((ruta) => readFileSync(ruta, "utf8"))
  .join("\n");

const pasos = CAPITULOS.flatMap((c) => c.pasos);

test("hay nueve capítulos, en el orden del flujo", () => {
  assert.deepEqual(CAPITULOS.map((c) => c.id), [
    "arranque", "tablero", "planos", "revision", "catalogo",
    "presupuesto", "programa", "revisiones", "tu-obra",
  ]);
});

for (const paso of pasos.filter((p) => p.ancla)) {
  test(`el ancla de ${paso.id} existe en una pantalla: ${paso.ancla}`, () => {
    assert.ok(
      fuente.includes(`"${paso.ancla}"`),
      `ninguna pantalla declara data-tour="${paso.ancla}"`,
    );
  });
}

test("los ids de paso son únicos", () => {
  const ids = pasos.map((p) => p.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("cada capítulo deja su transferencia y cada paso su texto", () => {
  for (const capitulo of CAPITULOS) {
    assert.ok(capitulo.transferencia.length > 20, capitulo.id);
    for (const paso of capitulo.pasos) {
      assert.equal(paso.capitulo, capitulo.id);
      assert.ok(paso.titulo && paso.cuerpo, paso.id);
    }
  }
});

test("ningún texto usa el vocabulario prohibido", () => {
  const prohibido = /detecci[oó]n|el motor|corrida/i;
  for (const capitulo of CAPITULOS) {
    for (const texto of [capitulo.transferencia, ...capitulo.pasos.flatMap((p) => [p.titulo, p.cuerpo])]) {
      assert.ok(!prohibido.test(texto), texto);
    }
  }
});

test("un paso «hacer» nunca avanza con Siguiente", () => {
  for (const paso of pasos.filter((p) => p.tipo === "hacer")) {
    assert.notEqual(paso.avanza.con, "siguiente", paso.id);
  }
});
