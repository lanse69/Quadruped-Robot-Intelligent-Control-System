"""Scene-aware observation mapping helpers for local simulation backends."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from qrics.sim.scene_geometry import NO_GO_CENTER, NO_GO_SIZE, TERRAIN_REGION_DEFAULTS
from qrics.sim.schema import (
    ForbiddenZone,
    ObstacleState,
    SceneObstacle,
    SceneProfile,
    SourceQuality,
    TerrainClass,
    TerrainRegion,
    Vec3,
)


@dataclass(frozen=True)
class ObstacleMappingConfig:
    fallback_distance_m: float = 0.0
    source_quality: SourceQuality = "direct"


def classify_terrain(scene: SceneProfile | None, position: Vec3) -> TerrainClass:
    """Map scene metadata and robot position into the QRICS terrain enum.

    Terrain regions are the authoritative source for editable mixed scenes.  The
    Web console serializes the moved slope/gravel/stairs blocks as inline terrain
    assets; API handoff converts them into ``SceneProfile.terrain_regions`` so the
    minimal, MuJoCo and Webots backends all classify terrain from the same metric
    rectangles that the user saw in the 2-D preview.
    """
    terrain = scene.terrain_pack if scene is not None else "flat"
    if terrain in {"flat", "slope", "gravel", "stairs", "low_friction"}:
        return cast(TerrainClass, terrain)
    if terrain in {"mixed", "mixed_terrain", "mixed_terrain_pack"}:
        if scene is not None and _inside_any_forbidden_zone(scene.forbidden_zones, position):
            return "low_friction"
        for region in _terrain_regions_for_scene(scene):
            if _inside_region(position, region.center, region.size):
                return region.terrain_class
        return "flat"
    return "unknown"


def nearest_obstacle_state(
    scene: SceneProfile | None,
    position: Vec3,
    *,
    config: ObstacleMappingConfig | None = None,
) -> ObstacleState:
    """Compute nearest obstacle distance from scene obstacle descriptors."""
    active_config = config if config is not None else ObstacleMappingConfig()
    if scene is None or not scene.obstacle_set:
        return ObstacleState(
            obstacle_detected=False,
            nearest_distance_m=0.0,
            nearest_point=Vec3(),
            source_quality=active_config.source_quality,
        )

    nearest: SceneObstacle | None = None
    nearest_clearance = math.inf
    nearest_surface = Vec3()
    for obstacle in scene.obstacle_set:
        clearance, surface = _obstacle_clearance_and_surface(obstacle, position)
        if clearance < nearest_clearance:
            nearest = obstacle
            nearest_clearance = clearance
            nearest_surface = surface

    if nearest is None:
        return ObstacleState(source_quality=active_config.source_quality)
    return ObstacleState(
        obstacle_detected=True,
        nearest_distance_m=float(nearest_clearance),
        nearest_point=nearest_surface,
        source_quality=active_config.source_quality,
    )


def _obstacle_clearance_and_surface(obstacle: SceneObstacle, position: Vec3) -> tuple[float, Vec3]:
    """Return clearance and closest obstacle surface point for supported typed geometry."""
    geometry = getattr(obstacle, "geometry_type", "cylinder")
    if geometry == "box":
        half_x = max(0.005, _size_or_default(obstacle.size.x, obstacle.radius_m * 2.0) * 0.5)
        half_y = max(0.005, _size_or_default(obstacle.size.y, obstacle.radius_m * 2.0) * 0.5)
        half_z = max(0.005, _size_or_default(obstacle.size.z, obstacle.height_m) * 0.5)
        min_x = obstacle.position.x - half_x
        max_x = obstacle.position.x + half_x
        min_y = obstacle.position.y - half_y
        max_y = obstacle.position.y + half_y
        min_z = obstacle.position.z - half_z
        max_z = obstacle.position.z + half_z
        clamped = Vec3(
            x=min(max(position.x, min_x), max_x),
            y=min(max(position.y, min_y), max_y),
            z=min(max(position.z, min_z), max_z),
        )
        dx = position.x - clamped.x
        dy = position.y - clamped.y
        dz = position.z - clamped.z
        return math.sqrt((dx * dx) + (dy * dy) + (dz * dz)), clamped

    dx = obstacle.position.x - position.x
    dy = obstacle.position.y - position.y
    dz = obstacle.position.z - position.z
    if geometry == "sphere":
        center_distance = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
        radius = max(0.0, obstacle.radius_m)
    else:
        # Cylinders are used for barrels/posts in local demos.  Use horizontal
        # radial clearance with a vertical clamp so robot-base obstacle distance
        # reflects the footprint rather than the obstacle center height alone.
        half_height = max(0.0, obstacle.height_m) * 0.5
        z_min = obstacle.position.z - half_height
        z_max = obstacle.position.z + half_height
        clamped_z = min(max(position.z, z_min), z_max)
        dz = obstacle.position.z - clamped_z
        center_distance = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
        radius = max(0.0, obstacle.radius_m)
    clearance = max(0.0, center_distance - radius)
    scale = 0.0 if center_distance <= 1.0e-9 else radius / center_distance
    return clearance, Vec3(
        x=obstacle.position.x - (dx * scale),
        y=obstacle.position.y - (dy * scale),
        z=obstacle.position.z - (dz * scale),
    )


def _size_or_default(value: float, fallback: float) -> float:
    return value if value > 0.0 else fallback


def demo_obstacle(scene_id: str = "api_demo_obstacle") -> SceneObstacle:
    """Default laptop-demo obstacle used when a task scene has no registered assets."""
    return SceneObstacle(
        obstacle_id=scene_id,
        position=Vec3(x=0.32, y=0.0, z=0.35),
        radius_m=0.08,
        height_m=0.35,
        geometry_type="cylinder",
    )


def _terrain_regions_for_scene(scene: SceneProfile | None) -> tuple[TerrainRegion, ...]:
    if scene is not None and scene.terrain_regions:
        return scene.terrain_regions
    return tuple(
        TerrainRegion(
            region_id=f"default_{name}",
            terrain_class=cast(TerrainClass, name),
            center=Vec3(center.x, center.y, 0.0),
            size=Vec3(size.x, size.y, size.z),
            slope_deg=12.0 if name == "slope" else 0.0,
            roughness_m=0.035 if name == "gravel" else 0.0,
            step_height_m=0.045 if name == "stairs" else 0.0,
            step_count=5 if name == "stairs" else 0,
        )
        for name, (center, size) in TERRAIN_REGION_DEFAULTS.items()
    )


def _inside_region(position: Vec3, center: Vec3, size: Vec3) -> bool:
    half_x = max(0.0, size.x) * 0.5
    half_y = max(0.0, size.y) * 0.5
    return abs(position.x - center.x) <= half_x and abs(position.y - center.y) <= half_y


def _inside_any_forbidden_zone(zones: tuple[ForbiddenZone, ...], position: Vec3) -> bool:
    if not zones:
        return _inside_region(
            position,
            Vec3(NO_GO_CENTER.x, NO_GO_CENTER.y, 0.0),
            Vec3(NO_GO_SIZE.x, NO_GO_SIZE.y, NO_GO_SIZE.z),
        )
    for zone in zones:
        if not zone.polygon:
            continue
        xs = [point.x for point in zone.polygon]
        ys = [point.y for point in zone.polygon]
        if min(xs) <= position.x <= max(xs) and min(ys) <= position.y <= max(ys):
            return True
    return False
