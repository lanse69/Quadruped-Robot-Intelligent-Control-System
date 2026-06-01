from qrics.isaac_lab import AdapterConfig, IsaacLabAdapter, SafeAction, SceneProfile, Vec3
from qrics.isaac_lab.action_mapper import map_safe_action_to_isaac_command


def test_adapter_lifecycle_and_step_contract() -> None:
    adapter = IsaacLabAdapter()

    assert adapter.name() == "isaac_lab"
    assert adapter.state() == "created"

    initialized = adapter.initialize(AdapterConfig())
    assert initialized.ok
    assert initialized.value == "initialized"

    loaded = adapter.load_scene(SceneProfile(scene_id="minimal_scene", version="0.1.0"))
    assert loaded.ok
    assert loaded.value == "scene_loaded"

    reset = adapter.reset()
    assert reset.ok
    assert reset.value is not None
    assert reset.value.terrain_class == "flat"

    action = SafeAction(
        action_id="safe_move",
        action_type="body_velocity",
        body_velocity=Vec3(x=0.5, y=0.0, z=0.0),
        yaw_rate_radps=0.1,
        decision="accepted",
        timestamp_ns=1,
    )
    stepped = adapter.step(action)
    assert stepped.ok
    assert stepped.value is not None
    assert stepped.value.state == "running"
    assert stepped.value.robot_state.stability_state == "stable"
    assert stepped.value.robot_state.pose.position.x > 0.0

    closed = adapter.close()
    assert closed.ok
    assert closed.value == "stopped"


def test_rejected_action_is_not_mapped() -> None:
    rejected = SafeAction(action_id="safe_rejected", action_type="stop", decision="rejected")

    mapped = map_safe_action_to_isaac_command(rejected)

    assert not mapped.ok
    assert mapped.errors[0].code == "ACTION_REJECTED"


def test_step_before_reset_is_rejected() -> None:
    adapter = IsaacLabAdapter()
    adapter.initialize(AdapterConfig())
    adapter.load_scene(SceneProfile(scene_id="minimal_scene", version="0.1.0"))

    action = SafeAction(action_id="safe_stop", action_type="stop", decision="accepted")
    stepped = adapter.step(action)

    assert not stepped.ok
    assert stepped.errors[0].code == "ADAPTER_NOT_RUNNING"
