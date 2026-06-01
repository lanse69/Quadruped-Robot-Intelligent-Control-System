"""Mapping from QRICS SafeAction to an Isaac-style command payload."""

from __future__ import annotations

from typing import TypeAlias

from qrics.isaac_lab.schema import AdapterResult, SafeAction

IsaacCommand: TypeAlias = dict[str, float | str]


def map_safe_action_to_isaac_command(action: SafeAction) -> AdapterResult[IsaacCommand]:
    """Convert a safety-gated action into a minimal command dictionary."""
    if action.decision == "rejected":
        return AdapterResult.failure(
            "ACTION_REJECTED",
            "Rejected SafeAction must not be mapped to an Isaac command",
        )

    if action.action_type in {"joint_position", "joint_velocity"}:
        return AdapterResult.failure(
            "JOINT_COMMAND_UNSUPPORTED",
            "Python Isaac adapter contract currently accepts only body-level safe actions",
        )

    if action.action_type == "body_velocity":
        return AdapterResult.success(
            {
                "command_type": "body_velocity",
                "linear_x_mps": action.body_velocity.x,
                "linear_y_mps": action.body_velocity.y,
                "linear_z_mps": action.body_velocity.z,
                "yaw_rate_radps": action.yaw_rate_radps,
            }
        )

    if action.action_type == "replan":
        return AdapterResult.success(
            {
                "command_type": "replan",
                "linear_x_mps": 0.0,
                "linear_y_mps": 0.0,
                "linear_z_mps": 0.0,
                "yaw_rate_radps": 0.0,
            }
        )

    command_type = "safe_stand" if action.action_type == "safe_stand" else "stop"
    return AdapterResult.success(
        {
            "command_type": command_type,
            "linear_x_mps": 0.0,
            "linear_y_mps": 0.0,
            "linear_z_mps": 0.0,
            "yaw_rate_radps": 0.0,
        }
    )
