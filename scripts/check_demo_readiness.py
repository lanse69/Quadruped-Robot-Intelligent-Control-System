#!/usr/bin/env python3
"""Print QRICS local demo readiness as JSON or Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.demo.readiness import (  # noqa: E402
    DemoReadinessConfig,
    collect_demo_readiness,
    render_readiness_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check QRICS local demo readiness")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="markdown",
        help="Output format.",
    )
    parser.add_argument(
        "--state-dir",
        default="",
        help="Override console state directory used for write checks.",
    )
    parser.add_argument(
        "--webots-executable",
        default="webots",
        help="Webots executable name/path to probe.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = collect_demo_readiness(
        DemoReadinessConfig(
            root_dir=ROOT_DIR,
            state_dir=Path(args.state_dir).expanduser() if args.state_dir else None,
            webots_executable=args.webots_executable,
        )
    )
    if args.format == "json":
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
    else:
        print(render_readiness_markdown(report), end="")
    return 0 if report.status in {"ready", "degraded"} else 2


if __name__ == "__main__":
    raise SystemExit(main())