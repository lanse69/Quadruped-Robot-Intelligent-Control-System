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
    "approved",
    "released",
    "baseline",
    "archived",
]
GateDecision = Literal["passed", "failed"]
ApprovalDecision = Literal["approved", "rejected"]
ReportExportFormat = Literal["json", "markdown"]
SceneApiState = Literal["draft", "baseline", "archived"]
SceneAssetType = Literal["terrain", "obstacle", "checkpoint", "no_go_zone", "sensor_mount"]
SceneGeometryType = Literal["none", "sphere", "box", "cylinder"]
SimulationBackend = Literal["minimal", "mujoco", "webots"]

EventTopic = Literal[
    "scene.lifecycle",
    "task.lifecycle",
    "control.status",
    "control.alert",
    "training.status",
    "policy.lifecycle",
    "replay.index",
    "report.export",
    "audit.record",
]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonDict: TypeAlias = dict[str, JsonValue]


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
class SceneAssetPayload:
    asset_id: str
    asset_type: SceneAssetType
    uri: str = ""
    checksum: str = ""
    frame_id: str = "world"
    required: bool = True
    geometry_type: SceneGeometryType = "none"
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    size: tuple[float, float, float] = (0.0, 0.0, 0.0)
    radius_m: float = 0.0
    height_m: float = 0.0

    def to_json(self) -> JsonDict:
        return {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "uri": self.uri,
            "checksum": self.checksum,
            "frame_id": self.frame_id,
            "required": self.required,
            "geometry_type": self.geometry_type,
            "position": list(self.position),
            "size": list(self.size),
            "radius_m": self.radius_m,
            "height_m": self.height_m,
        }


@dataclass(frozen=True)
class SensorProfilePayload:
    profile_id: str = "default_sensors"
    camera_enabled: bool = False
    depth_camera_enabled: bool = False
    lidar_enabled: bool = False
    imu_enabled: bool = True
    foot_contact_enabled: bool = True
    sample_rate_hz: int = 100
    noise_std: float = 0.0
    source_quality: str = "direct"

    def to_json(self) -> JsonDict:
        return {
            "profile_id": self.profile_id,
            "camera_enabled": self.camera_enabled,
            "depth_camera_enabled": self.depth_camera_enabled,
            "lidar_enabled": self.lidar_enabled,
            "imu_enabled": self.imu_enabled,
            "foot_contact_enabled": self.foot_contact_enabled,
            "sample_rate_hz": self.sample_rate_hz,
            "noise_std": self.noise_std,
            "source_quality": self.source_quality,
        }


