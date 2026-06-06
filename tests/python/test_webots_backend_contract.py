from qrics.api.simulation_runner import LocalSimulationRunner, SimulationRunRequest
from qrics.sim import (
    AdapterConfig,
    SafeAction,
    SceneObstacle,
    SceneProfile,
    SimulationAdapterFacade,
    Vec3,
)
from qrics.sim.backends.webots_env import WebotsQuadrupedEnv


def _started_webots_adapter() -> SimulationAdapterFacade:
    adapter = SimulationAdapterFacade(WebotsQuadrupedEnv(execute_webots=False))
    initialized = adapter.initialize(AdapterConfig(backend="webots", runtime_profile="webots_fast"))
    assert initialized.ok
    loaded = adapter.load_scene(SceneProfile(scene_id="webots_contract_scene", version="0.3.0"))
    assert loaded.ok
    reset = adapter.reset()
    assert reset.ok
    return adapter


def test_webots_backend_rejects_rejected_safe_action_without_external_process() -> None:
    adapter = _started_webots_adapter()

    rejected = adapter.step(
        SafeAction(
            action_id="webots_rejected_action",
            action_type="body_velocity",
            body_velocity=Vec3(x=0.2),
            decision="rejected",
            reason="contract test rejected action",
        )
    )

    assert not rejected.ok
    assert rejected.errors[0].code == "SAFE_ACTION_REJECTED"
    closed = adapter.close()
    assert closed.ok


def test_webots_backend_accepts_body_velocity_and_advances_state_without_external_process() -> None:
    adapter = _started_webots_adapter()

    before = adapter.robot_state()
    assert before.ok
    assert before.value is not None

    stepped = adapter.step(
        SafeAction(
            action_id="webots_safe_move",
            action_type="body_velocity",
            body_velocity=Vec3(x=0.4, y=0.0, z=0.0),
            yaw_rate_radps=0.2,
            decision="accepted",
            reason="contract test body velocity",
        )
    )

    assert stepped.ok
    assert stepped.value is not None
    assert stepped.value.state == "running"
    assert stepped.value.robot_state.timestamp_ns > before.value.timestamp_ns
    assert stepped.value.robot_state.pose.position.x > before.value.pose.position.x
    assert stepped.value.robot_state.angular_velocity.z == 0.2
    assert len(stepped.value.robot_state.contacts) == 4

    observed = adapter.observe()
    assert observed.ok
    assert observed.value is not None
    assert observed.value.base_pose.position.x == stepped.value.robot_state.pose.position.x

    closed = adapter.close()
    assert closed.ok
    assert closed.value == "stopped"


def test_local_simulation_runner_supports_webots_dry_run_handoff() -> None:
    runner = LocalSimulationRunner(webots_execute=False, presentation_enabled=False)

    summary = runner.run(
        SimulationRunRequest(
            run_id="run_api_webots",
            backend="webots",
            runtime_profile="webots_fast",
            step_count=5,
            forward_velocity_mps=0.30,
        )
    )

    assert summary.run_id == "run_api_webots"
    assert summary.backend == "webots"
    assert summary.runtime_profile == "webots_fast"
    assert summary.step_count == 5
    assert summary.sim_time_ns > 0
    assert summary.base_position[0] > 0.0
    assert summary.observation_quality == "estimated"


def test_webots_backend_maps_typed_obstacle_without_external_process() -> None:
    adapter = SimulationAdapterFacade(WebotsQuadrupedEnv(execute_webots=False))
    initialized = adapter.initialize(AdapterConfig(backend="webots", runtime_profile="webots_fast"))
    assert initialized.ok
    loaded = adapter.load_scene(
        SceneProfile(
            scene_id="webots_obstacle_scene",
            version="0.4.0",
            obstacle_set=(
                SceneObstacle(
                    obstacle_id="webots_demo_barrel",
                    position=Vec3(x=0.12, y=0.0, z=0.32),
                    radius_m=0.05,
                    height_m=0.35,
                ),
            ),
        )
    )
    assert loaded.ok
    reset = adapter.reset()
    assert reset.ok
    observed = adapter.observe()
    assert observed.ok
    assert observed.value is not None
    assert observed.value.obstacle_state.obstacle_detected is True
    assert observed.value.obstacle_state.nearest_distance_m <= 0.25
    assert adapter.close().ok
