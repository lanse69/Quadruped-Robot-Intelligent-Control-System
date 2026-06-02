"""Small simulation runner used by the dependency-free API facade.

The runner keeps the API layer independent from HTTP frameworks and databases,
but allows the demonstration facade to execute a real simulation backend for a
few control ticks.  It is intentionally short-lived: each handoff creates a
backend instance, runs bounded steps, records status/replay summaries, then
closes the backend.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from qrics.sim import AdapterConfig, SafeAction, SceneProfile, SimulationAdapterFacade, Vec3
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv


@dataclass(frozen=True)
class SimulationRunRequest:
    run_id: str
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    scene_id: str = "api_demo_scene"
    scene_version: str = "0.2.0"
    step_count: int = 20
    forward_velocity_mps: float = 0.25
    yaw_rate_radps: float = 0.05


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
    keyframes: tuple[str, ...]


class SimulationRunner(Protocol):
    def run(self, request: SimulationRunRequest) -> SimulationRunSummary: ...


class LocalSimulationRunner:
    """Bounded local simulation runner for API demonstration flow."""

    def run(self, request: SimulationRunRequest) -> SimulationRunSummary:
        adapter = self._create_adapter(request.backend)
        try:
            initialized = adapter.initialize(
                AdapterConfig(
                    adapter_name=f"api_{request.backend}",
                    adapter_version="0.2.0",
                    backend=request.backend,  # type: ignore[arg-type]
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
                )
            )
            if not loaded.ok:
                raise RuntimeError(_first_error(loaded.errors, "load_scene failed"))

            reset = adapter.reset()
            if not reset.ok:
                raise RuntimeError(_first_error(reset.errors, "reset failed"))

            latest_state = reset.value.robot_state if reset.value is not None else None
            keyframes: list[str] = []

            for step_index in range(max(1, request.step_count)):
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
                stepped = adapter.step(action)
                if not stepped.ok:
                    raise RuntimeError(_first_error(stepped.errors, "step failed"))
                if stepped.value is not None:
                    latest_state = stepped.value.robot_state
                    if latest_state.risk_score > 0.0 or latest_state.stability_state != "stable":
                        keyframes.append(f"risk_step_{step_index}")

            if latest_state is None:
                raise RuntimeError("simulation finished without robot_state")

            pos = latest_state.pose.position
            return SimulationRunSummary(
                run_id=request.run_id,
                backend=request.backend,
                runtime_profile=request.runtime_profile,
                step_count=max(1, request.step_count),
                sim_time_ns=latest_state.timestamp_ns,
                base_position=(pos.x, pos.y, pos.z),
                risk_score=latest_state.risk_score,
                stability_state=latest_state.stability_state,
                observation_quality="direct" if request.backend == "mujoco" else "estimated",
                keyframes=tuple(keyframes),
            )
        finally:
            adapter.close()

    def _create_adapter(self, backend: str) -> SimulationAdapterFacade:
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
        raise RuntimeError(f"Unsupported API simulation backend: {backend}")


def _first_error(errors: Iterable[object], fallback: str) -> str:
    for first in errors:
        code = getattr(first, "code", "SIMULATION_ERROR")
        message = getattr(first, "message", fallback)
        return f"{code}: {message}"
    return fallback
