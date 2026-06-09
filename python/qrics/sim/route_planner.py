"""Scene-aware 2-D task route planner for local QRICS simulation backends.

The local API and presentation backends use this module before producing
velocity commands.  It turns a semantic task sequence (platform -> A -> B ->
platform) into collision-free sub-waypoints using the same scene geometry that
is rendered by MuJoCo/Webots and reported by the Observation Schema.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Protocol, cast

from qrics.sim.scene_geometry import (
    NO_GO_CENTER,
    NO_GO_SIZE,
    ROBOT_ROUTE_RADIUS_M,
    TERRAIN_REGION_DEFAULTS,
)
from qrics.sim.schema import (
    ForbiddenZone,
    SceneObstacle,
    SceneProfile,
    TerrainClass,
    TerrainRegion,
    Vec3,
)


class RouteTargetLike(Protocol):
    """Read-only target contract accepted by the route planner.

    Using properties instead of mutable protocol attributes keeps the protocol
    compatible with frozen dataclasses and API DTOs while preserving mypy's
    structural type checking.
    """

    @property
    def target_id(self) -> str: ...

    @property
    def x(self) -> float: ...

    @property
    def y(self) -> float: ...

    @property
    def dwell_steps(self) -> int: ...


@dataclass(frozen=True)
class NavigationWaypoint:
    """Internal route waypoint followed by the demo controllers."""

    target_id: str
    x: float
    y: float
    dwell_steps: int = 0
    mission_target_index: int = -1
    is_mission_target: bool = False
    source_target_id: str = ""

    def to_json(self) -> dict[str, object]:
        """Return a stable API/presentation representation for this route node."""
        return {
            "waypoint_id": self.target_id,
            "target_id": self.target_id,
            "x": self.x,
            "y": self.y,
            "dwell_steps": self.dwell_steps,
            "mission_target_index": self.mission_target_index,
            "is_mission_target": self.is_mission_target,
            "source_target_id": self.source_target_id,
        }


@dataclass(frozen=True)
class PlannedRoute:
    waypoints: tuple[NavigationWaypoint, ...]
    blocked_object_count: int = 0
    terrain_region_count: int = 0
    detour_waypoint_count: int = 0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutePlanningConfig:
    grid_resolution_m: float = 0.06
    obstacle_padding_m: float = ROBOT_ROUTE_RADIUS_M
    forbidden_padding_m: float = ROBOT_ROUTE_RADIUS_M * 0.65
    line_check_step_m: float = 0.025
    max_grid_cells: int = 32000
    max_detour_waypoints_per_segment: int = 36


@dataclass(frozen=True)
class _GridSpec:
    min_x: float
    min_y: float
    resolution: float
    width: int
    height: int


@dataclass(frozen=True)
class _SegmentPlan:
    points: tuple[Vec3, ...]
    used_grid: bool
    note: str


_TERRAIN_COST: dict[TerrainClass, float] = {
    "flat": 1.0,
    "slope": 1.55,
    "gravel": 1.45,
    "stairs": 2.15,
    "low_friction": math.inf,
    "unknown": 1.80,
}


def plan_task_route(
    *,
    scene: SceneProfile,
    targets: tuple[RouteTargetLike, ...],
    config: RoutePlanningConfig | None = None,
    start: Vec3 | None = None,
) -> PlannedRoute:
    """Plan a complete task route through scene geometry.

    Forbidden/no-go zones and obstacle safety buffers are treated as blocked
    cells.  The default clearance uses an approximate robot footprint radius,
    so route detours are visible instead of merely clearing a point-mass path.
    Slope, gravel and stairs remain traversable but add cost, so the planner
    can detour when a safe low-cost route exists and still emits a route
    through them when the task requires it.  Low-friction terrain is treated as a
    forbidden region for navigation, matching the default Chinese task
    constraint "避开低摩擦区".
    """
    if not targets:
        return PlannedRoute(waypoints=())

    active_config = config if config is not None else RoutePlanningConfig()
    active_start = start if start is not None else Vec3(0.0, 0.0, 0.35)
    cursor = active_start
    waypoints: list[NavigationWaypoint] = []
    notes: list[str] = []
    detour_count = 0
    for mission_index, target in enumerate(targets):
        goal = Vec3(float(target.x), float(target.y), active_start.z)
        segment = _plan_segment(cursor, goal, scene, active_config)
        notes.append(f"{target.target_id}:{segment.note}")
        segment_points = list(segment.points)
        if segment_points and _same_xy(segment_points[0], cursor):
            segment_points = segment_points[1:]
        if not segment_points:
            segment_points = [goal]
        for point_index, point in enumerate(segment_points):
            final_for_mission = point_index == len(segment_points) - 1
            if final_for_mission:
                waypoints.append(
                    NavigationWaypoint(
                        target_id=target.target_id,
                        x=goal.x,
                        y=goal.y,
                        dwell_steps=max(0, int(target.dwell_steps)),
                        mission_target_index=mission_index,
                        is_mission_target=True,
                        source_target_id=target.target_id,
                    )
                )
            else:
                detour_count += 1
                waypoints.append(
                    NavigationWaypoint(
                        target_id=f"via_{mission_index}_{detour_count}",
                        x=point.x,
                        y=point.y,
                        dwell_steps=0,
                        mission_target_index=mission_index,
                        is_mission_target=False,
                        source_target_id=target.target_id,
                    )
                )
        cursor = goal

    return PlannedRoute(
        waypoints=tuple(_deduplicate_waypoints(waypoints)),
        blocked_object_count=len(scene.obstacle_set) + len(_forbidden_zones(scene)),
        terrain_region_count=len(_terrain_regions_for_scene(scene)),
        detour_waypoint_count=detour_count,
        notes=tuple(notes),
    )


def _plan_segment(
    start: Vec3,
    goal: Vec3,
    scene: SceneProfile,
    config: RoutePlanningConfig,
) -> _SegmentPlan:
    if _line_is_clear(start, goal, scene, config) and not _line_has_high_cost_terrain(
        start, goal, scene, config
    ):
        return _SegmentPlan(points=(start, goal), used_grid=False, note="direct_clear")

    grid = _build_grid(start, goal, scene, config)
    if grid.width * grid.height > config.max_grid_cells:
        return _SegmentPlan(points=(start, goal), used_grid=False, note="fallback_grid_too_large")

    start_index = _nearest_unblocked_index(_point_to_index(start, grid), grid, scene, config)
    goal_index = _nearest_unblocked_index(_point_to_index(goal, grid), grid, scene, config)
    if start_index is None or goal_index is None:
        return _SegmentPlan(
            points=(start, goal), used_grid=False, note="fallback_start_or_goal_blocked"
        )

    path = _astar(start_index, goal_index, grid, scene, config)
    if not path:
        return _SegmentPlan(points=(start, goal), used_grid=False, note="fallback_no_grid_path")

    raw_points = tuple(_index_to_point(index, grid, z=start.z) for index in path)
    simplified = _simplify_polyline(raw_points, scene, config)
    if len(simplified) > config.max_detour_waypoints_per_segment + 2:
        simplified = _thin_polyline(simplified, config.max_detour_waypoints_per_segment + 2)
    if not _same_xy(simplified[0], start):
        simplified = (start, *simplified)
    if not _same_xy(simplified[-1], goal):
        simplified = (*simplified, goal)
    return _SegmentPlan(points=simplified, used_grid=True, note="grid_detour")


def _build_grid(
    start: Vec3, goal: Vec3, scene: SceneProfile, config: RoutePlanningConfig
) -> _GridSpec:
    xs = [start.x, goal.x]
    ys = [start.y, goal.y]
    for obstacle in scene.obstacle_set:
        min_x, min_y, max_x, max_y = _obstacle_bounds(obstacle, config.obstacle_padding_m)
        xs.extend((min_x, max_x))
        ys.extend((min_y, max_y))
    for zone in _forbidden_zones(scene):
        min_x, min_y, max_x, max_y = _zone_bounds(zone, config.forbidden_padding_m)
        xs.extend((min_x, max_x))
        ys.extend((min_y, max_y))
    for region in _terrain_regions_for_scene(scene):
        xs.extend((region.center.x - region.size.x * 0.5, region.center.x + region.size.x * 0.5))
        ys.extend((region.center.y - region.size.y * 0.5, region.center.y + region.size.y * 0.5))

    margin = max(0.6, config.obstacle_padding_m * 3.0, config.forbidden_padding_m * 3.0)
    min_x = min(xs) - margin
    max_x = max(xs) + margin
    min_y = min(ys) - margin
    max_y = max(ys) + margin
    resolution = max(0.03, config.grid_resolution_m)
    width = max(3, int(math.ceil((max_x - min_x) / resolution)) + 1)
    height = max(3, int(math.ceil((max_y - min_y) / resolution)) + 1)
    return _GridSpec(min_x=min_x, min_y=min_y, resolution=resolution, width=width, height=height)


def _astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: _GridSpec,
    scene: SceneProfile,
    config: RoutePlanningConfig,
) -> tuple[tuple[int, int], ...]:
    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _priority, _counter, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            return _reconstruct_path(came_from, current)
        closed.add(current)
        for neighbor in _neighbors(current, grid):
            if neighbor in closed:
                continue
            if _blocked_index(neighbor, grid, scene, config) and neighbor != goal:
                continue
            current_point = _index_to_point(current, grid, z=0.35)
            neighbor_point = _index_to_point(neighbor, grid, z=0.35)
            if not _line_is_clear(current_point, neighbor_point, scene, config):
                continue
            distance = _xy_distance(current_point, neighbor_point)
            terrain_cost = _terrain_cost(scene, neighbor_point)
            if math.isinf(terrain_cost):
                continue
            tentative = g_score[current] + (distance * terrain_cost)
            if tentative >= g_score.get(neighbor, math.inf):
                continue
            came_from[neighbor] = current
            g_score[neighbor] = tentative
            counter += 1
            priority = tentative + _heuristic(neighbor, goal, grid)
            heapq.heappush(open_heap, (priority, counter, neighbor))
    return ()


def _neighbors(index: tuple[int, int], grid: _GridSpec) -> tuple[tuple[int, int], ...]:
    x, y = index
    items: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = x + dx
            ny = y + dy
            if 0 <= nx < grid.width and 0 <= ny < grid.height:
                items.append((nx, ny))
    return tuple(items)


def _reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int]], current: tuple[int, int]
) -> tuple[tuple[int, int], ...]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return tuple(path)


def _nearest_unblocked_index(
    index: tuple[int, int],
    grid: _GridSpec,
    scene: SceneProfile,
    config: RoutePlanningConfig,
) -> tuple[int, int] | None:
    ix, iy = index
    if (
        0 <= ix < grid.width
        and 0 <= iy < grid.height
        and not _blocked_index(index, grid, scene, config)
    ):
        return index
    max_radius = max(grid.width, grid.height)
    for radius in range(1, max_radius + 1):
        candidates: list[tuple[int, int]] = []
        for dx in range(-radius, radius + 1):
            candidates.append((ix + dx, iy - radius))
            candidates.append((ix + dx, iy + radius))
        for dy in range(-radius + 1, radius):
            candidates.append((ix - radius, iy + dy))
            candidates.append((ix + radius, iy + dy))
        for candidate in candidates:
            x, y = candidate
            if not (0 <= x < grid.width and 0 <= y < grid.height):
                continue
            if not _blocked_index(candidate, grid, scene, config):
                return candidate
    return None


def _blocked_index(
    index: tuple[int, int], grid: _GridSpec, scene: SceneProfile, config: RoutePlanningConfig
) -> bool:
    return _blocked_point(_index_to_point(index, grid, z=0.35), scene, config)


def _blocked_point(point: Vec3, scene: SceneProfile, config: RoutePlanningConfig) -> bool:
    for obstacle in scene.obstacle_set:
        if _obstacle_clearance(obstacle, point) <= config.obstacle_padding_m:
            return True
    for zone in _forbidden_zones(scene):
        if _inside_zone_with_padding(point, zone, config.forbidden_padding_m):
            return True
    return _terrain_at(scene, point) == "low_friction"


def _terrain_cost(scene: SceneProfile, point: Vec3) -> float:
    return _TERRAIN_COST.get(_terrain_at(scene, point), 1.80)


def _terrain_at(scene: SceneProfile, point: Vec3) -> TerrainClass:
    if _inside_any_forbidden_zone(scene, point):
        return "low_friction"
    if scene.terrain_pack in {"flat", "slope", "gravel", "stairs", "low_friction"}:
        return cast(TerrainClass, scene.terrain_pack)
    for region in _terrain_regions_for_scene(scene):
        if _inside_region(point, region):
            return region.terrain_class
    if scene.terrain_pack in {"mixed", "mixed_terrain", "mixed_terrain_pack"}:
        return "flat"
    return "unknown"


def _line_is_clear(
    start: Vec3, goal: Vec3, scene: SceneProfile, config: RoutePlanningConfig
) -> bool:
    return not any(
        _blocked_point(point, scene, config) for point in _sample_line(start, goal, config)
    )


def _line_has_high_cost_terrain(
    start: Vec3, goal: Vec3, scene: SceneProfile, config: RoutePlanningConfig
) -> bool:
    return any(_terrain_cost(scene, point) > 1.05 for point in _sample_line(start, goal, config))


def _sample_line(start: Vec3, goal: Vec3, config: RoutePlanningConfig) -> tuple[Vec3, ...]:
    distance = _xy_distance(start, goal)
    sample_count = max(1, int(math.ceil(distance / max(0.01, config.line_check_step_m))))
    return tuple(
        Vec3(
            x=start.x + (goal.x - start.x) * (index / sample_count),
            y=start.y + (goal.y - start.y) * (index / sample_count),
            z=start.z + (goal.z - start.z) * (index / sample_count),
        )
        for index in range(sample_count + 1)
    )


def _simplify_polyline(
    points: tuple[Vec3, ...], scene: SceneProfile, config: RoutePlanningConfig
) -> tuple[Vec3, ...]:
    if len(points) <= 2:
        return points
    simplified: list[Vec3] = [points[0]]
    anchor_index = 0
    while anchor_index < len(points) - 1:
        next_index = len(points) - 1
        while next_index > anchor_index + 1:
            if _line_is_clear(points[anchor_index], points[next_index], scene, config):
                break
            next_index -= 1
        simplified.append(points[next_index])
        anchor_index = next_index
    return tuple(simplified)


def _thin_polyline(points: tuple[Vec3, ...], max_points: int) -> tuple[Vec3, ...]:
    if len(points) <= max_points:
        return points
    if max_points <= 2:
        return (points[0], points[-1])
    step = (len(points) - 1) / (max_points - 1)
    return tuple(points[min(len(points) - 1, round(index * step))] for index in range(max_points))


def _deduplicate_waypoints(waypoints: list[NavigationWaypoint]) -> list[NavigationWaypoint]:
    deduped: list[NavigationWaypoint] = []
    for waypoint in waypoints:
        if deduped and math.hypot(waypoint.x - deduped[-1].x, waypoint.y - deduped[-1].y) < 0.025:
            if waypoint.is_mission_target:
                deduped[-1] = waypoint
            continue
        deduped.append(waypoint)
    return deduped


def _point_to_index(point: Vec3, grid: _GridSpec) -> tuple[int, int]:
    return (
        int(round((point.x - grid.min_x) / grid.resolution)),
        int(round((point.y - grid.min_y) / grid.resolution)),
    )


def _index_to_point(index: tuple[int, int], grid: _GridSpec, *, z: float) -> Vec3:
    return Vec3(
        x=grid.min_x + index[0] * grid.resolution,
        y=grid.min_y + index[1] * grid.resolution,
        z=z,
    )


def _heuristic(index: tuple[int, int], goal: tuple[int, int], grid: _GridSpec) -> float:
    return math.hypot(index[0] - goal[0], index[1] - goal[1]) * grid.resolution


def _xy_distance(lhs: Vec3, rhs: Vec3) -> float:
    return math.hypot(rhs.x - lhs.x, rhs.y - lhs.y)


def _same_xy(lhs: Vec3, rhs: Vec3) -> bool:
    return _xy_distance(lhs, rhs) <= 1.0e-6


def _obstacle_bounds(obstacle: SceneObstacle, padding: float) -> tuple[float, float, float, float]:
    if obstacle.geometry_type == "box":
        half_x = max(0.005, _size_or_default(obstacle.size.x, obstacle.radius_m * 2.0) * 0.5)
        half_y = max(0.005, _size_or_default(obstacle.size.y, obstacle.radius_m * 2.0) * 0.5)
    else:
        half_x = max(0.0, obstacle.radius_m)
        half_y = max(0.0, obstacle.radius_m)
    return (
        obstacle.position.x - half_x - padding,
        obstacle.position.y - half_y - padding,
        obstacle.position.x + half_x + padding,
        obstacle.position.y + half_y + padding,
    )


def _obstacle_clearance(obstacle: SceneObstacle, position: Vec3) -> float:
    if obstacle.geometry_type == "box":
        half_x = max(0.005, _size_or_default(obstacle.size.x, obstacle.radius_m * 2.0) * 0.5)
        half_y = max(0.005, _size_or_default(obstacle.size.y, obstacle.radius_m * 2.0) * 0.5)
        closest_x = min(max(position.x, obstacle.position.x - half_x), obstacle.position.x + half_x)
        closest_y = min(max(position.y, obstacle.position.y - half_y), obstacle.position.y + half_y)
        return math.hypot(position.x - closest_x, position.y - closest_y)
    return max(
        0.0,
        math.hypot(position.x - obstacle.position.x, position.y - obstacle.position.y)
        - max(0.0, obstacle.radius_m),
    )


def _zone_bounds(zone: ForbiddenZone, padding: float) -> tuple[float, float, float, float]:
    if not zone.polygon:
        return (
            NO_GO_CENTER.x - NO_GO_SIZE.x * 0.5 - padding,
            NO_GO_CENTER.y - NO_GO_SIZE.y * 0.5 - padding,
            NO_GO_CENTER.x + NO_GO_SIZE.x * 0.5 + padding,
            NO_GO_CENTER.y + NO_GO_SIZE.y * 0.5 + padding,
        )
    xs = [point.x for point in zone.polygon]
    ys = [point.y for point in zone.polygon]
    return min(xs) - padding, min(ys) - padding, max(xs) + padding, max(ys) + padding


def _inside_zone_with_padding(point: Vec3, zone: ForbiddenZone, padding: float) -> bool:
    min_x, min_y, max_x, max_y = _zone_bounds(zone, padding)
    if point.x < min_x or point.x > max_x or point.y < min_y or point.y > max_y:
        return False
    if padding > 0.0:
        # The current local scene editor emits rectangular no-go areas.  Expanded
        # bounding boxes are therefore the correct and conservative padding model.
        return True
    return _point_inside_polygon(point, zone.polygon)


def _inside_any_forbidden_zone(scene: SceneProfile, point: Vec3) -> bool:
    zones = _forbidden_zones(scene)
    return any(_inside_zone_with_padding(point, zone, 0.0) for zone in zones)


def _forbidden_zones(scene: SceneProfile) -> tuple[ForbiddenZone, ...]:
    if scene.forbidden_zones:
        return scene.forbidden_zones
    if scene.terrain_pack in {"low_friction", "mixed", "mixed_terrain", "mixed_terrain_pack"}:
        half_x = NO_GO_SIZE.x * 0.5
        half_y = NO_GO_SIZE.y * 0.5
        return (
            ForbiddenZone(
                zone_id="default_low_friction_zone",
                polygon=(
                    Vec3(NO_GO_CENTER.x - half_x, NO_GO_CENTER.y - half_y, 0.0),
                    Vec3(NO_GO_CENTER.x + half_x, NO_GO_CENTER.y - half_y, 0.0),
                    Vec3(NO_GO_CENTER.x + half_x, NO_GO_CENTER.y + half_y, 0.0),
                    Vec3(NO_GO_CENTER.x - half_x, NO_GO_CENTER.y + half_y, 0.0),
                ),
            ),
        )
    return ()


def _terrain_regions_for_scene(scene: SceneProfile) -> tuple[TerrainRegion, ...]:
    if scene.terrain_regions:
        return scene.terrain_regions
    if scene.terrain_pack in {"mixed", "mixed_terrain", "mixed_terrain_pack"}:
        keys: tuple[str, ...] = ("slope", "gravel", "stairs")
    elif scene.terrain_pack in {"slope", "gravel", "stairs", "low_friction"}:
        keys = (scene.terrain_pack,)
    else:
        keys = ()
    return tuple(
        TerrainRegion(
            region_id=f"default_{key}",
            terrain_class=cast(TerrainClass, key),
            center=Vec3(center.x, center.y, 0.0),
            size=Vec3(size.x, size.y, size.z),
            slope_deg=12.0 if key == "slope" else 0.0,
            roughness_m=0.035 if key == "gravel" else 0.0,
            step_height_m=0.045 if key == "stairs" else 0.0,
            step_count=5 if key == "stairs" else 0,
        )
        for key, (center, size) in TERRAIN_REGION_DEFAULTS.items()
        if key in keys
    )


def _inside_region(point: Vec3, region: TerrainRegion) -> bool:
    return (
        abs(point.x - region.center.x) <= max(0.0, region.size.x) * 0.5
        and abs(point.y - region.center.y) <= max(0.0, region.size.y) * 0.5
    )


def _point_inside_polygon(point: Vec3, polygon: tuple[Vec3, ...]) -> bool:
    if len(polygon) < 3:
        return False
    inside = False
    previous = len(polygon) - 1
    for current, lhs in enumerate(polygon):
        rhs = polygon[previous]
        crosses_y = (lhs.y > point.y) != (rhs.y > point.y)
        denominator = rhs.y - lhs.y
        if crosses_y and abs(denominator) > 1.0e-12:
            x_intersection = ((rhs.x - lhs.x) * (point.y - lhs.y) / denominator) + lhs.x
            if point.x < x_intersection:
                inside = not inside
        previous = current
    return inside


def _size_or_default(value: float, fallback: float) -> float:
    return value if value > 0.0 else fallback
