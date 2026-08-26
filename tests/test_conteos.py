"""Human counts are per-project human data, like reviews — they belong beside
them, not in a repo path a deployed server cannot write. The count that
matters most is for a family the engine never detected: those never appear in
a template generated from detections, and they are the expensive ones."""

from klave_engine.costing.conteos import ConteoHoja, ConteosDeProyecto, load_conteos, save_conteos


def test_counts_round_trip_through_the_project_store(tmp_path):
    conteos = ConteosDeProyecto(
        contado_por="Diego Gaytán",
        hojas=[
            ConteoHoja(hoja="E-02", familia="castillo", dibujados=118, detectados=118),
            ConteoHoja(hoja="E-02", familia="escalera", dibujados=2, detectados=0),
        ],
    )

    save_conteos(tmp_path, conteos)
    again = load_conteos(tmp_path)

    assert again.contado_por == "Diego Gaytán"
    assert len(again.hojas) == 2
    # Not just the count: the row contents themselves, or a swap/duplicate
    # bug in the write-read path would pass the two asserts above unnoticed.
    castillo = next(h for h in again.hojas if h.familia == "castillo")
    assert (castillo.hoja, castillo.dibujados, castillo.detectados) == ("E-02", 118, 118)


def test_a_family_the_engine_never_saw_survives_the_round_trip(tmp_path):
    """If this is lost, the measurement cannot see its own blind spot."""
    save_conteos(
        tmp_path,
        ConteosDeProyecto(
            hojas=[ConteoHoja(hoja="E-02", familia="escalera", dibujados=2, detectados=0)]
        ),
    )

    escalera = next(h for h in load_conteos(tmp_path).hojas if h.familia == "escalera")

    assert escalera.dibujados == 2
    assert escalera.detectados == 0


def test_sheets_fold_into_one_count_per_family(tmp_path):
    """Recall is measured per family across the whole obra; counting happens
    per sheet because that is how a person reads a plan."""
    conteos = ConteosDeProyecto(
        hojas=[
            ConteoHoja(hoja="E-01", familia="castillo", dibujados=60, detectados=58),
            ConteoHoja(hoja="E-02", familia="castillo", dibujados=58, detectados=56),
        ]
    )

    obra = conteos.a_conteo_de_obra("marina")

    castillo = next(c for c in obra.conteos if c.familia == "castillo")
    assert castillo.dibujados == 118


def test_missing_file_is_an_empty_count_not_an_error(tmp_path):
    assert load_conteos(tmp_path).hojas == []


def test_reviewing_a_project_promotes_its_gold_entry_past_baseline(tmp_path):
    """The promotion machinery has been complete since gold.py:293-310 and has
    been waiting for reviews that never came: every detection_reviews.json in
    the repo has zero decisions. This is the assertion that the loop closes —
    a reviewed project stops being a regression guard and starts being truth.

    A prior draft of this test stopped at asserting on ``load_reviews``
    output — a round trip already covered elsewhere — and never called
    ``gold.capture()``, so it could not have failed even if capture() ignored
    reviews entirely. Fixed to call capture() itself, before and after the
    review, so the promotion is what's under test, not just the storage.
    """
    from klave_engine.common.config import get_settings
    from klave_engine.costing.reviews import DetectionReview, ProjectReviews, save_reviews
    from klave_engine.evals.gold import capture

    settings = get_settings()
    control_dir = tmp_path / settings.processed_dir_name
    control_dir.mkdir(parents=True)
    (control_dir / "detections.json").write_text("[]", encoding="utf-8")

    before = capture(tmp_path, "obra-de-prueba", settings)
    assert before.status == "baseline"  # no reviews yet: a regression guard, not truth

    reviews = ProjectReviews()
    reviews.detections["C-1"] = DetectionReview(status="confirmed")
    reviews.detections["C-2"] = DetectionReview(status="excluded")
    save_reviews(control_dir, reviews)

    after = capture(tmp_path, "obra-de-prueba", settings)

    assert after.status == "partial"  # not "verified": no detections sign-off happened
    assert after.confirmed == ["C-1"]
    assert after.excluded == ["C-2"]


def test_the_conteos_endpoints_round_trip_over_http(data_dir, monkeypatch):
    """GET/PUT /projects/{id}/conteos is listed as a 'Produces' interface for
    this task, but none of the brief's four tests reach the API layer at
    all — only the module underneath it. This is the one that does.

    It also stands in for the "must not recompute" constraint: no
    detections.json, cost_report.json or catalog is ever created for this
    project, so if put_conteos tried to recompute, recompute_and_persist
    would either raise or 500 rather than silently succeed — a 200 with the
    saved body back is only possible because it never tries.
    """
    import json as json_module

    from fastapi.testclient import TestClient
    from klave_engine.common import config as config_module

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    client = TestClient(create_app())

    project_id = "obra-conteos-http"
    root = data_dir / "projects" / project_id
    (root / "processed").mkdir(parents=True, exist_ok=True)
    (data_dir / "projects_registry.json").write_text(
        json_module.dumps({project_id: str(root)})
    )

    empty = client.get(f"/projects/{project_id}/conteos")
    assert empty.status_code == 200
    assert empty.json()["hojas"] == []

    payload = {
        "contado_por": "",
        "contado_en": "",
        "hojas": [
            {
                "hoja": "E-02", "familia": "escalera",
                "dibujados": 2, "detectados": 0, "nota": "",
            },
        ],
    }
    put = client.put(
        f"/projects/{project_id}/conteos",
        json=payload,
        # HTTP headers are ASCII; a browser sends the UTF-8 bytes raw and
        # clean_actor() reverses the latin-1 mojibake Starlette produces
        # (apps/api/events.py). Mirror that here instead of an ASCII name,
        # so this test exercises the real header path, accents included.
        headers={"X-Actor": "Diego Gaytán".encode()},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["contado_por"] == "Diego Gaytán"  # filled in from the actor header
    assert body["hojas"][0] == {
        "hoja": "E-02", "familia": "escalera",
        "dibujados": 2, "detectados": 0, "nota": "",
    }

    again = client.get(f"/projects/{project_id}/conteos")
    assert again.json() == body  # what was saved is exactly what comes back
