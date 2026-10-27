"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { cargarRevisionB, createDemoProject, listProjects } from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { CAPITULOS } from "@/lib/recorrido/capitulos";
import type { Rect } from "@/lib/recorrido/colocar";
import { pasoActual, rutaHeredada } from "@/lib/recorrido/motor";
import { esCampoDeTexto } from "@/lib/recorrido/teclas";
import {
  almacen,
  configurarAlmacen,
  despachar,
  useRecorrido,
} from "@/lib/recorridoStore";
import { deleteRecorrido, fetchAuthStatus, getRecorrido, putRecorridoPaso } from "@/lib/session";
import { Foco } from "@/components/recorrido/Foco";
import { DialogoRecorrido } from "@/components/recorrido/MenuRecorrido";
import { TarjetaPaso } from "@/components/recorrido/TarjetaPaso";

const ESPERA_ANCLA_MS = 4000;

function rectDe(nodo: Element): Rect {
  const r = nodo.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

function escribiendo(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el?.tagName) return false;
  return esCampoDeTexto(el.tagName, el.isContentEditable, el.getAttribute("type") ?? undefined);
}

/**
 * El recorrido guiado: navega a la pantalla de cada paso, encuentra su ancla
 * (data-tour), la señala y pone la tarjeta al lado. Escucha rutas, clics y
 * teclas; los eventos del servidor llegan por RecorridoPuente.
 */
