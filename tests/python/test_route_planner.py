import math
from dataclasses import dataclass

from qrics.sim import ForbiddenZone, SceneObstacle, SceneProfile, Vec3
from qrics.sim.route_planner import plan_task_route


@dataclass(frozen=True)
class Target:
    target_id: str
    x: float
    y: float
    dwell_steps: int = 0


def _segment_samples(
    start: tuple[float, float], end: tuple[float, float], *, step_m: float = 0.025
) -> list[tuple[float, float]]:
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    count = max(1, int(math.ceil(distance / step_m)))
    return [
        (
            start[0] + (end[0] - start[0]) * index / count,
            start[1] + (end[1] - start[1]) * index / count,
        )
        for index in range(count + 1)
    ]


def test_route_planner_inserts_via_waypoints_around_obstacle() -> None:
    scene = SceneProfile(
        scene_id="obstacle_route",
        version="0.1.0",
        obstacle_set=(
            SceneObstacle(
                obstacle_id="barrel_on_direct_path",
                position=Vec3(x=0.45, y=0.0, z=0.35),
                radius_m=0.12,
                height_m=0.35,
            ),
        ),
    )

    route = plan_task_route(scene=scene, targets=(Target("A", 0.9, 0.0),))

    assert route.detour_waypoint_count > 0
    assert route.waypoints[-1].target_id == "A"
    assert any(abs(waypoint.y) > 0.20 for waypoint in route.waypoints)

    points = [(0.0, 0.0), *((waypoint.x, waypoint.y) for waypoint in route.waypoints)]
    for start, end in zip(points, points[1:], strict=False):
        for x, y in _segment_samples(start, end):
            clearance = math.hypot(x - 0.45, y - 0.0) - 0.12
            assert clearance > 0.20


def test_route_planner_treats_low_friction_zone_as_blocked() -> None:
    scene = SceneProfile(
        scene_id="no_go_route",
        version="0.1.0",
        forbidden_zones=(
            ForbiddenZone(
                zone_id="low_friction_no_go",
                polygon=(
                    Vec3(0.35, -0.20, 0.0),
                    Vec3(0.65, -0.20, 0.0),
                    Vec3(0.65, 0.20, 0.0),
                    Vec3(0.35, 0.20, 0.0),
                ),
            ),
        ),
    )

    route = plan_task_route(scene=scene, targets=(Target("A", 0.95, 0.0),))

    assert route.detour_waypoint_count > 0
    points = [(0.0, 0.0), *((waypoint.x, waypoint.y) for waypoint in route.waypoints)]
    for start, end in zip(points, points[1:], strict=False):
        for x, y in _segment_samples(start, end):
            assert not (0.25 <= x <= 0.75 and -0.30 <= y <= 0.30)
