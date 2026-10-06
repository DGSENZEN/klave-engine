"""La medición del piloto: el tiempo activo cuenta huecos de hasta 10 min y
abre sesión tras una pausa, el proceso se mide por sus trabajos, la entrega
por su primera exportación, cada hoja por sus decisiones, y el ahorro contra
lo que la oficina declara — nunca contra una base inventada."""

import json
from datetime import UTC, datetime, timedelta

from klave_engine.common.actividad import leer, registrar
from klave_engine.costing.piloto import medir, tiempo_activo

T0 = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


def _at(minutos):
    return (T0 + timedelta(minutes=minutos)).isoformat()


def test_tiempo_activo():
    m = [T0 + timedelta(minutes=x) for x in (0, 4, 9, 60, 62)]
    # 1 (primera) + 4 + 5, pausa de 51 → +1 y nueva sesión, + 2
    assert tiempo_activo(m) == (13.0, 2)
    assert tiempo_activo([]) == (0.0, 0)


def test_medir(tmp_path):
    c = tmp_path / "processed"
    registrar(c, "project_created", "Diego", {}, at=_at(0))
    (c / "jobs").mkdir()
    (c / "jobs" / "j1.json").write_text(json.dumps(
        {"state": "processed", "created_at": _at(0), "updated_at": _at(2)}))
    registrar(c, "export", "Diego", {"formato": "opus"}, at=_at(30))
    labels = [{"kind": "deteccion", "key": "K-1", "action": "confirmed", "at": _at(m)}
              for m in (5, 8)] + [{"kind": "deteccion", "key": "Z-1", "action": "excluded",
                                   "at": _at(12)}]
    (c / "labels.jsonl").write_text("\n".join(json.dumps(r) for r in labels))
    (c / "piloto.json").write_text(json.dumps({"horas_metodo_anterior": 6,
                                               "export_importado": True}))
    dets = [{"display_label": "K-1", "evidence": {"source": "/x/E-01.dxf"}},
            {"display_label": "Z-1", "evidence": {"source": "/x/E-02.dxf"}}]
    r = medir(c, dets)
    assert r["procesamiento"] == {"corridas": 1, "ultima_min": 2.0, "total_min": 2.0}
    # momentos humanos: 5, 8, 12, 30 → 1 + 3 + 4, pausa 18 → +1 = 9 min, 2 sesiones
    assert (r["revision"]["minutos_activos"], r["revision"]["sesiones"]) == (9.0, 2)
    assert r["entrega"]["minutos_desde_inicio"] == 30.0 and r["entrega"]["formatos"] == ["opus"]
    hojas = {h["hoja"]: h for h in r["por_hoja"]}
    assert hojas["E-01.dxf"]["decisiones"] == 2 and hojas["E-01.dxf"]["minutos_estimados"] == 6.0
    assert r["metodo_anterior"]["ahorro_horas"] == round(6 - 9 / 60, 2)
    assert r["puerta"]["export_importado"] is True and "10 min" in r["como_se_mide"]


def test_sin_base_no_hay_ahorro(tmp_path):
    r = medir(tmp_path / "processed", [])
    assert r["metodo_anterior"]["ahorro_horas"] is None and r["inicio"] is None


def test_el_bus_guarda_la_actividad_y_las_entregas(data_dir, monkeypatch):
    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.events import BUS
    from apps.api.main import create_app

    config_module.get_settings.cache_clear()
    pid = "obra-piloto"
    root = data_dir / "projects" / pid
    processed = root / "processed"
    processed.mkdir(parents=True)
    (processed / "project_manifest.json").write_text(json.dumps({
        "project_id": pid, "project_name": "Obra", "root_path": str(root), "drawings": []}))
    (data_dir / "projects_registry.json").write_text(json.dumps({pid: str(root)}))
    client = TestClient(create_app())
    BUS.publish("presence_updated", project_id=pid, actor="Ana")  # no se guarda
    BUS.publish("review_updated", project_id=pid, actor="Ana", data={"action": "confirmed",
                                                                     "summary": {"x": 1}})
    tipos = [e["tipo"] for e in leer(processed)]
    assert tipos == ["review_updated"] and "summary" not in leer(processed)[0]["datos"]
    r = client.put(f"/projects/{pid}/piloto", json={"horas_metodo_anterior": 12,
                                                    "generadores_aceptados": True},
                   headers={"X-Actor": "Ana"})
    assert r.status_code == 200, r.text
    body = client.get(f"/projects/{pid}/piloto").json()
    assert body["metodo_anterior"]["horas"] == 12 and body["puerta"]["generadores_aceptados"]
    assert body["revision"]["personas"] == ["Ana"]
