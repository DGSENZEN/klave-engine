"use client";

import { useEffect, useRef } from "react";
import { useProjectLive } from "@/components/ProjectLive";
import { obraRecienLista } from "@/lib/recorrido/obra";
import { despachar, senalRecorrido } from "@/lib/recorridoStore";

const SAMPLE_PREFIX = "obra_de_ejemplo";

/** Los eventos del proyecto, al recorrido. Vive dentro de ProjectLiveProvider. */
export function RecorridoPuente() {
  const { latestEvent } = useProjectLive();
  useEffect(() => {
    if (!latestEvent) return;
    despachar({
      tipo: "evento",
      evento: {
        type: latestEvent.type,
        project_id: latestEvent.project_id,
        data: latestEvent.data as Record<string, unknown>,
      },
    });
  }, [latestEvent]);
  return null;
}

/** El estado de la obra de ejemplo, al recorrido: cuál es y si ya está
 * lista. Al terminar de procesarse mientras se mira (la primera vez o tras la
 * Rev B) emite la señal «obra.lista», que es lo que esperan los pasos que la
 * procesan; abrirla ya leída no la emite. */
export function useRecorridoObra(projectId: string, estadoTrabajo: string | null): void {
  const anterior = useRef<string | null>(null);
  useEffect(() => {
    if (!projectId.startsWith(SAMPLE_PREFIX) || estadoTrabajo === null) return;
    despachar({ tipo: "obra", projectId, lista: estadoTrabajo === "processed" });
    if (obraRecienLista(anterior.current, estadoTrabajo)) senalRecorrido("obra.lista");
    anterior.current = estadoTrabajo;
  }, [projectId, estadoTrabajo]);
}
