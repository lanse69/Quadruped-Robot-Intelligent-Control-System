"""Load local QRICS demo scene JSON into backend-agnostic simulation schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from qrics.sim.schema import (
    Checkpoint,
    ForbiddenZone,
    Pose,
    SceneGeometryType,
    SceneObstacle,
    SceneProfile,
    TerrainClass,
    TerrainRegion,
    Vec3,
)

_INLINE_TERRAIN_CLASSES: tuple[TerrainClass, ...] = (
    "slope",
    "gravel",
    "stairs",
    "low_friction",
    "flat",
)


def load_scene_profile_from_json(path: str | Path) -> SceneProfile:
    """Load a compact QRICS scene file for local MuJoCo/Webots demo scripts.

    Supported input intentionally mirrors the API scene payload fields used by
    ``SceneAssetPayload`` while returning the lighter ``qrics.sim.SceneProfile``
    consumed by local simulation backends.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("scene JSON root must be an object")
    scene_id = str(raw.get("scene_id", raw.get("id", "local_demo_scene"))).strip()
    version = str(raw.get("scene_version", raw.get("version", "0.1.0"))).strip()
    if not scene_id or not version:
        raise ValueError("scene_id and version must not be empty")
    return SceneProfile(
        scene_id=scene_id,
        version=version,
        name=str(raw.get("name", scene_id)),
        terrain_pack=str(raw.get("terrain_pack", "flat")),
        obstacle_set=tuple(_load_obstacles(raw)),
        terrain_regions=tuple(_load_terrain_regions(raw)),
        checkpoints=tuple(_load_checkpoints(raw)),
        forbidden_zones=tuple(_load_forbidden_zones(raw)),
    )


def _load_obstacles(raw: dict[str, Any]) -> list[SceneObstacle]:
    raw_obstacles = raw.get("obstacles")
    if raw_obstacles is None:
        raw_obstacles = raw.get("assets", [])
    if not isinstance(raw_obstacles, list):
        raise ValueError("scene obstacles/assets must be a list")
    obstacles: list[SceneObstacle] = []
    for index, item in enumerate(raw_obstacles):
        if not isinstance(item, dict):
            raise ValueError(f"obstacle item #{index} must be an object")
        asset_type = str(item.get("asset_type", "obstacle"))
        if asset_type != "obstacle":
            continue
        geometry = _geometry_type(str(item.get("geometry_type", "cylinder")))
        position = _vec3(item.get("position", [0.35 + index * 0.35, 0.0, 0.35]))
        size = _vec3(item.get("size", [0.0, 0.0, 0.0]))
        radius = float(item.get("radius_m", 0.0))
        height = float(item.get("height_m", 0.0))
        if radius <= 0.0 and (size.x > 0.0 or size.y > 0.0):
            radius = max(size.x, size.y) * 0.5
        if height <= 0.0 and size.z > 0.0:
            height = size.z
        obstacles.append(
            SceneObstacle(
                obstacle_id=str(item.get("id", item.get("asset_id", f"obstacle_{index}"))),
                position=position,
                radius_m=max(0.01, radius if radius > 0.0 else 0.08),
                height_m=max(0.01, height if height > 0.0 else 0.35),
                geometry_type=geometry,
                size=size,
            )
        )
    return obstacles


def _load_terrain_regions(raw: dict[str, Any]) -> list[TerrainRegion]:
    raw_regions = raw.get("terrain_regions")
    if raw_regions is None:
        raw_regions = raw.get("assets", [])
    if not isinstance(raw_regions, list):
        raise ValueError("scene terrain_regions/assets must be a list")
    regions: list[TerrainRegion] = []
    for index, item in enumerate(raw_regions):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type", "terrain"))
        if asset_type != "terrain":
            continue
        terrain_class = _terrain_class_from_region(item)
        if terrain_class is None:
            continue
        position = _vec3(item.get("position", [0.0, 0.0, 0.0]))
        size = _vec3(item.get("size", [0.0, 0.0, 0.0]))
        regions.append(
            TerrainRegion(
                region_id=str(item.get("id", item.get("asset_id", f"terrain_{index}"))),
                terrain_class=terrain_class,
                center=position,
                size=size,
            )
        )
    return regions


def _terrain_class_from_region(item: dict[str, Any]) -> TerrainClass | None:
    value = str(item.get("terrain_class", "")).strip()
    asset_id = str(item.get("asset_id", item.get("id", ""))).strip()
    uri = str(item.get("uri", "")).strip()
    for candidate in (value, asset_id, uri):
        for terrain in _INLINE_TERRAIN_CLASSES:
            if candidate == terrain or f"/{terrain}" in candidate or f"_{terrain}_" in candidate:
                return terrain
    return None


def _load_checkpoints(raw: dict[str, Any]) -> list[Checkpoint]:
    raw_items = raw.get("checkpoints")
    if raw_items is None:
        raw_items = raw.get("assets", [])
    if not isinstance(raw_items, list):
        raise ValueError("scene checkpoints/assets must be a list")
    checkpoints: list[Checkpoint] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        if str(item.get("asset_type", "checkpoint")) != "checkpoint":
            continue
        position = _vec3(item.get("position", [0.0, 0.0, 0.02]))
        checkpoints.append(
            Checkpoint(
                checkpoint_id=str(item.get("id", item.get("asset_id", f"checkpoint_{index}"))),
                pose=Pose(position=position),
                dwell_time_s=float(item.get("dwell_time_s", 0.0)),
            )
        )
    return checkpoints


def _load_forbidden_zones(raw: dict[str, Any]) -> list[ForbiddenZone]:
    raw_items = raw.get("forbidden_zones")
    if raw_items is None:
        raw_items = raw.get("assets", [])
    if not isinstance(raw_items, list):
        raise ValueError("scene forbidden_zones/assets must be a list")
    zones: list[ForbiddenZone] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type", ""))
        if asset_type not in {"no_go_zone", "forbidden_zone"}:
            continue
        polygon_value = item.get("polygon")
        polygon: list[Vec3] = []
        if isinstance(polygon_value, list) and polygon_value:
            polygon = [_vec3(point) for point in polygon_value]
        else:
            position = _vec3(item.get("position", [0.0, 0.0, 0.0]))
            size = _vec3(item.get("size", [0.0, 0.0, 0.0]))
            half_x = max(0.01, size.x * 0.5)
            half_y = max(0.01, size.y * 0.5)
            polygon = [
                Vec3(position.x - half_x, position.y - half_y, position.z),
                Vec3(position.x + half_x, position.y - half_y, position.z),
                Vec3(position.x + half_x, position.y + half_y, position.z),
                Vec3(position.x - half_x, position.y + half_y, position.z),
            ]
        zones.append(
            ForbiddenZone(
                zone_id=str(item.get("id", item.get("asset_id", f"forbidden_{index}"))),
                polygon=tuple(polygon),
            )
        )
    return zones


def _vec3(value: object) -> Vec3:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return Vec3(x=float(value[0]), y=float(value[1]), z=float(value[2]))
    raise ValueError("vector fields must be [x, y, z]")


def _geometry_type(value: str) -> SceneGeometryType:
    if value in {"cylinder", "sphere", "box"}:
        return cast(SceneGeometryType, value)
    if value == "none":
        return "cylinder"
    raise ValueError("geometry_type must be one of: cylinder, sphere, box")
