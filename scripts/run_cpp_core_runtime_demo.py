#!/usr/bin/env python3
"""Run the optional C++ core runtime smoke demo and print JSON evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from qrics.api.core_runtime import probe_core_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default="", help="Path to qrics_core_runtime executable")
    parser.add_argument("--timeout", type=float, default=5.0, help="Execution timeout in seconds")
    args = parser.parse_args()

    result = probe_core_runtime(args.binary or None, timeout_s=args.timeout)
    print(json.dumps(result.to_json(), ensure_ascii=False, indent=2))
    return 0 if result.available else 1


if __name__ == "__main__":
    raise SystemExit(main())