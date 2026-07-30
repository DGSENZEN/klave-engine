"""Real-time collaboration: event bus, SSE stream, and versioned overrides."""

import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.config import Settings
from klave_engine.evals.fixtures import write_demo_project

from apps.api.dependencies import get_settings as api_get_settings
from apps.api.events import (
    BUS,
    PRESENCE,
    EventBus,
    PresenceStore,
    clean_actor,
    clean_client_id,
    clean_location_label,
    clean_location_path,
)
from apps.api.main import create_app
from apps.api.routes.events import _stream_response


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    data_dir = tmp_path_factory.mktemp("collab_data")
    write_demo_project(data_dir / "demo_project_001")
    app = create_app()
    app.dependency_overrides[api_get_settings] = lambda: Settings(data_dir=data_dir)
    return TestClient(app)


@pytest.fixture(scope="module")
def project_id(client: TestClient) -> str:
    root = client.app.dependency_overrides[api_get_settings]().data_dir / "demo_project_001"
    response = client.post("/projects", json={"project_name": "Demo", "root_path": str(root)})
    assert response.status_code == 201, response.text
    pid = response.json()["project_id"]
    assert client.post(f"/projects/{pid}/process").status_code == 202
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = client.get(f"/projects/{pid}/status").json()["state"]
        if state == "processed":
            return pid
        assert state != "failed"
        time.sleep(0.02)
    pytest.fail("processing did not finish")


# --- event bus semantics -------------------------------------------------------


def test_bus_sequences_and_filters() -> None:
    bus = EventBus()
    bus.publish("a", project_id="p1")
    bus.publish("b", project_id="p2")
    global_event = bus.publish("c")  # global (no project)

    assert [e.type for e in bus.since(0)] == ["a", "b", "c"]
    # Project streams see their own events plus global ones.
    assert [e.type for e in bus.since(0, project_id="p1")] == ["a", "c"]
    assert bus.since(global_event.seq) == []
    assert bus.latest_seq() == 3


def test_publish_wakes_subscribers_immediately() -> None:
    """A publish from a worker thread wakes an SSE waiter within a round trip,
    not on a poll interval — this is what makes cross-user sync feel instant."""

    async def scenario() -> float:
        waiter = BUS.subscribe()
        try:
            start = time.monotonic()
            threading.Thread(
                target=lambda: BUS.publish("ping", project_id="wake_test")
            ).start()
            await asyncio.wait_for(waiter.wait(), timeout=1.0)
            return time.monotonic() - start
        finally:
            BUS.unsubscribe(waiter)

    assert asyncio.run(scenario()) < 0.3


def test_bus_history_is_bounded() -> None:
    bus = EventBus()
    bus._events = type(bus._events)(maxlen=5)  # small window for the test
    for i in range(10):
        bus.publish(f"e{i}")
    survivors = bus.since(0)
    assert len(survivors) == 5
    assert survivors[0].type == "e5"  # oldest events evicted, order preserved


def test_clean_actor() -> None:
    assert clean_actor("  Ana   López ") == "Ana López"
    assert clean_actor("x" * 100) == "x" * 40
    assert clean_actor("   ") is None
    assert clean_actor(None) is None
    assert clean_client_id(" browser-1 ") == "browser-1"
    assert clean_client_id("x" * 100) == "x" * 80
    assert clean_location_path("/proyecto/p/parametros") == "/proyecto/p/parametros"
    assert clean_location_path("https://example.com") == ""
    assert clean_location_label("  Parámetros   e Insumos ") == "Parámetros e Insumos"


