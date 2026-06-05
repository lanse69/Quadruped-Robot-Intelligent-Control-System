"""Small simulation runner used by the dependency-free API facade.

The runner keeps the API layer independent from HTTP frameworks and databases,
but allows the demonstration facade to execute a local MuJoCo/Webots/minimal
backend for a bounded number of control ticks.  The runner records terrain,
obstacle and safety summaries so API handoff and replay responses can show the
same observation facts that the C++ Safety Shield consumes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, cast

from qrics.sim import (
    AdapterConfig,
    SafeAction,
    SceneObstacle,
    SceneProfile,
    SimulationAdapterFacade,
    Vec3,
)
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.schema import BackendKind, ObservationPacket


@dataclass(frozen=True)
class SimulationRunRequest:
    run_id: str
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    scene_id: str = "api_demo_scene"
    scene_version: str = "0.2.0"
    terrain_pack: str = "flat"
    obstacles: tuple[SceneObstacle, ...] = ()
    step_count: int = 20
    forward_velocity_mps: float = 0.25
    yaw_rate_radps: float = 0.05
    obstacle_replan_distance_m: float = 0.25


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


class SimulationRunner(Protocol):
    def run(self, request: SimulationRunRequest) -> SimulationRunSummary: ...


class LocalSimulationRunner:
    """Bounded local simulation runner for API demonstration flow."""

    def __init__(self, *, webots_execute: bool = True) -> None:
        self._webots_execute = webots_execute

    def run(self, request: SimulationRunRequest) -> SimulationRunSummary:
        backend_kind = _backend_kind(request.backend)
        adapter = self._create_adapter(backend_kind)
        try:
            initialized = adapter.initialize(
                AdapterConfig(
                    adapter_name=f"api_{request.backend}",
                    adapter_version="0.3.0",
                    schema_version="0.3.0",
                    backend=backend_kind,
                    runtime_profile=request.runtime_profile,
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
                        action = _body_velocity_action(request, step_index)
                        latest_action = "body_velocity"
                else:
                    action = _body_velocity_action(request, step_index)
                    latest_action = "body_velocity"

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
            )
        finally:
            adapter.close()

    def _create_adapter(self, backend: BackendKind) -> SimulationAdapterFacade:
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

            return SimulationAdapterFacade(WebotsQuadrupedEnv(execute_webots=self._webots_execute))
        raise RuntimeError(f"Unsupported API simulation backend: {backend}")


def _body_velocity_action(request: SimulationRunRequest, step_index: int) -> SafeAction:
    return SafeAction(
        action_id=f"api_demo_action_{step_index}",
        source_proposal_id=f"api_demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=request.forward_velocity_mps, y=0.0, z=0.0),
        yaw_rate_radps=request.yaw_rate_radps,
        decision="accepted",
        reason="API facade bounded simulation step",
        timestamp_ns=step_index,
    )


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
