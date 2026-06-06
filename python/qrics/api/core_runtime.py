"""Optional bridge to the C++ QRICS core runtime executable.

The Web/API layer remains Python for local desktop usability, but the control
contract is implemented in C++ under ``qrics_core``.  This helper detects the
built ``qrics_core_runtime`` binary and can run a bounded smoke task that emits
JSON evidence from the C++ TaskExecutor/SafetyShield/SimulationAdapter path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from qrics.api.schemas import JsonDict


@dataclass(frozen=True)
class CoreRuntimeProbeResult:
    available: bool
    binary_path: str = ""
    command: tuple[str, ...] = ()
    summary: JsonDict | None = None
    error: str = ""

    def to_json(self) -> JsonDict:
        return {
            "available": self.available,
            "binary_path": self.binary_path,
            "command": list(self.command),
            "summary": self.summary or {},
            "error": self.error,
        }


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def locate_core_runtime_binary(root: Path | None = None) -> Path | None:
    env_path = os.environ.get("QRICS_CPP_CORE_RUNTIME_BIN", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    root_dir = root or repository_root()
    candidates = (
        root_dir / "build" / "dev-gcc-debug" / "qrics_core_runtime",
        root_dir / "build" / "release-gcc" / "qrics_core_runtime",
        root_dir / "build" / "dev-clang-debug" / "qrics_core_runtime",
    )
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    path_binary = shutil.which("qrics_core_runtime")
    if path_binary:
        return Path(path_binary)
    return None


def probe_core_runtime(
    binary_path: Path | str | None = None, *, timeout_s: float = 5.0
) -> CoreRuntimeProbeResult:
    binary = Path(binary_path) if binary_path is not None else locate_core_runtime_binary()
    if binary is None:
        return CoreRuntimeProbeResult(
            available=False,
            error=(
                "qrics_core_runtime binary not found; build it with "
                "`cmake --preset dev-gcc-debug && cmake --build --preset dev-gcc-debug`."
            ),
        )

    command = (
        str(binary),
        "--run-id",
        "py_core_probe",
        "--backend",
        "minimal",
        "--profile",
        "headless_fast",
        "--terrain",
        "flat",
        "--steps",
        "8",
        "--task-path",
        "A:0.18:0.0:0.35:0",
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as exc:
        return CoreRuntimeProbeResult(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"failed to execute C++ core runtime: {exc}",
        )

    if completed.returncode != 0:
        return CoreRuntimeProbeResult(
            available=False,
            binary_path=str(binary),
            command=command,
            error=(
                completed.stderr or completed.stdout or f"exit code {completed.returncode}"
            ).strip(),
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return CoreRuntimeProbeResult(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"C++ runtime returned non-JSON output: {exc}",
        )
    return CoreRuntimeProbeResult(
        available=True,
        binary_path=str(binary),
        command=command,
        summary=cast(JsonDict, parsed),
    )