def test_presence_tracks_multiple_sessions_per_browser() -> None:
    presence = PresenceStore()

    viewers = presence.join(
        "p1",
        "client-a",
        "Ana",
        "s1",
        "/proyecto/p1",
        "Resumen",
    )
    assert viewers[0]["client_id"] == "client-a"
    assert viewers[0]["actor"] == "Ana"
    assert viewers[0]["location_path"] == "/proyecto/p1"
    assert viewers[0]["location_label"] == "Resumen"

    viewers = presence.join(
        "p1",
        "client-a",
        "Ana María",
        "s2",
        "/proyecto/p1/parametros",
        "Parámetros",
    )
    assert len(viewers) == 1
    assert viewers[0]["actor"] == "Ana María"
    assert viewers[0]["location_label"] == "Parámetros"

    assert len(presence.leave("p1", "client-a", "s1")) == 1
    assert presence.leave("p1", "client-a", "s2") == []


# --- SSE stream ----------------------------------------------------------------


def test_events_stream_says_hello_and_replays(client: TestClient) -> None:
    marker = BUS.publish("test_marker", project_id="sse_test")
    assert "/projects/{project_id}/events" in client.get("/openapi.json").json()["paths"]

    class Request:
        headers = {"last-event-id": str(marker.seq - 1)}

        async def is_disconnected(self) -> bool:
            return False

    async def chunks() -> list[str]:
        response = _stream_response(Request(), "sse_test")  # type: ignore[arg-type]
        assert response.media_type == "text/event-stream"
        iterator = response.body_iterator
        first = await anext(iterator)
        second = await anext(iterator)
        await iterator.aclose()
        return [first, second]

    lines = asyncio.run(chunks())
    assert "event: hello" in lines[0]
    assert "test_marker" in lines[1]


def test_project_stream_tracks_presence() -> None:
    class Request:
        headers: dict[str, str] = {}

        async def is_disconnected(self) -> bool:
            return False

    async def chunks() -> list[str]:
        response = _stream_response(  # type: ignore[arg-type]
            Request(),
            "presence_stream",
            "Ana",
            "client-a",
            "/proyecto/presence_stream/parametros",
            "Parámetros",
        )
        iterator = response.body_iterator
        first = await anext(iterator)
        second = await anext(iterator)
        await iterator.aclose()
        return [first, second]

    lines = asyncio.run(chunks())
    assert "event: hello" in lines[0]
    assert '"actor": "Ana"' in lines[0]
    hello_payload = json.loads(
        next(line[6:] for line in lines[0].splitlines() if line.startswith("data: "))
    )
    assert hello_payload["presence"][0]["location_label"] == "Parámetros"
    assert "presence_updated" in lines[1]
    assert PRESENCE.viewers("presence_stream") == []


def test_project_activity_endpoint_publishes_event(client: TestClient, project_id: str) -> None:
    response = client.post(
        f"/projects/{project_id}/activity",
        json={
            "client_id": " client-a ",
            "action": " editing_costing ",
            "label": "  Utilidad (%) ",
            "location_path": f"/proyecto/{project_id}/parametros",
            "location_label": " Parámetros ",
        },
        headers={"X-Actor": "Ana"},
    )

    assert response.status_code == 202, response.text
    event = BUS.since(response.json()["seq"] - 1, project_id=project_id)[0]
    assert event.type == "collaborator_activity"
    assert event.actor == "Ana"
    assert event.data == {
        "client_id": "client-a",
        "action": "editing_costing",
        "label": "Utilidad (%)",
        "location_path": f"/proyecto/{project_id}/parametros",
        "location_label": "Parámetros",
    }


def test_collab_endpoints_reject_unknown_projects(client: TestClient) -> None:
    activity = {"client_id": "c", "action": "editing_costing"}
    assert client.post("/projects/ghost/activity", json=activity).status_code == 404
    assert (
        client.post("/projects/ghost/presence", json={"client_id": "c"}).status_code == 404
    )


