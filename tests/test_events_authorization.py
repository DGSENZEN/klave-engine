"""SSE attribution and project access stay bound to the authenticated viewer."""

import asyncio
import json
from dataclasses import dataclass, field

import pytest
from starlette.requests import Request

from apps.api.auth.store import UsersDbUnavailable
from apps.api.events import EventBus, PresenceStore
from apps.api.routes import events


@dataclass
class EventUsers:
    workspaces: dict[str, str] = field(
        default_factory=lambda: {"private": "ws-a", "shared": "ws-a", "other": "ws-b"}
    )
    roles: dict[str, str] = field(
        default_factory=lambda: {"shared": "viewer", "legacy": "viewer", "other": "viewer"}
    )
    sessions: dict[str, dict] = field(
        default_factory=lambda: {"member-session": viewer(), "admin-session": viewer("admin")}
    )
    unavailable: bool = False

    def check_available(self):
        if self.unavailable:
            raise UsersDbUnavailable("unavailable")

    def project_workspace_map(self):
        self.check_available()
        return dict(self.workspaces)

    def project_workspace_id(self, project_id):
        self.check_available()
        # Pre-workspace projects belong to the default workspace.
        return self.workspaces.get(project_id, "ws-a")

    def project_ids_for_user(self, user_id):
        self.check_available()
        return set(self.roles) if user_id == "u1" else set()

    def project_role(self, project_id, user_id):
        self.check_available()
        return self.roles.get(project_id) if user_id == "u1" else None

    def get_session_user(self, token):
        self.check_available()
        user = self.sessions.get(token)
        return dict(user) if user else None


def viewer(role="member"):
    return {
        "user_id": "u1",
        "workspace_id": "ws-a",
        "name": "Ana",
        "email": "ana@example.test",
        "picture": None,
        "role": role,
        "status": "active",
    }


def stream_request(user, *, polls_before_disconnect=2):
    polls = 0

    async def receive():
        nonlocal polls
        polls += 1
        if polls > polls_before_disconnect:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": b"", "more_body": False}

    headers = [(b"last-event-id", b"0")]
    if user is not None:
        headers.append((b"cookie", f"klave_session={user['role']}-session".encode()))
    request = Request({"type": "http", "headers": headers}, receive)
    request.state.user = user
    return request


def payload(frame):
    return json.loads(frame.split("data: ", 1)[1])


def delivered(frames):
    return [payload(frame) for frame in frames if frame.startswith("id:")]


@pytest.fixture
def live(monkeypatch):
    bus, presence, users = EventBus(), PresenceStore(), EventUsers()
    monkeypatch.setattr(events, "BUS", bus)
    monkeypatch.setattr(events, "PRESENCE", presence)
    monkeypatch.setattr(events, "get_users", lambda: users)
    monkeypatch.setattr(events, "DISCONNECT_POLL_SECONDS", 0.001)
    return bus, presence, users


@pytest.mark.parametrize(
    "user,expected_actor", [(None, "Forged"), (dict(viewer(), name="Cached name"), "Ana")]
)
def test_presence_uses_session_name_in_protected_mode(live, user, expected_actor):
    bus, presence, _users = live

    async def join():
        response = events._stream_response(
            stream_request(user), project_id="shared", actor="Forged", client_id="tab-1"
        )
        iterator = response.body_iterator
        try:
            hello = payload(await anext(iterator))
            assert hello["presence"][0]["actor"] == expected_actor
            assert presence.viewers("shared")[0]["actor"] == expected_actor
        finally:
            await iterator.aclose()

    asyncio.run(join())
    assert [event.actor for event in bus.since(0)] == [expected_actor, expected_actor]


