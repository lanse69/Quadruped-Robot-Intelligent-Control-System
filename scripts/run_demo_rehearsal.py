#!/usr/bin/env python3
"""Run a QRICS local defence end-to-end rehearsal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.api.schemas import SimulationBackend
from qrics.demo.rehearsal import (
    DemoRehearsalConfig,
    render_rehearsal_markdown,
    run_demo_rehearsal,
    write_rehearsal_report,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the QRICS local defence rehearsal: scene save, preview, one-click task run, "
            "safety override, replay/audit query, and lightweight training/evaluation gate."
        )
    )
    parser.add_argument("--backend", default="minimal", choices=("minimal", "mujoco", "webots"))
    parser.add_argument("--runtime-profile", default="headless_fast")
    parser.add_argument("--step-count", type=int, default=12)
    parser.add_argument(
        "--task-text",
        default="从平台出发，避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
    )
    parser.add_argument("--scene-id", default="defense_rehearsal_scene")
    parser.add_argument("--scene-version", default="0.5.0")
    parser.add_argument(
        "--fixed-scene-version",
        action="store_true",
        help="Use the exact scene version instead of appending a timestamp suffix.",
    )
    parser.add_argument(
        "--webots-execute",
        action="store_true",
        help="Allow the Webots backend to launch Webots during rehearsal.",
    )
    parser.add_argument(
        "--skip-training-gate",
        action="store_true",
        help="Skip the lightweight training/evaluation/model lifecycle segment.",
    )
    parser.add_argument(
        "--skip-overrides",
        action="store_true",
        help="Skip Safe-Stand and emergency stop commands.",
    )
    parser.add_argument("--output-dir", default="runtime/demo-rehearsal")
    parser.add_argument("--format", choices=("summary", "markdown", "json"), default="summary")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    backend = cast(SimulationBackend, args.backend)
    report = run_demo_rehearsal(
        config=DemoRehearsalConfig(
            backend=backend,
            runtime_profile=str(args.runtime_profile),
            step_count=max(1, int(args.step_count)),
            task_text=str(args.task_text),
            scene_id=str(args.scene_id),
            scene_version=str(args.scene_version),
            unique_scene_version=not bool(args.fixed_scene_version),
            webots_execute=bool(args.webots_execute),
            include_training_gate=not bool(args.skip_training_gate),
            include_overrides=not bool(args.skip_overrides),
        )
    )
    json_path, markdown_path = write_rehearsal_report(report, args.output_dir)
    if args.format == "json":
        print(json_path.read_text(encoding="utf-8"))
    elif args.format == "markdown":
        print(render_rehearsal_markdown(report))
    else:
        print("QRICS local defence rehearsal")
        print(f"status: {report.status}")
        print(f"backend: {report.backend}")
        print(f"runtime_profile: {report.runtime_profile}")
        print(f"scene: {report.scene_ref.id}:{report.scene_ref.version}")
        print(f"run_id: {report.run_id or '-'}")
        print(f"steps: {len(report.steps)}")
        print(f"failed_steps: {len(report.failed_steps)}")
        print(f"evidence_json: {json_path}")
        print(f"evidence_markdown: {markdown_path}")
        if report.failed_steps:
            print("failed_step_ids: " + ", ".join(step.step_id for step in report.failed_steps))
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())