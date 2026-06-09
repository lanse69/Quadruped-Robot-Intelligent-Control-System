"""Webots supervisor controller for QRICS local demonstration runs.

The controller reads a QRICS-generated JSON run specification from the
``QRICS_WEBOTS_RUN_SPEC`` environment variable, animates the quadruped body in a
Webots world, and writes a JSON summary to ``QRICS_WEBOTS_RUN_OUTPUT``.  It uses
Webots only as the local visual/simulation presentation process; QRICS safety
and task decisions remain outside this controller.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, cast

from controller import Supervisor  # type: ignore[import-not-found]

_LEG_SPECS: dict[str, tuple[str, tuple[float, float, float]]] = {
    "front_left": ("QRICS_LEG_FL", (0.20, 0.13, -0.14)),
    "front_right": ("QRICS_LEG_FR", (0.20, -0.13, -0.14)),
    "rear_left": ("QRICS_LEG_RL", (-0.20, 0.13, -0.14)),
    "rear_right": ("QRICS_LEG_RR", (-0.20, -0.13, -0.14)),
}

_CRAWL_OFFSETS: dict[str, float] = {
    "front_left": 0.00,
    "rear_right": 0.25,
    "front_right": 0.50,
    "rear_left": 0.75,
}

_TROT_OFFSETS: dict[str, float] = {
    "front_left": 0.00,
    "rear_right": 0.00,
    "front_right": 0.50,
    "rear_left": 0.50,
}


class _LegHandle:
    def __init__(self, translation_field: Any, rotation_field: Any) -> None:
        self.translation_field = translation_field
        self.rotation_field = rotation_field


def _resolve_leg_handles(supervisor: Supervisor) -> dict[str, _LegHandle]:
    handles: dict[str, _LegHandle] = {}
    for foot_name, (def_name, _nominal) in _LEG_SPECS.items():
        node = supervisor.getFromDef(def_name)
        if node is None:
            continue
        handles[foot_name] = _LegHandle(
            translation_field=node.getField("translation"),
            rotation_field=node.getField("rotation"),
        )
    return handles


def _visual_gait(vx: float, vy: float, yaw_rate: float, terrain: str) -> str:
    speed = math.hypot(vx, vy)
    if speed < 0.035 and abs(yaw_rate) < 0.05:
        return "stand"
    if terrain in {"stairs", "low_friction"} or speed < 0.12:
        return "crawl"
    if terrain in {"slope", "gravel", "unknown", "mixed", "mixed_terrain", "mixed_terrain_pack"}:
        return "cautious_trot"
    return "trot"


def _visual_gait_frequency_hz(gait: str, speed: float) -> float:
    if gait == "stand":
        return 0.0
    if gait == "crawl":
        return 0.85 + min(0.25, speed * 0.5)
    if gait == "cautious_trot":
        return 1.10 + min(0.30, speed * 0.6)
    return 1.45 + min(0.45, speed * 0.75)


def _visual_gait_duty(gait: str) -> float:
    if gait == "stand":
        return 1.0
    if gait == "crawl":
        return 0.78
    if gait == "cautious_trot":
        return 0.66
    return 0.58


def _wrap01(value: float) -> float:
    wrapped = value - math.floor(value)
    return wrapped + 1.0 if wrapped < 0.0 else wrapped


def _swing_progress(local_phase: float, duty_factor: float) -> float:
    if local_phase <= duty_factor:
        return 0.0
    return max(0.0, min(1.0, (local_phase - duty_factor) / max(1.0e-6, 1.0 - duty_factor)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _apply_leg_animation(
    handles: dict[str, _LegHandle],
    *,
    gait_phase: float,
    vx: float,
    vy: float,
    yaw_rate: float,
    terrain: str,
) -> str:
    gait = _visual_gait(vx, vy, yaw_rate, terrain)
    duty = _visual_gait_duty(gait)
    offsets = _CRAWL_OFFSETS if gait == "crawl" else _TROT_OFFSETS
    speed = math.hypot(vx, vy)
    stride_x = _clamp(vx * 0.16, -0.055, 0.055)
    stride_y = _clamp(vy * 0.10, -0.035, 0.035)
    turn_stride = _clamp(yaw_rate * 0.020, -0.025, 0.025)
    lift = 0.0 if gait == "stand" else _clamp(0.018 + speed * 0.055, 0.018, 0.050)

    for foot_name, handle in handles.items():
        nominal = _LEG_SPECS[foot_name][1]
        if gait == "stand":
            handle.translation_field.setSFVec3f([nominal[0], nominal[1], nominal[2]])
            handle.rotation_field.setSFRotation([0.0, 1.0, 0.0, 0.0])
            continue

        local_phase = _wrap01(gait_phase + offsets.get(foot_name, 0.0))
        swing = local_phase > duty
        swing_s = _swing_progress(local_phase, duty)
        phase_shape = math.sin(math.pi * swing_s) if swing else 0.0
        stance_shape = -0.25 if not swing else swing_s - 0.5
        front_sign = 1.0 if nominal[0] >= 0.0 else -1.0
        side_sign = 1.0 if nominal[1] >= 0.0 else -1.0
        tx = nominal[0] + stride_x * stance_shape + turn_stride * front_sign * side_sign
        ty = nominal[1] + stride_y * (0.5 if swing else -0.2)
        tz = nominal[2] + lift * phase_shape
        pitch = _clamp(
            (0.18 if swing else -0.06) * math.sin(2.0 * math.pi * local_phase), -0.22, 0.22
        )
        handle.translation_field.setSFVec3f([tx, ty, tz])
        handle.rotation_field.setSFRotation([0.0, 1.0, 0.0, pitch])
    return gait


def _read_spec() -> dict[str, Any]:
    spec_path = os.environ.get("QRICS_WEBOTS_RUN_SPEC", "")
    if not spec_path:
        return {"commands": [], "initial_position": [0.0, 0.0, 0.32]}
    parsed: Any = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("QRICS Webots run spec must be a JSON object")
    return cast(dict[str, Any], parsed)


def _write_output(payload: dict[str, Any]) -> None:
    output_path = os.environ.get("QRICS_WEBOTS_RUN_OUTPUT", "")
    if output_path:
        Path(output_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _pending_command_files(command_dir: str, consumed: set[str]) -> list[dict[str, Any]]:
    if not command_dir:
        return []
    directory = Path(command_dir)
    if not directory.exists():
        return []
    commands: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        command_id = str(payload.get("command_id", path.name))
        if command_id in consumed:
            continue
        consumed.add(command_id)
        payload["command_id"] = command_id
        commands.append(payload)
    return commands


def _targets_from_command(command: dict[str, Any]) -> list[tuple[str, float, float]]:
    raw_targets = command.get("task_path", [])
    if not isinstance(raw_targets, list):
        return []
    targets: list[tuple[str, float, float]] = []
    for index, item in enumerate(raw_targets):
        if not isinstance(item, dict):
            continue
        position = item.get("position", [])
        if not isinstance(position, list) or len(position) < 2:
            continue
        targets.append(
            (str(item.get("id", f"target_{index}")), float(position[0]), float(position[1]))
        )
    return targets


def _write_state_output(
    sim_time_s: float,
    x: float,
    y: float,
    z: float,
    yaw: float,
    command_count: int,
    gait_name: str = "stand",
    gait_phase: float = 0.0,
) -> None:
    _write_output(
        {
            "ok": True,
            "sim_time_ns": int(sim_time_s * 1_000_000_000),
            "base_position": [x, y, z],
            "yaw_rad": yaw,
            "command_count": command_count,
            "gait_name": gait_name,
            "gait_phase": gait_phase,
        }
    )


def _hold_visible(supervisor: Supervisor, seconds: float) -> None:
    hold_seconds = max(0.0, seconds)
    timestep_ms = int(supervisor.getBasicTimeStep())
    if timestep_ms <= 0:
        timestep_ms = 16
    frames = int(math.ceil(hold_seconds / (timestep_ms / 1000.0))) if hold_seconds else 0
    for _ in range(frames):
        if supervisor.step(timestep_ms) == -1:
            break


def _safe_hold_seconds(spec: dict[str, Any] | None = None) -> float:
    if spec is not None:
        try:
            return max(0.0, float(spec.get("hold_seconds", 0.0)))
        except Exception:
            pass
    raw = os.environ.get("QRICS_WEBOTS_HOLD_SECONDS", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 120.0


def _spawn_terrain(supervisor: Supervisor, spec: dict[str, Any]) -> None:
    root = supervisor.getRoot()
    children = root.getField("children")
    terrain = str(spec.get("terrain_pack", "flat"))
    _spawn_semantic_markers(children, spec)
    for region in _terrain_regions(spec, terrain):
        terrain_class = str(region.get("terrain_class", "flat"))
        if terrain_class == "slope":
            _spawn_slope_region(children, region)
        elif terrain_class == "stairs":
            _spawn_stairs_region(children, region)
        elif terrain_class == "gravel":
            _spawn_gravel_region(children, region)


def _terrain_regions(spec: dict[str, Any], terrain: str) -> list[dict[str, Any]]:
    raw_regions = spec.get("terrain_regions", [])
    if isinstance(raw_regions, list) and raw_regions:
        return [region for region in raw_regions if isinstance(region, dict)]
    defaults = {
        "slope": ([1.35, 0.60, 0.0], [1.20, 0.56, 0.10]),
        "gravel": ([0.95, -0.48, 0.0], [0.88, 0.58, 0.07]),
        "stairs": ([1.72, -0.46, 0.0], [0.95, 0.56, 0.24]),
    }
    if terrain in {"mixed", "mixed_terrain", "mixed_terrain_pack"}:
        keys = ["slope", "gravel", "stairs"]
    elif terrain in defaults:
        keys = [terrain]
    else:
        keys = []
    return [
        {
            "id": f"default_{key}",
            "terrain_class": key,
            "position": defaults[key][0],
            "size": defaults[key][1],
        }
        for key in keys
    ]


def _region_position_and_size(region: dict[str, Any]) -> tuple[float, float, float, float, float]:
    position = region.get("position", [0.0, 0.0, 0.0])
    size = region.get("size", [1.0, 1.0, 0.05])
    if not isinstance(position, list) or len(position) < 2:
        position = [0.0, 0.0, 0.0]
    if not isinstance(size, list) or len(size) < 2:
        size = [1.0, 1.0, 0.05]
    return (
        float(position[0]),
        float(position[1]),
        max(0.05, float(size[0])),
        max(0.05, float(size[1])),
        max(0.02, float(size[2] if len(size) > 2 else 0.05)),
    )


def _spawn_slope_region(children: Any, region: dict[str, Any]) -> None:
    x, y, width, depth, thickness = _region_position_and_size(region)
    slope_rad = -math.radians(_clamp(float(region.get("slope_deg", 12.0) or 12.0), 2.0, 24.0))
    children.importMFNodeFromString(
        -1,
        f"""Solid {{
          translation {x:.6f} {y:.6f} {thickness * 0.5:.6f}
          rotation 0 1 0 {slope_rad:.6f}
          children [
            Shape {{
              appearance PBRAppearance {{
                baseColor 0.25 0.55 0.25
                roughness 0.7
              }}
              geometry Box {{ size {width:.6f} {depth:.6f} {thickness:.6f} }}
            }}
          ]
          name "qrics_slope_visual"
          boundingObject Box {{ size {width:.6f} {depth:.6f} {thickness:.6f} }}
        }}""",
    )


def _spawn_stairs_region(children: Any, region: dict[str, Any]) -> None:
    x, y, width, depth, thickness = _region_position_and_size(region)
    step_count = max(2, min(8, int(region.get("step_count", 5) or 5)))
    step_height = _clamp(
        float(region.get("step_height_m", thickness / step_count) or thickness / step_count),
        0.015,
        0.09,
    )
    step_width = max(0.12, width / step_count)
    start_x = x - width * 0.5
    for index in range(step_count):
        height = step_height * (index + 1)
        step_x = start_x + (index + 0.5) * step_width
        children.importMFNodeFromString(
            -1,
            f"""Solid {{
              translation {step_x:.6f} {y:.6f} {height * 0.5:.6f}
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.52 0.52 0.50
                    roughness 0.8
                  }}
                  geometry Box {{
                    size {step_width * 0.92:.6f} {depth:.6f} {height:.6f}
                  }}
                }}
              ]
              name "qrics_step_{index}"
              boundingObject Box {{ size {step_width * 0.92:.6f} {depth:.6f} {height:.6f} }}
            }}""",
        )


def _spawn_gravel_region(children: Any, region: dict[str, Any]) -> None:
    x, y, width, depth, _thickness = _region_position_and_size(region)
    roughness = _clamp(float(region.get("roughness_m", 0.035) or 0.035), 0.012, 0.08)
    columns = max(3, min(10, int(width / 0.16)))
    rows = max(2, min(7, int(depth / 0.16)))
    for index in range(columns * rows):
        col = index % columns
        row = index // columns
        rock_x = x + (((col + 0.5) / columns) - 0.5) * width
        rock_y = y + (((row + 0.5) / rows) - 0.5) * depth
        radius = roughness * (0.75 + (index % 3) * 0.22)
        children.importMFNodeFromString(
            -1,
            f"""Solid {{
              translation {rock_x:.6f} {rock_y:.6f} {radius:.6f}
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.45 0.42 0.36
                    roughness 0.9
                  }}
                  geometry Sphere {{ radius {radius:.6f} }}
                }}
              ]
              name "qrics_gravel_{index}"
              boundingObject Sphere {{ radius {radius:.6f} }}
            }}""",
        )


def _spawn_semantic_markers(children: Any, spec: dict[str, Any]) -> None:
    checkpoint_map = {
        "A": [0.90, 0.34, 0.02],
        "B": [1.85, -0.30, 0.02],
        "platform": [0.0, 0.0, 0.02],
    }
    for checkpoint in spec.get("checkpoints", []):
        if not isinstance(checkpoint, dict):
            continue
        cid = str(checkpoint.get("id", ""))
        if cid not in checkpoint_map:
            continue
        position = checkpoint.get("position", checkpoint_map[cid])
        if isinstance(position, list) and len(position) >= 2:
            checkpoint_map[cid] = [
                float(position[0]),
                float(position[1]),
                float(position[2] if len(position) > 2 else 0.02),
            ]

    zone_box = _zone_box(spec)
    if zone_box is not None:
        zx, zy, zw, zh = zone_box
        children.importMFNodeFromString(
            -1,
            f"""Transform {{
              translation {zx:.6f} {zy:.6f} 0.006
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor 0.25 0.45 0.95
                    transparency 0.45
                    roughness 0.2
                  }}
                  geometry Box {{ size {zw:.6f} {zh:.6f} 0.012 }}
                }}
              ]
            }}""",
        )

    for name, radius, color in (
        ("A", 0.135, "0.10 0.70 0.20"),
        ("B", 0.135, "0.78 0.56 0.12"),
    ):
        x, y, _z = checkpoint_map[name]
        children.importMFNodeFromString(
            -1,
            f"""Transform {{
              translation {x:.6f} {y:.6f} 0.012
              children [
                Shape {{
                  appearance PBRAppearance {{
                    baseColor {color}
                    transparency 0.30
                    roughness 0.5
                  }}
                  geometry Cylinder {{ radius {radius:.6f} height 0.018 }}
                }}
              ]
            }}""",
        )
    px, py, _pz = checkpoint_map["platform"]
    children.importMFNodeFromString(
        -1,
        f"""Transform {{
          translation {px:.6f} {py:.6f} 0.009
          children [
            Shape {{
              appearance PBRAppearance {{
                baseColor 0.10 0.36 0.75
                transparency 0.45
                roughness 0.45
              }}
              geometry Box {{ size 0.86 0.62 0.018 }}
            }}
          ]
        }}""",
    )


def _zone_box(spec: dict[str, Any]) -> tuple[float, float, float, float] | None:
    zones = spec.get("forbidden_zones", [])
    if not isinstance(zones, list) or not zones:
        return None
    first = zones[0]
    if not isinstance(first, dict):
        return None
    polygon = first.get("polygon", [])
    if not isinstance(polygon, list) or not polygon:
        return None
    points = [point for point in polygon if isinstance(point, list) and len(point) >= 2]
    if not points:
        return None
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    return (
        (min(xs) + max(xs)) * 0.5,
        (min(ys) + max(ys)) * 0.5,
        max(xs) - min(xs),
        max(ys) - min(ys),
    )


def _spawn_obstacles(supervisor: Supervisor, spec: dict[str, Any]) -> None:
    root = supervisor.getRoot()
    children = root.getField("children")
    for index, obstacle in enumerate(spec.get("obstacles", [])):
        if not isinstance(obstacle, dict):
            continue
        position = obstacle.get("position", [0.0, 0.0, 0.2])
        if not isinstance(position, list) or len(position) != 3:
            position = [0.0, 0.0, 0.2]
        x = float(position[0])
        y = float(position[1])
        z = float(position[2])
        radius = max(0.035, min(0.22, float(obstacle.get("radius_m", 0.08))))
        height = max(0.05, min(0.75, float(obstacle.get("height_m", 0.30))))
        geometry_type = str(obstacle.get("geometry_type", "cylinder"))
        size = obstacle.get("size", [radius * 2.0, radius * 2.0, height])
        if not isinstance(size, list) or len(size) != 3:
            size = [radius * 2.0, radius * 2.0, height]
        raw_sx = float(size[0])
        raw_sy = float(size[1])
        raw_sz = float(size[2])
        sx = max(0.01, raw_sx if raw_sx > 0.0 else radius * 2.0)
        sy = max(0.01, raw_sy if raw_sy > 0.0 else radius * 2.0)
        sz = max(0.01, raw_sz if raw_sz > 0.0 else height)
        if geometry_type == "sphere":
            geometry_node = f"Sphere {{ radius {radius:.6f} }}"
            bounding_node = geometry_node
        elif geometry_type == "box":
            geometry_node = f"Box {{ size {sx:.6f} {sy:.6f} {sz:.6f} }}"
            bounding_node = geometry_node
        else:
            geometry_node = f"Cylinder {{ radius {radius:.6f} height {height:.6f} }}"
            bounding_node = geometry_node
        node = f"""Solid {{
          translation {x:.6f} {y:.6f} {z:.6f}
          children [
            Shape {{
              appearance PBRAppearance {{ baseColor 0.75 0.25 0.12 roughness 0.6 }}
              geometry {geometry_node}
            }}
          ]
          name "qrics_obstacle_{index}"
          boundingObject {bounding_node}
        }}"""
        children.importMFNodeFromString(-1, node)


def _command_frame_budget(command: dict[str, Any], frame_dt_s: float) -> int:
    steps = max(1, int(command.get("step_count", 1) or 1))
    try:
        control_dt_s = float(command.get("control_dt_s", frame_dt_s) or frame_dt_s)
    except (TypeError, ValueError):
        control_dt_s = frame_dt_s
    control_dt_s = max(frame_dt_s, control_dt_s)
    frame_dt_s = max(1.0e-6, frame_dt_s)
    return max(1, int(math.ceil((steps * control_dt_s) / frame_dt_s)))


def _run_controller_loop(supervisor: Supervisor, spec: dict[str, Any]) -> None:
    timestep_ms = int(supervisor.getBasicTimeStep())
    base = supervisor.getFromDef("QRICS_BASE")
    if base is None:
        _write_output({"ok": False, "error": "QRICS_BASE node not found"})
        _hold_visible(supervisor, _safe_hold_seconds(spec))
        return

    _spawn_terrain(supervisor, spec)
    _spawn_obstacles(supervisor, spec)

    terrain = str(spec.get("terrain_pack", "flat"))
    leg_handles = _resolve_leg_handles(supervisor)
    gait_phase = 0.0
    gait_name = "stand"

    translation = base.getField("translation")
    rotation = base.getField("rotation")
    initial = spec.get("initial_position", [0.0, 0.0, 0.32])
    x = float(initial[0])
    y = float(initial[1])
    z = float(initial[2])
    yaw = 0.0
    translation.setSFVec3f([x, y, z])
    rotation.setSFRotation([0.0, 0.0, 1.0, yaw])

    sim_time_s = 0.0
    command_count = 0
    for command in spec.get("commands", []):
        duration_s = max(0.0, float(command.get("duration_s", 0.016)))
        vx = 0.0 if command.get("stop", False) else float(command.get("vx", 0.0))
        vy = 0.0 if command.get("stop", False) else float(command.get("vy", 0.0))
        yaw_rate = 0.0 if command.get("stop", False) else float(command.get("yaw_rate", 0.0))
        frame_count = max(1, int(math.ceil(duration_s / (timestep_ms / 1000.0))))
        dt_s = duration_s / frame_count
        command_count += 1
        for _ in range(frame_count):
            x += vx * dt_s
            y += vy * dt_s
            yaw += yaw_rate * dt_s
            gait_name = _apply_leg_animation(
                leg_handles,
                gait_phase=gait_phase,
                vx=vx,
                vy=vy,
                yaw_rate=yaw_rate,
                terrain=terrain,
            )
            gait_phase = _wrap01(
                gait_phase + dt_s * _visual_gait_frequency_hz(gait_name, math.hypot(vx, vy))
            )
            body_bob = 0.0 if gait_name == "stand" else 0.008 * math.sin(2.0 * math.pi * gait_phase)
            translation.setSFVec3f([x, y, z + body_bob])
            rotation.setSFRotation([0.0, 0.0, 1.0, yaw])
            sim_time_s += dt_s
            if supervisor.step(timestep_ms) == -1:
                break

    hold_seconds = max(0.0, float(spec.get("hold_seconds", 0.0)))
    hold_frames = int(math.ceil(hold_seconds / (timestep_ms / 1000.0))) if hold_seconds else 0
    command_dir = str(spec.get("command_dir", ""))
    consumed_commands: set[str] = set()
    active_targets: list[tuple[str, float, float]] = []
    active_target_index = 0
    active_remaining_steps = 0
    active_forward = 0.0
    active_yaw_rate = 0.0
    dt_s = timestep_ms / 1000.0

    _write_state_output(sim_time_s, x, y, z, yaw, command_count, gait_name, gait_phase)
    for _ in range(hold_frames):
        for pending in _pending_command_files(command_dir, consumed_commands):
            command_type = str(pending.get("command_type", "run_path"))
            command_count += 1
            if command_type == "run_path":
                active_targets = _targets_from_command(pending)
                active_target_index = 0
                active_remaining_steps = _command_frame_budget(pending, dt_s)
                active_forward = abs(float(pending.get("forward_velocity_mps", 0.22))) or 0.22
                active_yaw_rate = float(pending.get("yaw_rate_radps", 0.0))
            else:
                active_targets = []
                active_remaining_steps = 1
                active_forward = 0.0
                active_yaw_rate = 0.0

        vx = 0.0
        vy = 0.0
        yaw_rate = 0.0
        if active_remaining_steps > 0 and active_targets:
            consumed_step = True
            target = active_targets[min(active_target_index, len(active_targets) - 1)]
            dx = target[1] - x
            dy = target[2] - y
            distance = math.hypot(dx, dy)
            arrival_threshold = 0.035 if active_target_index >= len(active_targets) - 1 else 0.08
            if distance <= arrival_threshold and active_target_index < len(active_targets) - 1:
                active_target_index += 1
                target = active_targets[active_target_index]
                dx = target[1] - x
                dy = target[2] - y
                distance = math.hypot(dx, dy)
            step_distance = max(0.0, active_forward) * dt_s
            if distance <= max(0.001, step_distance):
                x = target[1]
                y = target[2]
                if active_target_index >= len(active_targets) - 1:
                    active_targets = []
                    active_remaining_steps = 0
                else:
                    active_target_index += 1
                distance = 0.0
            if distance > 1.0e-6:
                vx = active_forward * dx / distance
                vy = active_forward * dy / distance
                yaw_rate = max(-0.8, min(0.8, math.atan2(dy, dx) * 0.35))
                if step_distance > distance:
                    vx = dx / max(0.001, dt_s)
                    vy = dy / max(0.001, dt_s)
            else:
                yaw_rate = active_yaw_rate
            x += vx * dt_s
            y += vy * dt_s
            yaw += yaw_rate * dt_s
            if consumed_step:
                active_remaining_steps = max(0, active_remaining_steps - 1)
        elif active_remaining_steps > 0:
            yaw_rate = active_yaw_rate
            yaw += yaw_rate * dt_s
            active_remaining_steps -= 1

        gait_name = _apply_leg_animation(
            leg_handles,
            gait_phase=gait_phase,
            vx=vx,
            vy=vy,
            yaw_rate=yaw_rate,
            terrain=terrain,
        )
        gait_phase = _wrap01(
            gait_phase + dt_s * _visual_gait_frequency_hz(gait_name, math.hypot(vx, vy))
        )
        body_bob = 0.0 if gait_name == "stand" else 0.008 * math.sin(2.0 * math.pi * gait_phase)
        translation.setSFVec3f([x, y, z + body_bob])
        rotation.setSFRotation([0.0, 0.0, 1.0, yaw])
        sim_time_s += dt_s
        _write_state_output(sim_time_s, x, y, z, yaw, command_count, gait_name, gait_phase)
        if supervisor.step(timestep_ms) == -1:
            break


def main() -> None:
    supervisor = Supervisor()
    spec: dict[str, Any] | None = None
    try:
        spec = _read_spec()
        _run_controller_loop(supervisor, spec)
    except Exception as exc:
        _write_output({"ok": False, "error": f"controller failed: {exc}"})
        # Keep the window visible instead of letting a supervisor error look like
        # an immediate Webots crash.  The presentation log/output then contains
        # the actual controller-side failure.
        _hold_visible(supervisor, _safe_hold_seconds(spec))


if __name__ == "__main__":
    main()
