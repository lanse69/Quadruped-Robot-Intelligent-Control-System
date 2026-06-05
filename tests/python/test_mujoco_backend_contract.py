import pytest

pytest.importorskip("mujoco")

from qrics.sim import (
    AdapterConfig,
    SafeAction,
    SceneObstacle,
    SceneProfile,
    SimulationAdapterFacade,
    Vec3,
)
from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv


def _started_mujoco_adapter() -> SimulationAdapterFacade:
    adapter = SimulationAdapterFacade(MujocoQuadrupedEnv())
    initialized = adapter.initialize(
        AdapterConfig(backend="mujoco", runtime_profile="headless_fast")
    )
    assert initialized.ok
    loaded = adapter.load_scene(SceneProfile(scene_id="mujoco_contract_scene", version="0.2.0"))
    assert loaded.ok
    reset = adapter.reset()
    assert reset.ok
    return adapter


def test_mujoco_backend_lifecycle_reset_and_state_contract() -> None:
    adapter = _started_mujoco_adapter()

    state = adapter.robot_state()
    assert state.ok
    assert state.value is not None
    assert state.value.pose.position.z > 0.1
    assert len(state.value.contacts) == 4
    assert state.value.terrain_class == "flat"

    observed = adapter.observe()
    assert observed.ok
    assert observed.value is not None
    assert observed.value.observation_id.startswith("mujoco_obs_")
    assert len(observed.value.contacts) == 4

    closed = adapter.close()
    assert closed.ok
    assert closed.value == "stopped"


def test_mujoco_backend_steps_real_physics_and_advances_timestamp() -> None:
    adapter = _started_mujoco_adapter()

    last_timestamp_ns = 0
    last_x = 0.0
    for step_index in range(20):
        stepped = adapter.step(
            SafeAction(
                action_id=f"safe_move_{step_index}",
                action_type="body_velocity",
                body_velocity=Vec3(x=0.25, y=0.0, z=0.0),
                yaw_rate_radps=0.05,
                decision="accepted",
                reason="MuJoCo contract test body velocity",
                timestamp_ns=step_index,
            )
        )
        assert stepped.ok
        assert stepped.value is not None
        last_timestamp_ns = stepped.value.robot_state.timestamp_ns
        last_x = stepped.value.robot_state.pose.position.x
        assert len(stepped.value.robot_state.contacts) == 4

    assert last_timestamp_ns > 0
    assert last_x > -0.25

    closed = adapter.close()
    assert closed.ok


def test_mujoco_backend_blocks_rejected_safe_action() -> None:
    adapter = _started_mujoco_adapter()

    rejected = adapter.step(
        SafeAction(
            action_id="rejected_mujoco_action",
            action_type="body_velocity",
            body_velocity=Vec3(x=0.25),
            decision="rejected",
            reason="contract test rejected action",
        )
    )

    assert not rejected.ok
    assert rejected.errors[0].code == "SAFE_ACTION_REJECTED"

    state_after_rejection = adapter.robot_state()
    assert state_after_rejection.ok
    assert state_after_rejection.value is not None
    assert state_after_rejection.value.timestamp_ns == 0

    closed = adapter.close()
    assert closed.ok


def test_mujoco_backend_binds_typed_obstacle_into_scene_model() -> None:
    adapter = SimulationAdapterFacade(MujocoQuadrupedEnv())
    initialized = adapter.initialize(
        AdapterConfig(backend="mujoco", runtime_profile="headless_fast")
    )
    assert initialized.ok
    loaded = adapter.load_scene(
        SceneProfile(
            scene_id="mujoco_obstacle_scene",
            version="0.4.0",
            obstacle_set=(
                SceneObstacle(
                    obstacle_id="mujoco_demo_barrel",
                    position=Vec3(x=0.12, y=0.0, z=0.35),
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
