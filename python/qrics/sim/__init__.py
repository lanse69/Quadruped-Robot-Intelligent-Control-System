"""Backend-agnostic Python simulation contract for QRICS.

The package intentionally avoids importing heavyweight optional backends at
module import time. MuJoCo and Webots backends are loaded only when requested
explicitly, so minimal contract tests and Isaac Lab compatibility imports keep
working on machines where optional local simulators have not yet been installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qrics.sim.adapter import SimulationAdapterFacade
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.runtime_profile import RuntimeProfile, get_runtime_profile
from qrics.sim.scene_loader import load_scene_profile_from_json
from qrics.sim.schema import (
    AdapterConfig,
    AdapterResult,
    AdapterState,
    AdapterStepResult,
    Checkpoint,
    ContactState,
    ForbiddenZone,
    ObservationPacket,
    Pose,
    Quaternion,
    ResourceRef,
    RobotState,
    SafeAction,
    SceneGeometryType,
    SceneObstacle,
    SceneProfile,
    Vec3,
)

if TYPE_CHECKING:  # pragma: no cover - used by static type checkers only.
    from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv
    from qrics.sim.backends.webots_env import WebotsQuadrupedEnv


def __getattr__(name: str) -> object:
    if name == "MujocoQuadrupedEnv":
        from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv

        return MujocoQuadrupedEnv
    if name == "WebotsQuadrupedEnv":
        from qrics.sim.backends.webots_env import WebotsQuadrupedEnv

        return WebotsQuadrupedEnv
    raise AttributeError(f"module 'qrics.sim' has no attribute {name!r}")


__all__ = [
    "AdapterConfig",
    "AdapterResult",
    "AdapterState",
    "AdapterStepResult",
    "Checkpoint",
    "ContactState",
    "ForbiddenZone",
    "MinimalQuadrupedEnv",
    "MujocoQuadrupedEnv",
    "WebotsQuadrupedEnv",
    "ObservationPacket",
    "Pose",
    "Quaternion",
    "ResourceRef",
    "RobotState",
    "RuntimeProfile",
    "SafeAction",
    "SceneGeometryType",
    "SceneObstacle",
    "SceneProfile",
    "SimulationAdapterFacade",
    "Vec3",
    "get_runtime_profile",
    "load_scene_profile_from_json",
]
