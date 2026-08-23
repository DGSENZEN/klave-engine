"""Events stay inside their taller: a workspace sees its own projects' events
and its own global events, never another taller's names or members."""

from apps.api.events import EventBus


def test_since_filters_by_workspace_through_projects_and_global_events():
    bus = EventBus()
    bus.publish("project_created", project_id="p-a", data={"name": "Torre A"})
    bus.publish("project_created", project_id="p-b", data={"name": "Casa B"})
    bus.publish("user_pending", data={"user_id": "u1"}, workspace_id="ws-a")
    bus.publish("user_pending", data={"user_id": "u2"}, workspace_id="ws-b")
    bus.publish("catalog_updated", data={"what": "insumo"})  # no workspace: everyone
    bus.publish("run_published", project_id="p-orphan", data={})  # unknown project
    projects = {"p-a": "ws-a", "p-b": "ws-b"}

    seen_a = [(e.type, e.project_id) for e in bus.since(0, None, "ws-a", projects)]
    assert seen_a == [
        ("project_created", "p-a"), ("user_pending", None), ("catalog_updated", None),
    ]
    seen_b = [(e.type, e.project_id) for e in bus.since(0, None, "ws-b", projects)]
    assert ("project_created", "p-a") not in seen_b and ("user_pending", None) in seen_b
    # Open mode (no workspace) still sees everything.
    assert len(bus.since(0)) == 6
    # A project stream of another taller's project yields nothing of it.
    assert bus.since(0, "p-b", "ws-a", projects) == [
        e for e in bus.since(0, "p-b", "ws-a", projects) if e.project_id is None
    ]


def test_user_events_carry_no_email():
    bus = EventBus()
    event = bus.publish("user_joined", data={"user_id": "u1"}, workspace_id="ws-a")
    assert "email" not in event.to_json()["data"]
    assert "workspace_id" not in event.to_json()  # internal routing, not payload
