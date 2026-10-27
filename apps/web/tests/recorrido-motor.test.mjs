import assert from "node:assert/strict";
import { test } from "node:test";
import { createRequire } from "node:module";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { avanzar, pasoActual, rutaDelPaso, rutaHeredada, ESTADO_INICIAL } = require(
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
      paso("a.crear", "arranque", "hacer", { con: "evento", tipo: "run_published" },
        { accion: "crear_obra", libre: true }),
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

const { esCampoDeTexto } = require(join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "teclas.js"));

test("las flechas siguen funcionando después de hacer clic en un botón", () => {
  assert.equal(esCampoDeTexto("BUTTON", false), false);
  assert.equal(esCampoDeTexto("INPUT", false, "checkbox"), false);
  assert.equal(esCampoDeTexto("INPUT", false, "text"), true);
  assert.equal(esCampoDeTexto("TEXTAREA", false), true);
  assert.equal(esCampoDeTexto("SELECT", false), true);
  assert.equal(esCampoDeTexto("DIV", true), true);
});

test("continuar un capítulo a medias retoma el primer paso sin hacer", () => {
  const conAvance = run(conObra, { tipo: "progreso", progreso: { "p.lectura": "hecho" } });
  assert.equal(run(conAvance, { tipo: "iniciar", capitulo: "planos" }).indice, 1);
});

test("retomar un paso sin ruta propia lleva a la ruta del paso anterior", () => {
  assert.equal(rutaHeredada(CAPS[1], 2, "obra_1"), "/proyecto/obra_1/plano");
  assert.equal(rutaHeredada(CAPS[1], 0, "obra_1"), "/proyecto/obra_1/lectura");
  assert.equal(rutaHeredada(CAPS[2], 1, "obra_1"), "/proyecto/obra_1/presupuesto");
});

const { obraRecienLista } = require(join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "obra.js"));

test("«obra.lista» sólo cuando la obra termina de procesarse, no al abrirla ya lista", () => {
  assert.equal(obraRecienLista(null, "processed"), false);       // abrir una obra ya leída
  assert.equal(obraRecienLista("running", "processed"), true);   // terminó mientras mirabas
  assert.equal(obraRecienLista("queued", "processed"), true);
  assert.equal(obraRecienLista("processed", "processed"), false);
  assert.equal(obraRecienLista("running", "failed"), false);
});

test("con los «hacer» hechos y un «mirar» pendiente, retoma el pendiente en repaso", () => {
  const caps = [{
    id: "revisiones", titulo: "R", minutos: 1, requiereObra: false, transferencia: "t",
    pasos: [
      paso("r.b", "revisiones", "hacer", { con: "senal", nombre: "obra.lista" }),
      paso("r.ver", "revisiones", "mirar", { con: "siguiente" }),
    ],
  }];
  const casi = avanzar(ESTADO_INICIAL, { tipo: "progreso", progreso: { "r.b": "hecho" } }, caps);
  const e = avanzar(casi, { tipo: "iniciar", capitulo: "revisiones" }, caps);
  assert.equal(e.repaso, true);
  assert.equal(e.indice, 1);
});


// --- Revisión final ------------------------------------------------------------

test("sin obra lista, el arranque abre en «crear» y no en repaso (no hay bucle)", () => {
  const hecho = run(ESTADO_INICIAL, { tipo: "progreso", progreso: { "a.hola": "hecho", "a.crear": "saltado" } });
  const e = run(hecho, { tipo: "iniciar", capitulo: "planos" });
  assert.equal(e.capitulo, "arranque");
  assert.equal(e.indice, 1);
  assert.equal(e.repaso, false);
});

test("fuera de ruta también en un paso que hereda su pantalla", () => {
  // pr.exp no dice ruta: vive en /presupuesto, la del paso anterior.
  const enExportar = { ...run(conObra, { tipo: "iniciar", capitulo: "presupuesto" }), indice: 1 };
  const e = run(enExportar, { tipo: "ruta", pathname: "/proyecto/obra_1/revision" });
  assert.equal(e.fueraDeRuta, true);
  assert.equal(run(e, { tipo: "ruta", pathname: "/proyecto/obra_1/presupuesto" }).fueraDeRuta, false);
});

test("un paso «libre» (crear la obra) puede llevarte a otra pantalla sin salir del recorrido", () => {
  const e = { ...run(ESTADO_INICIAL, { tipo: "iniciar", capitulo: "arranque" }), indice: 1 };
  assert.equal(run(e, { tipo: "ruta", pathname: "/proyecto/obra_1" }).fueraDeRuta, false);
});

test("retomar el mismo paso cuenta como otra visita (para volver a su pantalla)", () => {
  const a = run(conObra, { tipo: "iniciar", capitulo: "planos" });
  const b = run(run(a, { tipo: "pausar" }), { tipo: "iniciar", capitulo: "planos" });
  assert.equal(a.indice, b.indice);
  assert.notEqual(a.visita, b.visita);
});

test("un ancla que aparece tarde deja de estar perdida", () => {
  const e = run(enPlanos(0), { tipo: "ancla_perdida" });
  assert.equal(run(e, { tipo: "ancla_encontrada" }).anclaPerdida, false);
});

const { teclaDelRecorrido } = require(join(process.env.KLAVE_TEST_LIB_DIR, "recorrido", "teclas.js"));

test("las teclas de la pantalla mandan: Esc y flechas sólo cuando nadie más las usó", () => {
  const base = { defaultPrevented: false, enTarjeta: false, escribiendo: false, tipo: "mirar", ancla: "lectura.metricas" };
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowRight" }), "siguiente");
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowRight", defaultPrevented: true }), null);
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowRight", ancla: "visor.lienzo" }), null);
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowRight", tipo: "hacer" }), null);
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowRight", tipo: null }), "siguiente");
  assert.equal(teclaDelRecorrido({ ...base, key: "Escape" }), null);
  assert.equal(teclaDelRecorrido({ ...base, key: "Escape", enTarjeta: true }), "pausar");
  assert.equal(teclaDelRecorrido({ ...base, key: "ArrowLeft", escribiendo: true }), null);
});
