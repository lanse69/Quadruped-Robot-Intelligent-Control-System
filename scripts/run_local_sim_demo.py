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

from qrics.sim import AdapterConfig, SafeAction, SceneProfile, SimulationAdapterFacade, Vec3
from qrics.sim.scene_loader import load_scene_profile_from_json
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
        "--forward", type=float, default=0.25, help="Nominal forward velocity command."
    )
    parser.add_argument("--yaw-rate", type=float, default=0.10, help="Nominal yaw-rate command.")
    return parser


def _safe_action(step_index: int, forward_velocity: float, yaw_rate: float) -> SafeAction:
    return SafeAction(
        action_id=f"demo_body_velocity_{step_index}",
        source_proposal_id=f"demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=forward_velocity, y=0.0, z=0.0),
        yaw_rate_radps=yaw_rate,
        decision="accepted",
        reason="local MuJoCo demo command",
        timestamp_ns=step_index * 20_000_000,
    )


def _path_action(
    step_index: int,
    position: Vec3,
    target: tuple[str, float, float],
    forward_velocity: float,
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
    return SafeAction(
        action_id=f"demo_path_{step_index}_{target_id}",
        source_proposal_id=f"demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=vx, y=vy, z=0.0),
        yaw_rate_radps=max(-0.8, min(0.8, math.atan2(dy, dx) * 0.35)),
        decision="accepted",
        reason=f"local MuJoCo task-path target {target_id}",
        timestamp_ns=step_index * 20_000_000,
    )


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
                action = _path_action(step_index, position, target, float(args.forward))
            else:
                action = _safe_action(step_index, float(args.forward), float(args.yaw_rate))
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