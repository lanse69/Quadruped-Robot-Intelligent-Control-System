"""File-based local presentation command channel for MuJoCo/Webots viewers.

The API facade launches a long-lived presentation process for the selected
scene.  Subsequent task handoff calls write small JSON command files into the
process workspace.  The MuJoCo demo process and the Webots supervisor controller
poll that directory and execute only already-safety-gated, high-level motion
commands.  The channel deliberately does not expose joint commands or simulator
private objects.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

PresentationCommandType = Literal["run_path", "stop", "safe_stand"]


@dataclass(frozen=True)
class PresentationTarget:
    target_id: str
    x: float
    y: float
    dwell_steps: int = 0

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.target_id,
            "position": [self.x, self.y, 0.32],
            "dwell_steps": self.dwell_steps,
        }


@dataclass(frozen=True)
class PresentationCommand:
    command_id: str
    run_id: str
    command_type: PresentationCommandType
    created_ns: int = field(default_factory=time.time_ns)
    step_count: int = 0
    control_dt_s: float = 0.02
    forward_velocity_mps: float = 0.0
    yaw_rate_radps: float = 0.0
    task_path: tuple[PresentationTarget, ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "schema_version": "qrics.presentation.command.v1",
            "command_id": self.command_id,
            "run_id": self.run_id,
            "command_type": self.command_type,
            "created_ns": self.created_ns,
            "step_count": self.step_count,
            "control_dt_s": self.control_dt_s,
            "forward_velocity_mps": self.forward_velocity_mps,
            "yaw_rate_radps": self.yaw_rate_radps,
            "task_path": [target.to_json() for target in self.task_path],
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> PresentationCommand:
        command_type = str(payload.get("command_type", "run_path"))
        if command_type not in {"run_path", "stop", "safe_stand"}:
            raise ValueError("presentation command_type must be run_path, stop or safe_stand")
        return cls(
            command_id=str(payload.get("command_id", "")) or uuid.uuid4().hex,
            run_id=str(payload.get("run_id", "")),
            command_type=cast(PresentationCommandType, command_type),
            created_ns=_coerce_int(payload.get("created_ns"), default=time.time_ns(), minimum=0),
            step_count=_coerce_int(payload.get("step_count"), default=0, minimum=0),
            control_dt_s=_coerce_float(payload.get("control_dt_s"), default=0.02, minimum=0.001),
            forward_velocity_mps=_coerce_float(payload.get("forward_velocity_mps"), default=0.0),
            yaw_rate_radps=_coerce_float(payload.get("yaw_rate_radps"), default=0.0),
            task_path=tuple(targets_from_payload(payload.get("task_path", []))),
        )


def build_run_path_command(
    *,
    run_id: str,
    task_path: tuple[PresentationTarget, ...],
    step_count: int,
    control_dt_s: float,
    forward_velocity_mps: float,
    yaw_rate_radps: float,
) -> PresentationCommand:
    return PresentationCommand(
        command_id=f"cmd_{_safe_token(run_id)}_{time.time_ns()}_{uuid.uuid4().hex[:8]}",
        run_id=run_id,
        command_type="run_path",
        step_count=max(1, step_count),
        control_dt_s=max(0.001, control_dt_s),
        forward_velocity_mps=forward_velocity_mps,
        yaw_rate_radps=yaw_rate_radps,
        task_path=task_path,
    )


def build_stop_command(
    *, run_id: str, command_type: PresentationCommandType = "stop"
) -> PresentationCommand:
    if command_type not in {"stop", "safe_stand"}:
        raise ValueError("stop command must be stop or safe_stand")
    return PresentationCommand(
        command_id=f"cmd_{_safe_token(run_id)}_{time.time_ns()}_{uuid.uuid4().hex[:8]}",
        run_id=run_id,
        command_type=command_type,
        step_count=1,
    )


def write_presentation_command(command_dir: str | Path, command: PresentationCommand) -> Path:
    directory = Path(command_dir)
    directory.mkdir(parents=True, exist_ok=True)
    file_name = f"{command.created_ns:020d}_{_safe_token(command.command_id)}.json"
    target = directory / file_name
    tmp = directory / f".{file_name}.tmp"
    tmp.write_text(json.dumps(command.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    return target


def read_presentation_command(path: str | Path) -> PresentationCommand:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("presentation command file must contain a JSON object")
    return PresentationCommand.from_json(cast(dict[str, object], raw))


def iter_pending_presentation_commands(
    command_dir: str | Path,
    *,
    consumed_command_ids: set[str] | None = None,
) -> list[PresentationCommand]:
    directory = Path(command_dir)
    if not directory.exists():
        return []
    consumed = consumed_command_ids if consumed_command_ids is not None else set()
    commands: list[PresentationCommand] = []
    for path in sorted(directory.glob("*.json")):
        try:
            command = read_presentation_command(path)
        except Exception:
            continue
        if command.command_id in consumed:
            continue
        commands.append(command)
    return commands


def targets_from_scene_json(path: str | Path) -> tuple[PresentationTarget, ...]:
    if not str(path):
        return ()
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return ()
    return tuple(targets_from_scene_payload(raw))


def targets_from_scene_payload(payload: object) -> list[PresentationTarget]:
    if not isinstance(payload, dict):
        return []
    return targets_from_payload(payload.get("task_path", []))


def targets_from_payload(value: object) -> list[PresentationTarget]:
    if not isinstance(value, list):
        return []
    targets: list[PresentationTarget] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        position = item.get("position", [])
        if not isinstance(position, list) or len(position) < 2:
            continue
        try:
            x = float(position[0])
            y = float(position[1])
        except (TypeError, ValueError):
            continue
        targets.append(
            PresentationTarget(
                target_id=str(item.get("id", item.get("target_id", f"target_{index}"))),
                x=x,
                y=y,
                dwell_steps=max(0, int(item.get("dwell_steps", 0) or 0)),
            )
        )
    return targets


def _coerce_int(value: object, *, default: int, minimum: int | None = None) -> int:
    if isinstance(value, bool):
        coerced = int(value)
    elif isinstance(value, int):
        coerced = value
    elif isinstance(value, float):
        coerced = int(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            coerced = default
        else:
            try:
                coerced = int(stripped)
            except ValueError:
                coerced = default
    else:
        coerced = default
    if minimum is not None:
        return max(minimum, coerced)
    return coerced


def _coerce_float(value: object, *, default: float, minimum: float | None = None) -> float:
    if isinstance(value, (bool, int, float)):
        coerced = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            coerced = default
        else:
            try:
                coerced = float(stripped)
            except ValueError:
                coerced = default
    else:
        coerced = default
    if minimum is not None:
        return max(minimum, coerced)
    return coerced


def _safe_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)
    return token[:120] or "command"