export function RecorridoProvider() {
  const estado = useRecorrido();
  const router = useRouter();
  const pathname = usePathname();
  const [rect, setRect] = useState<Rect | null>(null);
  const [ocupada, setOcupada] = useState(false);
  const capitulo = CAPITULOS.find((c) => c.id === estado.capitulo) ?? null;
  const paso = pasoActual(estado, CAPITULOS);
  const clavePaso = estado.activo ? `${estado.capitulo}:${estado.indice}` : "";
  const navegado = useRef("");

  // El progreso vive en la cuenta cuando hay cuentas; si no, en el navegador.
  useEffect(() => {
    let vivo = true;
    void fetchAuthStatus().then(async (status) => {
      const conCuenta = status.mode === "protected" && Boolean(status.user);
      configurarAlmacen(
        conCuenta
          ? { cargar: getRecorrido, guardar: putRecorridoPaso, borrar: deleteRecorrido }
          : null,
      );
      const progreso = await almacen.cargar();
      if (vivo) despachar({ tipo: "progreso", progreso });
    });
    // La obra de ejemplo de esta persona, si ya existe: así un capítulo
    // salteado no la vuelve a crear (ni a procesar).
    void listProjects()
      .then((proyectos) => {
        const obra = proyectos.find((p) => p.project_id.startsWith("obra_de_ejemplo"));
        if (vivo && obra) {
          despachar({ tipo: "obra", projectId: obra.project_id, lista: obra.status === "processed" });
        }
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  // Cada paso nuevo lleva a su pantalla (una vez: si la persona se va, el
  // recorrido no la arrastra de regreso; la tarjeta le ofrece volver).
  useEffect(() => {
    if (!paso || !capitulo || navegado.current === clavePaso) return;
    navegado.current = clavePaso;
    const destino = rutaHeredada(capitulo, estado.indice, estado.projectId);
    if (destino && destino.split("?")[0] !== pathname) router.push(destino);
  }, [clavePaso, paso, capitulo, estado.indice, estado.projectId, pathname, router]);

  useEffect(() => {
    if (pathname) despachar({ tipo: "ruta", pathname });
  }, [pathname]);

  // El ancla: se busca hasta 4 s y luego se sigue su caja mientras el paso dure.
  const ancla = paso?.ancla ?? null;
  useEffect(() => {
    if (!ancla || estado.fueraDeRuta) return;
    let nodo: Element | null = null;
    let cuadro = 0;
    const seguir = () => {
      cancelAnimationFrame(cuadro);
      cuadro = requestAnimationFrame(() => setRect(nodo ? rectDe(nodo) : null));
    };
    const alClic = () => despachar({ tipo: "clic", ancla });
    const tamano = new ResizeObserver(seguir);
    const enganchar = (encontrado: Element) => {
      nodo = encontrado;
      nodo.scrollIntoView({
        block: "center",
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
      });
      nodo.addEventListener("click", alClic, true);
      tamano.observe(nodo);
      seguir();
    };
    const buscar = () => document.querySelector(`[data-tour="${CSS.escape(ancla)}"]`);
    const observador = new MutationObserver(() => {
      const encontrado = buscar();
      if (encontrado && encontrado !== nodo) {
        nodo?.removeEventListener("click", alClic, true);
        enganchar(encontrado);
      } else if (!encontrado && nodo) {
        nodo.removeEventListener("click", alClic, true);
        nodo = null;
        seguir();
      }
    });
    observador.observe(document.body, { childList: true, subtree: true });
    const inicial = buscar();
    if (inicial) enganchar(inicial);
    const espera = window.setTimeout(() => {
      if (!nodo) despachar({ tipo: "ancla_perdida" });
    }, ESPERA_ANCLA_MS);
    window.addEventListener("scroll", seguir, true);
    window.addEventListener("resize", seguir);
    return () => {
      window.clearTimeout(espera);
      cancelAnimationFrame(cuadro);
      observador.disconnect();
      tamano.disconnect();
      nodo?.removeEventListener("click", alClic, true);
      window.removeEventListener("scroll", seguir, true);
      window.removeEventListener("resize", seguir);
      requestAnimationFrame(() => setRect(null));
    };
  }, [ancla, clavePaso, estado.fueraDeRuta]);

  // Esc pausa; ← → sólo mueven pasos «mirar» y nunca mientras se escribe.
  const tipo = paso?.tipo ?? null;
  useEffect(() => {
    if (!estado.activo) return;
    function alTeclear(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey || escribiendo(event.target)) return;
      // La tarjeta de transferencia (sin paso) también avanza con →.
      const conFlechas = tipo === "mirar" || tipo === null;
      if (event.key === "Escape") despachar({ tipo: "pausar" });
      else if (conFlechas && event.key === "ArrowRight") despachar({ tipo: "siguiente" });
      else if (conFlechas && event.key === "ArrowLeft") despachar({ tipo: "atras" });
    }
    document.addEventListener("keydown", alTeclear);
    return () => document.removeEventListener("keydown", alTeclear);
  }, [estado.activo, tipo]);

  async function accion() {
    if (!paso?.accion) return;
    setOcupada(true);
    try {
      if (paso.accion === "crear_obra") {
        const obra = await createDemoProject(getBrowserActor());
        despachar({ tipo: "obra", projectId: obra.project_id, lista: false });
        router.push(`/proyecto/${encodeURIComponent(obra.project_id)}`);
      } else if (estado.projectId) {
        await cargarRevisionB(estado.projectId);
      }
    } catch {
      // La tarjeta sigue: la persona puede reintentar o saltar el paso.
    } finally {
      setOcupada(false);
    }
  }

  function volver() {
    if (!capitulo) return;
    const destino = rutaHeredada(capitulo, estado.indice, estado.projectId);
    if (destino) router.push(destino);
  }

  if (!estado.activo || !capitulo) return <DialogoRecorrido />;
  const ultimo = CAPITULOS[CAPITULOS.length - 1]?.id === capitulo.id;
  return (
    <>
      <DialogoRecorrido />
      {paso && !estado.fueraDeRuta && (
        <Foco rect={estado.anclaPerdida ? null : rect} tipo={estado.repaso ? "mirar" : paso.tipo} />
      )}
      <TarjetaPaso
        capitulo={capitulo}
        paso={paso}
        indice={estado.indice}
        rect={rect}
        repaso={estado.repaso}
        anclaPerdida={estado.anclaPerdida}
        fueraDeRuta={estado.fueraDeRuta}
        ocupada={ocupada}
        esUltimoCapitulo={ultimo}
        onSiguiente={() => despachar({ tipo: "siguiente" })}
        onAtras={() => despachar({ tipo: "atras" })}
        onSaltar={() => despachar({ tipo: "saltar" })}
        onPausar={() => despachar({ tipo: "pausar" })}
        onVolver={volver}
        onAccion={() => void accion()}
      />
    </>
  );
}
