"""Reemplazar o retirar una hoja: la revisión C sustituye a la B, nunca se suma
a ella. La hoja vieja se guarda aparte, la conversión vieja no se reusa, y
agregar una hoja con un número que ya está se detiene a preguntar."""

import asyncio
import os
import time
from io import BytesIO

import pytest
from fastapi import HTTPException, Request, UploadFile
from klave_engine.common.config import Settings
from klave_engine.ingestion.manifest import load_manifest
from klave_engine.ingestion.project_loader import clave_de_hoja, ingest_project

from apps.api import jobs as jobs_module
from apps.api.dependencies import ProjectStore
from apps.api.routes import projects

DWG_B = b"AC1032" + b"B" * 64
DWG_C = b"AC1032" + b"C" * 64
DXF = b"  0\nSECTION\n  2\nENTITIES\n  0\nENDSEC\n  0\nEOF\n"


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [
        ("01-s-101.dxf", "S-101"),
        ("02-es-200-rev-c.dwg", "ES-200"),
        ("S-101 Rev B.dxf", "S-101"),
        ("03-plano_cimentacion_rev2.dxf", "plano_cimentacion"),
        ("04-plano-cimentacion-v3.dwg", "plano-cimentacion"),
        ("01-02_estructural_l_04_-_26_01_15.dwg", "02_estructural_l_04_-_26_01_15"),
    ],
)
def test_sheet_key_ignores_order_prefix_and_revision(nombre, clave):
    assert clave_de_hoja(nombre) == clave


def _proyecto(data_dir, *hojas: tuple[str, bytes]):
    settings = Settings(data_dir=data_dir)
    store = ProjectStore(settings)
    root = data_dir / "uploads" / "obra"
    drawings = root / "drawings"
    drawings.mkdir(parents=True)
    for nombre, contenido in hojas:
        (drawings / nombre).write_bytes(contenido)
    ingest_project(root, project_id="obra")
    store.register("obra", root)
    return settings, store, root, drawings


def _encolar(monkeypatch):
    llamadas = []
    fake = jobs_module.Job(project_id="obra", job_id="j", run_id="r")

    def enqueue(project_id, *_a, **_k):
        llamadas.append(project_id)
        return fake, True

    monkeypatch.setattr(projects.JOB_STORE, "enqueue", enqueue)
    return llamadas


def _upload(nombre: str, contenido: bytes) -> UploadFile:
    return UploadFile(filename=nombre, file=BytesIO(contenido))


def test_a_converted_dxf_older_than_its_dwg_is_not_reused(data_dir):
    _, _, root, drawings = _proyecto(data_dir, ("01-s-101.dwg", DWG_B))
    manifest = load_manifest(root)
    file_id = manifest.source_files[0].file_id
    converted = root / "converted" / file_id / "01-s-101.dxf"
    converted.parent.mkdir(parents=True)
    converted.write_bytes(DXF)
    assert ingest_project(root, project_id="obra").converted_files  # newer: reused
    # The DWG changes after its conversion: the old DXF is somebody else's drawing.
    older = time.time() - 60
    os.utime(converted, (older, older))
    (drawings / "01-s-101.dwg").write_bytes(DWG_C)
    assert ingest_project(root, project_id="obra").converted_files == []


def test_replacing_a_sheet_keeps_its_name_and_sets_the_old_one_aside(data_dir, monkeypatch):
    settings, store, root, drawings = _proyecto(
        data_dir, ("01-s-101.dwg", DWG_B), ("02-s-102.dxf", DXF)
    )
    file_id = load_manifest(root).source_files[0].file_id
    stale = root / "converted" / file_id / "01-s-101.dxf"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(DXF)
    encolados = _encolar(monkeypatch)

    result = asyncio.run(projects.replace_project_file(
        "obra", "01-s-101.dwg", Request({"type": "http"}), _upload("S-101 rev C.dwg", DWG_C),
        store=store, settings=settings,
    ))

    assert (drawings / "01-s-101.dwg").read_bytes() == DWG_C
    retiradas = list((drawings / "retiradas").rglob("01-s-101.dwg"))
    assert len(retiradas) == 1 and retiradas[0].read_bytes() == DWG_B
    assert not stale.exists()
    sheets = [f.path for f in load_manifest(root).source_files]
    assert sheets == ["drawings/01-s-101.dwg", "drawings/02-s-102.dxf"]
    assert encolados == ["obra"] and result["reemplazada"] == "01-s-101.dwg"


