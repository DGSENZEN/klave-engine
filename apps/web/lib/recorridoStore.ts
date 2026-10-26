"use client";

import { useSyncExternalStore } from "react";
import { CAPITULOS } from "./recorrido/capitulos";
import { avanzar, ESTADO_INICIAL, pasoActual } from "./recorrido/motor";
import { crearAlmacen, type AlmacenProgreso } from "./recorrido/progreso";
import type { CapituloId, Entrada, EstadoRecorrido } from "./recorrido/tipos";

// El estado del recorrido para React: un almacén de módulo (no un contexto),
// leído con useSyncExternalStore. Cada entrada pasa por el motor puro; aquí
// sólo se guarda el progreso nuevo y se avisa a quien escucha.

let estado: EstadoRecorrido = ESTADO_INICIAL;
const oyentes = new Set<() => void>();

const memoria = new Map<string, string>();
const localSeguro = {
  getItem: (k: string) => {
    try {
      return window.localStorage.getItem(k);
    } catch {
      return memoria.get(k) ?? null;
    }
  },
  setItem: (k: string, v: string) => {
    try {
      window.localStorage.setItem(k, v);
    } catch {
      memoria.set(k, v);
    }
  },
  removeItem: (k: string) => {
    try {
      window.localStorage.removeItem(k);
    } catch {
      memoria.delete(k);
    }
  },
};

let actual: AlmacenProgreso = crearAlmacen(null, localSeguro);

/** Dónde vive el progreso; el proveedor lo apunta a la cuenta cuando hay cuentas. */
export const almacen: AlmacenProgreso = {
  cargar: () => actual.cargar(),
  guardar: (pasoId, valor) => actual.guardar(pasoId, valor),
  borrar: () => actual.borrar(),
};

export function configurarAlmacen(remoto: AlmacenProgreso | null): void {
  actual = crearAlmacen(remoto, localSeguro);
}

export function despachar(entrada: Entrada): void {
  const antes = estado;
  if (entrada.tipo === "ancla_perdida") {
    const paso = pasoActual(antes, CAPITULOS);
    if (paso && !antes.anclaPerdida) {
      void almacen.guardar(paso.id, "no_encontrado");
      console.warn(`recorrido: no encontré [data-tour="${paso.ancla}"] (${paso.id})`);
    }
  }
  estado = avanzar(antes, entrada, CAPITULOS);
  if (entrada.tipo !== "progreso") {
    for (const [id, valor] of Object.entries(estado.progreso)) {
      if (antes.progreso[id] !== valor) void almacen.guardar(id, valor);
    }
  }
  if (estado !== antes) oyentes.forEach((oyente) => oyente());
}

export function iniciarCapitulo(id: CapituloId): void {
  despachar({ tipo: "iniciar", capitulo: id });
}

export function senalRecorrido(nombre: string): void {
  despachar({ tipo: "senal", nombre });
}

function suscribir(oyente: () => void): () => void {
  oyentes.add(oyente);
  return () => oyentes.delete(oyente);
}

export function useRecorrido(): EstadoRecorrido {
  return useSyncExternalStore(suscribir, () => estado, () => ESTADO_INICIAL);
}
