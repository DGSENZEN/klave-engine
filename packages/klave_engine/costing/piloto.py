"""La medición del piloto: cuánto tiempo le tomó a la oficina ir del plano a
los generadores, comparado con las horas que dice que le toma a su modo.

Todo sale de lo que el proyecto ya guarda — la actividad (``actividad.jsonl``),
las decisiones de Revisión con su hora (``labels.jsonl``) y los trabajos de
proceso — y es una **estimación que se dice como tal**: el tiempo activo suma
los huecos de hasta diez minutos entre las acciones de una persona; un hueco
más largo es una pausa y abre otra sesión, que cuenta un minuto por su
primera acción. Klave nunca inventa la base: las horas del método anterior
las declara la oficina."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePath

from klave_engine.common.actividad import leer

PILOTO_FILENAME = "piloto.json"
PAUSA_MIN = 10.0
MINUTO_INICIAL = 1.0
# Lo que hace una persona (no el motor): decidir, ajustar, mapear, entregar.
HUMANOS = {
    "review_updated", "project_updated", "version_saved", "version_restored",
    "catalog_updated", "export", "ajuste_guardado", "convenio_guardado",
    "estimacion_guardada", "finiquito_guardado", "catalogo_convocante", "nota_bitacora",
    "project_shared",
}


def _t(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _minutos(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60.0


def tiempo_activo(momentos: list[datetime]) -> tuple[float, int]:
    """(minutos activos, sesiones) de una lista de momentos."""
    if not momentos:
        return 0.0, 0
    orden = sorted(momentos)
    total, sesiones = MINUTO_INICIAL, 1
    for antes, despues in zip(orden, orden[1:], strict=False):
        hueco = _minutos(antes, despues)
        if hueco <= PAUSA_MIN:
            total += hueco
        else:
            total += MINUTO_INICIAL
            sesiones += 1
    return round(total, 1), sesiones


def _trabajos(control_dir: Path) -> list[dict]:
    out = []
    for path in sorted((control_dir / "jobs").glob("*.json")):
        try:
            out.append(json.loads(path.read_text("utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _labels(control_dir: Path) -> list[dict]:
    path = control_dir / "labels.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text("utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def leer_declarado(control_dir: Path) -> dict:
    path = control_dir / PILOTO_FILENAME
    try:
        return json.loads(path.read_text("utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def medir(control_dir: Path, detections: list[dict] | None = None) -> dict:
    """El informe del piloto de un proyecto."""
    actividad = leer(control_dir)
    labels = _labels(control_dir)
    declarado = leer_declarado(control_dir)

    creado = next((_t(e["at"]) for e in actividad if e["tipo"] == "project_created"), None)
    procesos = []
    for job in _trabajos(control_dir):
        ini, fin = _t(job.get("created_at")), _t(job.get("updated_at"))
        if job.get("state") == "processed" and ini and fin:
            procesos.append(round(_minutos(ini, fin), 1))

    momentos = [t for e in actividad if e["tipo"] in HUMANOS and (t := _t(e.get("at")))]
    momentos += [t for lab in labels if (t := _t(lab.get("at")))]
    activo, sesiones = tiempo_activo(momentos)

    exportes = [e for e in actividad if e["tipo"] == "export"]
    primera = _t(exportes[0]["at"]) if exportes else None
    inicio = creado or (min(momentos) if momentos else None)

    hoja_de: dict[str, str] = {}
    for d in detections or []:
        hoja = PurePath(str((d.get("evidence") or {}).get("source") or "")).name
        for k in (d.get("display_label"), d.get("detection_id")):
            if k:
                hoja_de.setdefault(str(k), hoja)
    decisiones = [lab for lab in labels if lab.get("kind") in ("deteccion", "propuesta", "omitido")]
    por_hoja = Counter(
        hoja_de.get(str(lab.get("key")), "") or PurePath(str(lab.get("sheet") or "")).name
        or "sin hoja"
        for lab in decisiones
    )
    total_decisiones = sum(por_hoja.values())
    hojas = [
        {"hoja": hoja, "decisiones": n,
         "minutos_estimados": round(activo * n / total_decisiones, 1) if total_decisiones else 0}
        for hoja, n in por_hoja.most_common()
    ]
    con_hoja = [h for h in hojas if h["hoja"] != "sin hoja"]

    horas_antes = declarado.get("horas_metodo_anterior")
    horas_klave = round(activo / 60.0, 2)
    return {
        "inicio": inicio.isoformat() if inicio else None,
        "procesamiento": {"corridas": len(procesos),
                          "ultima_min": procesos[-1] if procesos else None,
                          "total_min": round(sum(procesos), 1)},
        "revision": {"minutos_activos": activo, "sesiones": sesiones,
                     "decisiones": total_decisiones, "personas": sorted(
                         {e["actor"] for e in actividad if e.get("actor")}
                         | {str(lab.get("actor")) for lab in labels if lab.get("actor")})},
        "entrega": {
            "primera": primera.isoformat() if primera else None,
            "minutos_desde_inicio": round(_minutos(inicio, primera), 1)
            if inicio and primera else None,
            "formatos": sorted({str(e["datos"].get("formato") or "") for e in exportes} - {""}),
            "exportaciones": len(exportes),
        },
        "por_hoja": hojas,
        "minutos_por_hoja": round(activo / len(con_hoja), 1) if con_hoja else None,
        "metodo_anterior": {
            "horas": horas_antes,
            "horas_klave": horas_klave,
            "ahorro_horas": round(horas_antes - horas_klave, 2)
            if isinstance(horas_antes, (int, float)) else None,
        },
        "puerta": {
            "generadores_aceptados": declarado.get("generadores_aceptados"),
            "export_importado": declarado.get("export_importado"),
            "notas": declarado.get("notas", ""),
        },
        "como_se_mide": (
            f"Tiempo activo: suma de los huecos de hasta {int(PAUSA_MIN)} min entre acciones "
            "de una persona; un hueco mayor es una pausa. Por hoja: el tiempo activo repartido "
            "según sus decisiones. Las horas del método anterior las declara la oficina."
        ),
    }