@pytest.mark.parametrize(
    "user,expected_projects",
    [
        (viewer(), ["shared", "legacy"]),
        (viewer("admin"), ["private", "shared", "legacy"]),
        (None, ["private", "shared", "other", "legacy"]),
    ],
)
def test_global_stream_respects_current_project_grants_and_workspace(live, user, expected_projects):
    bus, _presence, _users = live
    for project_id in ("private", "shared", "other", "legacy"):
        bus.publish("project_updated", project_id=project_id, data={"name": project_id})

    async def collect():
        response = await events.events_stream(stream_request(user))
        return [frame async for frame in response.body_iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert [event["project_id"] for event in delivered(frames)] == expected_projects


@pytest.mark.parametrize("scope", ["shared", None])
@pytest.mark.parametrize("buffered", [False, True])
def test_stream_stops_delivering_project_events_after_grant_revocation(live, scope, buffered):
    bus, _presence, users = live
    bus.publish("project_updated", project_id="shared", data={"name": "Before"})
    if buffered:
        bus.publish("project_updated", project_id="shared", data={"name": "Buffered secret"})

    async def collect():
        iterator = events._stream_response(stream_request(viewer()), project_id=scope).body_iterator
        await anext(iterator)  # hello
        first = payload(await anext(iterator))
        assert first["data"] == {"name": "Before"}
        users.roles.pop("shared")
        bus.publish("project_updated", project_id="shared", data={"name": "Secret after revoke"})
        return [frame async for frame in iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert delivered(frames) == []


@pytest.mark.parametrize("scope", ["shared", None])
@pytest.mark.parametrize("buffered", [False, True])
def test_authenticated_stream_fails_closed_when_users_database_becomes_unavailable(
    live, scope, buffered
):
    bus, _presence, users = live
    bus.publish("project_updated", project_id="shared")
    if buffered:
        bus.publish("project_updated", project_id="shared", data={"name": "Buffered secret"})

    async def collect():
        iterator = events._stream_response(stream_request(viewer()), project_id=scope).body_iterator
        await anext(iterator)  # hello
        await anext(iterator)  # authorized event
        users.unavailable = True
        bus.publish("project_updated", project_id="shared", data={"name": "Unavailable"})
        return [frame async for frame in iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert delivered(frames) == []


@pytest.mark.parametrize("denial", ["revoked", "unavailable", "wrong_workspace"])
def test_unauthorized_project_access_cannot_join_presence_or_receive_hello(live, denial):
    bus, presence, users = live
    if denial == "revoked":
        users.roles.pop("shared")
    elif denial == "unavailable":
        users.unavailable = True
    else:
        users.workspaces["shared"] = "ws-b"

    async def collect():
        response = events._stream_response(
            stream_request(viewer()), project_id="shared", actor="Forged", client_id="tab-1"
        )
        return [frame async for frame in response.body_iterator]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=1)) == []
    assert presence.viewers("shared") == []
    assert bus.since(0) == []


@pytest.mark.parametrize(
    "user,project_id",
    [
        (viewer(), "shared"), (viewer(), "legacy"),
        (viewer("admin"), "private"), (viewer("admin"), "legacy"),
    ],
)
def test_project_stream_preserves_member_grants_and_admin_legacy_access(live, user, project_id):
    bus, _presence, _users = live
    bus.publish("project_updated", project_id=project_id, data={"name": "Allowed"})

    async def collect():
        response = events._stream_response(stream_request(user), project_id=project_id)
        return [frame async for frame in response.body_iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert [event["data"] for event in delivered(frames)] == [{"name": "Allowed"}]


def test_revoked_stream_removes_its_presence(live):
    bus, presence, users = live

    async def collect():
        iterator = events._stream_response(
            stream_request(viewer()), project_id="shared", client_id="tab-1"
        ).body_iterator
        hello = payload(await anext(iterator))
        assert [item["actor"] for item in hello["presence"]] == ["Ana"]
        users.roles.pop("shared")
        bus.publish("project_updated", project_id="shared", data={"name": "Secret"})
        return [frame async for frame in iterator]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=1)) == []
    assert presence.viewers("shared") == []
    assert bus.since(0)[-1].data == {"viewers": []}


@pytest.mark.parametrize("change", ["logged_out", "disabled", "demoted"])
@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("buffered", [False, True])
def test_stream_rechecks_current_session_identity_after_connection(live, change, scoped, buffered):
    bus, _presence, users = live
    user = viewer("admin") if change == "demoted" else viewer()
    project_id = "private" if change == "demoted" else "shared"
    token = f"{user['role']}-session"
    bus.publish("project_updated", project_id=project_id, data={"name": "Before"})
    if buffered:
        bus.publish("project_updated", project_id=project_id, data={"name": "Buffered secret"})

    async def collect():
        iterator = events._stream_response(
            stream_request(user), project_id=project_id if scoped else None
        ).body_iterator
        await anext(iterator)  # hello
        assert payload(await anext(iterator))["data"] == {"name": "Before"}
        if change == "logged_out":
            users.sessions.pop(token)
        elif change == "disabled":
            users.sessions[token]["status"] = "disabled"
        else:
            users.sessions[token]["role"] = "member"
        bus.publish("project_updated", project_id=project_id, data={"name": "After"})
        return [frame async for frame in iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert delivered(frames) == []


@pytest.mark.parametrize("status", [None, "disabled", "pending"])
def test_invalidated_session_cannot_receive_initial_presence(live, status):
    bus, presence, users = live
    if status is None:
        users.sessions.pop("member-session")
    else:
        users.sessions["member-session"]["status"] = status

    async def collect():
        response = events._stream_response(
            stream_request(viewer()), project_id="shared", actor="Forged", client_id="tab-1"
        )
        return [frame async for frame in response.body_iterator]

    assert asyncio.run(asyncio.wait_for(collect(), timeout=1)) == []
    assert presence.viewers("shared") == []
    assert bus.since(0) == []
