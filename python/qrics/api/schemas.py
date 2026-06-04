"""API-facing schemas for the QRICS application facade.

The module intentionally uses only the Python standard library.  It models the
boundary that will later be wrapped by FastAPI/WebSocket handlers without making
those runtime dependencies mandatory for local tests or CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

ApiRole = Literal["operator", "algorithm_engineer", "test_engineer", "admin", "auditor"]
TaskApiState = Literal["preview_ready", "rejected", "confirmed", "handed_off", "cancelled"]
ControlApiState = Literal["created", "running", "paused", "succeeded", "failed", "cancelled"]
OverrideType = Literal["emergency_stop", "manual_control", "safe_stand", "pause", "resume"]
TrainingJobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
PolicyApiStage = Literal[
    "draft",
    "candidate",
    "gate_passed",
    "gate_failed",
    "released",
    "baseline",
    "archived",
]
GateDecision = Literal["passed", "failed"]
EventTopic = Literal[
    "task.lifecycle",
    "control.status",
    "control.alert",
    "training.status",
    "policy.lifecycle",
    "replay.index",
    "audit.record",
]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonDict: TypeAlias = dict[str, object]


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    actor_id: str = "operator"
    role: ApiRole = "operator"


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    field: str = ""


@dataclass(frozen=True)
class ApiResponse:
    ok: bool
    data: JsonDict = field(default_factory=dict)
    errors: tuple[ApiError, ...] = ()
    request_id: str = ""

    @classmethod
    def success(cls, *, data: JsonDict, request_id: str) -> ApiResponse:
        return cls(ok=True, data=data, request_id=request_id)

    @classmethod
    def failure(cls, *, code: str, message: str, request_id: str, field: str = "") -> ApiResponse:
        return cls(
            ok=False,
            errors=(ApiError(code=code, message=message, field=field),),
            request_id=request_id,
        )


@dataclass(frozen=True)
class ResourceRef:
    id: str
    version: str = ""


@dataclass(frozen=True)
class WaypointView:
    waypoint_id: str
    name: str = ""
    terrain_hint: str = "flat"
    dwell_time_s: float = 0.0


@dataclass(frozen=True)
class TaskSubmissionPayload:
    source_text: str
    scene_ref: ResourceRef = field(
        default_factory=lambda: ResourceRef(id="minimal_scene", version="0.1.0")
    )
    require_confirmation: bool = True


@dataclass(frozen=True)
class TaskPreviewResponse:
    task_id: str
    state: TaskApiState
    goal: str
    waypoints: tuple[WaypointView, ...]
    selected_policy_reason: str
    risk_summary: str
    operator_action_required: bool

    def to_json(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "goal": self.goal,
            "waypoints": [item.waypoint_id for item in self.waypoints],
            "selected_policy_reason": self.selected_policy_reason,
            "risk_summary": self.risk_summary,
            "operator_action_required": self.operator_action_required,
        }


@dataclass(frozen=True)
class TaskLifecycleResponse:
    task_id: str
    state: TaskApiState
    event_count: int
    latest_event: str

    def to_json(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "event_count": self.event_count,
            "latest_event": self.latest_event,
        }


@dataclass(frozen=True)
class OverridePayload:
    command_type: OverrideType
    reason: str = ""


@dataclass(frozen=True)
class ControlStatusResponse:
    run_id: str
    state: ControlApiState
    current_node_id: str = ""
    completed_node_count: int = 0
    control_step_count: int = 0
    risk_score: float = 0.0
    latest_action: str = "stop"
    reason: str = ""
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    sim_time_ns: int = 0
    base_position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    observation_quality: str = "estimated"

    def to_json(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "state": self.state,
            "current_node_id": self.current_node_id,
            "completed_node_count": self.completed_node_count,
            "control_step_count": self.control_step_count,
            "risk_score": self.risk_score,
            "latest_action": self.latest_action,
            "reason": self.reason,
            "backend": self.backend,
            "runtime_profile": self.runtime_profile,
            "sim_time_ns": self.sim_time_ns,
            "base_position": list(self.base_position),
            "observation_quality": self.observation_quality,
        }


@dataclass(frozen=True)
class MetricSummaryPayload:
    success_rate: float
    collision_rate: float
    tracking_error_m: float
    recovery_rate: float
    energy_proxy: float
    hard_constraint_violation_count: int = 0


@dataclass(frozen=True)
class TrainingPlanPayload:
    training_id: str
    scene_ref: ResourceRef
    algorithm: str = "ppo_placeholder"
    max_iterations: int = 100
    num_envs: int = 1
    seed: int = 42


@dataclass(frozen=True)
class TrainingJobResponse:
    job_id: str
    state: TrainingJobState
    scene_ref: ResourceRef
    algorithm: str

    def to_json(self) -> JsonDict:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
            "algorithm": self.algorithm,
        }


@dataclass(frozen=True)
class PolicyRegistrationPayload:
    policy_ref: ResourceRef
    artifact_uri: str
    metrics: MetricSummaryPayload
    checksum: str = ""


@dataclass(frozen=True)
class GateReportPayload:
    policy_ref: ResourceRef
    decision: GateDecision
    reason: str


@dataclass(frozen=True)
class PolicyStateResponse:
    policy_ref: ResourceRef
    stage: PolicyApiStage
    is_current_baseline: bool = False
    reason: str = ""

    def to_json(self) -> JsonDict:
        return {
            "policy_id": self.policy_ref.id,
            "policy_version": self.policy_ref.version,
            "stage": self.stage,
            "is_current_baseline": self.is_current_baseline,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ReplayQuery:
    run_id: str
    event_type: str = ""


@dataclass(frozen=True)
class ReplayResponse:
    run_id: str
    segment_count: int
    keyframe_count: int
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    first_timestamp_ns: int = 0
    last_timestamp_ns: int = 0
    keyframes: tuple[str, ...] = ()
    manifest_uri: str = ""
    manifest_checksum: str = ""

    def to_json(self) -> JsonDict:
        return {
            "run_id": self.run_id,
            "segment_count": self.segment_count,
            "keyframe_count": self.keyframe_count,
            "backend": self.backend,
            "runtime_profile": self.runtime_profile,
            "first_timestamp_ns": self.first_timestamp_ns,
            "last_timestamp_ns": self.last_timestamp_ns,
            "keyframes": list(self.keyframes),
            "manifest_uri": self.manifest_uri,
            "manifest_checksum": self.manifest_checksum,
        }


@dataclass(frozen=True)
class AuditQuery:
    actor_id: str = ""
    object_id: str = ""
    action: str = ""


@dataclass(frozen=True)
class AuditRecordResponse:
    audit_id: str
    actor_id: str
    action: str
    object_ref: ResourceRef
    result: str
    reason: str
    request_id: str = ""
    actor_role: ApiRole = "operator"
    timestamp_ns: int = 0

    def to_json(self) -> JsonDict:
        return {
            "audit_id": self.audit_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "action": self.action,
            "object_id": self.object_ref.id,
            "object_version": self.object_ref.version,
            "result": self.result,
            "reason": self.reason,
            "request_id": self.request_id,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    topic: EventTopic
    run_id: str = ""
    message: str = ""
    payload: JsonDict = field(default_factory=dict)
    request_id: str = ""
    timestamp_ns: int = 0

    def to_json(self) -> JsonDict:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "run_id": self.run_id,
            "message": self.message,
            "payload": self.payload,
            "request_id": self.request_id,
            "timestamp_ns": self.timestamp_ns,
        }
