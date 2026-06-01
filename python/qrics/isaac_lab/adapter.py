"""Python Isaac Lab adapter facade following the C++ SimulationAdapter contract."""

from __future__ import annotations

from qrics.isaac_lab.action_mapper import map_safe_action_to_isaac_command
from qrics.isaac_lab.minimal_env import MinimalQuadrupedEnv
from qrics.isaac_lab.observation_mapper import map_isaac_observation, map_isaac_robot_state
from qrics.isaac_lab.schema import (
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
    """Minimal adapter boundary; real Isaac Lab runtime can replace the backend later."""

    def __init__(self, backend: MinimalQuadrupedEnv | None = None) -> None:
        self._backend = backend or MinimalQuadrupedEnv()

    def name(self) -> str:
        return "isaac_lab"

    def state(self) -> AdapterState:
        return self._backend.state

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        return AdapterResult.success(self._backend.initialize(config))

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[AdapterState]:
        if self._backend.state not in {"initialized", "scene_loaded", "running", "stopped"}:
            return AdapterResult.failure(
                "ADAPTER_NOT_INITIALIZED",
                "initialize() must be called before load_scene()",
            )
        return AdapterResult.success(self._backend.load_scene(scene_profile))

    def reset(self) -> AdapterResult[ObservationPacket]:
        if self._backend.state != "scene_loaded":
            return AdapterResult.failure(
                "SCENE_NOT_LOADED",
                "load_scene() must be called before reset()",
            )
        raw_observation = self._backend.reset()
        return map_isaac_observation(raw_observation, self._backend.timestamp_ns)

    def observe(self) -> AdapterResult[ObservationPacket]:
        if self._backend.state not in {"running", "scene_loaded"}:
            return AdapterResult.failure(
                "ADAPTER_NOT_RUNNING",
                "observe() requires a loaded or running environment",
            )
        return map_isaac_observation(self._backend.observe(), self._backend.timestamp_ns)

    def robot_state(self) -> AdapterResult[RobotState]:
        if self._backend.state not in {"running", "scene_loaded"}:
            return AdapterResult.failure(
                "ADAPTER_NOT_RUNNING",
                "robot_state() requires a loaded or running environment",
            )
        return map_isaac_robot_state(self._backend.observe(), self._backend.timestamp_ns)

    def step(self, action: SafeAction) -> AdapterResult[AdapterStepResult]:
        if self._backend.state != "running":
            return AdapterResult.failure(
                "ADAPTER_NOT_RUNNING",
                "step() requires reset() to put the environment into running state",
            )

        command = map_safe_action_to_isaac_command(action)
        if not command.ok or command.value is None:
            return AdapterResult.failure(
                command.errors[0].code if command.errors else "ACTION_MAPPING_FAILED",
                command.errors[0].message if command.errors else "SafeAction mapping failed",
            )

        raw_observation = self._backend.step(command.value)
        observation = map_isaac_observation(raw_observation, self._backend.timestamp_ns)
        state = map_isaac_robot_state(raw_observation, self._backend.timestamp_ns)
        if not observation.ok or observation.value is None:
            return AdapterResult.failure("OBSERVATION_MAPPING_FAILED", "Observation mapping failed")
        if not state.ok or state.value is None:
            return AdapterResult.failure("ROBOT_STATE_MAPPING_FAILED", "Robot state mapping failed")

        return AdapterResult.success(
            AdapterStepResult(
                observation=observation.value,
                robot_state=state.value,
                state=self._backend.state,
            )
        )

    def close(self) -> AdapterResult[AdapterState]:
        return AdapterResult.success(self._backend.close())
