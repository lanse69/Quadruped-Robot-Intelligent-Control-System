"""Python Isaac Lab adapter facade following the C++ SimulationAdapter contract.

This module intentionally remains a lightweight compatibility layer until the
real Isaac Lab runtime is installed.  It delegates to the backend-neutral
``MinimalQuadrupedEnv`` while preserving the public Isaac Lab adapter lifecycle
used by the existing tests and documentation.
"""

from __future__ import annotations

from qrics.isaac_lab.action_mapper import map_safe_action_to_isaac_command
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.schema import (
    AdapterConfig,
    AdapterResult,
    AdapterState,
    AdapterStepResult,
    ObservationPacket,
    RobotState,
    SafeAction,
    SceneProfile,
)


class IsaacLabAdapter:
    """Compatibility adapter boundary for the future real Isaac Lab backend."""

    def __init__(self, backend: MinimalQuadrupedEnv | None = None) -> None:
        self._backend = backend or MinimalQuadrupedEnv()

    def name(self) -> str:
        return "isaac_lab"

    def state(self) -> AdapterState:
        return self._backend.state()

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        return self._backend.initialize(config)

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[AdapterState]:
        loaded = self._backend.load_scene(scene_profile)
        if not loaded.ok:
            return AdapterResult.failure(
                loaded.errors[0].code if loaded.errors else "SCENE_LOAD_FAILED",
                loaded.errors[0].message if loaded.errors else "Scene loading failed.",
            )
        return AdapterResult.success(self._backend.state())

    def reset(self) -> AdapterResult[ObservationPacket]:
        reset = self._backend.reset()
        if not reset.ok or reset.value is None:
            return AdapterResult.failure(
                reset.errors[0].code if reset.errors else "RESET_FAILED",
                reset.errors[0].message if reset.errors else "Reset failed.",
            )
        return AdapterResult.success(reset.value.observation)

    def observe(self) -> AdapterResult[ObservationPacket]:
        return self._backend.observe()

    def robot_state(self) -> AdapterResult[RobotState]:
        return self._backend.robot_state()

    def step(self, action: SafeAction) -> AdapterResult[AdapterStepResult]:
        if self._backend.state() != "running":
            return AdapterResult.failure(
                "ADAPTER_NOT_RUNNING",
                "step() requires reset() to put the environment into running state",
            )

        command = map_safe_action_to_isaac_command(action)
        if not command.ok:
            return AdapterResult.failure(
                command.errors[0].code if command.errors else "ACTION_MAPPING_FAILED",
                command.errors[0].message if command.errors else "SafeAction mapping failed.",
            )

        return self._backend.step(action)

    def close(self) -> AdapterResult[AdapterState]:
        return self._backend.close()
