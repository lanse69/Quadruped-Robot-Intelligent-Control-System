"""Mapping from Isaac-style state dictionaries to QRICS observation schema."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from qrics.isaac_lab.schema import (
    AdapterResult,
    ContactState,
    ImuSample,
    ObservationPacket,
    Pose,
    Quaternion,
    RobotState,
    SourceQuality,
    StabilityState,
    TerrainClass,
    Vec3,
)


def _as_float(value: object, fallback: float = 0.0) -> float:
    if isinstance(value, int | float):
        return float(value)
    return fallback


def _as_bool(value: object, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return fallback


def _as_str(value: object, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    return fallback


def _as_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return value
    return ()


def _vec3_from(value: object) -> Vec3:
    sequence = _as_sequence(value)
    if len(sequence) < 3:
        return Vec3()
    return Vec3(
        x=_as_float(sequence[0]),
        y=_as_float(sequence[1]),
        z=_as_float(sequence[2]),
    )


def _quat_from(value: object) -> Quaternion:
    sequence = _as_sequence(value)
    if len(sequence) < 4:
        return Quaternion()
    return Quaternion(
        w=_as_float(sequence[0], 1.0),
        x=_as_float(sequence[1]),
        y=_as_float(sequence[2]),
        z=_as_float(sequence[3]),
    )


def _terrain_from(value: object) -> TerrainClass:
    text = _as_str(value, "unknown")
    if text in {"flat", "slope", "gravel", "stairs", "low_friction"}:
        return text  # type: ignore[return-value]
    return "unknown"


def _stability_from(value: object) -> StabilityState:
    text = _as_str(value, "unknown")
    if text in {"stable", "unstable", "fallen", "recovering"}:
        return text  # type: ignore[return-value]
    return "unknown"


def _source_quality_from(value: object, fallback: SourceQuality = "estimated") -> SourceQuality:
    text = _as_str(value, fallback)
    if text in {"direct", "estimated", "missing"}:
        return text  # type: ignore[return-value]
    return fallback


def _contacts_from(value: object) -> tuple[ContactState, ...]:
    contacts: list[ContactState] = []
    for item in _as_sequence(value):
        if not isinstance(item, Mapping):
            continue
        contacts.append(
            ContactState(
                foot_name=_as_str(item.get("foot_name")),
                in_contact=_as_bool(item.get("in_contact")),
                normal_force_n=_as_float(item.get("normal_force_n")),
            )
        )
    return tuple(contacts)


def map_isaac_observation(
    raw: Mapping[str, object],
    timestamp_ns: int,
) -> AdapterResult[ObservationPacket]:
    """Convert a minimal Isaac-style observation mapping to QRICS ObservationPacket."""
    observation = ObservationPacket(
        observation_id=_as_str(raw.get("observation_id"), "observation_0"),
        timestamp_ns=timestamp_ns,
        imu=ImuSample(
            linear_acceleration=_vec3_from(raw.get("imu_linear_acceleration")),
            angular_velocity=_vec3_from(raw.get("imu_angular_velocity")),
            orientation=_quat_from(raw.get("imu_orientation")),
            source_quality=_source_quality_from(raw.get("imu_source_quality"), "direct"),
        ),
        contacts=_contacts_from(raw.get("contacts")),
        base_pose=Pose(
            position=_vec3_from(raw.get("base_position")),
            orientation=_quat_from(raw.get("base_orientation")),
        ),
        linear_velocity=_vec3_from(raw.get("linear_velocity")),
        angular_velocity=_vec3_from(raw.get("angular_velocity")),
        terrain_class=_terrain_from(raw.get("terrain_class")),
    )
    return AdapterResult.success(observation)


def map_isaac_robot_state(
    raw: Mapping[str, object],
    timestamp_ns: int,
) -> AdapterResult[RobotState]:
    """Convert a minimal Isaac-style state mapping to QRICS RobotState."""
    state = RobotState(
        timestamp_ns=timestamp_ns,
        pose=Pose(
            position=_vec3_from(raw.get("base_position")),
            orientation=_quat_from(raw.get("base_orientation")),
        ),
        linear_velocity=_vec3_from(raw.get("linear_velocity")),
        angular_velocity=_vec3_from(raw.get("angular_velocity")),
        contacts=_contacts_from(raw.get("contacts")),
        terrain_class=_terrain_from(raw.get("terrain_class")),
        stability_state=_stability_from(raw.get("stability_state")),
        risk_score=_as_float(raw.get("risk_score")),
    )
    return AdapterResult.success(state)
