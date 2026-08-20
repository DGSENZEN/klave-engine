"""Server-Sent Events stream: how every connected client stays in sync."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.api.dependencies import ProjectStore, get_store
from apps.api.events import (
    BUS,
    DISCONNECT_POLL_SECONDS,
    HEARTBEAT_SECONDS,
    PRESENCE,
    clean_actor,
    clean_client_id,
    clean_location_label,
    clean_location_path,
)

router = APIRouter()
ACTIVITY_LABEL_MAX_CHARS = 120

# Actions are a closed vocabulary shared with the web client's activity
# renderer; free-form strings would otherwise flow into every viewer's feed.
ALLOWED_ACTIVITY_ACTIONS = frozenset(
    {
        "editing_costing",
        "saving_costing",
        "resetting_costing",
        "exporting_budget",
        "viewing",
    }
)

# The unscoped stream backs the landing page's project list; it carries
# project lifecycle only, never per-user presence or activity detail.
GLOBAL_STREAM_EVENT_TYPES = frozenset(
    {"project_created", "project_updated", "job_updated", "run_published"}
)


class ActivityRequest(BaseModel):
    client_id: str | None = None
    action: str
    label: str | None = None
    location_path: str | None = None
    location_label: str | None = None


class PresenceUpdateRequest(BaseModel):
    client_id: str
    location_path: str | None = None
    location_label: str | None = None


def _clean_activity_label(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())[:ACTIVITY_LABEL_MAX_CHARS]


def _hello(seq: int, presence: list[dict[str, str]] | None = None) -> str:
    payload: dict[str, object] = {"seq": seq}
    if presence is not None:
        payload["presence"] = presence
    return f"retry: 3000\nevent: hello\nid: {seq}\ndata: {json.dumps(payload)}\n\n"


def _stream_response(
    request: Request,
    project_id: str | None = None,
    actor: str | None = None,
    client_id: str | None = None,
    location_path: str | None = None,
    location_label: str | None = None,
    event_types: frozenset[str] | None = None,
) -> StreamingResponse:
    """Live event stream, optionally filtered to one project.

    Emits a named ``hello`` event immediately (with the current sequence
    number), then pushes mutation events as they happen, with periodic
    heartbeat comments to keep intermediaries from closing the connection.
    """
    last_event_id = request.headers.get("last-event-id")
    try:
        since = int(last_event_id) if last_event_id else BUS.latest_seq()
    except ValueError:
        since = BUS.latest_seq()
    # A restarted server counts sequences from zero again; a client resuming
    # with a stale higher cursor would silently drop every new event until the
    # counter caught up. Clamp so delivery always resumes from live state.
    since = min(since, BUS.latest_seq())
    viewer_actor = clean_actor(actor)
    viewer_client_id = clean_client_id(client_id)
    viewer_location_path = clean_location_path(location_path)
    viewer_location_label = clean_location_label(location_label)
    session_id = uuid4().hex
    tracks_presence = bool(project_id and viewer_actor and viewer_client_id)

    async def stream() -> AsyncIterator[str]:
        cursor = since
        waiter = BUS.subscribe()
        presence = PRESENCE.viewers(project_id) if project_id is not None else None
        if tracks_presence:
            assert project_id is not None
            assert viewer_actor is not None
            assert viewer_client_id is not None
            presence = PRESENCE.join(
                project_id,
                viewer_client_id,
                viewer_actor,
                session_id,
                viewer_location_path,
                viewer_location_label,
            )
            BUS.publish(
                "presence_updated",
                project_id=project_id,
                actor=viewer_actor,
                data={"viewers": presence},
            )
        try:
            yield _hello(cursor, presence)
            last_beat = time.monotonic()
            while not await request.is_disconnected():
                # Clear before draining so a publish that races the drain sets
                # the flag and wakes the next wait instead of being missed.
                waiter.clear()
                pending = BUS.since(cursor, project_id)
                for event in pending:
                    cursor = event.seq
                    if event_types is not None and event.type not in event_types:
                        continue
                    yield event.to_sse()
                    last_beat = time.monotonic()
                if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                    last_beat = time.monotonic()
                    yield ": ping\n\n"
                if pending:
                    continue  # more may have arrived; re-drain before blocking
                # Wake immediately on the next publish; time out to heartbeat
                # and to re-check disconnection.
                timeout = min(
                    DISCONNECT_POLL_SECONDS,
                    max(0.05, HEARTBEAT_SECONDS - (time.monotonic() - last_beat)),
                )
                try:
                    await asyncio.wait_for(waiter.wait(), timeout=timeout)
                except TimeoutError:
                    pass
        finally:
            BUS.unsubscribe(waiter)
            if tracks_presence:
                assert project_id is not None
                assert viewer_actor is not None
                assert viewer_client_id is not None
                presence = PRESENCE.leave(project_id, viewer_client_id, session_id)
                BUS.publish(
                    "presence_updated",
                    project_id=project_id,
                    actor=viewer_actor,
                    data={"viewers": presence},
                )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/events")
async def events_stream(request: Request) -> StreamingResponse:
    return _stream_response(request, event_types=GLOBAL_STREAM_EVENT_TYPES)


@router.get("/projects/{project_id}/events")
async def project_events_stream(
    project_id: str,
    request: Request,
    actor: str | None = None,
    client_id: str | None = None,
    location_path: str | None = None,
    location_label: str | None = None,
    store: ProjectStore = Depends(get_store),
) -> StreamingResponse:
    store.get_root(project_id)  # 404 for unknown projects before joining presence
    return _stream_response(
        request,
        project_id,
        actor,
        client_id,
        location_path,
        location_label,
    )


@router.get("/projects/{project_id}/events/history")
def project_events_history(
    project_id: str,
    limit: int = 100,
    store: ProjectStore = Depends(get_store),
) -> dict:
    """Recent project (and global) events from the in-memory buffer.

    The change timeline is event-sourced; without history a client that
    connects late or reconnects across a gap would never see other users'
    committed changes. Bounded by the bus buffer — recent activity, not an
    audit log.
    """
    store.get_root(project_id)
    limit = max(1, min(limit, 200))
    events = BUS.since(0, project_id)
    return {"events": [event.to_json() for event in events[-limit:]]}


@router.post("/projects/{project_id}/activity", status_code=202)
async def project_activity(
    project_id: str,
    activity: ActivityRequest,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
) -> dict:
    store.get_root(project_id)
    action = " ".join(activity.action.split())
    if action not in ALLOWED_ACTIVITY_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail={"error_type": "unknown_activity_action", "action": action},
        )
    actor = clean_actor(x_actor)
    client_id = clean_client_id(activity.client_id)
    event = BUS.publish(
        "collaborator_activity",
        project_id=project_id,
        actor=actor,
        data={
            "client_id": client_id,
            "action": action,
            "label": _clean_activity_label(activity.label),
            "location_path": clean_location_path(activity.location_path),
            "location_label": clean_location_label(activity.location_label),
        },
    )
    return {"seq": event.seq}


@router.post("/projects/{project_id}/presence", status_code=202)
async def project_presence_update(
    project_id: str,
    update: PresenceUpdateRequest,
    x_actor: Annotated[str | None, Header()] = None,
    store: ProjectStore = Depends(get_store),
) -> dict:
    """Update a connected viewer's location without reconnecting their stream."""
    store.get_root(project_id)
    client_id = clean_client_id(update.client_id)
    if client_id is None:
        raise HTTPException(
            status_code=422,
            detail={"error_type": "missing_client_id"},
        )
    viewers = PRESENCE.update_location(
        project_id,
        client_id,
        clean_location_path(update.location_path),
        clean_location_label(update.location_label),
    )
    if viewers is None:
        return {"tracked": False}
    BUS.publish(
        "presence_updated",
        project_id=project_id,
        actor=clean_actor(x_actor),
        data={"viewers": viewers},
    )
    return {"tracked": True}
