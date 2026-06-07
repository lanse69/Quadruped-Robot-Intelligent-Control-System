#!/usr/bin/env python3
"""Run a local QRICS simulation demo on the MuJoCo backend."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.sim import (
    AdapterConfig,
    SafeAction,
    SceneProfile,
    SimulationAdapterFacade,
    TerrainClass,
    Vec3,
)
from qrics.sim.gait import with_locomotion_hint
from qrics.sim.scene_loader import load_scene_profile_from_json
from qrics.sim.presentation_channel import (
    PresentationCommand,
    iter_pending_presentation_commands,
    targets_from_scene_json,
)
from qrics.sim.runtime_profile import PROFILES


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QRICS local MuJoCo simulation demo.")
    parser.add_argument(
        "--profile",
        default="balanced_visual",
        choices=sorted(PROFILES),
        help="Runtime profile. balanced_visual is the default for local demonstration.",
    )
    parser.add_argument(
        "--seconds", type=_positive_float, default=None, help="Demo duration in seconds."
    )
    parser.add_argument(
        "--viewer",
        action="store_true",
        help="Prefer a MuJoCo passive viewer. If the viewer fails, retry headless_fast.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Requested display width for documentation/logging.",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Requested display height for documentation/logging.",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="Reserve video-recording intent for future rich_demo support; no video file is written yet.",
    )
    parser.add_argument(
        "--scene-json",
        default="",
        help="Optional local QRICS scene JSON with typed box/sphere/cylinder obstacles.",
    )
    parser.add_argument(
        "--command-dir",
        default="",
        help=(
            "Optional directory watched for QRICS presentation command JSON files. "
            "When set, the viewer stays open and executes commands written by the API."
        ),
    )
    parser.add_argument(
        "--forward", type=float, default=0.25, help="Nominal forward velocity command."
    )
    parser.add_argument("--yaw-rate", type=float, default=0.10, help="Nominal yaw-rate command.")
    return parser


def _safe_action(
    step_index: int,
    forward_velocity: float,
    yaw_rate: float,
    terrain: TerrainClass = "flat",
) -> SafeAction:
    action = SafeAction(
        action_id=f"demo_body_velocity_{step_index}",
        source_proposal_id=f"demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=forward_velocity, y=0.0, z=0.0),
        yaw_rate_radps=yaw_rate,
        decision="accepted",
        reason="local MuJoCo demo command",
        timestamp_ns=step_index * 20_000_000,
    )
    return with_locomotion_hint(action, terrain=terrain)


def _path_action(
    step_index: int,
    position: Vec3,
    target: tuple[str, float, float],
    forward_velocity: float,
    terrain: TerrainClass = "flat",
) -> SafeAction:
    target_id, target_x, target_y = target
    dx = target_x - position.x
    dy = target_y - position.y
    distance = math.hypot(dx, dy)
    speed = max(0.05, abs(forward_velocity))
    if distance > 1.0e-6:
        vx = speed * dx / distance
        vy = speed * dy / distance
    else:
        vx = 0.0
        vy = 0.0
    action = SafeAction(
        action_id=f"demo_path_{step_index}_{target_id}",
        source_proposal_id=f"demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=vx, y=vy, z=0.0),
        yaw_rate_radps=max(-0.8, min(0.8, math.atan2(dy, dx) * 0.35)),
        decision="accepted",
        reason=f"local MuJoCo task-path target {target_id}",
        timestamp_ns=step_index * 20_000_000,
    )
    return with_locomotion_hint(action, terrain=terrain)


def _task_path_from_scene(scene_json: str) -> list[tuple[str, float, float]]:
    if not scene_json:
        return []
    try:
        raw = json.loads(Path(scene_json).read_text(encoding="utf-8"))
    except Exception:
        return []
    path = raw.get("task_path") if isinstance(raw, dict) else None
    if not isinstance(path, list):
        return []
    targets: list[tuple[str, float, float]] = []
    for index, item in enumerate(path):
        if not isinstance(item, dict):
            continue
        position = item.get("position", [])
        if not isinstance(position, list) or len(position) < 2:
            continue
        targets.append(
            (str(item.get("id", f"target_{index}")), float(position[0]), float(position[1]))
        )
    return targets


def _stop_action(step_index: int) -> SafeAction:
    return SafeAction(
        action_id=f"demo_stop_{step_index}",
        source_proposal_id=f"demo_proposal_{step_index}",
        action_type="stop",
        decision="accepted",
        reason="local MuJoCo demo stop",
        timestamp_ns=step_index * 20_000_000,
    )


def _create_adapter() -> SimulationAdapterFacade:
    try:
        from qrics.sim.backends.mujoco_env import MujocoQuadrupedEnv
    except ModuleNotFoundError as exc:
        missing = exc.name or "mujoco"
        raise RuntimeError(
            "MuJoCo backend is not installed. Activate the project venv and run "
            '"python -m pip install -e .[local-sim]" before starting the local demo. '
            f"Missing module: {missing}"
        ) from exc

    return SimulationAdapterFacade(MujocoQuadrupedEnv())


def _initialize_and_reset(adapter: SimulationAdapterFacade, profile: str, scene_json: str = ""):
    initialized = adapter.initialize(
        AdapterConfig(
            adapter_name="local_mujoco",
            adapter_version="0.2.0",
            backend="mujoco",
            runtime_profile=profile,
        )
    )
    if not initialized.ok:
        return initialized

    scene = (
        load_scene_profile_from_json(scene_json)
        if scene_json
        else SceneProfile(
            scene_id="local_mujoco_demo_scene", version="0.2.0", name="Local MuJoCo Demo"
        )
    )
    loaded = adapter.load_scene(scene)
    if not loaded.ok:
        return loaded

    return adapter.reset()


def _print_failure(prefix: str, result: object) -> None:
    errors = getattr(result, "errors", ())
    if errors:
        first = errors[0]
        print(f"{prefix}: {first.code}: {first.message}", file=sys.stderr)
    else:
        print(prefix, file=sys.stderr)



def _target_tuples_for_command(
    command: PresentationCommand,
    scene_json: str,
) -> list[tuple[str, float, float]]:
    targets = command.task_path or targets_from_scene_json(scene_json)
    return [(target.target_id, target.x, target.y) for target in targets]


def _run_interactive_demo(
    args: argparse.Namespace,
    adapter: SimulationAdapterFacade,
    profile: object,
    requested_profile: str,
    duration_s: float,
    reset: object,
) -> int:
    """Keep a MuJoCo viewer open and consume API-authored command files."""
    step_period_s = 0.02
    step_count = max(1, int(duration_s / step_period_s))
    consumed: set[str] = set()
    active_targets: list[tuple[str, float, float]] = []
    active_forward = float(args.forward)
    active_yaw_rate = float(args.yaw_rate)
    active_remaining_steps = 0
    target_index = 0
    last_state = reset.value.robot_state if getattr(reset, "value", None) is not None else None
    wall_start = time.monotonic()

    print(f"presentation_command_dir: {args.command_dir}", flush=True)
    try:
        for step_index in range(step_count):
            for command in iter_pending_presentation_commands(
                str(args.command_dir), consumed_command_ids=consumed
            ):
                consumed.add(command.command_id)
                if command.command_type == "run_path":
                    active_targets = _target_tuples_for_command(command, str(args.scene_json))
                    active_forward = command.forward_velocity_mps or float(args.forward)
                    active_yaw_rate = command.yaw_rate_radps or float(args.yaw_rate)
                    active_remaining_steps = max(1, command.step_count)
                    target_index = 0
                    print(
                        "presentation_command_received: "
                        f"{command.command_id} run_id={command.run_id} "
                        f"targets={len(active_targets)} steps={active_remaining_steps}",
                        flush=True,
                    )
                elif command.command_type in {"stop", "safe_stand"}:
                    active_targets = []
                    active_remaining_steps = 1
                    active_forward = 0.0
                    active_yaw_rate = 0.0
                    print(
                        "presentation_command_received: "
                        f"{command.command_id} {command.command_type}",
                        flush=True,
                    )

            if active_remaining_steps > 0 and active_targets and last_state is not None:
                target = active_targets[min(target_index, len(active_targets) - 1)]
                position = last_state.pose.position
                if math.hypot(target[1] - position.x, target[2] - position.y) <= 0.08:
                    target_index = min(target_index + 1, len(active_targets) - 1)
                    target = active_targets[target_index]
                terrain = getattr(last_state, "terrain_class", "flat")
                action = _path_action(step_index, position, target, active_forward, terrain)
                active_remaining_steps -= 1
            elif active_remaining_steps > 0:
                terrain = getattr(last_state, "terrain_class", "flat") if last_state is not None else "flat"
                action = _safe_action(step_index, active_forward, active_yaw_rate, terrain)
                active_remaining_steps -= 1
            else:
                action = _stop_action(step_index)

            stepped = adapter.step(action)
            if not stepped.ok:
                _print_failure("interactive demo step failed", stepped)
                return 1
            if stepped.value is not None:
                last_state = stepped.value.robot_state

            if getattr(profile, "render_mode", "") == "viewer":
                elapsed = time.monotonic() - wall_start
                target_s = (step_index + 1) * step_period_s
                if target_s > elapsed:
                    time.sleep(min(0.02, target_s - elapsed))
    finally:
        adapter.close()

    wall_elapsed = time.monotonic() - wall_start
    if last_state is None:
        print("interactive demo completed, but no robot state was returned", file=sys.stderr)
        return 1

    print("demo_result: ok")
    print(f"actual_profile: {requested_profile}")
    print(f"interactive_mode: true")
    print(f"steps: {step_count}")
    print(f"wall_elapsed_s: {wall_elapsed:.3f}")
    print(f"robot_time_ns: {last_state.timestamp_ns}")
    print(
        "base_position: "
        f"x={last_state.pose.position.x:.3f}, "
        f"y={last_state.pose.position.y:.3f}, "
        f"z={last_state.pose.position.z:.3f}"
    )
    print(f"stability_state: {last_state.stability_state}")
    print(f"risk_score: {last_state.risk_score:.3f}")
    print(f"consumed_presentation_commands: {len(consumed)}")
    return 0


def run_demo(args: argparse.Namespace) -> int:
    requested_profile = str(args.profile)
    if args.viewer and requested_profile == "headless_fast":
        requested_profile = "balanced_visual"

    if args.record and requested_profile != "rich_demo":
        print("record requested: switching runtime profile to rich_demo intent")
        requested_profile = "rich_demo"

    profile = PROFILES[requested_profile]
    duration_s = float(
        args.seconds if args.seconds is not None else min(20.0, profile.max_demo_seconds)
    )
    duration_s = min(duration_s, profile.max_demo_seconds)

    try:
        adapter = _create_adapter()
    except RuntimeError as exc:
        print(f"demo startup failed: {exc}", file=sys.stderr)
        return 1

    print("QRICS local MuJoCo simulation demo")
    print(f"profile: {requested_profile}")
    print(f"requested_display: {args.width}x{args.height}")
    print(f"duration_s: {duration_s:.2f}")

    reset = _initialize_and_reset(adapter, requested_profile, str(args.scene_json))
    if not reset.ok and requested_profile != "headless_fast":
        _print_failure("viewer/profile startup failed; retrying with headless_fast", reset)
        adapter.close()
        requested_profile = "headless_fast"
        profile = PROFILES[requested_profile]
        duration_s = min(duration_s, profile.max_demo_seconds)
        try:
            adapter = _create_adapter()
        except RuntimeError as exc:
            print(f"demo startup failed: {exc}", file=sys.stderr)
            return 1
        reset = _initialize_and_reset(adapter, requested_profile, str(args.scene_json))

    if not reset.ok:
        _print_failure("demo startup failed", reset)
        adapter.close()
        return 1

    if str(args.command_dir):
        return _run_interactive_demo(args, adapter, profile, requested_profile, duration_s, reset)

    step_period_s = 0.02
    step_count = max(1, int(duration_s / step_period_s))
    task_path = _task_path_from_scene(str(args.scene_json))
    target_index = 0
    wall_start = time.monotonic()
    last_state = reset.value.robot_state if reset.value is not None else None

    try:
        for step_index in range(step_count):
            if task_path and last_state is not None:
                target = task_path[min(target_index, len(task_path) - 1)]
                position = last_state.pose.position
                if math.hypot(target[1] - position.x, target[2] - position.y) <= 0.08:
                    target_index = min(target_index + 1, len(task_path) - 1)
                    target = task_path[target_index]
                terrain = getattr(last_state, "terrain_class", "flat")
                action = _path_action(step_index, position, target, float(args.forward), terrain)
            else:
                terrain = getattr(last_state, "terrain_class", "flat") if last_state is not None else "flat"
                action = _safe_action(step_index, float(args.forward), float(args.yaw_rate), terrain)
            stepped = adapter.step(action)
            if not stepped.ok:
                _print_failure("demo step failed", stepped)
                return 1
            if stepped.value is not None:
                last_state = stepped.value.robot_state

            if profile.render_mode == "viewer":
                elapsed = time.monotonic() - wall_start
                target = (step_index + 1) * step_period_s
                if target > elapsed:
                    time.sleep(min(0.02, target - elapsed))

        stopped = adapter.step(_stop_action(step_count))
        if not stopped.ok:
            _print_failure("demo stop failed", stopped)
            return 1
        if stopped.value is not None:
            last_state = stopped.value.robot_state
    finally:
        adapter.close()

    wall_elapsed = time.monotonic() - wall_start
    if last_state is None:
        print("demo completed, but no robot state was returned", file=sys.stderr)
        return 1

    print("demo_result: ok")
    print(f"actual_profile: {requested_profile}")
    print(f"steps: {step_count}")
    print(f"wall_elapsed_s: {wall_elapsed:.3f}")
    print(f"robot_time_ns: {last_state.timestamp_ns}")
    print(
        "base_position: "
        f"x={last_state.pose.position.x:.3f}, "
        f"y={last_state.pose.position.y:.3f}, "
        f"z={last_state.pose.position.z:.3f}"
    )
    print(f"stability_state: {last_state.stability_state}")
    print(f"risk_score: {last_state.risk_score:.3f}")
    print(f"contacts: {len(last_state.contacts)}")
    if args.record:
        print(
            "record_note: video recording is reserved for rich_demo wiring; no video file was written."
        )
    return 0


def main() -> int:
    return run_demo(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())