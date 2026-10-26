import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { avanzar, pasoActual, rutaDelPaso, ESTADO_INICIAL } = require(
  join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "motor.js"),
);
const { crearAlmacen } = require(join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "progreso.js"));

const paso = (id, capitulo, tipo, avanza, extra = {}) => ({
  id, capitulo, tipo, avanza, titulo: id, cuerpo: "", ...extra,
});
const CAPS = [
  {
    id: "arranque", titulo: "Arranque", minutos: 2, requiereObra: false, transferencia: "t0",
    pasos: [
      paso("a.hola", "arranque", "mirar", { con: "siguiente" }, { ruta: "~/" }),
      paso("a.crear", "arranque", "hacer", { con: "evento", tipo: "run_published" }),
    ],
  },
  {
    id: "planos", titulo: "Planos", minutos: 5, requiereObra: true, transferencia: "t1",
    pasos: [
      paso("p.lectura", "planos", "mirar", { con: "siguiente" }, { ruta: "/lectura" }),
      paso("p.decidir", "planos", "hacer", {
        con: "evento", tipo: "review_updated", si: (d) => String(d.action).startsWith("detection_"),
      }, { ruta: "/plano" }),
      paso("p.mover", "planos", "hacer", { con: "senal", nombre: "visor.mover" }, { ruta: "/plano" }),
    ],
  },
  {
    id: "presupuesto", titulo: "Presupuesto", minutos: 5, requiereObra: true, transferencia: "t2",
    pasos: [
      paso("pr.gen", "presupuesto", "hacer", { con: "ruta", ruta: "/plano" }, { ruta: "/presupuesto" }),
      paso("pr.exp", "presupuesto", "hacer", { con: "clic" }, { ancla: "presupuesto.exportar" }),
    ],
  },
];
const run = (estado, ...entradas) => entradas.reduce((e, x) => avanzar(e, x, CAPS), estado);
const conObra = run(ESTADO_INICIAL, { tipo: "obra", projectId: "obra_1", lista: true });
const enPlanos = (indice) => ({ ...run(conObra, { tipo: "iniciar", capitulo: "planos" }), indice });
const evento = (type, data = {}, project_id = "obra_1") => ({ tipo: "evento", evento: { type, project_id, data } });

test("mirar avanza con siguiente", () => {
  const e = run(enPlanos(0), { tipo: "siguiente" });
  assert.equal(e.indice, 1);
  assert.equal(e.progreso["p.lectura"], "hecho");
});

test("hacer ignora siguiente", () => {
  const e = run(enPlanos(1), { tipo: "siguiente" });
  assert.equal(e.indice, 1);
  assert.equal(e.progreso["p.decidir"], undefined);
});

test("hacer avanza con su evento", () => {
  const e = run(enPlanos(1), evento("review_updated", { action: "detection_excluded" }));
  assert.equal(e.indice, 2);
  assert.equal(e.progreso["p.decidir"], "hecho");
});

test("ignora eventos de otro proyecto", () => {
  const e = run(enPlanos(1), evento("review_updated", { action: "detection_excluded" }, "otra"));
  assert.equal(e.indice, 1);
});

test("si filtra la acción", () => {
  const e = run(enPlanos(1), evento("review_updated", { action: "verification_units" }));
  assert.equal(e.indice, 1);
});

test("una señal avanza su paso", () => {
  const e = run(enPlanos(2), { tipo: "senal", nombre: "visor.mover" });
  assert.equal(e.indice, 3);
  assert.equal(run(enPlanos(2), { tipo: "senal", nombre: "otra" }).indice, 2);
});

test("saltar queda registrado", () => {
  const e = run(enPlanos(1), { tipo: "saltar" });
  assert.equal(e.indice, 2);
  assert.equal(e.progreso["p.decidir"], "saltado");
});

test("sin obra va al arranque", () => {
  const e = run(ESTADO_INICIAL, { tipo: "iniciar", capitulo: "planos" });
  assert.equal(e.capitulo, "arranque");
  assert.equal(e.activo, true);
});

