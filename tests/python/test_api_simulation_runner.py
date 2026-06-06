from typing import Any

from pytest import MonkeyPatch

from qrics.api.simulation_runner import LocalSimulationRunner, SimulationRunRequest
from qrics.sim import SceneObstacle, Vec3


def test_local_simulation_runner_minimal_backend_returns_status_summary() -> None:
    runner = LocalSimulationRunner()

    summary = runner.run(
        SimulationRunRequest(
            run_id="run_api_minimal",
            backend="minimal",
            runtime_profile="headless_fast",
            step_count=5,
            forward_velocity_mps=0.30,
        )
    )

    assert summary.run_id == "run_api_minimal"
    assert summary.backend == "minimal"
    assert summary.runtime_profile == "headless_fast"
    assert summary.step_count == 5
    assert summary.sim_time_ns > 0
    assert summary.base_position[0] > 0.0
    assert summary.observation_quality == "estimated"


def test_local_simulation_runner_records_obstacle_replan_evidence() -> None:
    runner = LocalSimulationRunner()

    summary = runner.run(
        SimulationRunRequest(
            run_id="run_api_obstacle",
            backend="minimal",
            runtime_profile="headless_fast",
            terrain_pack="mixed_terrain_pack",
            obstacles=(
                SceneObstacle(
                    obstacle_id="demo_barrel",
                    position=Vec3(x=0.12, y=0.0, z=0.35),
                    radius_m=0.05,
                    height_m=0.35,
                ),
            ),
            step_count=4,
            forward_velocity_mps=0.30,
        )
    )

    assert summary.run_id == "run_api_obstacle"
    assert summary.latest_action == "replan"
    assert summary.terrain_class == "flat"
    assert summary.obstacle_detected is True
    assert summary.nearest_obstacle_distance_m <= 0.25
    assert summary.safety_events
    assert any("CollisionRisk" in event for event in summary.safety_events)
    assert any(keyframe.startswith("safety_step_") for keyframe in summary.keyframes)


def test_visual_webots_request_launches_persistent_presentation_process(
    monkeypatch: MonkeyPatch,
) -> None:
    launched: list[dict[str, object]] = []

    class DummyProcess:
        pid = 43210

        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: Any) -> DummyProcess:
        launched.append({"command": command, "kwargs": kwargs})
        return DummyProcess()

    monkeypatch.setattr("qrics.api.simulation_runner.subprocess.Popen", fake_popen)

    runner = LocalSimulationRunner(
        webots_execute=False,
        presentation_hold_seconds=12.0,
    )
    summary = runner.run(
        SimulationRunRequest(
            run_id="run_visual_webots",
            backend="webots",
            runtime_profile="webots_fast",
            step_count=2,
        )
    )

    assert summary.backend == "webots"
    assert summary.runtime_profile == "webots_fast"
    assert summary.presentation_pid == 43210
    assert summary.presentation_log_path.endswith("presentation.log")
    assert launched
    command = launched[0]["command"]
    assert isinstance(command, list)
    assert "run_webots_demo.py" in command[1]
    assert "--seconds" in command
    assert "12.000" in command


def test_visual_presentation_reuses_existing_process_for_same_scene(
    monkeypatch: MonkeyPatch,
) -> None:
    launched: list[list[str]] = []

    class DummyProcess:
        pid = 54321

        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: Any) -> DummyProcess:
        launched.append(command)
        return DummyProcess()

    monkeypatch.setattr("qrics.api.simulation_runner.subprocess.Popen", fake_popen)

    runner = LocalSimulationRunner(webots_execute=False, presentation_hold_seconds=12.0)
    request = SimulationRunRequest(
        run_id="run_visual_webots_reuse",
        backend="webots",
        runtime_profile="webots_fast",
        step_count=2,
    )
    first = runner.run(request)
    second = runner.run(request)

    assert first.presentation_pid == 54321
    assert second.presentation_pid == 54321
    assert len(launched) == 1