def test_a_dwg_replaced_by_a_dxf_keeps_the_sheet_stem(data_dir, monkeypatch):
    settings, store, root, drawings = _proyecto(data_dir, ("01-s-101.dwg", DWG_B))
    _encolar(monkeypatch)
    asyncio.run(projects.replace_project_file(
        "obra", "01-s-101.dwg", Request({"type": "http"}), _upload("S-101.dxf", DXF),
        store=store, settings=settings,
    ))
    assert sorted(p.name for p in drawings.iterdir() if p.is_file()) == ["01-s-101.dxf"]


@pytest.mark.parametrize(("nombre", "status"), [("99-no-existe.dxf", 404), ("../obra.dxf", 400)])
def test_replacing_needs_an_existing_sheet_name(data_dir, monkeypatch, nombre, status):
    settings, store, _, drawings = _proyecto(data_dir, ("01-s-101.dxf", DXF))
    _encolar(monkeypatch)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(projects.replace_project_file(
            "obra", nombre, Request({"type": "http"}), _upload("S-101.dxf", DXF),
            store=store, settings=settings,
        ))
    assert caught.value.status_code == status
    assert [p.name for p in drawings.iterdir()] == ["01-s-101.dxf"]


def test_a_failed_replacement_puts_the_old_sheet_back(data_dir, monkeypatch):
    settings, store, root, drawings = _proyecto(data_dir, ("01-s-101.dwg", DWG_B))
    _encolar(monkeypatch)

    def falla(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(projects, "ingest_project", falla)
    with pytest.raises(OSError):
        asyncio.run(projects.replace_project_file(
            "obra", "01-s-101.dwg", Request({"type": "http"}), _upload("S-101.dwg", DWG_C),
            store=store, settings=settings,
        ))
    assert (drawings / "01-s-101.dwg").read_bytes() == DWG_B
    assert not list(drawings.glob("retiradas/**/*.dwg"))


def test_retiring_a_sheet_sets_it_aside_and_reprocesses(data_dir, monkeypatch):
    settings, store, root, drawings = _proyecto(
        data_dir, ("01-s-101.dxf", DXF), ("02-s-102.dxf", DXF)
    )
    encolados = _encolar(monkeypatch)
    result = projects.retire_project_file(
        "obra", "02-s-102.dxf", Request({"type": "http"}), store=store, settings=settings
    )
    assert [f.path for f in load_manifest(root).source_files] == ["drawings/01-s-101.dxf"]
    assert list((drawings / "retiradas").rglob("02-s-102.dxf"))
    assert encolados == ["obra"] and result["sheet_count"] == 1


def test_the_last_sheet_cannot_be_retired(data_dir, monkeypatch):
    settings, store, _, drawings = _proyecto(data_dir, ("01-s-101.dxf", DXF))
    _encolar(monkeypatch)
    with pytest.raises(HTTPException) as caught:
        projects.retire_project_file(
            "obra", "01-s-101.dxf", Request({"type": "http"}), store=store, settings=settings
        )
    assert caught.value.status_code == 409
    assert (drawings / "01-s-101.dxf").exists()


def test_adding_a_sheet_number_that_is_already_there_asks_first(data_dir, monkeypatch):
    settings, store, root, drawings = _proyecto(data_dir, ("01-s-101.dxf", DXF))
    encolados = _encolar(monkeypatch)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(projects.add_project_files(
            "obra", Request({"type": "http"}),
            [_upload("S-101 rev C.dxf", DXF), _upload("S-102.dxf", DXF)],
            store=store, settings=settings,
        ))
    assert caught.value.status_code == 409
    detail = caught.value.detail
    assert detail["error_type"] == "hoja_repetida"
    assert detail["repetidas"] == [{"nueva": "S-101 rev C.dxf", "existente": "01-s-101.dxf"}]
    assert [p.name for p in drawings.iterdir()] == ["01-s-101.dxf"] and encolados == []

    asyncio.run(projects.add_project_files(
        "obra", Request({"type": "http"}), [_upload("S-101 rev C.dxf", DXF)],
        repetidas="agregar", store=store, settings=settings,
    ))
    assert len(load_manifest(root).source_files) == 2


def test_adding_can_replace_the_repeated_sheets_and_add_the_rest_in_one_go(
    data_dir, monkeypatch
):
    settings, store, root, drawings = _proyecto(data_dir, ("01-s-101.dwg", DWG_B))
    encolados = _encolar(monkeypatch)
    asyncio.run(projects.add_project_files(
        "obra", Request({"type": "http"}),
        [_upload("S-101 rev C.dwg", DWG_C), _upload("S-102.dxf", DXF)],
        repetidas="reemplazar", store=store, settings=settings,
    ))
    sheets = [f.path for f in load_manifest(root).source_files]
    assert sheets == ["drawings/01-s-101.dwg", "drawings/02-s-102.dxf"]
    assert (drawings / "01-s-101.dwg").read_bytes() == DWG_C
    assert list(drawings.glob("retiradas/*/01-s-101.dwg"))
    assert encolados == ["obra"]  # one change, one reprocess


def test_the_drawing_set_does_not_change_while_it_is_being_read(data_dir, monkeypatch):
    # Un trabajo activo ya leyó (o está leyendo) las hojas: un cambio a media
    # lectura se perdería, porque el reproceso devuelve el trabajo en curso.
    settings, store, root, drawings = _proyecto(
        data_dir, ("01-s-101.dxf", DXF), ("02-s-102.dxf", DXF)
    )
    activo = jobs_module.Job(project_id="obra", job_id="j", run_id="r", state="running")
    monkeypatch.setattr(projects.JOB_STORE, "get", lambda *_a, **_k: activo)
    llamadas = [
        lambda: projects.retire_project_file(
            "obra", "02-s-102.dxf", Request({"type": "http"}), store=store, settings=settings
        ),
        lambda: asyncio.run(projects.replace_project_file(
            "obra", "01-s-101.dxf", Request({"type": "http"}), _upload("S-101.dxf", DXF),
            store=store, settings=settings,
        )),
        lambda: asyncio.run(projects.add_project_files(
            "obra", Request({"type": "http"}), [_upload("S-103.dxf", DXF)],
            store=store, settings=settings,
        )),
    ]
    for llamada in llamadas:
        with pytest.raises(HTTPException) as caught:
            llamada()
        assert caught.value.status_code == 409
        assert caught.value.detail["error_type"] == "processing_in_progress"
    assert sorted(p.name for p in drawings.iterdir()) == ["01-s-101.dxf", "02-s-102.dxf"]


def test_cambios_pairs_a_renamed_revision_by_its_sheet_number():
    from klave_engine.costing.cambios import comparar_elementos
    from klave_engine.detection.results import Detection, DetectionType
    from klave_engine.graph.evidence import EvidencePacket

    def columna(fuente: str, x: float) -> Detection:
        return Detection(
            detection_id=f"{fuente}-{x}", detection_type=DetectionType.column_tag,
            label="C-1", bbox=(x, 0.0, x + 0.3, 0.3), confidence=0.9,
            evidence=EvidencePacket(source=fuente, method="test"), mark="C-1",
        )

    antes = [columna("drawings/01-s-101-rev-b.dxf", 1.0), columna("drawings/02-s-102.dxf", 1.0)]
    despues = [columna("drawings/03-s-101-rev-c.dxf", 1.0), columna("drawings/02-s-102.dxf", 1.0)]
    assert comparar_elementos(antes, despues, 1.0, 1.0) == []
