#!/usr/bin/env python3
"""Run a QRICS local Webots presentation demo.

By default this script launches Webots when the `webots` command is available.
Use `--dry-run` to verify the QRICS backend contract and generated command plan
without starting the external Webots process.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.sim import AdapterConfig, SafeAction, SceneProfile, SimulationAdapterFacade, Vec3
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
    return parser


def _safe_action(step_index: int, forward_velocity: float, yaw_rate: float) -> SafeAction:
    return SafeAction(
        action_id=f"webots_demo_body_velocity_{step_index}",
        source_proposal_id=f"webots_demo_proposal_{step_index}",
        action_type="body_velocity",
        body_velocity=Vec3(x=forward_velocity, y=0.0, z=0.0),
        yaw_rate_radps=yaw_rate,
        decision="accepted",
        reason="local Webots demo command",
        timestamp_ns=step_index * 32_000_000,
    )


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

    adapter = SimulationAdapterFacade(WebotsQuadrupedEnv(execute_webots=execute_webots))
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

    loaded = adapter.load_scene(
        SceneProfile(scene_id="local_webots_demo_scene", version="0.3.0", name="Local Webots Demo")
    )
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
    last_state = None

    try:
        for step_index in range(step_count):
            stepped = adapter.step(
                _safe_action(step_index, float(args.forward), float(args.yaw_rate))
            )
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