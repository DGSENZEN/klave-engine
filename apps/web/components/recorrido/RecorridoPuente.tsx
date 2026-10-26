"use client";

import { useEffect } from "react";
import { useProjectLive } from "@/components/ProjectLive";
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
 * lista. Al terminar de procesarse (la primera vez o tras la Rev B) emite la
 * señal «obra.lista», que es lo que esperan los pasos que la procesan. */
export function useRecorridoObra(projectId: string, estadoTrabajo: string | null): void {
  useEffect(() => {
    if (!projectId.startsWith(SAMPLE_PREFIX) || estadoTrabajo === null) return;
    const lista = estadoTrabajo === "processed";
    despachar({ tipo: "obra", projectId, lista });
    if (lista) senalRecorrido("obra.lista");
  }, [projectId, estadoTrabajo]);
}
