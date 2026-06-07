"""Small simulation runner used by the dependency-free API facade.

The runner keeps the API layer independent from HTTP frameworks and databases,
but allows the demonstration facade to execute a local MuJoCo/Webots/minimal
backend for a bounded number of control ticks.  The runner records terrain,
obstacle and safety summaries so API handoff and replay responses can show the
same observation facts that the C++ Safety Shield consumes.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol, cast

from qrics.sim import (
    AdapterConfig,
    Checkpoint,
    ForbiddenZone,
    SafeAction,
    SceneObstacle,
    SceneProfile,
    SimulationAdapterFacade,
    Vec3,
)
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.gait import with_locomotion_hint
from qrics.sim.presentation_channel import (
    PresentationTarget,
    build_run_path_command,
    build_stop_command,
    write_presentation_command,
)
from qrics.sim.runtime_profile import get_runtime_profile
from qrics.sim.schema import BackendKind, ObservationPacket, TerrainClass


@dataclass(frozen=True)
class SimulationTaskTarget:
    target_id: str
    x: float
    y: float
    dwell_steps: int = 0


@dataclass(frozen=True)
class SimulationRunRequest:
    run_id: str
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    scene_id: str = "api_demo_scene"
    scene_version: str = "0.2.0"
    terrain_pack: str = "flat"
    obstacles: tuple[SceneObstacle, ...] = ()
    checkpoints: tuple[Checkpoint, ...] = ()
    forbidden_zones: tuple[ForbiddenZone, ...] = ()
    step_count: int = 20
    forward_velocity_mps: float = 0.25
    yaw_rate_radps: float = 0.05
    obstacle_replan_distance_m: float = 0.25
    task_path: tuple[SimulationTaskTarget, ...] = ()


@dataclass(frozen=True)
class SimulationRunSummary:
    run_id: str
    backend: str
    runtime_profile: str
    step_count: int
    sim_time_ns: int
    base_position: tuple[float, float, float]
    risk_score: float
    stability_state: str
    observation_quality: str
    terrain_class: str
    obstacle_detected: bool
    nearest_obstacle_distance_m: float
    keyframes: tuple[str, ...]
    safety_events: tuple[str, ...]
    latest_action: str = "body_velocity"
    presentation_pid: int = 0
    presentation_log_path: str = ""
    presentation_workspace: str = ""
    presentation_command: tuple[str, ...] = ()
    presentation_command_dir: str = ""
    presentation_command_path: str = ""


class SimulationRunner(Protocol):
    def run(self, request: SimulationRunRequest) -> SimulationRunSummary: ...

    def send_control_command(
        self, *, run_id: str, backend: str, command_type: str
    ) -> PresentationControlDispatch: ...


class LocalSimulationRunner:
    """Bounded local simulation runner for API demonstration flow."""

    def __init__(
        self,
        *,
        webots_execute: bool = True,
        presentation_enabled: bool = True,
        presentation_hold_seconds: float | None = None,
    ) -> None:
        self._webots_execute = webots_execute
        self._presentation_hold_seconds = presentation_hold_seconds
        # Contract/dry-run callers pass webots_execute=False to avoid launching
        # the external Webots process.  Keep presentation windows disabled in
        # that mode unless a caller explicitly provides a presentation hold time
        # for a visual presentation test or UI preview/run path.
        self._presentation_enabled = presentation_enabled and (
            webots_execute or presentation_hold_seconds is not None
        )
        self._presentation_processes: dict[str, ActivePresentation] = {}

    def run(self, request: SimulationRunRequest) -> SimulationRunSummary:
        presentation = self._maybe_launch_presentation(request)
        backend_kind = _backend_kind(request.backend)
        adapter_request = _headless_request_for_api_summary(request)
        adapter = self._create_adapter(
            backend_kind,
            execute_webots=(
                False if presentation.pid > 0 and backend_kind == "webots" else self._webots_execute
            ),
        )
        try:
            initialized = adapter.initialize(
                AdapterConfig(
                    adapter_name=f"api_{request.backend}",
                    adapter_version="0.3.0",
                    schema_version="0.3.0",
                    backend=backend_kind,
                    runtime_profile=adapter_request.runtime_profile,
                )
            )
            if not initialized.ok:
                raise RuntimeError(_first_error(initialized.errors, "initialize failed"))

            loaded = adapter.load_scene(
                SceneProfile(
                    scene_id=request.scene_id,
                    version=request.scene_version,
                    name="API demo scene",
                    terrain_pack=request.terrain_pack,
                    obstacle_set=request.obstacles,
                    checkpoints=request.checkpoints,
                    forbidden_zones=request.forbidden_zones,
                )
            )
            if not loaded.ok:
                raise RuntimeError(_first_error(loaded.errors, "load_scene failed"))

            reset = adapter.reset()
            if not reset.ok:
                raise RuntimeError(_first_error(reset.errors, "reset failed"))

            latest_state = reset.value.robot_state if reset.value is not None else None
            latest_observation = reset.value.observation if reset.value is not None else None
            keyframes: list[str] = []
            safety_events: list[str] = []
            latest_action = "body_velocity"
            executed_steps = 0
            target_index = 0
            dwell_remaining = 0

            for step_index in range(max(1, request.step_count)):
                observed = adapter.observe()
                if observed.ok and observed.value is not None:
                    latest_observation = observed.value
                    event = _safety_event_for_observation(
                        latest_observation,
                        replan_distance_m=request.obstacle_replan_distance_m,
                    )
                    if event:
                        safety_events.append(event)
                        keyframes.append(f"safety_step_{step_index}:{event}")
                        action = SafeAction(
                            action_id=f"api_demo_replan_{step_index}",
                            source_proposal_id=f"api_demo_proposal_{step_index}",
                            action_type="replan",
                            decision="replan",
                            reason=event,
                            timestamp_ns=step_index,
                        )
                        latest_action = "replan"
                    else:
                        action, target_index, dwell_remaining = _task_or_body_velocity_action(
                            request, step_index, latest_observation, target_index, dwell_remaining
                        )
                        latest_action = action.action_type
                else:
                    action, target_index, dwell_remaining = _task_or_body_velocity_action(
                        request, step_index, latest_observation, target_index, dwell_remaining
                    )
                    latest_action = action.action_type

                stepped = adapter.step(action)
                if not stepped.ok:
                    raise RuntimeError(_first_error(stepped.errors, "step failed"))
                executed_steps += 1
                if stepped.value is not None:
                    latest_state = stepped.value.robot_state
                    latest_observation = stepped.value.observation
                    if latest_state.risk_score > 0.0 or latest_state.stability_state != "stable":
                        keyframes.append(f"risk_step_{step_index}")

            if latest_state is None:
                raise RuntimeError("simulation finished without robot_state")

            pos = latest_state.pose.position
            if latest_observation is None:
                observation_quality = "missing"
                terrain_class = latest_state.terrain_class
                obstacle_detected = False
                nearest_obstacle_distance_m = 0.0
            else:
                observation_quality = latest_observation.imu.source_quality
                terrain_class = latest_observation.terrain_class
                obstacle_detected = latest_observation.obstacle_state.obstacle_detected
                nearest_obstacle_distance_m = latest_observation.obstacle_state.nearest_distance_m

            return SimulationRunSummary(
                run_id=request.run_id,
                backend=request.backend,
                runtime_profile=request.runtime_profile,
                step_count=executed_steps,
                sim_time_ns=latest_state.timestamp_ns,
                base_position=(pos.x, pos.y, pos.z),
                risk_score=latest_state.risk_score,
                stability_state=latest_state.stability_state,
                observation_quality=observation_quality,
                terrain_class=terrain_class,
                obstacle_detected=obstacle_detected,
                nearest_obstacle_distance_m=nearest_obstacle_distance_m,
                keyframes=tuple(keyframes),
                safety_events=tuple(safety_events),
                latest_action=latest_action,
                presentation_pid=presentation.pid,
                presentation_log_path=presentation.log_path,
                presentation_workspace=presentation.workspace,
                presentation_command=presentation.command,
                presentation_command_dir=presentation.command_dir,
                presentation_command_path=presentation.command_path,
            )
        finally:
            adapter.close()

    def send_control_command(
        self, *, run_id: str, backend: str, command_type: str
    ) -> PresentationControlDispatch:
        """Forward high-priority control overrides to an open presentation window.

        The bounded API summary path already updates repository state, but the
        defence/demo viewer is a separate process.  This method keeps the
        visible MuJoCo/Webots window consistent with EmergencyStop and
        Safe-Stand requests by writing the same file-based command channel used
        for task paths.
        """
        self._reap_finished_presentations()
        backend_kind = _backend_kind(backend)
        if backend_kind not in {"mujoco", "webots"}:
            return PresentationControlDispatch()

        active = self._presentation_processes.get(backend_kind)
        if active is None or active.process.poll() is not None or not active.command_dir:
            return PresentationControlDispatch()

        presentation_command_type = _presentation_override_command_type(command_type)
        if presentation_command_type is None:
            return PresentationControlDispatch(
                pid=int(active.process.pid),
                workspace=active.workspace,
                command_dir=active.command_dir,
            )
        try:
            command = build_stop_command(run_id=run_id, command_type=presentation_command_type)
            command_path = write_presentation_command(active.command_dir, command)
        except Exception as exc:
            return PresentationControlDispatch(
                pid=int(active.process.pid),
                workspace=active.workspace,
                command_dir=active.command_dir,
                error=str(exc),
            )
        return PresentationControlDispatch(
            pid=int(active.process.pid),
            workspace=active.workspace,
            command_dir=active.command_dir,
            command_path=str(command_path),
        )

    def _create_adapter(
        self, backend: BackendKind, *, execute_webots: bool | None = None
    ) -> SimulationAdapterFacade:
        if backend == "minimal":
            return SimulationAdapterFacade(MinimalQuadrupedEnv())
        if backend == "mujoco":
            try:
                from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv
            except ModuleNotFoundError as exc:
                raise RuntimeError(
                    "MuJoCo backend is not installed. "
                    "Install with `python -m pip install -e .[local-sim]`."
                ) from exc
            return SimulationAdapterFacade(MujocoQuadrupedEnv())
        if backend == "webots":
            from qrics.sim.backends.webots_env import WebotsQuadrupedEnv

            return SimulationAdapterFacade(
                WebotsQuadrupedEnv(
                    execute_webots=(
                        self._webots_execute if execute_webots is None else execute_webots
                    )
                )
            )
        raise RuntimeError(f"Unsupported API simulation backend: {backend}")

    def _maybe_launch_presentation(self, request: SimulationRunRequest) -> PresentationLaunch:
        self._reap_finished_presentations()
        if not self._presentation_enabled:
            return PresentationLaunch()
        backend = _backend_kind(request.backend)
        if backend not in {"mujoco", "webots"}:
            return PresentationLaunch()
        try:
            profile = get_runtime_profile(request.runtime_profile)
        except ValueError:
            return PresentationLaunch()
        if profile.render_mode != "viewer":
            return PresentationLaunch()

        signature = _presentation_signature(request)
        active = self._presentation_processes.get(backend)
        if active is not None and active.process.poll() is None and active.signature == signature:
            command_path = self._send_presentation_task_command(active, request)
            return PresentationLaunch(
                pid=int(active.process.pid),
                log_path=active.log_path,
                workspace=active.workspace,
                command=active.command,
                command_dir=active.command_dir,
                command_path=command_path,
            )
        if active is not None and active.process.poll() is None:
            _terminate_process_group(active.process)

        root_dir = Path(__file__).resolve().parents[3]
        script = (
            root_dir
            / "scripts"
            / ("run_local_sim_demo.py" if backend == "mujoco" else "run_webots_demo.py")
        )
        if not script.exists():
            return PresentationLaunch(error=f"presentation script not found: {script}")

        workspace = Path(
            tempfile.mkdtemp(prefix=f"qrics_{backend}_{_safe_run_id(request.run_id)}_")
        )
        scene_path = workspace / "scene.json"
        log_path = workspace / "presentation.log"
        command_dir = workspace / "commands"
        command_dir.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(
            json.dumps(_scene_payload_for_presentation(request), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        duration_s = self._presentation_duration_s(request)
        command = [
            sys.executable,
            str(script),
            "--profile",
            request.runtime_profile,
            "--seconds",
            f"{duration_s:.3f}",
            "--scene-json",
            str(scene_path),
            "--command-dir",
            str(command_dir),
            "--forward",
            str(request.forward_velocity_mps),
            "--yaw-rate",
            str(request.yaw_rate_radps),
        ]
        if backend == "mujoco":
            command.append("--viewer")

        env = dict(os.environ)
        python_dir = root_dir / "python"
        env["PYTHONPATH"] = (
            f"{python_dir}{os.pathsep}{env['PYTHONPATH']}"
            if env.get("PYTHONPATH")
            else str(python_dir)
        )
        if backend == "webots":
            env.setdefault("QRICS_WEBOTS_HOLD_SECONDS", str(max(120.0, duration_s)))

        log_file = log_path.open("w", encoding="utf-8")
        try:
            process: subprocess.Popen[bytes] = subprocess.Popen(
                command,
                cwd=str(root_dir),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        except Exception as exc:
            log_file.close()
            return PresentationLaunch(
                error=f"presentation launch failed: {exc}",
                log_path=str(log_path),
                workspace=str(workspace),
                command=tuple(command),
            )
        active_presentation = ActivePresentation(
            process=process,
            signature=signature,
            log_path=str(log_path),
            workspace=str(workspace),
            command=tuple(command),
            command_dir=str(command_dir),
        )
        self._presentation_processes[backend] = active_presentation
        command_path = self._send_presentation_task_command(active_presentation, request)
        return PresentationLaunch(
            pid=int(process.pid),
            log_path=str(log_path),
            workspace=str(workspace),
            command=tuple(command),
            command_dir=str(command_dir),
            command_path=command_path,
        )

    def _send_presentation_task_command(
        self, active: ActivePresentation, request: SimulationRunRequest
    ) -> str:
        if not active.command_dir or not request.task_path:
            return ""
        try:
            profile = get_runtime_profile(request.runtime_profile)
        except ValueError:
            return ""
        control_dt_s = profile.physics_timestep_s * max(1, profile.control_decimation)
        command = build_run_path_command(
            run_id=request.run_id,
            task_path=tuple(
                PresentationTarget(
                    target_id=target.target_id,
                    x=target.x,
                    y=target.y,
                    dwell_steps=target.dwell_steps,
                )
                for target in request.task_path
            ),
            step_count=max(1, request.step_count),
            control_dt_s=control_dt_s,
            forward_velocity_mps=request.forward_velocity_mps,
            yaw_rate_radps=request.yaw_rate_radps,
        )
        try:
            return str(write_presentation_command(active.command_dir, command))
        except Exception:
            return ""

    def _presentation_duration_s(self, request: SimulationRunRequest) -> float:
        if self._presentation_hold_seconds is not None:
            return max(5.0, float(self._presentation_hold_seconds))
        env_value = os.environ.get("QRICS_PRESENTATION_HOLD_SECONDS", "").strip()
        if env_value:
            try:
                return max(5.0, float(env_value))
            except ValueError:
                pass
        profile = get_runtime_profile(request.runtime_profile)
        step_dt_s = profile.physics_timestep_s * max(1, profile.control_decimation)
        requested_s = request.step_count * step_dt_s
        return max(45.0, min(profile.max_demo_seconds, requested_s))

    def _reap_finished_presentations(self) -> None:
        self._presentation_processes = {
            backend: active
            for backend, active in self._presentation_processes.items()
            if active.process.poll() is None
        }


@dataclass(frozen=True)
class PresentationControlDispatch:
    pid: int = 0
    workspace: str = ""
    command_dir: str = ""
    command_path: str = ""
    error: str = ""


@dataclass(frozen=True)
class ActivePresentation:
    process: subprocess.Popen[bytes]
    signature: str
    log_path: str = ""
    workspace: str = ""
    command: tuple[str, ...] = ()
    command_dir: str = ""


@dataclass(frozen=True)
class PresentationLaunch:
    pid: int = 0
    log_path: str = ""
    workspace: str = ""
    command: tuple[str, ...] = ()
    command_dir: str = ""
    command_path: str = ""
    error: str = ""


PresentationOverrideCommand = Literal["stop", "safe_stand"]


def _presentation_override_command_type(command_type: str) -> PresentationOverrideCommand | None:
    if command_type == "safe_stand":
        return "safe_stand"
    if command_type in {"emergency_stop", "manual_control", "pause"}:
        return "stop"
    # Resume is an application-level state transition.  The viewer will accept
    # a subsequent run_path command when the operator starts or re-hands off a
    # task, so no file command is written here.
    return None


def _task_or_body_velocity_action(
    request: SimulationRunRequest,
    step_index: int,
    observation: ObservationPacket | None,
    target_index: int,
    dwell_remaining: int,
) -> tuple[SafeAction, int, int]:
    if not request.task_path or observation is None:
        return (
            _body_velocity_action(request, step_index, terrain="flat"),
            target_index,
            dwell_remaining,
        )

    current = observation.base_pose.position
    if dwell_remaining > 0:
        return (
            _hold_action(request, step_index, terrain=observation.terrain_class),
            target_index,
            dwell_remaining - 1,
        )

    active_index = min(target_index, len(request.task_path) - 1)
    target = request.task_path[active_index]
    dx = target.x - current.x
    dy = target.y - current.y
    distance = math.hypot(dx, dy)
    if distance <= 0.08 and active_index < len(request.task_path) - 1:
        target_index = active_index + 1
        target = request.task_path[target_index]
        dwell_remaining = max(0, target.dwell_steps)
        dx = target.x - current.x
        dy = target.y - current.y
        distance = math.hypot(dx, dy)
    elif distance <= 0.08:
        return (
            _hold_action(request, step_index, terrain=observation.terrain_class),
            target_index,
            max(0, target.dwell_steps),
        )

    speed = max(0.05, abs(request.forward_velocity_mps))
    if distance > 1.0e-6:
        vx = speed * dx / distance
        vy = speed * dy / distance
    else:
        vx = 0.0
        vy = 0.0
    yaw_rate = max(-0.8, min(0.8, math.atan2(dy, dx) * 0.35))
    action = SafeAction(
        action_id=f"api_task_action_{step_index}_{target.target_id}",
        source_proposal_id=f"api_task_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=vx, y=vy, z=0.0),
        yaw_rate_radps=yaw_rate,
        decision="accepted",
        reason=f"Task path tracking toward {target.target_id}",
        timestamp_ns=step_index,
    )
    return (
        with_locomotion_hint(action, terrain=observation.terrain_class),
        target_index,
        dwell_remaining,
    )


def _body_velocity_action(
    request: SimulationRunRequest, step_index: int, *, terrain: TerrainClass = "flat"
) -> SafeAction:
    action = SafeAction(
        action_id=f"api_demo_action_{step_index}",
        source_proposal_id=f"api_demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=request.forward_velocity_mps, y=0.0, z=0.0),
        yaw_rate_radps=request.yaw_rate_radps,
        decision="accepted",
        reason="API facade bounded simulation step",
        timestamp_ns=step_index,
    )
    return with_locomotion_hint(action, terrain=terrain)


def _hold_action(
    request: SimulationRunRequest, step_index: int, *, terrain: TerrainClass = "flat"
) -> SafeAction:
    action = SafeAction(
        action_id=f"api_task_hold_{step_index}",
        source_proposal_id=f"api_task_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(),
        yaw_rate_radps=0.0,
        decision="accepted",
        reason="Task target reached, holding position",
        timestamp_ns=step_index,
    )
    return with_locomotion_hint(action, terrain=terrain)


def _safety_event_for_observation(
    observation: ObservationPacket,
    *,
    replan_distance_m: float,
) -> str:
    obstacle = observation.obstacle_state
    if (
        obstacle.obstacle_detected
        and obstacle.nearest_distance_m > 0.0
        and obstacle.nearest_distance_m <= replan_distance_m
    ):
        return (
            "CollisionRisk: nearest obstacle "
            f"{obstacle.nearest_distance_m:.3f} m <= {replan_distance_m:.3f} m"
        )
    return ""


def _headless_request_for_api_summary(request: SimulationRunRequest) -> SimulationRunRequest:
    try:
        profile = get_runtime_profile(request.runtime_profile)
    except ValueError:
        return request
    if request.backend in {"mujoco", "webots"} and profile.render_mode == "viewer":
        return replace(request, runtime_profile="headless_fast")
    return request


def _scene_payload_for_presentation(request: SimulationRunRequest) -> dict[str, object]:
    return {
        "scene_id": request.scene_id,
        "version": request.scene_version,
        "name": f"QRICS presentation {request.run_id}",
        "terrain_pack": request.terrain_pack,
        "task_path": [
            {
                "id": target.target_id,
                "position": [target.x, target.y, 0.32],
                "dwell_steps": target.dwell_steps,
            }
            for target in request.task_path
        ],
        "checkpoints": [
            {
                "id": checkpoint.checkpoint_id,
                "asset_type": "checkpoint",
                "position": [
                    checkpoint.pose.position.x,
                    checkpoint.pose.position.y,
                    checkpoint.pose.position.z,
                ],
                "dwell_time_s": checkpoint.dwell_time_s,
            }
            for checkpoint in request.checkpoints
        ],
        "forbidden_zones": [
            {
                "id": zone.zone_id,
                "asset_type": "no_go_zone",
                "polygon": [[point.x, point.y, point.z] for point in zone.polygon],
            }
            for zone in request.forbidden_zones
        ],
        "obstacles": [
            {
                "id": obstacle.obstacle_id,
                "asset_type": "obstacle",
                "geometry_type": obstacle.geometry_type,
                "position": [
                    obstacle.position.x,
                    obstacle.position.y,
                    obstacle.position.z,
                ],
                "radius_m": obstacle.radius_m,
                "height_m": obstacle.height_m,
                "size": [obstacle.size.x, obstacle.size.y, obstacle.size.z],
            }
            for obstacle in request.obstacles
        ],
    }


def _safe_run_id(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return safe[:80] or "run"


def _presentation_signature(request: SimulationRunRequest) -> str:
    payload = {
        "backend": request.backend,
        "profile": request.runtime_profile,
        "scene_id": request.scene_id,
        "scene_version": request.scene_version,
        "terrain": request.terrain_pack,
        "obstacles": [
            [
                obstacle.obstacle_id,
                obstacle.geometry_type,
                round(obstacle.position.x, 3),
                round(obstacle.position.y, 3),
                round(obstacle.position.z, 3),
                round(obstacle.radius_m, 3),
                round(obstacle.height_m, 3),
                round(obstacle.size.x, 3),
                round(obstacle.size.y, 3),
                round(obstacle.size.z, 3),
            ]
            for obstacle in request.obstacles
        ],
        # The presentation process represents an open viewer for a scene.
        # Runtime task commands are intentionally excluded so clicking Run
        # after Preview reuses the already-open simulator window instead of
        # terminating it and starting a new one.  The API still executes the
        # requested task in its bounded headless summary path.
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, 15)
        else:
            process.terminate()
        process.wait(timeout=1.5)
    except Exception:
        try:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, 9)
            else:
                process.kill()
        except Exception:
            pass


def _backend_kind(backend: str) -> BackendKind:
    if backend in {"minimal", "mujoco", "webots"}:
        return cast(BackendKind, backend)
    raise RuntimeError(f"Unsupported API simulation backend: {backend}")


def _first_error(errors: Iterable[object], fallback: str) -> str:
    for first in errors:
        code = getattr(first, "code", "SIMULATION_ERROR")
        message = getattr(first, "message", fallback)
        return f"{code}: {message}"
    return fallback