test("capítulo hecho entra en repaso y ahí siguiente avanza un hacer", () => {
  const hecho = run(conObra, { tipo: "progreso", progreso: { "p.decidir": "hecho", "p.mover": "saltado" } });
  const e = run(hecho, { tipo: "iniciar", capitulo: "planos" });
  assert.equal(e.repaso, true);
  assert.equal(run({ ...e, indice: 1 }, { tipo: "siguiente" }).indice, 2);
  assert.equal(run(conObra, { tipo: "iniciar", capitulo: "planos" }).repaso, false);
});

test("fuera de ruta", () => {
  const e = run(enPlanos(0), { tipo: "ruta", pathname: "/proyecto/obra_1/riesgos" });
  assert.equal(e.fueraDeRuta, true);
  const vuelta = run(e, { tipo: "ruta", pathname: "/proyecto/obra_1/lectura" });
  assert.equal(vuelta.fueraDeRuta, false);
});

test("un paso que avanza por ruta avanza al llegar", () => {
  const e = run(conObra, { tipo: "iniciar", capitulo: "presupuesto" },
    { tipo: "ruta", pathname: "/proyecto/obra_1/plano" });
  assert.equal(e.indice, 1);
  assert.equal(e.fueraDeRuta, false);
});

test("clic en su ancla avanza; en otra no", () => {
  const e = { ...run(conObra, { tipo: "iniciar", capitulo: "presupuesto" }), indice: 1 };
  assert.equal(run(e, { tipo: "clic", ancla: "otra" }).indice, 1);
  assert.equal(run(e, { tipo: "clic", ancla: "presupuesto.exportar" }).indice, 2);
});

test("ancla perdida se limpia al cambiar de paso", () => {
  const e = run(enPlanos(0), { tipo: "ancla_perdida" });
  assert.equal(e.anclaPerdida, true);
  assert.equal(run(e, { tipo: "siguiente" }).anclaPerdida, false);
});

test("fin de capítulo muestra la transferencia y luego sigue al siguiente", () => {
  const fin = run(enPlanos(2), { tipo: "senal", nombre: "visor.mover" });
  assert.equal(fin.activo, true);
  assert.equal(pasoActual(fin, CAPS), null);
  const siguiente = run(fin, { tipo: "siguiente" });
  assert.equal(siguiente.capitulo, "presupuesto");
  assert.equal(siguiente.indice, 0);
});

test("el último capítulo termina el recorrido", () => {
  const e = { ...run(conObra, { tipo: "iniciar", capitulo: "presupuesto" }), indice: 2 };
  assert.equal(run(e, { tipo: "siguiente" }).activo, false);
});

test("pausar conserva el lugar", () => {
  const e = run(enPlanos(1), { tipo: "pausar" });
  assert.equal(e.activo, false);
  assert.equal(e.indice, 1);
  assert.equal(run(e, evento("review_updated", { action: "detection_confirmed" })).indice, 1);
});

test("rutas: del proyecto, del taller y sin obra", () => {
  const [p0] = CAPS[1].pasos;
  assert.equal(rutaDelPaso(p0, "obra 1"), "/proyecto/obra%201/lectura");
  assert.equal(rutaDelPaso(CAPS[0].pasos[0], null), "/");
  assert.equal(rutaDelPaso(p0, null), null);
  assert.equal(rutaDelPaso(CAPS[0].pasos[1], "x"), null);
});

function memoria() {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) };
}

test("progreso cae a local", async () => {
  const local = memoria();
  const roto = {
    cargar: async () => { throw new Error("db"); },
    guardar: async () => { throw new Error("db"); },
    borrar: async () => { throw new Error("db"); },
  };
  const almacen = crearAlmacen(roto, local);
  await almacen.guardar("p.decidir", "hecho");
  await almacen.guardar("p.mover", "no_encontrado");
  assert.deepEqual(await almacen.cargar(), { "p.decidir": "hecho" });
  await almacen.borrar();
  assert.deepEqual(await almacen.cargar(), {});
});

test("progreso remoto gana cuando responde", async () => {
  const local = memoria();
  const remoto = {
    cargar: async () => ({ "a.crear": "hecho" }),
    guardar: async () => {},
    borrar: async () => {},
  };
  assert.deepEqual(await crearAlmacen(remoto, local).cargar(), { "a.crear": "hecho" });
  assert.deepEqual(await crearAlmacen(null, local).cargar(), { "a.crear": "hecho" });  // quedó en lo local
  assert.deepEqual(await crearAlmacen(null, memoria()).cargar(), {});
});
