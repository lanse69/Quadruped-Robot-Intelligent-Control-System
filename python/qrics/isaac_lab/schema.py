"""Python-side QRICS adapter schema aligned with the C++ domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Literal, TypeVar

ActionType = Literal[
    "joint_position",
    "joint_velocity",
    "body_velocity",
    "stop",
    "safe_stand",
    "replan",
]

SafetyDecision = Literal[
    "accepted",
    "clipped",
    "rejected",
    "emergency_stop",
    "safe_stand",
    "replan",
]

AdapterState = Literal[
    "created",
    "initialized",
    "scene_loaded",
    "running",
    "stopped",
    "error",
]

TerrainClass = Literal[
    "unknown",
    "flat",
    "slope",
    "gravel",
    "stairs",
    "low_friction",
]

StabilityState = Literal["unknown", "stable", "unstable", "fallen", "recovering"]

SourceQuality = Literal["direct", "estimated", "missing"]

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
class Checksum:
    algorithm: str = "sha256"
    value: str = ""


@dataclass(frozen=True)
class AdapterConfig:
    adapter_name: str = "isaac_lab"
    adapter_version: str = "0.1.0"
    schema_version: str = "0.1.0"


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    pose: Pose = field(default_factory=Pose)
    dwell_time_s: float = 0.0


@dataclass(frozen=True)
class SceneProfile:
    scene_id: str
    version: str
    name: str = ""
    terrain_pack: str = "flat"
    checkpoints: tuple[Checkpoint, ...] = ()
    checksum: Checksum = field(default_factory=Checksum)


@dataclass(frozen=True)
class SafeAction:
    action_id: str
    source_proposal_id: str = ""
    action_type: ActionType = "stop"
    body_velocity: Vec3 = field(default_factory=Vec3)
    yaw_rate_radps: float = 0.0
    decision: SafetyDecision = "accepted"
    reason: str = ""
    timestamp_ns: int = 0


@dataclass(frozen=True)
class ImuSample:
    linear_acceleration: Vec3 = field(default_factory=Vec3)
    angular_velocity: Vec3 = field(default_factory=Vec3)
    orientation: Quaternion = field(default_factory=Quaternion)
    source_quality: SourceQuality = "direct"


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
