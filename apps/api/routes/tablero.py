"""El estado del tablero: una sola lectura barata.

Cada nodo del anteproyecto (planos, revisión, catálogo, presupuesto,
programa, contrato) se compone SOLO de artefactos que ya están en disco —
manifest, parse_summary, cost_report, risk_report, reviews y candados.
Nunca los caminos pesados de recomputo. Un artefacto ausente degrada el
nodo a «pendiente», jamás a un 500: la falla sigue siendo útil.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from klave_engine.common.config import Settings
from klave_engine.costing.reviews import GATED_NODES, load_reviews

from apps.api.dependencies import ProjectStore, get_settings, get_store
from apps.api.jobs import JOB_STORE

router = APIRouter(prefix="/projects")


def _optional(store: ProjectStore, project_id: str, name: str) -> Any:
    try:
        return store.read_artifact(project_id, name)
    except HTTPException:
        return None


def _chip(label: str, tone: str, href: str | None = None) -> dict:
    """href es un fragmento de ruta del proyecto (p.ej. «/lectura»); el
    frontend lo antepone con /proyecto/{id}."""
    chip: dict[str, Any] = {"label": label, "tone": tone}
    if href:
        chip["href"] = href
    return chip


def _my_role(request: Request, project_id: str, settings: Settings) -> str | None:
    """El rol del que mira: admin del taller, o su rol en el proyecto.

    En modo abierto no hay cuentas y el rol es None — el frontend lo lee
    como «todos pueden», la misma libertad local-first de siempre."""
    user = getattr(request.state, "user", None)
    if user is None:
        return None
    if user.get("role") == "admin":
        return "admin"
    try:
        from apps.api.auth.store import get_user_store

        users = get_user_store(settings.users_database_url)
        return users.project_role(project_id, str(user["user_id"]))
    except Exception:  # noqa: BLE001 — sin base de usuarios, sin veredicto
        return None


@router.get("/{project_id}/tablero")
def get_tablero(
    project_id: str,
    request: Request,
    store: ProjectStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    root = store.get_root(project_id)
    control_dir = root / settings.processed_dir_name
    reviews = load_reviews(control_dir)
    gates = {
        node: {
            "approved_at": state.approved_at.isoformat() if state.approved_at else None,
            "approved_by": state.approved_by,
        }
        for node, state in reviews.gates.items()
        if node in GATED_NODES
    }

    # --- planos: qué se leyó y qué tan completo -----------------------------
    status = "unknown"
    sheet_count = 0
    try:
        manifest = store.get_manifest(project_id)
        status = manifest.processing_status.value
        sheet_count = len(manifest.source_files)
    except Exception:  # noqa: BLE001 — sin manifest el nodo queda pendiente
        pass
    job = JOB_STORE.get(project_id, root, settings)
    if job is not None and job.state in ("queued", "running", "failed"):
        status = job.state

    parse_summary = _optional(store, project_id, "parse_summary.json") or []
    coverages = [row.get("coverage") for row in parse_summary if isinstance(row, dict)]
    legibles = sum(1 for c in coverages if c == "ok")
    con_verdicto = sum(1 for c in coverages if c)
    planos_chips = [_chip(f"{sheet_count} archivos", "muted", "/lectura")]
    if con_verdicto:
        tone = "ok" if legibles == con_verdicto else "warn"
        planos_chips.append(
            _chip(f"{legibles} de {con_verdicto} legibles", tone, "/lectura")
        )
    if status == "failed":
        planos_estado = "atencion"
        planos_chips.append(_chip("procesamiento fallido", "bad"))
    elif status in ("queued", "running"):
        planos_estado = "pendiente"
        planos_chips.append(_chip("procesando…", "muted"))
    elif not parse_summary:
        planos_estado = "pendiente"
    else:
        planos_estado = "ok" if legibles == con_verdicto else "atencion"

    # --- revisión: la firma humana, paso por paso ---------------------------
    verification = reviews.verification
    pasos = [
        verification.units_confirmed_at is not None,
        verification.detections_confirmed_at is not None,
        verification.assumptions_confirmed_at is not None,
    ]
    confirmados = sum(pasos)
    revision_chips = [
        _chip(f"{confirmados} de 3 pasos", "ok" if confirmados == 3 else "warn",
              "/resumen")
    ]
    excluidos = sum(1 for r in reviews.detections.values() if r.status == "excluded")
    if excluidos:
        revision_chips.append(_chip(f"{excluidos} excluidas", "muted", "/revision"))
    risk_report = _optional(store, project_id, "risk_report.json")
    if risk_report:
        hallazgos = len(risk_report.get("findings") or [])
        if hallazgos:
            revision_chips.append(_chip(f"{hallazgos} riesgos", "warn", "/riesgos"))
    if not parse_summary:
        revision_estado = "pendiente"
    elif confirmados == 3:
        revision_estado = "ok"
    else:
        revision_estado = "atencion" if confirmados else "pendiente"

    # --- catálogo y presupuesto: el dinero con sus huecos a la vista --------
    cost_report = _optional(store, project_id, "cost_report.json")
    lines: list[dict] = []
    grand_total = None
    units_reliable = None
    if cost_report:
        boq = cost_report.get("boq") or {}
        lines = boq.get("lines") or []
        units_reliable = boq.get("units_reliable")
        integration = cost_report.get("integration") or {}
        grand_total = integration.get("grand_total")
    sin_precio = sum(1 for line in lines if line.get("unpriced"))

    if cost_report is None:
        catalogo_estado = "pendiente"
        catalogo_chips = [_chip("sin corrida de costos", "muted")]
    elif sin_precio:
        catalogo_estado = "atencion"
        catalogo_chips = [
            _chip(f"{sin_precio} de {len(lines)} sin precio", "warn", "/presupuesto")
        ]
    else:
        catalogo_estado = "ok"
        catalogo_chips = [
            _chip(f"{len(lines)} conceptos con precio", "ok", "/presupuesto")
        ]

    presupuesto_chips = []
    if grand_total is not None:
        presupuesto_chips.append(
            _chip(f"${grand_total:,.2f} {cost_report.get('currency', 'MXN')}",
                  "ok" if units_reliable else "warn", "/presupuesto")
        )
    if units_reliable is False:
        presupuesto_chips.append(_chip("unidades sin confirmar", "warn", "/resumen"))
    if sin_precio:
        presupuesto_chips.append(_chip(f"{sin_precio} líneas sin precio", "warn"))
    if cost_report is None:
        presupuesto_estado = "pendiente"
    elif units_reliable is False or sin_precio:
        presupuesto_estado = "atencion"
    else:
        presupuesto_estado = "ok"

    # --- programa y contrato: los nodos con candado -------------------------
    def _gated(node: str, listo: str, requisito_previo: str | None) -> tuple[str, list]:
        chips = []
        if node in gates:
            chips.append(_chip(f"abierto por {gates[node]['approved_by'] or '—'}", "ok"))
            return listo, chips
        faltan = []
        if confirmados < 3:
            faltan.append(f"verificación {confirmados} de 3")
        if requisito_previo and requisito_previo not in gates:
            faltan.append(f"requiere abrir {requisito_previo}")
        chips.append(_chip("con candado", "muted"))
        for falta in faltan:
            chips.append(_chip(falta, "warn"))
        return "bloqueado", chips

    programa_estado, programa_chips = _gated("programa", "ok", None)
    contrato_estado, contrato_chips = _gated("contrato", "ok", "programa")

    return {
        "project_id": project_id,
        "my_role": _my_role(request, project_id, settings),
        "gates": gates,
        "nodes": {
            "planos": {"estado": planos_estado, "chips": planos_chips},
            "revision": {"estado": revision_estado, "chips": revision_chips},
            "catalogo": {"estado": catalogo_estado, "chips": catalogo_chips},
            "presupuesto": {"estado": presupuesto_estado, "chips": presupuesto_chips},
            "programa": {"estado": programa_estado, "chips": programa_chips},
            "contrato": {"estado": contrato_estado, "chips": contrato_chips},
        },
    }
