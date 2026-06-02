"""Backend-agnostic Python simulation contract for QRICS.

The package intentionally avoids importing heavyweight optional backends at
module import time.  MuJoCo is loaded only when ``MujocoQuadrupedEnv`` is
requested explicitly, so minimal contract tests and Isaac Lab compatibility
imports keep working on machines where MuJoCo has not yet been installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qrics.sim.adapter import SimulationAdapterFacade
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.runtime_profile import RuntimeProfile, get_runtime_profile
from qrics.sim.schema import (
    AdapterConfig,
    AdapterResult,
    AdapterState,
    AdapterStepResult,
    Checkpoint,
    ContactState,
    ObservationPacket,
    Pose,
    Quaternion,
    ResourceRef,
    RobotState,
    SafeAction,
    SceneProfile,
    Vec3,
)

if TYPE_CHECKING:  # pragma: no cover - used by static type checkers only.
    from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv


def __getattr__(name: str) -> object:
    if name == "MujocoQuadrupedEnv":
        from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv

        return MujocoQuadrupedEnv
    raise AttributeError(f"module 'qrics.sim' has no attribute {name!r}")


__all__ = [
    "AdapterConfig",
    "AdapterResult",
    "AdapterState",
    "AdapterStepResult",
    "Checkpoint",
    "ContactState",
    "MinimalQuadrupedEnv",
    "MujocoQuadrupedEnv",
    "ObservationPacket",
    "Pose",
    "Quaternion",
    "ResourceRef",
    "RobotState",
    "RuntimeProfile",
    "SafeAction",
    "SceneProfile",
    "SimulationAdapterFacade",
    "Vec3",
    "get_runtime_profile",
]
