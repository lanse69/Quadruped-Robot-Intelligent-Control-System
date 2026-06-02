"""Simulation backend implementations.

MuJoCo is an optional runtime dependency.  Keep imports lazy so backend-neutral
code can run before the local physical simulator is installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv

if TYPE_CHECKING:  # pragma: no cover - used by static type checkers only.
    from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv


def __getattr__(name: str) -> object:
    if name == "MujocoQuadrupedEnv":
        from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv

        return MujocoQuadrupedEnv
    raise AttributeError(f"module 'qrics.sim.backends' has no attribute {name!r}")


__all__ = ["MinimalQuadrupedEnv", "MujocoQuadrupedEnv"]
