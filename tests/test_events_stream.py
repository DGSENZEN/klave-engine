"""Cursor and replay behavior of the live SSE response."""

import asyncio
import json

import pytest
from starlette.requests import Request

from apps.api.events import EventBus
from apps.api.routes import events


@pytest.mark.parametrize(
    ("initial_project_id", "initial_type", "expected_sequences"),
    [
        ("p-visible", "project_updated", [1, 2]),
        ("p-hidden", "project_updated", [2]),
        ("p-visible", "collaborator_activity", [2]),
    ],
)
def test_stream_delivers_publish_after_drain_snapshot(
    monkeypatch, initial_project_id, initial_type, expected_sequences
):
    bus = EventBus()
    bus.publish(initial_type, project_id=initial_project_id)
    monkeypatch.setattr(events, "BUS", bus)
    monkeypatch.setattr(events, "DISCONNECT_POLL_SECONDS", 0.001)
    original_since = bus.since
    late_event = None

    def publish_after_snapshot(*args, **kwargs):
        nonlocal late_event
        pending = original_since(*args, **kwargs)
        if late_event is None:
            late_event = bus.publish("project_updated", project_id="p-visible")
        return pending

    monkeypatch.setattr(bus, "since", publish_after_snapshot)

    async def collect():
        polls = 0

        async def receive():
            nonlocal polls
            polls += 1
            if polls >= 3:
                return {"type": "http.disconnect"}
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(
            {"type": "http", "headers": [(b"last-event-id", b"0")]}, receive
        )
        response = events._stream_response(
            request,
            project_id="p-visible",
            event_types=events.GLOBAL_STREAM_EVENT_TYPES,
        )
        return [frame async for frame in response.body_iterator]

    frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    delivered = [
        json.loads(frame.split("data: ", 1)[1])
        for frame in frames
        if not frame.startswith("retry:")
    ]
    assert [event["seq"] for event in delivered] == expected_sequences


@pytest.mark.parametrize(
    ("last_event_id", "hello_sequence", "expected_sequences"),
    [("1", 1, [2, 3]), ("99", 2, [3]), ("invalid", 2, [3]), (None, 2, [3])],
)
def test_stream_replays_from_reconnect_cursor_and_delivers_new_events(
    monkeypatch, last_event_id, hello_sequence, expected_sequences
):
    bus = EventBus()
    bus.publish("project_updated")
    bus.publish("project_updated")
    monkeypatch.setattr(events, "BUS", bus)

    async def collect():
        polls = 0

        async def receive():
            nonlocal polls
            polls += 1
            if polls > 1:
                return {"type": "http.disconnect"}
            return {"type": "http.request", "body": b"", "more_body": False}

        headers = [] if last_event_id is None else [(b"last-event-id", last_event_id.encode())]
        request = Request({"type": "http", "headers": headers}, receive)
        iterator = events._stream_response(request).body_iterator
        hello = await anext(iterator)
        bus.publish("project_updated")
        frames = [frame async for frame in iterator]
        return hello, frames

    hello, frames = asyncio.run(asyncio.wait_for(collect(), timeout=1))
    assert json.loads(hello.split("data: ", 1)[1]) == {"seq": hello_sequence}
    assert [json.loads(frame.split("data: ", 1)[1])["seq"] for frame in frames] == (
        expected_sequences
    )
