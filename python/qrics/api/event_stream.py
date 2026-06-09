"""In-memory event stream for API tests and demo runs."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import RLock

from qrics.api.schemas import EventEnvelope, EventTopic, JsonDict


@dataclass
class InMemoryEventStream:
    """Small append-only event stream used by the dependency-free API facade."""

    _events: list[EventEnvelope] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def append(
        self,
        *,
        topic: EventTopic,
        request_id: str,
        message: str,
        run_id: str = "",
        payload: JsonDict | None = None,
    ) -> EventEnvelope:
        """Append one event and return the stored envelope."""

        event = EventEnvelope(
            event_id=f"event_{len(self._events) + 1}",
            topic=topic,
            run_id=run_id,
            message=message,
            payload=payload or {},
            request_id=request_id,
            timestamp_ns=time.time_ns(),
        )
        return self.append_envelope(event)

    def append_envelope(self, event: EventEnvelope) -> EventEnvelope:
        """Append an already-created event envelope."""

        with self._lock:
            self._events.append(event)
        return event

    def list_events(self) -> tuple[EventEnvelope, ...]:
        """Return all events without clearing the stream."""

        with self._lock:
            return tuple(self._events)

    def drain(self) -> tuple[EventEnvelope, ...]:
        """Return all currently buffered events and clear the stream."""

        with self._lock:
            events = tuple(self._events)
            self._events.clear()
        return events

    def query(
        self,
        *,
        topic: EventTopic | None = None,
        run_id: str = "",
        request_id: str = "",
    ) -> tuple[EventEnvelope, ...]:
        """Return a filtered, non-destructive event snapshot."""

        with self._lock:
            result: list[EventEnvelope] = list(self._events)
        if topic is not None:
            result = [event for event in result if event.topic == topic]
        if run_id:
            result = [event for event in result if event.run_id == run_id]
        if request_id:
            result = [event for event in result if event.request_id == request_id]
        return tuple(result)
