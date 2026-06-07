"""Simulation adapter schema shared by all QRICS Python backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeAlias, TypeVar

BackendKind: TypeAlias = Literal["minimal", "mujoco", "webots", "isaac_lab"]
ActionType: TypeAlias = Literal[
    "joint_position",
    "joint_velocity",
    "body_velocity",
    "stop",
    "safe_stand",
    "replan",
]
SafetyDecision: TypeAlias = Literal[
    "accepted",
    "clipped",
    "rejected",
    "emergency_stop",
    "safe_stand",
    "replan",
]
AdapterState: TypeAlias = Literal[
    "created", "initialized", "scene_loaded", "running", "stopped", "error"
]
TerrainClass: TypeAlias = Literal["unknown", "flat", "slope", "gravel", "stairs", "low_friction"]
StabilityState: TypeAlias = Literal["unknown", "stable", "unstable", "fallen", "recovering"]
SourceQuality: TypeAlias = Literal["direct", "estimated", "missing"]
SceneGeometryType: TypeAlias = Literal["cylinder", "sphere", "box"]
GaitType: TypeAlias = Literal["stand", "crawl", "trot", "cautious_trot", "recovery"]
FootPhase: TypeAlias = Literal["stance", "swing"]

T = TypeVar("T")


@dataclass(frozen=True)
class AdapterError:
    code: str
    message: str


@dataclass(frozen=True)
class AdapterResult(Generic[T]):
    ok: bool
    value: T | None = None
    errors: tuple[AdapterError, ...] = ()

    @classmethod
    def success(cls, value: T) -> AdapterResult[T]:
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, code: str, message: str) -> AdapterResult[T]:
        return cls(ok=False, errors=(AdapterError(code=code, message=message),))


@dataclass(frozen=True)
class Vec3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Quaternion:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class Pose:
    position: Vec3 = field(default_factory=Vec3)
    orientation: Quaternion = field(default_factory=Quaternion)


@dataclass(frozen=True)
class ResourceRef:
    id: str = ""
    version: str = ""


@dataclass(frozen=True)
class JointCommand:
    joint_name: str
    target_position_rad: float = 0.0
    target_velocity_radps: float = 0.0
    target_torque_nm: float = 0.0


@dataclass(frozen=True)
class FootstepTarget:
    foot_name: str
    phase: FootPhase = "stance"
    nominal_position_body: Vec3 = field(default_factory=Vec3)
    target_position_body: Vec3 = field(default_factory=Vec3)
    phase_in_cycle: float = 0.0
    duty_factor: float = 1.0


@dataclass(frozen=True)
class LocomotionHint:
    enabled: bool = False
    gait_type: GaitType = "stand"
    gait_name: str = "stand"
    normalized_phase: float = 0.0
    step_frequency_hz: float = 0.0
    stride_length_m: float = 0.0
    lateral_stride_m: float = 0.0
    swing_height_m: float = 0.0
    duty_factor: float = 1.0
    body_height_m: float = 0.35
    feet: tuple[FootstepTarget, ...] = ()


@dataclass(frozen=True)
class Checksum:
    algorithm: str = "sha256"
    value: str = ""


@dataclass(frozen=True)
class AdapterConfig:
    adapter_name: str = "local_sim"
    adapter_version: str = "0.2.0"
    schema_version: str = "0.2.0"
    backend: BackendKind = "mujoco"
    runtime_profile: str = "balanced_visual"


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    pose: Pose = field(default_factory=Pose)
    dwell_time_s: float = 0.0


@dataclass(frozen=True)
class SceneObstacle:
    obstacle_id: str
    position: Vec3 = field(default_factory=Vec3)
    radius_m: float = 0.25
    height_m: float = 0.40
    geometry_type: SceneGeometryType = "cylinder"
    size: Vec3 = field(default_factory=Vec3)


@dataclass(frozen=True)
class ForbiddenZone:
    zone_id: str
    polygon: tuple[Vec3, ...] = ()


@dataclass(frozen=True)
class SceneProfile:
    scene_id: str
    version: str
    name: str = ""
    terrain_pack: str = "flat"
    obstacle_set: tuple[SceneObstacle, ...] = ()
    checkpoints: tuple[Checkpoint, ...] = ()
    forbidden_zones: tuple[ForbiddenZone, ...] = ()
    checksum: Checksum = field(default_factory=Checksum)


@dataclass(frozen=True)
class SafeAction:
    action_id: str
    source_proposal_id: str = ""
    action_type: ActionType = "stop"
    body_velocity: Vec3 = field(default_factory=Vec3)
    yaw_rate_radps: float = 0.0
    joint_commands: tuple[JointCommand, ...] = ()
    locomotion_hint: LocomotionHint = field(default_factory=LocomotionHint)
    decision: SafetyDecision = "accepted"
    reason: str = ""
    timestamp_ns: int = 0


@dataclass(frozen=True)
class ImuSample:
    linear_acceleration: Vec3 = field(default_factory=Vec3)
    angular_velocity: Vec3 = field(default_factory=Vec3)
    orientation: Quaternion = field(default_factory=Quaternion)
    source_quality: SourceQuality = "estimated"


@dataclass(frozen=True)
class ContactState:
    foot_name: str
    in_contact: bool = False
    normal_force_n: float = 0.0


@dataclass(frozen=True)
class ObstacleState:
    obstacle_detected: bool = False
    nearest_distance_m: float = 0.0
    nearest_point: Vec3 = field(default_factory=Vec3)
    source_quality: SourceQuality = "estimated"


@dataclass(frozen=True)
class ObservationPacket:
    observation_id: str
    timestamp_ns: int = 0
    imu: ImuSample = field(default_factory=ImuSample)
    contacts: tuple[ContactState, ...] = ()
    base_pose: Pose = field(default_factory=Pose)
    linear_velocity: Vec3 = field(default_factory=Vec3)
    angular_velocity: Vec3 = field(default_factory=Vec3)
    terrain_class: TerrainClass = "unknown"
    obstacle_state: ObstacleState = field(default_factory=ObstacleState)


@dataclass(frozen=True)
class RobotState:
    timestamp_ns: int = 0
    pose: Pose = field(default_factory=Pose)
    linear_velocity: Vec3 = field(default_factory=Vec3)
    angular_velocity: Vec3 = field(default_factory=Vec3)
    contacts: tuple[ContactState, ...] = ()
    terrain_class: TerrainClass = "unknown"
    stability_state: StabilityState = "unknown"
    risk_score: float = 0.0


@dataclass(frozen=True)
class AdapterStepResult:
    observation: ObservationPacket
    robot_state: RobotState
    state: AdapterState = "running"
