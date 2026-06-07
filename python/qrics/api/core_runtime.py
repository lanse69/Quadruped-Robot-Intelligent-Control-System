"""Bridge to the C++ QRICS core runtime executable.

The Web/API layer remains Python for local desktop usability, while the control
contract is implemented in C++ under ``qrics_core``.  This module detects the
built ``qrics_core_runtime`` binary and can run bounded task executions that
emit JSON evidence from the C++ TaskExecutor/SafetyShield/SimulationAdapter path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from qrics.api.schemas import JsonDict

CoreGeometryType = Literal["box", "cylinder", "sphere"]


@dataclass(frozen=True)
class CoreRuntimeTaskTarget:
    target_id: str
    x: float
    y: float
    z: float = 0.35
    dwell_time_s: float = 0.0


@dataclass(frozen=True)
class CoreRuntimeSceneObstacle:
    obstacle_id: str
    geometry_type: CoreGeometryType = "cylinder"
    x: float = 0.0
    y: float = 0.0
    z: float = 0.20
    size_x: float = 0.0
    size_y: float = 0.0
    size_z: float = 0.0
    radius_m: float = 0.12
    height_m: float = 0.35


@dataclass(frozen=True)
class CoreRuntimeForbiddenZone:
    zone_id: str
    polygon: tuple[tuple[float, float, float], ...]


@dataclass(frozen=True)
class CoreRuntimeRunRequest:
    run_id: str
    backend: str = "minimal"
    runtime_profile: str = "headless_fast"
    scene_id: str = "api_demo_scene"
    scene_version: str = "0.1.0"
    terrain_pack: str = "flat"
    step_count: int = 120
    task_path: tuple[CoreRuntimeTaskTarget, ...] = ()
    obstacles: tuple[CoreRuntimeSceneObstacle, ...] = ()
    forbidden_zones: tuple[CoreRuntimeForbiddenZone, ...] = ()
    evidence_dir: Path | str = ""
    clear_default_assets: bool = True


@dataclass(frozen=True)
class CoreRuntimeResult:
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


# Backwards-compatible public name used by the previous probe contract.
CoreRuntimeProbeResult = CoreRuntimeResult


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
) -> CoreRuntimeResult:
    request = CoreRuntimeRunRequest(
        run_id="py_core_probe",
        backend="minimal",
        runtime_profile="headless_fast",
        terrain_pack="flat",
        step_count=8,
        task_path=(CoreRuntimeTaskTarget("A", 0.18, 0.0, 0.35, 0.0),),
        clear_default_assets=False,
    )
    return run_core_runtime_task(request, binary_path=binary_path, timeout_s=timeout_s)


def run_core_runtime_task(
    request: CoreRuntimeRunRequest,
    binary_path: Path | str | None = None,
    *,
    timeout_s: float = 8.0,
) -> CoreRuntimeResult:
    binary = Path(binary_path) if binary_path is not None else locate_core_runtime_binary()
    if binary is None:
        return CoreRuntimeResult(
            available=False,
            error=(
                "qrics_core_runtime binary not found; build it with "
                "`cmake --preset dev-gcc-debug && cmake --build --preset dev-gcc-debug`."
            ),
        )

    command = _build_core_runtime_command(binary, request)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as exc:
        return CoreRuntimeResult(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"failed to execute C++ core runtime: {exc}",
        )

    if completed.returncode != 0:
        return CoreRuntimeResult(
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
        return CoreRuntimeResult(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"C++ runtime returned non-JSON output: {exc}",
        )
    return CoreRuntimeResult(
        available=True,
        binary_path=str(binary),
        command=command,
        summary=cast(JsonDict, parsed),
    )


def _build_core_runtime_command(binary: Path, request: CoreRuntimeRunRequest) -> tuple[str, ...]:
    command: list[str] = [
        str(binary),
        "--run-id",
        request.run_id,
        "--backend",
        request.backend,
        "--profile",
        request.runtime_profile,
        "--terrain",
        request.terrain_pack,
        "--scene-id",
        request.scene_id,
        "--scene-version",
        request.scene_version,
        "--steps",
        str(max(1, request.step_count)),
    ]
    if request.clear_default_assets:
        command.append("--clear-default-assets")
    if request.task_path:
        command.extend(["--task-path", _encode_task_path(request.task_path)])
    for obstacle in request.obstacles:
        command.extend(["--obstacle", _encode_obstacle(obstacle)])
    for zone in request.forbidden_zones:
        command.extend(["--forbidden-zone", _encode_forbidden_zone(zone)])
    evidence_dir = str(request.evidence_dir).strip()
    if evidence_dir:
        command.extend(["--evidence-dir", evidence_dir])
    return tuple(command)


def _encode_task_path(targets: Sequence[CoreRuntimeTaskTarget]) -> str:
    return ",".join(
        ":".join(
            (
                _safe_token(target.target_id),
                _number(target.x),
                _number(target.y),
                _number(target.z),
                _number(target.dwell_time_s),
            )
        )
        for target in targets
    )


def _encode_obstacle(obstacle: CoreRuntimeSceneObstacle) -> str:
    return ":".join(
        (
            _safe_token(obstacle.obstacle_id),
            obstacle.geometry_type,
            _number(obstacle.x),
            _number(obstacle.y),
            _number(obstacle.z),
            _number(obstacle.size_x),
            _number(obstacle.size_y),
            _number(obstacle.size_z),
            _number(obstacle.radius_m),
            _number(obstacle.height_m),
        )
    )


def _encode_forbidden_zone(zone: CoreRuntimeForbiddenZone) -> str:
    points = ";".join(":".join((_number(x), _number(y), _number(z))) for x, y, z in zone.polygon)
    return f"{_safe_token(zone.zone_id)}:{points}"


def _safe_token(value: str) -> str:
    cleaned = str(value).strip() or "unnamed"
    return cleaned.replace(":", "_").replace(",", "_").replace(";", "_")


def _number(value: float) -> str:
    return f"{float(value):.6g}"
