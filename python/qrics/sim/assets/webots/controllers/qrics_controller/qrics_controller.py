"""Webots supervisor controller for QRICS local demonstration runs.

The controller reads a QRICS-generated JSON run specification from the
``QRICS_WEBOTS_RUN_SPEC`` environment variable, animates the quadruped body in a
Webots world, and writes a JSON summary to ``QRICS_WEBOTS_RUN_OUTPUT``.  It uses
Webots only as the local visual/simulation presentation process; QRICS safety
and task decisions remain outside this controller.
"""

# The controller embeds Webots node definitions as compact VRML/WBT snippets.
# Keeping the snippets close to their Webots form is more maintainable than
# wrapping every appearance/geometry token across many Python string fragments.
# ruff: noqa: E501

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, cast

from controller import Supervisor  # type: ignore[import-not-found]


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


def _spawn_terrain(supervisor: Supervisor, spec: dict[str, Any]) -> None:
    root = supervisor.getRoot()
    children = root.getField("children")
    terrain = str(spec.get("terrain_pack", "flat"))
    _spawn_semantic_markers(children, spec)
    if terrain == "slope":
        children.importMFNodeFromString(
            -1,
            """Solid {
              translation 1.60 0 0.035
              rotation 0 1 0 -0.14
              children [ Shape { appearance PBRAppearance { baseColor 0.25 0.55 0.25 roughness 0.7 } geometry Box { size 2.4 2.2 0.07 } } ]
              name "qrics_slope_visual"
              boundingObject Box { size 2.4 2.2 0.07 }
              physics Physics { mass 0.0 }
            }""",
        )
    elif terrain == "stairs":
        for index in range(4):
            height = 0.05 + index * 0.05
            x = 0.85 + index * 0.34
            children.importMFNodeFromString(
                -1,
                f"""Solid {{
                  translation {x:.6f} 0 {height * 0.5:.6f}
                  children [ Shape {{ appearance PBRAppearance {{ baseColor 0.52 0.52 0.50 roughness 0.8 }} geometry Box {{ size 0.32 1.7 {height:.6f} }} }} ]
                  name "qrics_step_{index}"
                  boundingObject Box {{ size 0.32 1.7 {height:.6f} }}
                  physics Physics {{ mass 0.0 }}
                }}""",
            )
    if terrain in {"gravel", "mixed", "mixed_terrain", "mixed_terrain_pack"}:
        for index in range(18):
            x = 0.65 + (index % 6) * 0.26
            y = -0.55 + (index // 6) * 0.36
            radius = 0.025 + (index % 3) * 0.008
            children.importMFNodeFromString(
                -1,
                f"""Solid {{
                  translation {x:.6f} {y:.6f} {radius:.6f}
                  children [ Shape {{ appearance PBRAppearance {{ baseColor 0.45 0.42 0.36 roughness 0.9 }} geometry Sphere {{ radius {radius:.6f} }} }} ]
                  name "qrics_gravel_{index}"
                  boundingObject Sphere {{ radius {radius:.6f} }}
                  physics Physics {{ mass 0.0 }}
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
              children [ Shape {{ appearance PBRAppearance {{ baseColor 0.25 0.45 0.95 transparency 0.45 roughness 0.2 }} geometry Box {{ size {zw:.6f} {zh:.6f} 0.012 }} }} ]
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
              children [ Shape {{ appearance PBRAppearance {{ baseColor {color} transparency 0.30 roughness 0.5 }} geometry Cylinder {{ radius {radius:.6f} height 0.018 }} }} ]
            }}""",
        )
    px, py, _pz = checkpoint_map["platform"]
    children.importMFNodeFromString(
        -1,
        f"""Transform {{
          translation {px:.6f} {py:.6f} 0.009
          children [ Shape {{ appearance PBRAppearance {{ baseColor 0.10 0.36 0.75 transparency 0.45 roughness 0.45 }} geometry Box {{ size 0.86 0.62 0.018 }} }} ]
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
          physics Physics {{ mass 0.0 }}
        }}"""
        children.importMFNodeFromString(-1, node)


def main() -> None:
    spec = _read_spec()
    supervisor = Supervisor()
    timestep_ms = int(supervisor.getBasicTimeStep())
    base = supervisor.getFromDef("QRICS_BASE")
    if base is None:
        _write_output({"ok": False, "error": "QRICS_BASE node not found"})
        return

    _spawn_terrain(supervisor, spec)
    _spawn_obstacles(supervisor, spec)

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
    for command in spec.get("commands", []):
        duration_s = max(0.0, float(command.get("duration_s", 0.016)))
        vx = 0.0 if command.get("stop", False) else float(command.get("vx", 0.0))
        vy = 0.0 if command.get("stop", False) else float(command.get("vy", 0.0))
        yaw_rate = 0.0 if command.get("stop", False) else float(command.get("yaw_rate", 0.0))
        frame_count = max(1, int(math.ceil(duration_s / (timestep_ms / 1000.0))))
        dt_s = duration_s / frame_count
        for _ in range(frame_count):
            x += vx * dt_s
            y += vy * dt_s
            yaw += yaw_rate * dt_s
            translation.setSFVec3f([x, y, z])
            rotation.setSFRotation([0.0, 0.0, 1.0, yaw])
            sim_time_s += dt_s
            if supervisor.step(timestep_ms) == -1:
                break

    _write_output(
        {
            "ok": True,
            "sim_time_ns": int(sim_time_s * 1_000_000_000),
            "base_position": [x, y, z],
            "yaw_rad": yaw,
            "command_count": len(spec.get("commands", [])),
        }
    )

    hold_seconds = max(0.0, float(spec.get("hold_seconds", 0.0)))
    hold_frames = int(math.ceil(hold_seconds / (timestep_ms / 1000.0))) if hold_seconds else 0
    for _ in range(hold_frames):
        if supervisor.step(timestep_ms) == -1:
            break


if __name__ == "__main__":
    main()
