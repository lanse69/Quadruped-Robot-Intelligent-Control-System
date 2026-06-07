from qrics.sim import AdapterConfig, SafeAction, SceneProfile, SimulationAdapterFacade, Vec3
from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv
from qrics.sim.backends.webots_env import WebotsQuadrupedEnv
from qrics.sim.gait import synthesize_locomotion_hint, with_locomotion_hint


def test_gait_synthesis_enriches_safe_action_with_feet_and_joint_hints() -> None:
    action = SafeAction(
        action_id="safe_walk_flat",
        action_type="body_velocity",
        body_velocity=Vec3(x=0.32),
        decision="accepted",
        timestamp_ns=780_000_000,
    )

    enriched = with_locomotion_hint(action, terrain="flat")

    assert enriched.locomotion_hint.enabled is True
    assert enriched.locomotion_hint.gait_type == "trot"
    assert len(enriched.locomotion_hint.feet) == 4
    assert len(enriched.joint_commands) == 12
    assert {foot.phase for foot in enriched.locomotion_hint.feet} <= {"stance", "swing"}


def test_cautious_terrain_selects_lower_duty_gait() -> None:
    hint = synthesize_locomotion_hint(
        velocity=Vec3(x=0.18),
        yaw_rate_radps=0.0,
        terrain="low_friction",
        timestamp_ns=1_100_000_000,
    )

    assert hint.gait_type == "crawl"
    assert hint.duty_factor >= 0.70
    assert hint.body_height_m < 0.35


def test_minimal_backend_surfaces_locomotion_contact_phases() -> None:
    adapter = SimulationAdapterFacade(MinimalQuadrupedEnv())
    assert adapter.initialize(AdapterConfig(backend="minimal")).ok
    assert adapter.load_scene(SceneProfile(scene_id="gait_minimal", version="0.4.0")).ok
    assert adapter.reset().ok

    action = with_locomotion_hint(
        SafeAction(
            action_id="safe_walk_minimal",
            action_type="body_velocity",
            body_velocity=Vec3(x=0.30),
            decision="accepted",
            timestamp_ns=780_000_000,
        ),
        terrain="flat",
    )
    stepped = adapter.step(action)

    assert stepped.ok
    assert stepped.value is not None
    contacts = stepped.value.robot_state.contacts
    assert len(contacts) == 4
    assert any(not contact.in_contact for contact in contacts)
    assert any(contact.in_contact for contact in contacts)
    assert adapter.close().ok


def test_webots_dry_backend_accepts_enriched_locomotion_command() -> None:
    adapter = SimulationAdapterFacade(WebotsQuadrupedEnv(execute_webots=False))
    assert adapter.initialize(AdapterConfig(backend="webots", runtime_profile="webots_fast")).ok
    assert adapter.load_scene(SceneProfile(scene_id="gait_webots", version="0.4.0")).ok
    assert adapter.reset().ok

    action = with_locomotion_hint(
        SafeAction(
            action_id="safe_walk_webots",
            action_type="body_velocity",
            body_velocity=Vec3(x=0.24),
            decision="accepted",
            timestamp_ns=780_000_000,
        ),
        terrain="flat",
    )
    stepped = adapter.step(action)

    assert stepped.ok
    assert stepped.value is not None
    assert len(stepped.value.robot_state.contacts) == 4
    assert any(not contact.in_contact for contact in stepped.value.robot_state.contacts)
    assert adapter.close().ok
