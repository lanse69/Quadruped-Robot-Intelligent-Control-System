"""Deterministic non-physics backend for QRICS simulation contract tests.

This backend is intentionally simple and must not be used as the real physics
presentation path.  Use `MujocoQuadrupedEnv` for local physical simulation and
reserve this class for fast unit tests, API smoke tests and environments where a
MuJoCo installation is not available.
"""

from __future__ import annotations

from qrics.sim.commands import command_from_safe_action
from qrics.sim.observation_mapping import (
    ObstacleMappingConfig,
    classify_terrain,
    nearest_obstacle_state,
)
from qrics.sim.runtime_profile import get_runtime_profile
from qrics.sim.schema import (
    AdapterConfig,
    AdapterResult,
    AdapterState,
    AdapterStepResult,
    ContactState,
    ImuSample,
    ObservationPacket,
    Pose,
    RobotState,
    SafeAction,
    SceneProfile,
    TerrainClass,
    Vec3,
)


class MinimalQuadrupedEnv:
    """Small in-process backend that mimics the QRICS simulation lifecycle."""

    def __init__(self) -> None:
        self._state: AdapterState = "created"
        self._timestamp_ns = 0
        self._position_x = 0.0
        self._position_y = 0.0
        self._yaw = 0.0
        self._last_linear_velocity = Vec3()
        self._last_yaw_rate = 0.0
        self._scene: SceneProfile | None = None
        self._config: AdapterConfig | None = None

    def name(self) -> str:
        return "minimal"

    def state(self) -> AdapterState:
        return self._state

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        self._config = config
        self._state = "initialized"
        return AdapterResult.success(self._state)

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[SceneProfile]:
        if self._state not in {"initialized", "scene_loaded", "running", "stopped"}:
            return AdapterResult.failure(
                "BACKEND_NOT_INITIALIZED",
                "initialize() must be called before load_scene().",
            )
        self._scene = scene_profile
        self._state = "scene_loaded"
        return AdapterResult.success(scene_profile)

    def reset(self) -> AdapterResult[AdapterStepResult]:
        if self._state != "scene_loaded":
            return AdapterResult.failure(
                "SCENE_NOT_LOADED", "load_scene() must be called before reset()."
            )
        self._timestamp_ns = 0
        self._position_x = 0.0
        self._position_y = 0.0
        self._yaw = 0.0
        self._last_linear_velocity = Vec3()
        self._last_yaw_rate = 0.0
        self._state = "running"
        return self._step_result()

    def step(self, safe_action: SafeAction) -> AdapterResult[AdapterStepResult]:
        if self._state != "running":
            return AdapterResult.failure(
                "BACKEND_NOT_RUNNING", "reset() must be called before step()."
            )

        command_result = command_from_safe_action(safe_action)
        if not command_result.ok or command_result.value is None:
            return AdapterResult.failure(
                (
                    command_result.errors[0].code
                    if command_result.errors
                    else "COMMAND_MAPPING_FAILED"
                ),
                (
                    command_result.errors[0].message
                    if command_result.errors
                    else "SafeAction mapping failed."
                ),
            )

        dt_s = self._control_dt_s()
        command = command_result.value
        if command.stop or command.safe_stand:
            self._last_linear_velocity = Vec3()
            self._last_yaw_rate = 0.0
        else:
            self._last_linear_velocity = command.linear_velocity
            self._last_yaw_rate = command.yaw_rate_radps
            self._position_x += command.linear_velocity.x * dt_s
            self._position_y += command.linear_velocity.y * dt_s
            self._yaw += command.yaw_rate_radps * dt_s
        self._timestamp_ns += int(dt_s * 1_000_000_000)
        return self._step_result()

    def observe(self) -> AdapterResult[ObservationPacket]:
        if self._state not in {"scene_loaded", "running"}:
            return AdapterResult.failure(
                "BACKEND_NOT_RUNNING", "observe() requires a loaded scene."
            )
        return AdapterResult.success(self._observation())

    def robot_state(self) -> AdapterResult[RobotState]:
        if self._state not in {"scene_loaded", "running"}:
            return AdapterResult.failure(
                "BACKEND_NOT_RUNNING", "robot_state() requires a loaded scene."
            )
        return AdapterResult.success(self._robot_state())

    def close(self) -> AdapterResult[AdapterState]:
        self._state = "stopped"
        return AdapterResult.success(self._state)

    def _control_dt_s(self) -> float:
        if self._config is None:
            return 0.04
        try:
            profile = get_runtime_profile(self._config.runtime_profile)
        except ValueError:
            return 0.04
        return profile.physics_timestep_s * max(1, profile.control_decimation)

    def _step_result(self) -> AdapterResult[AdapterStepResult]:
        return AdapterResult.success(
            AdapterStepResult(
                observation=self._observation(),
                robot_state=self._robot_state(),
                state=self._state,
            )
        )

    def _observation(self) -> ObservationPacket:
        state = self._robot_state()
        return ObservationPacket(
            observation_id=f"minimal_obs_{self._timestamp_ns}",
            timestamp_ns=self._timestamp_ns,
            imu=ImuSample(
                linear_acceleration=Vec3(0.0, 0.0, 9.81),
                angular_velocity=state.angular_velocity,
                orientation=state.pose.orientation,
                source_quality="estimated",
            ),
            contacts=state.contacts,
            base_pose=state.pose,
            linear_velocity=state.linear_velocity,
            angular_velocity=state.angular_velocity,
            terrain_class=state.terrain_class,
            obstacle_state=nearest_obstacle_state(
                self._scene,
                state.pose.position,
                config=ObstacleMappingConfig(source_quality="estimated"),
            ),
        )

    def _robot_state(self) -> RobotState:
        terrain_class = self._terrain_class()
        return RobotState(
            timestamp_ns=self._timestamp_ns,
            pose=Pose(
                position=self._robot_position(),
            ),
            linear_velocity=self._last_linear_velocity,
            angular_velocity=Vec3(0.0, 0.0, self._last_yaw_rate),
            contacts=(
                ContactState("front_left", True, 25.0),
                ContactState("front_right", True, 25.0),
                ContactState("rear_left", True, 25.0),
                ContactState("rear_right", True, 25.0),
            ),
            terrain_class=terrain_class,
            stability_state="stable",
            risk_score=0.0,
        )

    def _terrain_class(self) -> TerrainClass:
        return classify_terrain(self._scene, self._robot_position())

    def _robot_position(self) -> Vec3:
        return Vec3(self._position_x, self._position_y, 0.35)
