from qrics.api.simulation_runner import LocalSimulationRunner, SimulationRunRequest


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
