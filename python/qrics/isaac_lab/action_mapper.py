"""Backward-compatible action mapper for Isaac Lab contract tests.

The backend-agnostic mapper in :mod:`qrics.sim.commands` is the canonical
implementation.  This module preserves the old Isaac Lab import path and the
old ``ACTION_REJECTED`` error code used by the adapter contract tests.
"""

from __future__ import annotations

from qrics.sim.commands import MotionCommand, command_from_safe_action
from qrics.sim.schema import AdapterResult, SafeAction


def map_safe_action_to_isaac_command(action: SafeAction) -> AdapterResult[MotionCommand]:
    mapped = command_from_safe_action(action)
    if mapped.ok:
        return mapped
    if mapped.errors and mapped.errors[0].code == "SAFE_ACTION_REJECTED":
        return AdapterResult.failure("ACTION_REJECTED", mapped.errors[0].message)
    if mapped.errors:
        return AdapterResult.failure(mapped.errors[0].code, mapped.errors[0].message)
    return AdapterResult.failure("ACTION_MAPPING_FAILED", "SafeAction mapping failed.")


map_safe_action_to_command = map_safe_action_to_isaac_command

__all__ = [
    "MotionCommand",
    "command_from_safe_action",
    "map_safe_action_to_command",
    "map_safe_action_to_isaac_command",
]
