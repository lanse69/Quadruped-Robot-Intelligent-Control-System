#!/usr/bin/env python3
"""Generate a QRICS local demonstration evidence package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.demo.evidence import generate_evidence_bundle


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate QRICS local demo evidence files.")
    parser.add_argument("--output-dir", default="runtime/demo-evidence")
    parser.add_argument("--backend", default="minimal", choices=("minimal", "mujoco", "webots"))
    parser.add_argument("--runtime-profile", default="headless_fast")
    parser.add_argument("--task-text", default="避开障碍，巡检A后回到平台待命")
    parser.add_argument("--scene-json", default="")
    parser.add_argument("--webots-execute", action="store_true")
    parser.add_argument("--no-emergency-stop", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = generate_evidence_bundle(
        output_dir=args.output_dir,
        backend=args.backend,
        runtime_profile=args.runtime_profile,
        task_text=args.task_text,
        scene_json=args.scene_json or None,
        webots_execute=bool(args.webots_execute),
        trigger_emergency_stop=not bool(args.no_emergency_stop),
    )
    print(f"evidence_json: {result.evidence_json}")
    print(f"evidence_markdown: {result.evidence_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())