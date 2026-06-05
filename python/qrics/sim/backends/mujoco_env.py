"""MuJoCo-backed local quadruped simulation environment for QRICS.

This backend is the local, real-physics simulation path for development and
presentation on a mid-range laptop.  It deliberately keeps the same lifecycle as
QRICS' SimulationAdapter contract while using MuJoCo's actual `mj_step()` for
state evolution.  The base-velocity behaviour below is a lightweight velocity
servo for demonstration and integration testing; it is not the final gait
controller or reinforcement-learning policy runtime.
"""

from __future__ import annotations

import math
from importlib import import_module, resources
from pathlib import Path
from typing import Final, Protocol, cast

import mujoco

from qrics.sim.commands import MotionCommand, command_from_safe_action
from qrics.sim.observation_mapping import classify_terrain, nearest_obstacle_state
from qrics.sim.runtime_profile import RuntimeProfile, get_runtime_profile
from qrics.sim.schema import (
    AdapterConfig,
    AdapterResult,
    AdapterState,
    AdapterStepResult,
    ContactState,
    ImuSample,
    ObservationPacket,
    Pose,
    Quaternion,
    RobotState,
    SafeAction,
    SceneProfile,
    StabilityState,
    TerrainClass,
    Vec3,
)

FOOT_GEOM_NAMES: Final[tuple[str, str, str, str]] = (
    "fl_foot",
    "fr_foot",
    "rl_foot",
    "rr_foot",
)


class _MujocoViewerModule(Protocol):
    def launch_passive(self, model: object, data: object) -> object: ...


NOMINAL_STANCE: Final[dict[str, float]] = {
    "fl_hip_joint": 0.10,
    "fl_thigh_joint": 0.65,
    "fl_calf_joint": -1.25,
    "fr_hip_joint": -0.10,
    "fr_thigh_joint": 0.65,
    "fr_calf_joint": -1.25,
    "rl_hip_joint": 0.10,
    "rl_thigh_joint": 0.70,
    "rl_calf_joint": -1.30,
    "rr_hip_joint": -0.10,
    "rr_thigh_joint": 0.70,
    "rr_calf_joint": -1.30,
}


