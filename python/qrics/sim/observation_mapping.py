"""Scene-aware observation mapping helpers for local simulation backends."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from qrics.sim.schema import (
    ObstacleState,
    SceneObstacle,
    SceneProfile,
    SourceQuality,
    TerrainClass,
    Vec3,
)


@dataclass(frozen=True)
class ObstacleMappingConfig:
    fallback_distance_m: float = 0.0
    source_quality: SourceQuality = "direct"


def classify_terrain(scene: SceneProfile | None, position: Vec3) -> TerrainClass:
    """Map scene metadata and robot position into the QRICS terrain enum.

    Simple named terrain packs remain deterministic so API handoff, replay and
    local tests can reason about a terrain transition without requiring a heavy
    simulator-specific terrain query API.
    """
    terrain = scene.terrain_pack if scene is not None else "flat"
    if terrain in {"flat", "slope", "gravel", "stairs", "low_friction"}:
        return cast(TerrainClass, terrain)
    if terrain in {"mixed", "mixed_terrain", "mixed_terrain_pack"}:
        if position.x < 0.75:
            return "flat"
        if position.x < 1.50:
            return "gravel"
        if position.x < 2.25:
            return "slope"
        return "low_friction"
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
        dx = obstacle.position.x - position.x
        dy = obstacle.position.y - position.y
        dz = obstacle.position.z - position.z
        center_distance = math.sqrt((dx * dx) + (dy * dy) + (dz * dz))
        clearance = max(0.0, center_distance - max(0.0, obstacle.radius_m))
        if clearance < nearest_clearance:
            nearest = obstacle
            nearest_clearance = clearance
            if center_distance <= 1.0e-9:
                scale = 0.0
            else:
                scale = max(0.0, obstacle.radius_m) / center_distance
            nearest_surface = Vec3(
                x=obstacle.position.x - (dx * scale),
                y=obstacle.position.y - (dy * scale),
                z=obstacle.position.z - (dz * scale),
            )

    if nearest is None:
        return ObstacleState(source_quality=active_config.source_quality)
    return ObstacleState(
        obstacle_detected=True,
        nearest_distance_m=float(nearest_clearance),
        nearest_point=nearest_surface,
        source_quality=active_config.source_quality,
    )


def demo_obstacle(scene_id: str = "api_demo_obstacle") -> SceneObstacle:
    """Default laptop-demo obstacle used when a task scene has no registered assets."""
    return SceneObstacle(
        obstacle_id=scene_id,
        position=Vec3(x=0.32, y=0.0, z=0.35),
        radius_m=0.08,
        height_m=0.35,
    )
