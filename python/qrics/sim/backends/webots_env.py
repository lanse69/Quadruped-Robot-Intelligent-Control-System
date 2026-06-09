"""Webots-backed local visual simulation backend for QRICS.

The backend implements the same QRICS simulation protocol as the Minimal and
MuJoCo backends.  It keeps deterministic Python-side state for API responses and
can materialize a Webots world/controller bundle for actual local presentation
when the ``webots`` executable is available.  Tests use ``execute_webots=False``
so the contract is verified without requiring Webots in CI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Final

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
    TerrainClass,
    Vec3,
)

WEBOTS_RUN_SPEC_NAME: Final[str] = "qrics_webots_run.json"
WEBOTS_RUN_OUTPUT_NAME: Final[str] = "qrics_webots_output.json"


@dataclass(frozen=True)
class WebotsCommandFrame:
    duration_s: float
    vx: float = 0.0
    vy: float = 0.0
    yaw_rate: float = 0.0
    stop: bool = False

    def to_json(self) -> dict[str, float | bool]:
        return {
            "duration_s": self.duration_s,
            "vx": self.vx,
            "vy": self.vy,
            "yaw_rate": self.yaw_rate,
            "stop": self.stop,
        }


@dataclass
class WebotsRunBundle:
    workspace: Path
    world_path: Path
    controller_path: Path
    spec_path: Path
    output_path: Path
    commands: list[WebotsCommandFrame] = field(default_factory=list)


class WebotsQuadrupedEnv:
    """Local Webots backend with QRICS lifecycle-compatible methods."""

    def __init__(
        self,
        *,
        webots_binary: str | None = None,
        execute_webots: bool = True,
        command_dir: str | Path | None = None,
    ) -> None:
        self._state: AdapterState = "created"
        self._config: AdapterConfig | None = None
        self._scene: SceneProfile | None = None
        self._runtime_profile: RuntimeProfile | None = None
        self._webots_binary_override = webots_binary
        self._execute_webots = execute_webots
        self._command_dir = (
            Path(command_dir) if command_dir is not None and str(command_dir) else None
        )
        self._position = Vec3(0.0, 0.0, 0.32)
        self._yaw_rad = 0.0
        self._last_linear_velocity = Vec3()
        self._last_yaw_rate = 0.0
        self._last_command = MotionCommand(stop=True)
        self._timestamp_ns = 0
        self._commands: list[WebotsCommandFrame] = []
        self._last_output: dict[str, object] = {}

    def name(self) -> str:
        return "webots"

    def state(self) -> AdapterState:
        return self._state

    def initialize(self, config: AdapterConfig) -> AdapterResult[AdapterState]:
        try:
            runtime_profile = get_runtime_profile(config.runtime_profile)
        except ValueError as exc:
            self._state = "error"
            return AdapterResult.failure("WEBOTS_PROFILE_INVALID", str(exc))

        if self._execute_webots and self._resolve_webots_binary() is None:
            self._state = "error"
            return AdapterResult.failure(
                "WEBOTS_BINARY_NOT_FOUND",
                "Webots executable was not found. Install Webots, add `webots` to PATH, "
                "or run this backend with execute_webots=False for contract-only tests.",
            )

        self._config = config
        self._runtime_profile = runtime_profile
        self._state = "initialized"
        return AdapterResult.success(self._state)

    def load_scene(self, scene_profile: SceneProfile) -> AdapterResult[SceneProfile]:
        if self._state not in {"initialized", "scene_loaded", "running", "stopped"}:
            return AdapterResult.failure(
                "BACKEND_NOT_INITIALIZED", "initialize() must succeed before load_scene()."
            )
        self._scene = scene_profile
        self._state = "scene_loaded"
        return AdapterResult.success(scene_profile)

    def reset(self) -> AdapterResult[AdapterStepResult]:
        if self._state != "scene_loaded":
            return AdapterResult.failure(
                "SCENE_NOT_LOADED", "load_scene() must be called before reset()."
            )
        self._position = Vec3(0.0, 0.0, 0.32)
        self._yaw_rad = 0.0
        self._last_linear_velocity = Vec3()
        self._last_yaw_rate = 0.0
        self._last_command = MotionCommand(stop=True)
        self._timestamp_ns = 0
        self._commands.clear()
        self._last_output.clear()
        self._state = "running"
        return self._make_step_result()

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

        command = command_result.value
        self._last_command = command
        duration_s = self._control_dt_s()
        self._apply_command(command, duration_s)
        self._commands.append(
            WebotsCommandFrame(
                duration_s=duration_s,
                vx=self._last_linear_velocity.x,
                vy=self._last_linear_velocity.y,
                yaw_rate=self._last_yaw_rate,
                stop=command.stop or command.safe_stand,
            )
        )
        return self._make_step_result()

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
        if self._execute_webots and (self._commands or self._command_dir is not None):
            run_result = self._run_webots_bundle()
            if not run_result.ok:
                self._state = "error"
                return run_result
        self._state = "stopped"
        return AdapterResult.success(self._state)

    def last_webots_output(self) -> dict[str, object]:
        return dict(self._last_output)

    def _apply_command(self, command: MotionCommand, duration_s: float) -> None:
        if command.stop or command.safe_stand:
            self._last_linear_velocity = Vec3()
            self._last_yaw_rate = 0.0
        else:
            self._last_linear_velocity = command.linear_velocity
            self._last_yaw_rate = command.yaw_rate_radps
            self._position = Vec3(
                x=self._position.x + command.linear_velocity.x * duration_s,
                y=self._position.y + command.linear_velocity.y * duration_s,
                z=self._position.z,
            )
            self._yaw_rad += command.yaw_rate_radps * duration_s
        self._timestamp_ns += int(duration_s * 1_000_000_000)

    def _make_step_result(self) -> AdapterResult[AdapterStepResult]:
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
            observation_id=f"webots_obs_{self._timestamp_ns}",
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
            obstacle_state=nearest_obstacle_state(self._scene, state.pose.position),
        )

    def _robot_state(self) -> RobotState:
        return RobotState(
            timestamp_ns=self._timestamp_ns,
            pose=Pose(
                position=self._position,
                orientation=Quaternion(w=1.0, x=0.0, y=0.0, z=0.0),
            ),
            linear_velocity=self._last_linear_velocity,
            angular_velocity=Vec3(0.0, 0.0, self._last_yaw_rate),
            contacts=self._contacts(),
            terrain_class=self._terrain_class(),
            stability_state="stable",
            risk_score=0.0,
        )

    def _contacts(self) -> tuple[ContactState, ...]:
        hint = self._last_command.locomotion_hint
        if not hint.enabled or not hint.feet:
            return (
                ContactState("front_left", True, 20.0),
                ContactState("front_right", True, 20.0),
                ContactState("rear_left", True, 20.0),
                ContactState("rear_right", True, 20.0),
            )
        return tuple(
            ContactState(
                foot.foot_name,
                foot.phase == "stance",
                20.0 if foot.phase == "stance" else 0.0,
            )
            for foot in hint.feet
        )

    def _terrain_class(self) -> TerrainClass:
        return classify_terrain(self._scene, self._position)

    def _control_dt_s(self) -> float:
        profile = self._runtime_profile
        if profile is None:
            return 0.032
        return profile.physics_timestep_s * max(1, profile.control_decimation)

    def _resolve_webots_binary(self) -> str | None:
        if self._webots_binary_override:
            return self._webots_binary_override
        return shutil.which("webots") or (
            "/snap/bin/webots" if Path("/snap/bin/webots").exists() else None
        )

    def _run_webots_bundle(self) -> AdapterResult[AdapterState]:
        webots_binary = self._resolve_webots_binary()
        if webots_binary is None:
            return AdapterResult.failure(
                "WEBOTS_BINARY_NOT_FOUND", "Webots executable was not found."
            )

        workspace = self._prepare_bundle_workspace()
        cleanup_workspace = self._should_cleanup_workspace()
        try:
            bundle = self._materialize_bundle(workspace)
            hold_seconds = _webots_hold_seconds()
            bundle.spec_path.write_text(
                json.dumps(
                    {
                        "initial_position": [0.0, 0.0, 0.32],
                        "terrain_pack": (
                            self._scene.terrain_pack if self._scene is not None else "flat"
                        ),
                        "hold_seconds": hold_seconds,
                        "command_dir": (
                            str(self._command_dir) if self._command_dir is not None else ""
                        ),
                        "commands": [frame.to_json() for frame in bundle.commands],
                        "terrain_regions": _scene_terrain_regions_to_json(self._scene),
                        "checkpoints": _scene_checkpoints_to_json(self._scene),
                        "forbidden_zones": _scene_forbidden_zones_to_json(self._scene),
                        "obstacles": _scene_obstacles_to_json(self._scene),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            env = {
                **dict(os.environ),
                "QRICS_WEBOTS_RUN_SPEC": str(bundle.spec_path),
                "QRICS_WEBOTS_RUN_OUTPUT": str(bundle.output_path),
            }
            mode_args = ["--batch", "--mode=fast"]
            viewer_mode = (
                self._runtime_profile is not None and self._runtime_profile.render_mode == "viewer"
            )
            if viewer_mode:
                mode_args = []
            started_at = time.monotonic()
            completed = subprocess.run(
                [webots_binary, *mode_args, str(bundle.world_path)],
                check=False,
                text=True,
                capture_output=True,
                env=env,
                timeout=max(
                    10.0,
                    len(bundle.commands) * self._control_dt_s() + hold_seconds + 10.0,
                ),
            )
            elapsed_s = time.monotonic() - started_at
            if completed.returncode != 0:
                return AdapterResult.failure(
                    "WEBOTS_RUN_FAILED",
                    f"Webots exited with {completed.returncode}: {completed.stderr[-500:]}",
                )
            if bundle.output_path.exists():
                self._last_output = json.loads(bundle.output_path.read_text(encoding="utf-8"))
            # Some Linux/Snap Webots launchers return after delegating to the GUI
            # process.  In that case the QRICS wrapper process would exit and the
            # previous TemporaryDirectory cleanup removed the world/controller/spec
            # while Webots was still starting, which looked like an immediate crash.
            # Keep the wrapper and files alive for presentation sessions.
            if self._command_dir is not None and viewer_mode and elapsed_s < 2.0:
                time.sleep(min(max(0.0, hold_seconds - elapsed_s), hold_seconds))
        except subprocess.TimeoutExpired as exc:
            return AdapterResult.failure("WEBOTS_RUN_TIMEOUT", f"Webots run timed out: {exc}")
        except Exception as exc:
            return AdapterResult.failure("WEBOTS_RUN_FAILED", f"Webots run failed: {exc}")
        finally:
            if cleanup_workspace:
                shutil.rmtree(workspace, ignore_errors=True)
        return AdapterResult.success(self._state)

    def _prepare_bundle_workspace(self) -> Path:
        if self._command_dir is not None:
            workspace = self._command_dir.parent / "webots_bundle"
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)
            workspace.mkdir(parents=True, exist_ok=True)
            return workspace
        return create_webots_workspace(prefix="qrics_webots_")

    def _should_cleanup_workspace(self) -> bool:
        # Viewer workspaces intentionally remain available.  Webots may detach
        # from the launching wrapper and read controller/spec files after the
        # wrapper command has already returned.  Batch/headless runs still clean up.
        if self._runtime_profile is not None and self._runtime_profile.render_mode == "viewer":
            return False
        return self._command_dir is None

    def _materialize_bundle(self, workspace: Path) -> WebotsRunBundle:
        worlds = workspace / "worlds"
        controller_dir = workspace / "controllers" / "qrics_controller"
        worlds.mkdir(parents=True, exist_ok=True)
        controller_dir.mkdir(parents=True, exist_ok=True)

        world_path = worlds / "qrics_demo.wbt"
        controller_path = controller_dir / "qrics_controller.py"
        _copy_package_resource("qrics.sim.assets.webots.worlds", "qrics_demo.wbt", world_path)
        _copy_package_resource(
            "qrics.sim.assets.webots.controllers.qrics_controller",
            "qrics_controller.py",
            controller_path,
        )
        return WebotsRunBundle(
            workspace=workspace,
            world_path=world_path,
            controller_path=controller_path,
            spec_path=workspace / WEBOTS_RUN_SPEC_NAME,
            output_path=workspace / WEBOTS_RUN_OUTPUT_NAME,
            commands=list(self._commands),
        )


def _webots_hold_seconds() -> float:
    raw = os.environ.get("QRICS_WEBOTS_HOLD_SECONDS", "").strip()
    if not raw:
        # Presentation mode should stay visible long enough for a defence/demo.
        # Set QRICS_WEBOTS_HOLD_SECONDS=0 for one-shot batch runs.
        return 120.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 120.0


def create_webots_workspace(*, prefix: str = "qrics_webots_") -> Path:
    """Create a Webots-readable workspace outside system temporary directories.

    Snap-packaged Webots runs with a private /tmp namespace and can fail to
    open worlds/controllers/spec files created under Python's system temp dir.
    Keep generated QRICS Webots bundles under a normal, non-hidden directory in
    the user's home directory unless QRICS_WEBOTS_WORKSPACE_DIR overrides it.
    """

    root = _webots_workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=str(root)))


def _webots_workspace_root() -> Path:
    override = os.environ.get("QRICS_WEBOTS_WORKSPACE_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / "qrics_webots_runs"


def _scene_terrain_regions_to_json(scene: SceneProfile | None) -> list[dict[str, object]]:
    if scene is None:
        return []
    return [
        {
            "id": region.region_id,
            "terrain_class": region.terrain_class,
            "position": [region.center.x, region.center.y, region.center.z],
            "size": [region.size.x, region.size.y, region.size.z],
            "slope_deg": region.slope_deg,
            "roughness_m": region.roughness_m,
            "step_height_m": region.step_height_m,
            "step_count": region.step_count,
        }
        for region in scene.terrain_regions
    ]


def _scene_checkpoints_to_json(scene: SceneProfile | None) -> list[dict[str, object]]:
    if scene is None:
        return []
    return [
        {
            "id": checkpoint.checkpoint_id,
            "position": [
                checkpoint.pose.position.x,
                checkpoint.pose.position.y,
                checkpoint.pose.position.z,
            ],
            "dwell_time_s": checkpoint.dwell_time_s,
        }
        for checkpoint in scene.checkpoints
    ]


def _scene_forbidden_zones_to_json(scene: SceneProfile | None) -> list[dict[str, object]]:
    if scene is None:
        return []
    return [
        {
            "id": zone.zone_id,
            "polygon": [[point.x, point.y, point.z] for point in zone.polygon],
        }
        for zone in scene.forbidden_zones
    ]


def _scene_obstacles_to_json(scene: SceneProfile | None) -> list[dict[str, object]]:
    if scene is None:
        return []
    obstacles: list[dict[str, object]] = []
    for obstacle in scene.obstacle_set:
        obstacles.append(
            {
                "id": obstacle.obstacle_id,
                "position": [obstacle.position.x, obstacle.position.y, obstacle.position.z],
                "radius_m": obstacle.radius_m,
                "height_m": obstacle.height_m,
                "geometry_type": obstacle.geometry_type,
                "size": [obstacle.size.x, obstacle.size.y, obstacle.size.z],
            }
        )
    return obstacles


def _copy_package_resource(package: str, name: str, target: Path) -> None:
    resource = resources.files(package).joinpath(name)
    with resources.as_file(resource) as path:
        target.write_bytes(Path(path).read_bytes())
