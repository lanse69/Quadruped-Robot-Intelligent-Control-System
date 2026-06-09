"""Terrain-aware gait synthesis for local QRICS simulation backends.

The C++ core runtime remains the authoritative control chain.  This Python
module mirrors the same public gait evidence shape for the local MuJoCo/Webots
presentation path so the visible robot leg motion follows the same gait labels,
foot phases and nominal joint hints exposed by C++ evidence.
"""

from __future__ import annotations

import math
from dataclasses import replace

from qrics.sim.schema import (
    FootstepTarget,
    GaitType,
    JointCommand,
    LocomotionHint,
    SafeAction,
    TerrainClass,
    Vec3,
)

_NANOSECONDS_PER_SECOND = 1_000_000_000.0

_NOMINAL_FEET: dict[str, Vec3] = {
    "front_left": Vec3(0.22, 0.12, -0.35),
    "front_right": Vec3(0.22, -0.12, -0.35),
    "rear_left": Vec3(-0.22, 0.12, -0.35),
    "rear_right": Vec3(-0.22, -0.12, -0.35),
}

_FOOT_PREFIX: dict[str, str] = {
    "front_left": "fl",
    "front_right": "fr",
    "rear_left": "rl",
    "rear_right": "rr",
}


class GaitConfig:
    nominal_body_height_m = 0.35
    min_walk_speed_mps = 0.035
    crawl_frequency_hz = 0.85
    cautious_trot_frequency_hz = 1.15
    trot_frequency_hz = 1.55
    max_frequency_hz = 2.10
    max_stride_length_m = 0.24
    max_lateral_stride_m = 0.12
    max_swing_height_m = 0.11
    crawl_duty_factor = 0.78
    cautious_duty_factor = 0.66
    trot_duty_factor = 0.58
    cautious_body_drop_m = 0.025


def with_locomotion_hint(
    action: SafeAction,
    *,
    terrain: TerrainClass = "flat",
) -> SafeAction:
    """Return a SafeAction enriched with local presentation gait evidence."""
    if action.action_type != "body_velocity" or action.decision == "rejected":
        return action
    hint = synthesize_locomotion_hint(
        velocity=action.body_velocity,
        yaw_rate_radps=action.yaw_rate_radps,
        terrain=terrain,
        timestamp_ns=action.timestamp_ns,
    )
    return replace(action, locomotion_hint=hint, joint_commands=tuple(joint_hints(hint)))


def synthesize_locomotion_hint(
    *,
    velocity: Vec3,
    yaw_rate_radps: float,
    terrain: TerrainClass,
    timestamp_ns: int,
) -> LocomotionHint:
    speed = math.hypot(velocity.x, velocity.y)
    gait = _select_gait(terrain, speed, yaw_rate_radps)
    frequency = _gait_frequency(gait, terrain, speed)
    duty = _duty_factor(gait)
    phase = (
        0.0 if frequency <= 0.0 else _wrap01((timestamp_ns / _NANOSECONDS_PER_SECOND) * frequency)
    )
    stride_length = min(GaitConfig.max_stride_length_m, abs(velocity.x) / max(0.35, frequency))
    lateral_stride = min(GaitConfig.max_lateral_stride_m, abs(velocity.y) / max(0.35, frequency))
    swing_height = (
        0.0 if gait == "stand" else min(GaitConfig.max_swing_height_m, 0.025 + 0.10 * stride_length)
    )
    return LocomotionHint(
        enabled=True,
        gait_type=gait,
        gait_name=gait,
        normalized_phase=phase,
        step_frequency_hz=frequency,
        stride_length_m=stride_length,
        lateral_stride_m=lateral_stride,
        swing_height_m=swing_height,
        duty_factor=duty,
        body_height_m=_body_height(gait, terrain),
        feet=tuple(_foot_targets(gait, phase, duty, velocity, yaw_rate_radps, swing_height)),
    )


def joint_hints(hint: LocomotionHint) -> tuple[JointCommand, ...]:
    hints: list[JointCommand] = []
    stand = hint.gait_type == "stand"
    for foot in hint.feet:
        prefix = _FOOT_PREFIX.get(foot.foot_name, "rr")
        left_side = foot.foot_name in {"front_left", "rear_left"}
        front = foot.foot_name in {"front_left", "front_right"}
        swing = foot.phase == "swing"
        hip_nominal = 0.10 if left_side else -0.10
        thigh_nominal = 0.65 if front else 0.70
        calf_nominal = -1.25 if front else -1.30
        hip_delta = max(-0.18, min(0.18, foot.target_position_body.y * 0.52))
        phase_shape = (
            math.sin(math.pi * _swing_progress(foot.phase_in_cycle, foot.duty_factor))
            if swing
            else 0.0
        )
        fore_aft_delta = max(
            -0.14,
            min(0.14, foot.target_position_body.x - foot.nominal_position_body.x),
        )
        stance_recoil = -0.08 if not swing and not stand else 0.0
        hints.append(JointCommand(f"{prefix}_hip_joint", hip_nominal + hip_delta))
        hints.append(
            JointCommand(
                f"{prefix}_thigh_joint",
                thigh_nominal
                + (0.0 if stand else 0.34 * phase_shape - 1.15 * fore_aft_delta + stance_recoil),
            )
        )
        hints.append(
            JointCommand(
                f"{prefix}_calf_joint",
                calf_nominal
                - (0.0 if stand else 0.28 * phase_shape)
                + (0.46 * fore_aft_delta if not stand else 0.0),
            )
        )
    return tuple(hints)