class MujocoQuadrupedEnv:
    """Local MuJoCo backend that implements the QRICS Python simulation protocol."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        self._state: AdapterState = "created"
        self._config: AdapterConfig | None = None
        self._scene_profile: SceneProfile | None = None
        self._runtime_profile: RuntimeProfile | None = None
        self._model_path_override = Path(model_path) if model_path is not None else None
        self._model: mujoco.MjModel | None = None
        self._data: mujoco.MjData | None = None
        self._viewer: object | None = None
        self._last_command = MotionCommand(stop=True)
        self._step_count = 0

    def name(self) -> str:
        return "mujoco"

    def state(self) -> AdapterState:
        return self._state

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        """Load the MJCF asset and create the MuJoCo model/data pair."""
        try:
            runtime_profile = get_runtime_profile(config.runtime_profile)
            model_path = self._resolve_model_path()
            model = mujoco.MjModel.from_xml_path(str(model_path))
            model.opt.timestep = runtime_profile.physics_timestep_s
            data = mujoco.MjData(model)
        except Exception as exc:  # pragma: no cover - depends on host MuJoCo install
            self._state = "error"
            return AdapterResult.failure(
                "MUJOCO_INITIALIZE_FAILED",
                f"Failed to initialize MuJoCo backend: {exc}",
            )

        self._config = config
        self._runtime_profile = runtime_profile
        self._model = model
        self._data = data
        self._state = "initialized"
        return AdapterResult.success(self._state)

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[SceneProfile]:
        if self._state not in {"initialized", "scene_loaded", "running", "stopped"}:
            return AdapterResult.failure(
                "BACKEND_NOT_INITIALIZED",
                "initialize() must succeed before load_scene().",
            )

        self._scene_profile = scene_profile
        self._state = "scene_loaded"
        return AdapterResult.success(scene_profile)

    def reset(self) -> AdapterResult[AdapterStepResult]:
        if self._model is None or self._data is None:
            return AdapterResult.failure("MUJOCO_NOT_READY", "MuJoCo model/data are not available.")
        if self._state != "scene_loaded":
            return AdapterResult.failure(
                "SCENE_NOT_LOADED", "load_scene() must be called before reset()."
            )

        mujoco.mj_resetData(self._model, self._data)
        self._data.qpos[0] = 0.0
        self._data.qpos[1] = 0.0
        self._data.qpos[2] = 0.38
        self._data.qpos[3] = 1.0
        self._data.qpos[4] = 0.0
        self._data.qpos[5] = 0.0
        self._data.qpos[6] = 0.0
        self._data.qvel[:] = 0.0
        self._data.ctrl[:] = 0.0
        self._data.xfrc_applied[:, :] = 0.0
        self._apply_nominal_stance()
        self._step_count = 0
        self._last_command = MotionCommand(stop=True)
        mujoco.mj_forward(self._model, self._data)

        viewer_result = self._ensure_viewer_if_requested()
        if not viewer_result.ok:
            return viewer_result

        self._state = "running"
        return self._make_step_result()

    def step(self, safe_action: SafeAction) -> AdapterResult[AdapterStepResult]:
        if self._model is None or self._data is None:
            return AdapterResult.failure("MUJOCO_NOT_READY", "MuJoCo model/data are not available.")
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

        self._last_command = command_result.value
        control_decimation = (
            self._runtime_profile.control_decimation if self._runtime_profile else 10
        )
        for _ in range(max(1, control_decimation)):
            self._apply_command(self._last_command)
            mujoco.mj_step(self._model, self._data)
            self._step_count += 1

        self._sync_viewer()
        return self._make_step_result()

    def observe(self) -> AdapterResult[ObservationPacket]:
        if self._model is None or self._data is None:
            return AdapterResult.failure("MUJOCO_NOT_READY", "MuJoCo model/data are not available.")
        if self._state not in {"scene_loaded", "running"}:
            return AdapterResult.failure(
                "BACKEND_NOT_RUNNING", "observe() requires a loaded scene."
            )
        return AdapterResult.success(self._make_observation())

    def robot_state(self) -> AdapterResult[RobotState]:
        if self._model is None or self._data is None:
            return AdapterResult.failure("MUJOCO_NOT_READY", "MuJoCo model/data are not available.")
        if self._state not in {"scene_loaded", "running"}:
            return AdapterResult.failure(
                "BACKEND_NOT_RUNNING", "robot_state() requires a loaded scene."
            )
        return AdapterResult.success(self._make_robot_state())

    def close(self) -> AdapterResult[AdapterState]:
        self._close_viewer()
        self._state = "stopped"
        return AdapterResult.success(self._state)

    def _resolve_model_path(self) -> Path:
        if self._model_path_override is not None:
            return self._model_path_override

        try:
            asset = resources.files("qrics.sim.assets.quadrupeds").joinpath(
                "qrics_mini_quadruped.xml"
            )
            with resources.as_file(asset) as asset_path:
                return Path(asset_path)
        except Exception:
            return (
                Path(__file__).resolve().parents[1]
                / "assets"
                / "quadrupeds"
                / "qrics_mini_quadruped.xml"
            )

    def _ensure_viewer_if_requested(self) -> AdapterResult[AdapterStepResult]:
        if self._runtime_profile is None or self._runtime_profile.render_mode != "viewer":
            # The caller only inspects ok/errors for viewer startup.
            return AdapterResult.success(self._make_uninitialized_step_result())
        if self._viewer is not None:
            return AdapterResult.success(self._make_uninitialized_step_result())
        if self._model is None or self._data is None:
            return AdapterResult.failure("MUJOCO_NOT_READY", "MuJoCo model/data are not available.")

        try:  # pragma: no cover - viewer depends on local display server
            viewer = cast(_MujocoViewerModule, import_module("mujoco.viewer"))
            self._viewer = viewer.launch_passive(self._model, self._data)
        except Exception as exc:
            return AdapterResult.failure(
                "MUJOCO_VIEWER_FAILED",
                "MuJoCo physics initialized, but viewer startup failed. "
                "Use runtime_profile='headless_fast' or fix local display/GL settings. "
                f"Detail: {exc}",
            )
        return AdapterResult.success(self._make_uninitialized_step_result())

    def _make_uninitialized_step_result(self) -> AdapterStepResult:
        return AdapterStepResult(
            observation=ObservationPacket(observation_id="viewer_startup_placeholder"),
            robot_state=RobotState(),
            state=self._state,
        )

    def _close_viewer(self) -> None:
        if self._viewer is None:
            return
        close = getattr(self._viewer, "close", None)
        if callable(close):
            close()
        self._viewer = None

    def _sync_viewer(self) -> None:
        if self._viewer is None:
            return
        sync = getattr(self._viewer, "sync", None)
        if callable(sync):  # pragma: no cover - viewer depends on local display server
            sync()

    def _apply_nominal_stance(self) -> None:
        assert self._model is not None
        assert self._data is not None
        for joint_name, value in NOMINAL_STANCE.items():
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                continue
            qpos_adr = self._model.jnt_qposadr[joint_id]
            self._data.qpos[qpos_adr] = value

        for actuator_index in range(self._model.nu):
            actuator_name = mujoco.mj_id2name(
                self._model,
                mujoco.mjtObj.mjOBJ_ACTUATOR,
                actuator_index,
            )
            joint_name = actuator_name.removesuffix("_pos") + "_joint" if actuator_name else ""
            if joint_name in NOMINAL_STANCE:
                self._data.ctrl[actuator_index] = NOMINAL_STANCE[joint_name]

    def _apply_command(self, command: MotionCommand) -> None:
        assert self._model is not None
        assert self._data is not None
        self._data.xfrc_applied[:, :] = 0.0
        self._apply_nominal_stance()

        if command.stop or command.safe_stand:
            self._apply_base_velocity_servo(Vec3(), 0.0, stop_mode=True)
            return

        self._apply_base_velocity_servo(
            command.linear_velocity, command.yaw_rate_radps, stop_mode=False
        )

    def _apply_base_velocity_servo(
        self, target_velocity: Vec3, yaw_rate: float, *, stop_mode: bool
    ) -> None:
        """Apply a lightweight body-level velocity servo for demo-level locomotion.

        This intentionally uses MuJoCo external forces and joint position targets to
        produce visible, physics-integrated motion without pretending to be a final
        quadruped gait controller.
        """
        assert self._model is not None
        assert self._data is not None
        base_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, "base")
        if base_id < 0:
            return

        current_vx = self._qvel(0)
        current_vy = self._qvel(1)
        current_yaw_rate = self._qvel(5)

        linear_gain = 35.0 if stop_mode else 22.0
        yaw_gain = 8.0 if stop_mode else 5.0
        fx = linear_gain * (target_velocity.x - current_vx)
        fy = linear_gain * (target_velocity.y - current_vy)
        tz = yaw_gain * (yaw_rate - current_yaw_rate)

        # Keep forces modest so the demo remains stable on small laptop runs.
        self._data.xfrc_applied[base_id, 0] = max(-45.0, min(45.0, fx))
        self._data.xfrc_applied[base_id, 1] = max(-35.0, min(35.0, fy))
        self._data.xfrc_applied[base_id, 5] = max(-12.0, min(12.0, tz))

        if not stop_mode:
            self._apply_demo_leg_phase(target_velocity.x, yaw_rate)

    def _apply_demo_leg_phase(self, forward_velocity: float, yaw_rate: float) -> None:
        assert self._model is not None
        assert self._data is not None
        phase = self._step_count * 0.045
        amplitude = max(0.0, min(0.16, abs(forward_velocity) * 0.12 + abs(yaw_rate) * 0.05))
        diagonal_a = math.sin(phase) * amplitude
        diagonal_b = math.sin(phase + math.pi) * amplitude
        adjustments = {
            "fl_thigh_joint": diagonal_a,
            "rr_thigh_joint": diagonal_a,
            "fr_thigh_joint": diagonal_b,
            "rl_thigh_joint": diagonal_b,
            "fl_calf_joint": -0.5 * diagonal_a,
            "rr_calf_joint": -0.5 * diagonal_a,
            "fr_calf_joint": -0.5 * diagonal_b,
            "rl_calf_joint": -0.5 * diagonal_b,
        }
        for actuator_index in range(self._model.nu):
            actuator_name = mujoco.mj_id2name(
                self._model,
                mujoco.mjtObj.mjOBJ_ACTUATOR,
                actuator_index,
            )
            joint_name = actuator_name.removesuffix("_pos") + "_joint" if actuator_name else ""
            if joint_name in adjustments:
                nominal = NOMINAL_STANCE.get(joint_name, 0.0)
                self._data.ctrl[actuator_index] = nominal + adjustments[joint_name]

    def _qvel(self, index: int) -> float:
        """Return a generalized velocity component safely across MuJoCo bindings.

        MuJoCo stores the generalized velocity dimension on MjModel.nv.  MjData
        exposes the qvel array but does not expose an nv attribute in current
        Python bindings, so using data.nv raises AttributeError on real MuJoCo
        installs.
        """
        assert self._model is not None
        assert self._data is not None
        if index < 0 or index >= int(self._model.nv):
            return 0.0
        return float(self._data.qvel[index])

    def _make_step_result(self) -> AdapterResult[AdapterStepResult]:
        observation = self._make_observation()
        robot_state = self._make_robot_state()
        return AdapterResult.success(
            AdapterStepResult(
                observation=observation,
                robot_state=robot_state,
                state=self._state,
            )
        )

    def _make_observation(self) -> ObservationPacket:
        assert self._model is not None
        assert self._data is not None
        robot_state = self._make_robot_state()
        return ObservationPacket(
            observation_id=f"mujoco_obs_{self._step_count}",
            timestamp_ns=self._timestamp_ns(),
            imu=ImuSample(
                linear_acceleration=Vec3(0.0, 0.0, 9.81),
                angular_velocity=robot_state.angular_velocity,
                orientation=robot_state.pose.orientation,
                source_quality="estimated",
            ),
            contacts=robot_state.contacts,
            base_pose=robot_state.pose,
            linear_velocity=robot_state.linear_velocity,
            angular_velocity=robot_state.angular_velocity,
            terrain_class=self._terrain_class(),
            obstacle_state=nearest_obstacle_state(self._scene_profile, robot_state.pose.position),
        )

    def _make_robot_state(self) -> RobotState:
        assert self._data is not None
        position = self._position()
        orientation = Quaternion(
            w=float(self._data.qpos[3]),
            x=float(self._data.qpos[4]),
            y=float(self._data.qpos[5]),
            z=float(self._data.qpos[6]),
        )
        linear_velocity = Vec3(
            x=self._qvel(0),
            y=self._qvel(1),
            z=self._qvel(2),
        )
        angular_velocity = Vec3(
            x=self._qvel(3),
            y=self._qvel(4),
            z=self._qvel(5),
        )
        risk_score = self._orientation_risk(orientation, position.z)
        stability_state = self._stability_state(position.z, risk_score)

        return RobotState(
            timestamp_ns=self._timestamp_ns(),
            pose=Pose(position=position, orientation=orientation),
            linear_velocity=linear_velocity,
            angular_velocity=angular_velocity,
            contacts=self._contacts(),
            terrain_class=self._terrain_class(),
            stability_state=stability_state,
            risk_score=risk_score,
        )

    def _contacts(self) -> tuple[ContactState, ...]:
        assert self._model is not None
        assert self._data is not None
        contact_map: dict[str, float] = {name: 0.0 for name in FOOT_GEOM_NAMES}

        for contact_index in range(self._data.ncon):
            contact = self._data.contact[contact_index]
            geom_names = (
                mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom1) or "",
                mujoco.mj_id2name(self._model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom2) or "",
            )
            foot_name = next((name for name in geom_names if name in contact_map), "")
            if not foot_name:
                continue
            normal_force = self._contact_normal_force(contact_index)
            contact_map[foot_name] += normal_force

        return tuple(
            ContactState(
                foot_name=name.removesuffix("_foot"),
                in_contact=force > 0.0,
                normal_force_n=force,
            )
            for name, force in contact_map.items()
        )

    def _contact_normal_force(self, contact_index: int) -> float:
        assert self._model is not None
        assert self._data is not None
        try:
            import numpy as np

            force = np.zeros(6, dtype=float)
            mujoco.mj_contactForce(self._model, self._data, contact_index, force)
            return float(abs(force[0]))
        except Exception:
            return 1.0

    def _orientation_risk(self, orientation: Quaternion, base_height_m: float) -> float:
        roll, pitch = _roll_pitch_from_quat(orientation)
        attitude_risk = max(abs(roll), abs(pitch)) / 0.85
        height_risk = max(0.0, 0.24 - base_height_m) / 0.24
        return max(0.0, min(1.0, max(attitude_risk, height_risk)))

    def _stability_state(self, base_height_m: float, risk_score: float) -> StabilityState:
        if base_height_m < 0.16 or risk_score >= 0.95:
            return "fallen"
        if risk_score >= 0.55:
            return "unstable"
        return "stable"

    def _terrain_class(self) -> TerrainClass:
        if self._data is None:
            return "unknown"
        return classify_terrain(self._scene_profile, self._position())

    def _position(self) -> Vec3:
        assert self._data is not None
        return Vec3(
            x=float(self._data.qpos[0]),
            y=float(self._data.qpos[1]),
            z=float(self._data.qpos[2]),
        )

    def _timestamp_ns(self) -> int:
        if self._data is None:
            return 0
        return int(float(self._data.time) * 1_000_000_000)


def _roll_pitch_from_quat(quat: Quaternion) -> tuple[float, float]:
    sinr_cosp = 2.0 * (quat.w * quat.x + quat.y * quat.z)
    cosr_cosp = 1.0 - 2.0 * (quat.x * quat.x + quat.y * quat.y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (quat.w * quat.y - quat.z * quat.x)
    pitch = math.copysign(math.pi / 2.0, sinp) if abs(sinp) >= 1.0 else math.asin(sinp)
    return roll, pitch