def test_activity_rejects_unknown_actions(client: TestClient, project_id: str) -> None:
    response = client.post(
        f"/projects/{project_id}/activity",
        json={"client_id": "c", "action": "rm -rf importantstuff"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_type"] == "unknown_activity_action"


def test_presence_update_moves_viewer_without_reconnect(
    client: TestClient, project_id: str
) -> None:
    # Untracked clients are a no-op, not an error (navigation racing a disconnect).
    response = client.post(
        f"/projects/{project_id}/presence",
        json={"client_id": "client-x", "location_label": "Presupuesto"},
    )
    assert response.status_code == 202
    assert response.json() == {"tracked": False}

    PRESENCE.join(project_id, "client-x", "Ana", "s1", f"/proyecto/{project_id}", "Resumen")
    try:
        response = client.post(
            f"/projects/{project_id}/presence",
            json={
                "client_id": "client-x",
                "location_path": f"/proyecto/{project_id}/presupuesto",
                "location_label": "Presupuesto",
            },
            headers={"X-Actor": "Ana"},
        )
        assert response.status_code == 202
        assert response.json() == {"tracked": True}
        viewer = PRESENCE.viewers(project_id)[0]
        assert viewer["location_label"] == "Presupuesto"
        event = BUS.since(0, project_id=project_id)[-1]
        assert event.type == "presence_updated"
        assert event.data["viewers"][0]["location_label"] == "Presupuesto"
    finally:
        PRESENCE.leave(project_id, "client-x", "s1")


def test_global_stream_filters_to_lifecycle_events() -> None:
    from apps.api.routes.events import GLOBAL_STREAM_EVENT_TYPES

    marker = BUS.publish("costing_updated", project_id="filter_test")
    BUS.publish("run_published", project_id="filter_test")

    class Request:
        headers = {"last-event-id": str(marker.seq - 1)}

        async def is_disconnected(self) -> bool:
            return False

    async def chunks() -> list[str]:
        response = _stream_response(  # type: ignore[arg-type]
            Request(), event_types=GLOBAL_STREAM_EVENT_TYPES
        )
        iterator = response.body_iterator
        first = await anext(iterator)
        second = await anext(iterator)
        await iterator.aclose()
        return [first, second]

    lines = asyncio.run(chunks())
    assert "event: hello" in lines[0]
    assert "run_published" in lines[1]
    assert "costing_updated" not in lines[1]


# --- versioned overrides (optimistic concurrency) ------------------------------


def test_recompute_version_conflict_flow(client: TestClient, project_id: str) -> None:
    # First save on top of version 0 succeeds and is attributed.
    first = client.post(
        f"/projects/{project_id}/recompute",
        json={"insumo_prices": {"MAT-ACERO": 30000.0}, "version": 0},
        headers={"X-Actor": "Ana", "X-Client-Id": "browser-a"},
    )
    assert first.status_code == 200, first.text

    config = client.get(f"/projects/{project_id}/costing-config").json()
    assert config["version"] == 1
    assert config["updated_by"] == "Ana"

    # A collaborator still holding version 0 must get a 409, not overwrite.
    stale = client.post(
        f"/projects/{project_id}/recompute",
        json={"insumo_prices": {}, "version": 0},
        headers={"X-Actor": "Beto"},
    )
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["error_type"] == "version_conflict"
    assert detail["current_version"] == 1
    assert detail["updated_by"] == "Ana"

    # After reloading (version 1) the save goes through.
    fresh = client.post(
        f"/projects/{project_id}/recompute",
        json={"insumo_prices": {}, "version": 1},
        headers={"X-Actor": "Beto"},
    )
    assert fresh.status_code == 200
    assert client.get(f"/projects/{project_id}/costing-config").json()["version"] == 2

    # The saves were broadcast with attribution for other clients.
    costing_events = [
        e for e in BUS.since(0, project_id=project_id) if e.type == "costing_updated"
    ]
    assert [e.actor for e in costing_events] == ["Ana", "Beto"]
    assert costing_events[0].data["client_id"] == "browser-a"


def test_processing_publishes_job_events(client: TestClient, project_id: str) -> None:
    events = BUS.since(0, project_id=project_id)
    states = [e.data.get("state") for e in events if e.type == "job_updated"]
    assert "processed" in states
    assert any(e.type == "run_published" for e in events)