@dataclass(frozen=True)
class RandomizationProfilePayload:
    profile_id: str = "no_randomization"
    enabled: bool = False
    friction_range: tuple[float, float] = (1.0, 1.0)
    mass_scale_range: tuple[float, float] = (1.0, 1.0)
    sensor_noise_std: float = 0.0
    seed: int = 42

    def to_json(self) -> JsonDict:
        return {
            "profile_id": self.profile_id,
            "enabled": self.enabled,
            "friction_range": list(self.friction_range),
            "mass_scale_range": list(self.mass_scale_range),
            "sensor_noise_std": self.sensor_noise_std,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class SceneProfilePayload:
    scene_ref: ResourceRef
    name: str = ""
    terrain_pack: str = "flat"
    assets: tuple[SceneAssetPayload, ...] = ()
    sensor_profile: SensorProfilePayload = field(default_factory=SensorProfilePayload)
    randomization_profile: RandomizationProfilePayload = field(
        default_factory=RandomizationProfilePayload
    )
    state: SceneApiState = "draft"
    is_current_baseline: bool = False
    checksum: str = ""
    change_summary: str = ""
    validation_errors: tuple[str, ...] = ()

    def to_json(self) -> JsonDict:
        return {
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
            "name": self.name,
            "terrain_pack": self.terrain_pack,
            "state": self.state,
            "is_current_baseline": self.is_current_baseline,
            "asset_count": len(self.assets),
            "assets": [asset.to_json() for asset in self.assets],
            "sensor_profile": self.sensor_profile.to_json(),
            "randomization_profile": self.randomization_profile.to_json(),
            "checksum": self.checksum,
            "change_summary": self.change_summary,
            "validation_errors": list(self.validation_errors),
        }


@dataclass(frozen=True)
class SceneCreatePayload:
    scene_id: str
    version: str
    name: str = ""
    terrain_pack: str = "flat"
    assets: tuple[SceneAssetPayload, ...] = ()
    sensor_profile: SensorProfilePayload = field(default_factory=SensorProfilePayload)
    randomization_profile: RandomizationProfilePayload = field(
        default_factory=RandomizationProfilePayload
    )
    change_summary: str = ""


@dataclass(frozen=True)
class SceneCopyPayload:
    target_version: str
    change_summary: str = ""


@dataclass(frozen=True)
class WaypointView:
    waypoint_id: str
    name: str = ""
    terrain_hint: str = "flat"
    dwell_time_s: float = 0.0


@dataclass(frozen=True)
class SimulationRunOptionsPayload:
    backend: SimulationBackend = "minimal"
    runtime_profile: str = "headless_fast"
    step_count: int = 20
    forward_velocity_mps: float = 0.25
    yaw_rate_radps: float = 0.05
    obstacle_replan_distance_m: float = 0.25

    def to_json(self) -> JsonDict:
        return {
            "backend": self.backend,
            "runtime_profile": self.runtime_profile,
            "step_count": self.step_count,
            "forward_velocity_mps": self.forward_velocity_mps,
            "yaw_rate_radps": self.yaw_rate_radps,
            "obstacle_replan_distance_m": self.obstacle_replan_distance_m,
        }


@dataclass(frozen=True)
class SimulationPreviewPayload:
    scene_ref: ResourceRef = field(
        default_factory=lambda: ResourceRef(id="minimal_scene", version="0.1.0")
    )
    run_options: SimulationRunOptionsPayload = field(default_factory=SimulationRunOptionsPayload)


@dataclass(frozen=True)
class SimulationBackendCatalogResponse:
    backends: tuple[SimulationBackend, ...] = ("minimal", "mujoco", "webots")
    runtime_profiles: tuple[str, ...] = (
        "headless_fast",
        "balanced_visual",
        "webots_fast",
        "rich_demo",
    )

    def to_json(self) -> JsonDict:
        return {
            "backends": list(self.backends),
            "runtime_profiles": list(self.runtime_profiles),
            "defaults": SimulationRunOptionsPayload().to_json(),
            "default_backend": "minimal",
            "default_runtime_profile": "headless_fast",
            "recommended_local_demo": {
                "mujoco": "balanced_visual",
                "webots": "webots_fast",
            },
        }


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
    scene_ref: ResourceRef = field(
        default_factory=lambda: ResourceRef(id="minimal_scene", version="0.1.0")
    )

    def to_json(self) -> JsonDict:
        return {
            "task_id": self.task_id,
            "state": self.state,
            "goal": self.goal,
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
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
    terrain_class: str = "unknown"
    obstacle_detected: bool = False
    nearest_obstacle_distance_m: float = 0.0
    safety_event_count: int = 0
    presentation_pid: int = 0
    presentation_log_path: str = ""
    presentation_workspace: str = ""

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
            "terrain_class": self.terrain_class,
            "obstacle_detected": self.obstacle_detected,
            "nearest_obstacle_distance_m": self.nearest_obstacle_distance_m,
            "safety_event_count": self.safety_event_count,
            "presentation_pid": self.presentation_pid,
            "presentation_log_path": self.presentation_log_path,
            "presentation_workspace": self.presentation_workspace,
        }


@dataclass(frozen=True)
class MetricSummaryPayload:
    success_rate: float
    collision_rate: float
    tracking_error_m: float
    recovery_rate: float
    energy_proxy: float
    hard_constraint_violation_count: int = 0

    def to_json(self) -> JsonDict:
        return {
            "success_rate": self.success_rate,
            "collision_rate": self.collision_rate,
            "tracking_error_m": self.tracking_error_m,
            "recovery_rate": self.recovery_rate,
            "energy_proxy": self.energy_proxy,
            "hard_constraint_violation_count": self.hard_constraint_violation_count,
        }


@dataclass(frozen=True)
class TrainingResourceQuotaPayload:
    gpu_count: int = 0
    cpu_threads: int = 2
    memory_gb: float = 4.0
    max_runtime_s: int = 3600

    def to_json(self) -> JsonDict:
        return {
            "gpu_count": self.gpu_count,
            "cpu_threads": self.cpu_threads,
            "memory_gb": self.memory_gb,
            "max_runtime_s": self.max_runtime_s,
        }


@dataclass(frozen=True)
class TrainingPlanPayload:
    training_id: str
    scene_ref: ResourceRef
    algorithm: str = "ppo_placeholder"
    max_iterations: int = 100
    num_envs: int = 1
    seed: int = 42
    reward_config_version: str = "reward.default.v1"
    randomization_profile_id: str = "no_randomization"
    checkpoint_interval: int = 10
    resource_quota: TrainingResourceQuotaPayload = field(
        default_factory=TrainingResourceQuotaPayload
    )
    notes: str = ""

    def to_config_json(self) -> JsonDict:
        return {
            "training_id": self.training_id,
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
            "algorithm": self.algorithm,
            "max_iterations": self.max_iterations,
            "num_envs": self.num_envs,
            "seed": self.seed,
            "reward_config_version": self.reward_config_version,
            "randomization_profile_id": self.randomization_profile_id,
            "checkpoint_interval": self.checkpoint_interval,
            "resource_quota": self.resource_quota.to_json(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class TrainingJobResponse:
    job_id: str
    state: TrainingJobState
    scene_ref: ResourceRef
    algorithm: str
    max_iterations: int = 100
    num_envs: int = 1
    seed: int = 42
    reward_config_version: str = "reward.default.v1"
    randomization_profile_id: str = "no_randomization"
    checkpoint_interval: int = 10
    resource_quota: TrainingResourceQuotaPayload = field(
        default_factory=TrainingResourceQuotaPayload
    )
    config_hash: str = ""
    current_iteration: int = 0
    checkpoint_count: int = 0
    latest_checkpoint_uri: str = ""
    failure_reason: str = ""

    def to_json(self) -> JsonDict:
        return {
            "job_id": self.job_id,
            "state": self.state,
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
            "algorithm": self.algorithm,
            "max_iterations": self.max_iterations,
            "num_envs": self.num_envs,
            "seed": self.seed,
            "reward_config_version": self.reward_config_version,
            "randomization_profile_id": self.randomization_profile_id,
            "checkpoint_interval": self.checkpoint_interval,
            "resource_quota": self.resource_quota.to_json(),
            "config_hash": self.config_hash,
            "current_iteration": self.current_iteration,
            "checkpoint_count": self.checkpoint_count,
            "latest_checkpoint_uri": self.latest_checkpoint_uri,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class TrainingCheckpointPayload:
    iteration: int
    checkpoint_uri: str
    reason: str = ""


@dataclass(frozen=True)
class TrainingCompletionPayload:
    policy_ref: ResourceRef
    artifact_uri: str
    metrics: MetricSummaryPayload
    checksum: str = ""
    final_iteration: int = 0
    reason: str = "training completed"


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
class PolicyApprovalPayload:
    policy_ref: ResourceRef
    evaluation_id: str
    decision: ApprovalDecision
    reason: str


@dataclass(frozen=True)
class PolicyApprovalResponse:
    approval_id: str
    policy_ref: ResourceRef
    evaluation_id: str
    decision: ApprovalDecision
    approver_id: str
    approver_role: ApiRole
    reason: str
    request_id: str = ""
    timestamp_ns: int = 0

    def to_json(self) -> JsonDict:
        return {
            "approval_id": self.approval_id,
            "policy_id": self.policy_ref.id,
            "policy_version": self.policy_ref.version,
            "evaluation_id": self.evaluation_id,
            "decision": self.decision,
            "approver_id": self.approver_id,
            "approver_role": self.approver_role,
            "reason": self.reason,
            "request_id": self.request_id,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class PolicyStateResponse:
    policy_ref: ResourceRef
    stage: PolicyApiStage
    is_current_baseline: bool = False
    reason: str = ""
    artifact_uri: str = ""
    checksum: str = ""
    metrics: MetricSummaryPayload = field(
        default_factory=lambda: MetricSummaryPayload(0.0, 1.0, 999.0, 0.0, 0.0, 999)
    )

    def to_json(self) -> JsonDict:
        return {
            "policy_id": self.policy_ref.id,
            "policy_version": self.policy_ref.version,
            "stage": self.stage,
            "is_current_baseline": self.is_current_baseline,
            "reason": self.reason,
            "artifact_uri": self.artifact_uri,
            "checksum": self.checksum,
            "metrics": self.metrics.to_json(),
        }


@dataclass(frozen=True)
class EvaluationRunPayload:
    evaluation_id: str
    policy_ref: ResourceRef
    scene_ref: ResourceRef
    metrics: MetricSummaryPayload
    suite_id: str = "standard_v1"
    baseline_policy_ref: ResourceRef = field(default_factory=lambda: ResourceRef("", ""))
    replay_run_id: str = ""
    reason: str = ""


@dataclass(frozen=True)
class EvaluationReportResponse:
    evaluation_id: str
    policy_ref: ResourceRef
    scene_ref: ResourceRef
    suite_id: str
    metrics: MetricSummaryPayload
    decision: GateDecision
    reason: str
    baseline_policy_ref: ResourceRef = field(default_factory=lambda: ResourceRef("", ""))
    baseline_metrics: MetricSummaryPayload = field(
        default_factory=lambda: MetricSummaryPayload(0.0, 1.0, 999.0, 0.0, 0.0, 999)
    )
    baseline_diff: JsonDict = field(default_factory=dict)
    replay_run_id: str = ""

    def to_json(self) -> JsonDict:
        return {
            "evaluation_id": self.evaluation_id,
            "policy_id": self.policy_ref.id,
            "policy_version": self.policy_ref.version,
            "scene_id": self.scene_ref.id,
            "scene_version": self.scene_ref.version,
            "suite_id": self.suite_id,
            "decision": self.decision,
            "reason": self.reason,
            "metrics": self.metrics.to_json(),
            "baseline_policy_id": self.baseline_policy_ref.id,
            "baseline_policy_version": self.baseline_policy_ref.version,
            "baseline_metrics": self.baseline_metrics.to_json(),
            "baseline_diff": self.baseline_diff,
            "replay_run_id": self.replay_run_id,
        }


@dataclass(frozen=True)
class EvaluationReportExportPayload:
    evaluation_id: str
    report_format: ReportExportFormat = "json"
    reason: str = ""


@dataclass(frozen=True)
class EvaluationReportExportResponse:
    export_id: str
    evaluation_id: str
    report_format: ReportExportFormat
    uri: str
    checksum: str
    size_bytes: int
    generated_by: str
    request_id: str = ""
    timestamp_ns: int = 0
    summary: str = ""

    def to_json(self) -> JsonDict:
        return {
            "export_id": self.export_id,
            "evaluation_id": self.evaluation_id,
            "report_format": self.report_format,
            "uri": self.uri,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "generated_by": self.generated_by,
            "request_id": self.request_id,
            "timestamp_ns": self.timestamp_ns,
            "summary": self.summary,
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
    safety_events: tuple[str, ...] = ()
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
            "safety_events": list(self.safety_events),
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
