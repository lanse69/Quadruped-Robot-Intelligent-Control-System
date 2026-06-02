"""Simulation adapter facade shared by local and high-fidelity backends."""

from __future__ import annotations

from qrics.sim.backend_protocol import SimulationBackend
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


class SimulationAdapterFacade:
    def __init__(self, backend: SimulationBackend) -> None:
        self._backend = backend

    def name(self) -> str:
        return self._backend.name()

    def state(self) -> AdapterState:
        return self._backend.state()

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        return self._backend.initialize(config)

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[SceneProfile]:
        return self._backend.load_scene(scene_profile)

    def reset(self) -> AdapterResult[AdapterStepResult]:
        return self._backend.reset()

    def step(self, safe_action: SafeAction) -> AdapterResult[AdapterStepResult]:
        return self._backend.step(safe_action)

    def observe(self) -> AdapterResult[ObservationPacket]:
        return self._backend.observe()

    def robot_state(self) -> AdapterResult[RobotState]:
        return self._backend.robot_state()

    def close(self) -> AdapterResult[AdapterState]:
        return self._backend.close()
