#!/usr/bin/env python3
"""Run a QRICS local Webots presentation demo.

By default this script launches Webots when the `webots` command is available.
Use `--dry-run` to verify the QRICS backend contract and generated command plan
without starting the external Webots process.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
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
from qrics.sim.backends.webots_env import WebotsQuadrupedEnv
from qrics.sim.runtime_profile import PROFILES


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QRICS local Webots presentation demo.")
    parser.add_argument(
        "--profile",
        default="webots_fast",
        choices=sorted(PROFILES),
        help="Runtime profile. webots_fast is the default for local Webots demonstration.",
    )
    parser.add_argument("--seconds", type=_positive_float, default=12.0, help="Demo duration.")
    parser.add_argument("--forward", type=float, default=0.22, help="Forward velocity command.")
    parser.add_argument("--yaw-rate", type=float, default=0.08, help="Yaw-rate command.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the QRICS Webots backend without launching the external Webots process.",
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
            "Optional directory watched by the Webots supervisor for QRICS "
            "presentation commands while the window remains open."
        ),
    )
    return parser


def _safe_action(
    step_index: int,
    forward_velocity: float,
    yaw_rate: float,
    terrain: TerrainClass = "flat",
) -> SafeAction:
    action = SafeAction(
        action_id=f"webots_demo_body_velocity_{step_index}",
        source_proposal_id=f"webots_demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=forward_velocity, y=0.0, z=0.0),
        yaw_rate_radps=yaw_rate,
        decision="accepted",
        reason="local Webots demo command",
        timestamp_ns=step_index * 32_000_000,
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
        action_id=f"webots_demo_path_{step_index}_{target_id}",
        source_proposal_id=f"webots_demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=vx, y=vy, z=0.0),
        yaw_rate_radps=max(-0.8, min(0.8, math.atan2(dy, dx) * 0.35)),
        decision="accepted",
        reason=f"local Webots task-path target {target_id}",
        timestamp_ns=step_index * 32_000_000,
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


def _print_failure(prefix: str, result: object) -> None:
    errors = getattr(result, "errors", ())
    if errors:
        first = errors[0]
        print(f"{prefix}: {first.code}: {first.message}", file=sys.stderr)
    else:
        print(prefix, file=sys.stderr)


def run_demo(args: argparse.Namespace) -> int:
    webots_path = shutil.which("webots") or (
        "/snap/bin/webots" if Path("/snap/bin/webots").exists() else ""
    )
    execute_webots = not bool(args.dry_run)
    if execute_webots and not webots_path:
        print(
            "webots executable was not found. Install Webots or rerun with --dry-run "
            "to validate the QRICS side.",
            file=sys.stderr,
        )
        return 1

    adapter = SimulationAdapterFacade(
        WebotsQuadrupedEnv(
            execute_webots=execute_webots,
            command_dir=str(args.command_dir) if str(args.command_dir) else None,
        )
    )
    initialized = adapter.initialize(
        AdapterConfig(
            adapter_name="local_webots",
            adapter_version="0.3.0",
            backend="webots",
            runtime_profile=str(args.profile),
        )
    )
    if not initialized.ok:
        _print_failure("webots demo initialize failed", initialized)
        return 1

    scene = (
        load_scene_profile_from_json(str(args.scene_json))
        if str(args.scene_json)
        else SceneProfile(
            scene_id="local_webots_demo_scene", version="0.3.0", name="Local Webots Demo"
        )
    )
    loaded = adapter.load_scene(scene)
    if not loaded.ok:
        _print_failure("webots demo scene load failed", loaded)
        return 1

    reset = adapter.reset()
    if not reset.ok:
        _print_failure("webots demo reset failed", reset)
        return 1

    profile = PROFILES[str(args.profile)]
    step_period_s = profile.physics_timestep_s * max(1, profile.control_decimation)
    step_count = max(1, int(float(args.seconds) / step_period_s))
    if str(args.command_dir):
        closed = adapter.close()
        if not closed.ok:
            _print_failure("webots presentation close/external run failed", closed)
            return 1
        last_state = reset.value.robot_state if reset.value is not None else None
        print("QRICS local Webots presentation demo")
        print(f"profile: {args.profile}")
        print(f"dry_run: {bool(args.dry_run)}")
        print(f"webots_command: {webots_path or 'not-found'}")
        print(f"presentation_command_dir: {args.command_dir}")
        print("interactive_mode: true")
        if last_state is not None:
            print(f"robot_time_ns: {last_state.timestamp_ns}")
            print(
                "base_position: "
                f"x={last_state.pose.position.x:.3f}, "
                f"y={last_state.pose.position.y:.3f}, "
                f"z={last_state.pose.position.z:.3f}"
            )
        return 0

    task_path = _task_path_from_scene(str(args.scene_json))
    target_index = 0
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
                _print_failure("webots demo step failed", stepped)
                return 1
            if stepped.value is not None:
                last_state = stepped.value.robot_state
    finally:
        closed = adapter.close()
        if not closed.ok:
            _print_failure("webots demo close/external run failed", closed)
            return 1

    if last_state is None:
        print("webots demo completed without robot state", file=sys.stderr)
        return 1

    print("QRICS local Webots presentation demo")
    print(f"profile: {args.profile}")
    print(f"dry_run: {bool(args.dry_run)}")
    print(f"webots_command: {webots_path or 'not-found'}")
    print(f"steps: {step_count}")
    print(f"robot_time_ns: {last_state.timestamp_ns}")
    print(
        "base_position: "
        f"x={last_state.pose.position.x:.3f}, "
        f"y={last_state.pose.position.y:.3f}, "
        f"z={last_state.pose.position.z:.3f}"
    )
    print(f"stability_state: {last_state.stability_state}")
    print(f"risk_score: {last_state.risk_score:.3f}")
    return 0


def main() -> int:
    return run_demo(_build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())