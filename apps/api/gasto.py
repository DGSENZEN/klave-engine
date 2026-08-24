"""El gasto de IA: registrarlo y frenarlo cuando toca.

Un solo lugar donde se decide si una llamada al proveedor puede ocurrir y
dónde queda anotada, para que ni la lectura de hojas ni el copiloto tengan
que acordarse por su cuenta.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, Request
from klave_engine.common.bitacora import UsoIA, anotar_uso
from klave_engine.common.config import Settings
from klave_engine.llm.tarifas import consumo_del_mes, costo_estimado

from apps.api.tenancy import request_workspace_id


def workspace_de(request: Request | None, settings: Settings) -> str:
    """El taller al que se le cobra este consumo; "taller" en modo abierto."""
    return request_workspace_id(request) or settings.workspace_slug


def revisar_presupuesto(settings: Settings, workspace: str) -> None:
    """Rechaza la llamada cuando el taller ya llegó a su tope del mes.

    Frena en vez de avisar: un tope que solo advierte se ignora, y quien lo
    ignora se entera al llegar la factura."""
    tope = settings.ai_budget_usd
    if not tope or tope <= 0:
        return
    consumo = consumo_del_mes(settings.data_dir, workspace, tope_usd=tope)
    if consumo.excedido:
        raise HTTPException(
            status_code=429,
            detail={
                "error_type": "presupuesto_ia_agotado",
                "message": (
                    f"Este taller lleva ~${consumo.costo_estimado_usd:,.2f} USD "
                    f"estimados de IA este mes y su tope es ${tope:,.2f}. La lectura "
                    "y el copiloto se pausan hasta el mes que entra o hasta que un "
                    "administrador suba el tope (KLAVE_AI_BUDGET_USD)."
                ),
                "gastado_usd": consumo.costo_estimado_usd,
                "tope_usd": tope,
            },
        )


def registrar_uso(
    settings: Settings,
    workspace: str,
    *,
    project_id: str = "",
    modelo: str,
    proveedor: str,
    tipo: str,
    tokens_entrada: int,
    tokens_salida: int,
    actor: str = "",
) -> None:
    """Anota una llamada al proveedor con su costo estimado."""
    anotar_uso(
        settings.data_dir,
        UsoIA(
            ts=datetime.now(UTC).isoformat(),
            workspace=workspace,
            project_id=project_id,
            proveedor=proveedor,
            modelo=modelo,
            tipo=tipo,
            tokens_entrada=int(tokens_entrada or 0),
            tokens_salida=int(tokens_salida or 0),
            costo_estimado_usd=costo_estimado(modelo, tokens_entrada, tokens_salida),
            actor=actor,
        ),
    )
