"""El oyente del bus que guarda la actividad de cada proyecto
(``klave_engine.common.actividad``) para medir el piloto."""

from __future__ import annotations

from klave_engine.common.actividad import registrar

# Lo que no es trabajo de una persona sobre el proyecto: quién está viendo
# qué, o los pasos intermedios de un proceso.
IGNORADOS = {"presence_updated", "collaborator_activity", "gate_updated"}


def escucha(control_dir_de):
    """Un oyente del bus que guarda los eventos de cada proyecto.
    ``control_dir_de(project_id)`` da su carpeta ``processed/`` (o None)."""

    def oyente(event) -> None:
        if not event.project_id or event.type in IGNORADOS:
            return
        if event.type == "job_updated" and event.data.get("state") not in (
            "processed", "failed", "running",
        ):
            return
        if event.type == "job_updated" and event.data.get("state") == "running" and \
                str(event.data.get("stage", "")).startswith(("Convirtiendo", "Leyendo")):
            return  # el avance hoja por hoja no es un hito
        control = control_dir_de(event.project_id)
        if control is not None:
            registrar(control, event.type, event.actor, event.data, at=event.ts)

    return oyente
