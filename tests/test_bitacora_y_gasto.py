"""La bitácora local y el freno de gasto: observar sin estorbar, y frenar de
verdad cuando toca."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from klave_engine.common.bitacora import (
    ErrorRegistrado,
    UsoIA,
    anotar_error,
    anotar_uso,
    errores_recientes,
    redactar,
    uso_del_periodo,
)
from klave_engine.llm.tarifas import consumo_del_mes, costo_estimado, estimar_lectura, tarifa_de


def _uso(**kw) -> UsoIA:
    base = dict(
        ts=datetime.now(UTC).isoformat(),
        workspace="taller",
        project_id="obra",
        proveedor="gemini",
        modelo="gemini-3.7-flash",
        tipo="lectura_hoja",
        tokens_entrada=1000,
        tokens_salida=300,
        costo_estimado_usd=0.00105,
    )
    base.update(kw)
    return UsoIA(**base)  # type: ignore[arg-type]


def test_lo_anotado_se_puede_volver_a_leer(tmp_path: Path):
    anotar_uso(tmp_path, _uso())
    anotar_uso(tmp_path, _uso(workspace="otro"))
    hoy = datetime.now(UTC).date()
    todo = uso_del_periodo(tmp_path, hoy, hoy)
    assert len(todo) == 2
    solo_mio = uso_del_periodo(tmp_path, hoy, hoy, workspace="taller")
    assert len(solo_mio) == 1 and solo_mio[0]["project_id"] == "obra"


def test_nunca_se_escribe_una_llave_ni_un_correo():
    """La bitácora vive en la máquina del taller, pero eso no es excusa para
    guardar secretos en texto plano."""
    sucio = (
        "falló con AIzaSyCDoP5l-uvGYTPOIG5AwHijNyLtZqlbRQU y avisamos a "
        "ana@taller.mx con Bearer abc123def456ghi"
    )
    limpio = redactar(sucio)
    assert "AIza" not in limpio and "ana@taller.mx" not in limpio
    assert "Bearer abc123" not in limpio
    assert "falló con" in limpio  # el resto del mensaje sigue siendo útil


def test_un_fallo_al_anotar_no_tumba_a_quien_llama(tmp_path: Path):
    """Observar nunca puede romper lo observado."""
    imposible = tmp_path / "archivo"
    imposible.write_text("no soy carpeta")
    anotar_uso(imposible, _uso())  # no lanza
    anotar_error(
        imposible,
        ErrorRegistrado(
            ts=datetime.now(UTC).isoformat(), request_id="x", ruta="/y",
            metodo="GET", tipo="ValueError", mensaje="algo",
        ),
    )


def test_los_errores_salen_del_mas_reciente_al_mas_viejo(tmp_path: Path):
    ayer = (datetime.now(UTC) - timedelta(hours=20)).isoformat()
    for ts, ruta in ((ayer, "/viejo"), (datetime.now(UTC).isoformat(), "/nuevo")):
        anotar_error(
            tmp_path,
            ErrorRegistrado(
                ts=ts, request_id="r", ruta=ruta, metodo="POST",
                tipo="RuntimeError", mensaje="tronó",
            ),
        )
    filas = errores_recientes(tmp_path)
    assert [f["ruta"] for f in filas] == ["/nuevo", "/viejo"]


def test_el_costo_sale_de_la_tarifa_declarada():
    # 1M de entrada y 1M de salida a la tarifa declarada de gemini-3.7-flash.
    assert costo_estimado("gemini-3.7-flash", 1_000_000, 1_000_000) == pytest.approx(2.80)
    # Un modelo con sufijo hereda la tarifa de su familia.
    assert tarifa_de("claude-haiku-4-5-20251001") is not None


def test_un_modelo_sin_tarifa_cuesta_cero_y_se_cuenta_aparte(tmp_path: Path):
    """Cero significa «no sé», no «es gratis», y la interfaz debe poder
    distinguirlo: por eso el consumo lleva la cuenta de lo no tarifado."""
    assert costo_estimado("modelo-que-nadie-declaró", 500_000, 100_000) == 0.0
    anotar_uso(tmp_path, _uso(modelo="modelo-que-nadie-declaró", costo_estimado_usd=0.0))
    consumo = consumo_del_mes(tmp_path, "taller")
    assert consumo.sin_tarifar == 1
    assert consumo.costo_estimado_usd == 0.0


def test_el_tope_se_alcanza_y_se_reporta(tmp_path: Path):
    for _ in range(3):
        anotar_uso(tmp_path, _uso(costo_estimado_usd=2.0))
    consumo = consumo_del_mes(tmp_path, "taller", tope_usd=5.0)
    assert consumo.costo_estimado_usd == 6.0
    assert consumo.excedido is True
    assert consumo.porcentaje == 120.0

    holgado = consumo_del_mes(tmp_path, "taller", tope_usd=100.0)
    assert holgado.excedido is False and holgado.porcentaje == 6.0

    sin_tope = consumo_del_mes(tmp_path, "taller")
    assert sin_tope.excedido is False and sin_tope.porcentaje is None


def test_se_puede_estimar_una_obra_antes_de_leerla():
    """Antes de gastar, cuánto costaría: 22 hojas como las de Marina."""
    estimado = estimar_lectura(22, "gemini-3.7-flash")
    assert estimado > 0
    assert estimar_lectura(22, "modelo-sin-tarifa") == 0.0
