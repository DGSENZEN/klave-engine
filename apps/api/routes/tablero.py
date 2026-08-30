"""El estado del tablero: una sola lectura barata.

Cada nodo del anteproyecto (planos, revisión, catálogo, presupuesto,
programa, contrato) se compone SOLO de artefactos que ya están en disco —
manifest, parse_summary, cost_report, risk_report, reviews y candados.
Nunca los caminos pesados de recomputo. Un artefacto ausente degrada el
nodo a «pendiente», jamás a un 500: la falla sigue siendo útil.

Cada nodo dice sus hechos como pares etiqueta·valor (un hecho por renglón,
con denominador); el importe respeta el money gate — sin unidad confiable
no viaja ningún peso.
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


def _fact(label: str, value: str | None, tone: str, href: str | None = None) -> dict:
    """href es un fragmento de ruta del proyecto (p.ej. «/lectura»); el
    frontend lo antepone con /proyecto/{id}."""
    fact: dict[str, Any] = {"label": label, "value": value, "tone": tone}
    if href:
        fact["href"] = href
    return fact


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
    rows = [row for row in parse_summary if isinstance(row, dict)]
    coverages = [row.get("coverage") for row in rows]
    legibles = sum(1 for c in coverages if c == "ok")
    con_verdicto = sum(1 for c in coverages if c)
    entidades = sum(int(row.get("entity_count") or 0) for row in rows)
    planos_facts = [_fact("Archivos", f"{sheet_count}", "muted", "/lectura")]
    if con_verdicto:
        tone = "ok" if legibles == con_verdicto else "warn"
        planos_facts.append(
            _fact("Legibles", f"{legibles} de {con_verdicto}", tone, "/lectura")
        )
    if entidades:
        planos_facts.append(_fact("Entidades", f"{entidades:,}", "muted", "/lectura"))
    if status == "failed":
        planos_estado = "atencion"
        planos_facts.append(_fact("Procesamiento", "fallido", "bad"))
    elif status in ("queued", "running"):
        planos_estado = "pendiente"
        planos_facts.append(_fact("Procesamiento", "en curso", "muted"))
    elif not parse_summary:
        planos_estado = "pendiente"
    else:
        planos_estado = "ok" if legibles == con_verdicto else "atencion"

    # --- revisión: la firma humana, paso por paso ---------------------------
    verification = reviews.verification
    units_ok = verification.units_confirmed_at is not None
    pasos = [
        units_ok,
        verification.detections_confirmed_at is not None,
        verification.assumptions_confirmed_at is not None,
    ]
    confirmados = sum(pasos)
    revision_facts = [
        _fact(
            "Verificación",
            f"{confirmados} de 3 pasos",
            "ok" if confirmados == 3 else "warn",
            "/resumen",
        )
    ]
    excluidos = sum(1 for r in reviews.detections.values() if r.status == "excluded")
    if excluidos:
        revision_facts.append(_fact("Excluidas", f"{excluidos}", "muted", "/revision"))
    risk_report = _optional(store, project_id, "risk_report.json")
    if risk_report:
        hallazgos = len(risk_report.get("findings") or [])
        revision_facts.append(
            _fact("Riesgos", f"{hallazgos}", "warn" if hallazgos else "ok", "/riesgos")
        )
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
    financial: dict = {}
    schedule: dict = {}
    if cost_report:
        boq = cost_report.get("boq") or {}
        lines = boq.get("lines") or []
        units_reliable = boq.get("units_reliable")
        integration = cost_report.get("integration") or {}
        grand_total = integration.get("grand_total")
        financial = cost_report.get("financial") or {}
        schedule = cost_report.get("schedule") or {}
    sin_precio = sum(1 for line in lines if line.get("unpriced"))

    if cost_report is None:
        catalogo_estado = "pendiente"
        catalogo_facts = [_fact("Corrida de costos", "sin correr", "muted")]
    else:
        catalogo_estado = "atencion" if sin_precio else "ok"
        catalogo_facts = [
            _fact(
                "Con precio",
                f"{len(lines) - sin_precio} de {len(lines)}",
                "warn" if sin_precio else "ok",
                "/presupuesto",
            )
        ]
        if sin_precio:
            catalogo_facts.append(
                _fact("Sin precio", f"{sin_precio}", "warn", "/presupuesto")
            )

    presupuesto_facts = []
    # El money gate del tablero: sin unidad confiable no viaja ningún peso;
    # con unidad detectada pero sin firma, el importe viaja marcado.
    if units_reliable is False:
        presupuesto_facts.append(_fact("Unidades", "sin confirmar", "warn", "/resumen"))
    elif grand_total is not None:
        presupuesto_facts.append(
            _fact(
                "Total",
                f"${grand_total:,.2f} {cost_report.get('currency', 'MXN')}",
                "ok" if units_ok else "warn",
                "/presupuesto",
            )
        )
        if not units_ok:
            presupuesto_facts.append(
                _fact("Unidades", "sin verificar", "warn", "/resumen")
            )
    if sin_precio:
        presupuesto_facts.append(_fact("Sin precio", f"{sin_precio} líneas", "warn"))
    if cost_report is None:
        presupuesto_estado = "pendiente"
    elif units_reliable is False or sin_precio:
        presupuesto_estado = "atencion"
    else:
        presupuesto_estado = "ok"

    # --- programa y contrato: sus datos siempre visibles, más su candado ----
    programa_facts = []
    if schedule.get("total_duration_days"):
        # total_duration_days son días hábiles (así lo exporta el motor);
        # el calificador viaja con el número, siempre.
        programa_facts.append(
            _fact(
                "Plazo",
                f"{schedule['total_duration_days']} días hábiles",
                "muted",
                "/programa",
            )
        )
    if schedule.get("phases"):
        programa_facts.append(
            _fact("Fases", f"{len(schedule['phases'])}", "muted", "/programa")
        )

    contrato_facts = []
    if financial.get("advance_payment_pct") is not None:
        contrato_facts.append(
            _fact("Anticipo", f"{financial['advance_payment_pct']:.0f} %", "muted", "/contrato")
        )
    if financial.get("retention_pct") is not None:
        contrato_facts.append(
            _fact("Retención", f"{financial['retention_pct']:.0f} %", "muted", "/contrato")
        )
    if financial.get("periods"):
        contrato_facts.append(
            _fact(
                "Estimaciones",
                f"{len(financial['periods'])} periodos",
                "muted",
                "/estimaciones",
            )
        )

    def _gated(node: str, facts: list, requisito_previo: str | None) -> tuple[str, list]:
        """El candado no esconde los datos del nodo: los acompaña con lo que
        falta para abrirlo."""
        if node in gates:
            estado = "ok"
            return estado, facts
        faltan = []
        if confirmados < 3:
            faltan.append(
                _fact("Requisito", f"verificación {confirmados} de 3", "warn", "/resumen")
            )
        if requisito_previo and requisito_previo not in gates:
            faltan.append(_fact("Requisito", f"abrir {requisito_previo}", "warn"))
        return "bloqueado", facts + faltan

    programa_estado, programa_facts = _gated("programa", programa_facts, None)
    contrato_estado, contrato_facts = _gated("contrato", contrato_facts, "programa")

    return {
        "project_id": project_id,
        "my_role": _my_role(request, project_id, settings),
        "gates": gates,
        "nodes": {
            "planos": {"estado": planos_estado, "facts": planos_facts},
            "revision": {"estado": revision_estado, "facts": revision_facts},
            "catalogo": {"estado": catalogo_estado, "facts": catalogo_facts},
            "presupuesto": {"estado": presupuesto_estado, "facts": presupuesto_facts},
            "programa": {"estado": programa_estado, "facts": programa_facts},
            "contrato": {"estado": contrato_estado, "facts": contrato_facts},
        },
    }
