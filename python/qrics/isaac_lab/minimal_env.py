"""A deterministic lightweight backend used before real Isaac Lab is available."""

from __future__ import annotations

from qrics.isaac_lab.action_mapper import IsaacCommand
from qrics.isaac_lab.schema import AdapterConfig, AdapterState, SceneProfile


class MinimalQuadrupedEnv:
    """Small in-process environment that mimics the adapter lifecycle contract."""

    def __init__(self) -> None:
        self._state: AdapterState = "created"
        self._timestamp_ns = 0
        self._position_x = 0.0
        self._scene: SceneProfile | None = None
        self._config: AdapterConfig | None = None

    @property
    def state(self) -> AdapterState:
        return self._state

    def initialize(self, config: AdapterConfig) -> AdapterState:
        self._config = config
        self._state = "initialized"
        return self._state

    def load_scene(self, scene_profile: SceneProfile) -> AdapterState:
        self._scene = scene_profile
        self._state = "scene_loaded"
        return self._state

    def reset(self) -> dict[str, object]:
        self._timestamp_ns = 0
        self._position_x = 0.0
        self._state = "running"
        return self.observe()

    def step(self, command: IsaacCommand) -> dict[str, object]:
        self._timestamp_ns += 10_000_000
        self._position_x += float(command.get("linear_x_mps", 0.0)) * 0.01
        self._state = "running"
        return self.observe()

    def observe(self) -> dict[str, object]:
        terrain_class = self._scene.terrain_pack if self._scene is not None else "flat"
        return {
            "observation_id": f"obs_{self._timestamp_ns}",
            "base_position": [self._position_x, 0.0, 0.35],
            "base_orientation": [1.0, 0.0, 0.0, 0.0],
            "linear_velocity": [0.0, 0.0, 0.0],
            "angular_velocity": [0.0, 0.0, 0.0],
            "imu_linear_acceleration": [0.0, 0.0, 9.81],
            "imu_angular_velocity": [0.0, 0.0, 0.0],
            "imu_orientation": [1.0, 0.0, 0.0, 0.0],
            "terrain_class": terrain_class,
            "stability_state": "stable",
            "risk_score": 0.0,
            "contacts": [
                {"foot_name": "front_left", "in_contact": True, "normal_force_n": 25.0},
                {"foot_name": "front_right", "in_contact": True, "normal_force_n": 25.0},
                {"foot_name": "rear_left", "in_contact": True, "normal_force_n": 25.0},
                {"foot_name": "rear_right", "in_contact": True, "normal_force_n": 25.0},
            ],
        }

    def close(self) -> AdapterState:
        self._state = "stopped"
        return self._state

    @property
    def timestamp_ns(self) -> int:
        return self._timestamp_ns
