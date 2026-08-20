"""In-process event bus and presence for live multi-user sync.

Mutations (uploads, job progress, published runs, costing edits) publish
events here; connected clients receive them over the ``GET /events`` SSE
stream and refetch what changed. The bus is deliberately single-instance:
a bounded, sequence-numbered history guarded by a lock, safe to publish
into from both async routes and the job worker threads.

Delivery is event-driven: each SSE subscriber registers an ``asyncio.Event``
and blocks on it, and ``publish`` wakes every waiter through
``loop.call_soon_threadsafe`` — so an edit reaches other clients within a
round trip, not on a poll interval. Publishing is safe from worker threads
because the waiter's loop is captured at subscribe time. A multi-instance
deployment would swap only this module for a pub/sub adapter.

``Last-Event-ID`` is honoured on reconnect, so a briefly disconnected
client replays anything still in the history window instead of missing it.
"""

import asyncio
import json
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

HISTORY_LIMIT = 500
HEARTBEAT_SECONDS = 15.0
# Backstop cadence for noticing client disconnects between events; real
# delivery latency is set by the event wakeup, not this interval.
DISCONNECT_POLL_SECONDS = 2.0
ACTOR_MAX_CHARS = 40
CLIENT_ID_MAX_CHARS = 80
LOCATION_PATH_MAX_CHARS = 160
LOCATION_LABEL_MAX_CHARS = 60


@dataclass(frozen=True)
class Event:
    seq: int
    ts: str
    type: str
    project_id: str | None
    actor: str | None
    data: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type,
            "project_id": self.project_id,
            "actor": self.actor,
            "data": self.data,
        }

    def to_sse(self) -> str:
        return (
            f"id: {self.seq}\n"
            f"data: {json.dumps(self.to_json(), ensure_ascii=False)}\n\n"
        )


@dataclass
class EventBus:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _seq: int = 0
    _events: deque[Event] = field(default_factory=lambda: deque(maxlen=HISTORY_LIMIT))
    # Live SSE subscribers: their wakeup Event mapped to the loop it belongs to.
    _waiters: dict["asyncio.Event", "asyncio.AbstractEventLoop"] = field(
        default_factory=dict
    )

    def publish(
        self,
        event_type: str,
        project_id: str | None = None,
        actor: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Event:
        with self._lock:
            self._seq += 1
            event = Event(
                seq=self._seq,
                ts=datetime.now(UTC).isoformat(),
                type=event_type,
                project_id=project_id,
                actor=actor,
                data=data or {},
            )
            self._events.append(event)
            waiters = list(self._waiters.items())
        # Wake subscribers outside the lock, hopping to each waiter's loop so
        # publishes from worker threads are safe.
        for waiter, loop in waiters:
            try:
                loop.call_soon_threadsafe(waiter.set)
            except RuntimeError:
                pass  # loop already closed; unsubscribe races cleanup
        return event

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def since(self, seq: int, project_id: str | None = None) -> list[Event]:
        """Events after ``seq``; project-filtered streams also see global events."""
        with self._lock:
            return [
                event
                for event in self._events
                if event.seq > seq
                and (
                    project_id is None
                    or event.project_id == project_id
                    or event.project_id is None
                )
            ]

    def subscribe(self) -> "asyncio.Event":
        """Register a wakeup for the current loop; pair with ``unsubscribe``."""
        waiter = asyncio.Event()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._waiters[waiter] = loop
        return waiter

    def unsubscribe(self, waiter: "asyncio.Event") -> None:
        with self._lock:
            self._waiters.pop(waiter, None)


@dataclass
class PresenceEntry:
    client_id: str
    actor: str
    location_path: str = ""
    location_label: str = ""
    sessions: set[str] = field(default_factory=set)
    joined_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> dict[str, str]:
        return {
            "client_id": self.client_id,
            "actor": self.actor,
            "location_path": self.location_path,
            "location_label": self.location_label,
            "joined_at": self.joined_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PresenceStore:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _projects: dict[str, dict[str, PresenceEntry]] = field(default_factory=dict)

    def join(
        self,
        project_id: str,
        client_id: str,
        actor: str,
        session_id: str,
        location_path: str = "",
        location_label: str = "",
    ) -> list[dict[str, str]]:
        now = datetime.now(UTC).isoformat()
        with self._lock:
            project = self._projects.setdefault(project_id, {})
            entry = project.get(client_id)
            if entry is None:
                entry = PresenceEntry(
                    client_id=client_id,
                    actor=actor,
                    location_path=location_path,
                    location_label=location_label,
                    joined_at=now,
                )
                project[client_id] = entry
            entry.actor = actor
            entry.location_path = location_path
            entry.location_label = location_label
            entry.updated_at = now
            entry.sessions.add(session_id)
            return self._viewers_locked(project_id)

    def update_location(
        self,
        project_id: str,
        client_id: str,
        location_path: str,
        location_label: str,
    ) -> list[dict[str, str]] | None:
        """Move an existing viewer without churning their SSE session.

        Returns the refreshed viewer list, or ``None`` when the client has no
        live presence entry (navigation raced a disconnect) so callers can
        skip publishing.
        """
        with self._lock:
            entry = self._projects.get(project_id, {}).get(client_id)
            if entry is None:
                return None
            entry.location_path = location_path
            entry.location_label = location_label
            entry.updated_at = datetime.now(UTC).isoformat()
            return self._viewers_locked(project_id)

    def leave(self, project_id: str, client_id: str, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return []
            entry = project.get(client_id)
            if entry is None:
                return self._viewers_locked(project_id)
            entry.sessions.discard(session_id)
            if not entry.sessions:
                project.pop(client_id, None)
            if not project:
                self._projects.pop(project_id, None)
                return []
            return self._viewers_locked(project_id)

    def viewers(self, project_id: str) -> list[dict[str, str]]:
        with self._lock:
            return self._viewers_locked(project_id)

    def _viewers_locked(self, project_id: str) -> list[dict[str, str]]:
        return [
            viewer.to_json()
            for viewer in sorted(
                self._projects.get(project_id, {}).values(),
                key=lambda item: (item.actor.lower(), item.client_id),
            )
        ]


def clean_actor(value: str | None) -> str | None:
    """Normalize a client-provided display name (header) for event attribution."""
    if value is None:
        return None
    cleaned = " ".join(value.split())[:ACTOR_MAX_CHARS]
    return cleaned or None


def clean_client_id(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())[:CLIENT_ID_MAX_CHARS]
    return cleaned or None


def clean_location_path(value: str | None) -> str:
    if value is None:
        return ""
    cleaned = " ".join(value.split())[:LOCATION_PATH_MAX_CHARS]
    return cleaned if cleaned.startswith("/") else ""


def clean_location_label(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())[:LOCATION_LABEL_MAX_CHARS]


BUS = EventBus()
PRESENCE = PresenceStore()