def _select_gait(terrain: TerrainClass, speed_mps: float, yaw_rate_radps: float) -> GaitType:
    if speed_mps < GaitConfig.min_walk_speed_mps and abs(yaw_rate_radps) < 0.05:
        return "stand"
    if terrain in {"stairs", "low_friction"} or speed_mps < 0.12:
        return "crawl"
    if terrain in {"slope", "gravel", "unknown"}:
        return "cautious_trot"
    return "trot"


def _gait_frequency(gait: GaitType, terrain: TerrainClass, speed_mps: float) -> float:
    if gait == "stand":
        return 0.0
    base = {
        "crawl": GaitConfig.crawl_frequency_hz,
        "recovery": GaitConfig.crawl_frequency_hz,
        "cautious_trot": GaitConfig.cautious_trot_frequency_hz,
        "trot": GaitConfig.trot_frequency_hz,
        "stand": 0.0,
    }[gait]
    speed_boost = max(0.0, min(0.45, speed_mps * 0.75))
    terrain_scale = 0.88 if _cautious_terrain(terrain) else 1.0
    return max(0.30, min(GaitConfig.max_frequency_hz, (base + speed_boost) * terrain_scale))


def _duty_factor(gait: GaitType) -> float:
    if gait == "stand":
        return 1.0
    if gait == "crawl":
        return max(0.55, min(0.90, GaitConfig.crawl_duty_factor))
    if gait in {"cautious_trot", "recovery"}:
        return max(0.55, min(0.82, GaitConfig.cautious_duty_factor))
    return max(0.50, min(0.75, GaitConfig.trot_duty_factor))


def _body_height(gait: GaitType, terrain: TerrainClass) -> float:
    if gait == "stand":
        return GaitConfig.nominal_body_height_m
    drop = GaitConfig.cautious_body_drop_m if _cautious_terrain(terrain) else 0.0
    return max(0.25, GaitConfig.nominal_body_height_m - drop)


def _cautious_terrain(terrain: TerrainClass) -> bool:
    return terrain in {"slope", "gravel", "stairs", "low_friction", "unknown"}


def _foot_targets(
    gait: GaitType,
    phase: float,
    duty_factor: float,
    velocity: Vec3,
    yaw_rate_radps: float,
    swing_height: float,
) -> list[FootstepTarget]:
    offsets = (
        (("front_left", 0.00), ("rear_right", 0.25), ("front_right", 0.50), ("rear_left", 0.75))
        if gait == "crawl"
        else (
            ("front_left", 0.00),
            ("rear_right", 0.00),
            ("front_right", 0.50),
            ("rear_left", 0.50),
        )
    )
    forward_stride = max(
        -GaitConfig.max_stride_length_m, min(GaitConfig.max_stride_length_m, velocity.x * 0.42)
    )
    lateral_stride = max(
        -GaitConfig.max_lateral_stride_m, min(GaitConfig.max_lateral_stride_m, velocity.y * 0.22)
    )
    turn_stride = max(-0.035, min(0.035, yaw_rate_radps * 0.035))
    targets: list[FootstepTarget] = []
    for name, offset in offsets:
        nominal = _NOMINAL_FEET[name]
        local_phase = _wrap01(phase + offset)
        swing = gait != "stand" and local_phase > duty_factor
        swing_s = _swing_progress(local_phase, duty_factor)
        swing_lift = math.sin(math.pi * swing_s) * swing_height if swing else 0.0
        direction = 1.0 if nominal.x >= 0.0 else -1.0
        lateral_sign = 1.0 if nominal.y >= 0.0 else -1.0
        targets.append(
            FootstepTarget(
                foot_name=name,
                phase="swing" if swing else "stance",
                nominal_position_body=nominal,
                target_position_body=Vec3(
                    x=nominal.x
                    + (forward_stride * (swing_s - 0.5) if swing else -0.25 * forward_stride),
                    y=nominal.y + lateral_stride + (turn_stride * direction * lateral_sign),
                    z=nominal.z + swing_lift,
                ),
                phase_in_cycle=local_phase,
                duty_factor=duty_factor,
            )
        )
    return targets


def _swing_progress(local_phase: float, duty_factor: float) -> float:
    if local_phase <= duty_factor:
        return 0.0
    return max(0.0, min(1.0, (local_phase - duty_factor) / max(1.0e-6, 1.0 - duty_factor)))


def _wrap01(value: float) -> float:
    wrapped = value - math.floor(value)
    return wrapped + 1.0 if wrapped < 0.0 else wrapped
