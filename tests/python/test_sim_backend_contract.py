from qrics.sim import (
    AdapterConfig,
    SafeAction,
    SceneObstacle,
    SceneProfile,
    SimulationAdapterFacade,
    Vec3,
)
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv


def _started_minimal_adapter() -> SimulationAdapterFacade:
    adapter = SimulationAdapterFacade(MinimalQuadrupedEnv())
    initialized = adapter.initialize(
        AdapterConfig(backend="minimal", runtime_profile="headless_fast")
    )
    assert initialized.ok
    loaded = adapter.load_scene(SceneProfile(scene_id="minimal_contract_scene", version="0.2.0"))
    assert loaded.ok
    reset = adapter.reset()
    assert reset.ok
    return adapter


def test_minimal_backend_rejects_rejected_safe_action() -> None:
    adapter = _started_minimal_adapter()

    rejected = adapter.step(
        SafeAction(
            action_id="rejected_action",
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


def test_minimal_backend_accepts_body_velocity_and_advances_state() -> None:
    adapter = _started_minimal_adapter()

    before = adapter.robot_state()
    assert before.ok
    assert before.value is not None

    stepped = adapter.step(
        SafeAction(
            action_id="safe_move",
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


def test_minimal_backend_maps_scene_obstacles_into_observation_packet() -> None:
    adapter = SimulationAdapterFacade(MinimalQuadrupedEnv())
    initialized = adapter.initialize(
        AdapterConfig(backend="minimal", runtime_profile="headless_fast")
    )
    assert initialized.ok
    loaded = adapter.load_scene(
        SceneProfile(
            scene_id="minimal_obstacle_scene",
            version="0.3.0",
            terrain_pack="mixed_terrain_pack",
            obstacle_set=(
                SceneObstacle(
                    obstacle_id="demo_barrel",
                    position=Vec3(x=0.15, y=0.0, z=0.35),
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
    assert observed.value.terrain_class == "flat"
    assert observed.value.obstacle_state.obstacle_detected is True
    assert observed.value.obstacle_state.nearest_distance_m <= 0.25
    assert observed.value.obstacle_state.source_quality == "estimated"

    closed = adapter.close()
    assert closed.ok
