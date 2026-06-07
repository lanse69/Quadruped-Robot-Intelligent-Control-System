"""SafeAction to backend command mapping."""

from __future__ import annotations

from dataclasses import dataclass, field

from qrics.sim.schema import AdapterResult, JointCommand, LocomotionHint, SafeAction, Vec3


@dataclass(frozen=True)
class MotionCommand:
    linear_velocity: Vec3 = field(default_factory=Vec3)
    yaw_rate_radps: float = 0.0
    joint_commands: tuple[JointCommand, ...] = ()
    locomotion_hint: LocomotionHint = field(default_factory=LocomotionHint)
    safe_stand: bool = False
    stop: bool = False


def command_from_safe_action(action: SafeAction) -> AdapterResult[MotionCommand]:
    if action.decision == "rejected":
        return AdapterResult.failure(
            "SAFE_ACTION_REJECTED",
            "Rejected SafeAction must not be mapped to a simulation command.",
        )

    if action.action_type == "body_velocity":
        return AdapterResult.success(
            MotionCommand(
                linear_velocity=action.body_velocity,
                yaw_rate_radps=action.yaw_rate_radps,
                joint_commands=action.joint_commands,
                locomotion_hint=action.locomotion_hint,
            )
        )

    if action.action_type in {"stop", "replan"}:
        return AdapterResult.success(MotionCommand(stop=True))

    if action.action_type == "safe_stand" or action.decision in {"emergency_stop", "safe_stand"}:
        return AdapterResult.success(MotionCommand(stop=True, safe_stand=True))

    return AdapterResult.failure(
        "UNSUPPORTED_ACTION_TYPE",
        f"Unsupported SafeAction type for local simulation backend: {action.action_type}",
    )
