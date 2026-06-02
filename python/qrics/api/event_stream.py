"""In-memory event stream for API tests and demo runs."""

from __future__ import annotations

from dataclasses import dataclass, field

from qrics.api.schemas import EventEnvelope, EventTopic, JsonDict


@dataclass
class InMemoryEventStream:
    _events: list[EventEnvelope] = field(default_factory=list)

    def append(
        self,
        *,
        topic: EventTopic,
        request_id: str,
        message: str,
        run_id: str = "",
        payload: JsonDict | None = None,
    ) -> EventEnvelope:
        event = EventEnvelope(
            event_id=f"event_{len(self._events) + 1}",
            topic=topic,
            run_id=run_id,
            message=message,
            payload=payload or {},
            request_id=request_id,
        )
        self._events.append(event)
        return event

    def list_events(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._events)

    def query(
        self,
        *,
        topic: EventTopic | None = None,
        run_id: str = "",
    ) -> tuple[EventEnvelope, ...]:
        result = self._events
        if topic is not None:
            result = [event for event in result if event.topic == topic]
        if run_id:
            result = [event for event in result if event.run_id == run_id]
        return tuple(result)
