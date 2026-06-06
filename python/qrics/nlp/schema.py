"""Task-understanding schema for QRICS natural-language adapters.

The schema intentionally models only semantic task drafts.  It does not expose
joint commands, simulator actions, SafeAction, or adapter handles.  Any downstream
control command must still pass through the existing task graph, policy runtime,
and Safety Shield chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FallbackAction = Literal["safe_stand", "replan", "return_home", "stop"]


@dataclass(frozen=True)
class WaypointAlias:
    """A named waypoint and the surface forms accepted by the parser."""

    waypoint_id: str
    name: str
    aliases: tuple[str, ...]
    terrain_hint: str = "flat"
    default_dwell_time_s: float = 0.0


@dataclass(frozen=True)
class AvoidZoneAlias:
    """A no-go or warning zone alias visible to task parsing."""

    zone_id: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class TaskParseCatalog:
    """Scene-aware catalog used by a parser invocation."""

    waypoints: tuple[WaypointAlias, ...]
    avoid_zones: tuple[AvoidZoneAlias, ...]
    default_fallback_action: FallbackAction = "safe_stand"


@dataclass(frozen=True)
class ParsedWaypoint:
    waypoint_id: str
    name: str
    terrain_hint: str = "flat"
    dwell_time_s: float = 0.0

    def to_json(self) -> dict[str, str | float]:
        return {
            "waypoint_id": self.waypoint_id,
            "name": self.name,
            "terrain_hint": self.terrain_hint,
            "dwell_time_s": self.dwell_time_s,
        }


@dataclass(frozen=True)
class ParsedTaskDraft:
    """Structured TaskScript draft produced from natural-language input."""

    source_text: str
    goal: str
    parser_version: str
    waypoints: tuple[ParsedWaypoint, ...] = ()
    avoid_zone_ids: tuple[str, ...] = ()
    fallback_action: FallbackAction = "safe_stand"
    confidence: float = 0.0
    needs_confirmation: bool = True
    explanations: tuple[str, ...] = ()
    safety_rejection_reason: str = ""
    unmatched_phrases: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return bool(self.waypoints) and not self.safety_rejection_reason

    def to_task_script_json(self) -> dict[str, object]:
        return {
            "schema": "qrics.task_script.draft.v1",
            "source_text": self.source_text,
            "goal": self.goal,
            "parser_version": self.parser_version,
            "waypoints": [waypoint.to_json() for waypoint in self.waypoints],
            "constraints": {
                "avoid_zone_ids": list(self.avoid_zone_ids),
                "ai_output_boundary": "task_script_only",
            },
            "fallback_action": self.fallback_action,
            "confidence": self.confidence,
            "needs_confirmation": self.needs_confirmation,
            "explanations": list(self.explanations),
            "safety_rejection_reason": self.safety_rejection_reason,
            "unmatched_phrases": list(self.unmatched_phrases),
        }

    def to_task_graph_json(self) -> dict[str, object]:
        nodes: list[dict[str, object]] = []
        edges: list[dict[str, str]] = []
        previous = ""
        for index, waypoint in enumerate(self.waypoints):
            node_id = f"move_{index}_{waypoint.waypoint_id}"
            nodes.append(
                {
                    "node_id": node_id,
                    "type": "MoveTo",
                    "waypoint_id": waypoint.waypoint_id,
                    "terrain_hint": waypoint.terrain_hint,
                }
            )
            if previous:
                edges.append({"from": previous, "to": node_id, "condition": "completed"})
            previous = node_id
            if waypoint.dwell_time_s > 0.0:
                dwell_id = f"dwell_{index}_{waypoint.waypoint_id}"
                nodes.append(
                    {
                        "node_id": dwell_id,
                        "type": "Dwell",
                        "waypoint_id": waypoint.waypoint_id,
                        "duration_s": waypoint.dwell_time_s,
                    }
                )
                edges.append({"from": previous, "to": dwell_id, "condition": "arrived"})
                previous = dwell_id
        if previous:
            nodes.append(
                {
                    "node_id": "stop_terminal",
                    "type": "Stop",
                    "fallback_action": self.fallback_action,
                }
            )
            edges.append({"from": previous, "to": "stop_terminal", "condition": "completed"})
        return {
            "schema": "qrics.task_graph.preview.v1",
            "entry_node_id": nodes[0]["node_id"] if nodes else "",
            "terminal_node_id": "stop_terminal" if nodes else "",
            "nodes": nodes,
            "edges": edges,
        }


@dataclass(frozen=True)
class DirectActionGuard:
    """Safety-boundary rule used to reject low-level action requests."""

    token: str
    reason: str


@dataclass(frozen=True)
class ParserDiagnostics:
    """Human-readable parser diagnostics for reports and tests."""

    accepted: bool
    confidence: float
    messages: tuple[str, ...] = field(default_factory=tuple)
