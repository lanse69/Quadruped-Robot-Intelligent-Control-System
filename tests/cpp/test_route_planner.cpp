#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/planning/route_planner.hpp"
#include "qrics/scenario/scene_profile.hpp"

namespace {

[[nodiscard]] qrics::scenario::SceneProfile make_blocked_scene() {
  qrics::scenario::SceneObstacle obstacle{};
  obstacle.obstacle_id = "center_barrel";
  obstacle.geometry_type = qrics::scenario::SceneGeometryType::Cylinder;
  obstacle.pose.position = qrics::common::Vec3{0.55, 0.0, 0.25};
  obstacle.radius_m = 0.14;
  obstacle.height_m = 0.40;

  qrics::scenario::SceneProfile scene{};
  scene.scene_id = "cpp_route_planner_test_scene";
  scene.version = "0.1.0";
  scene.terrain_pack = "mixed_terrain_pack";
  scene.obstacles.push_back(obstacle);
  return scene;
}

[[nodiscard]] double distance_to_obstacle(const qrics::common::Vec3& point) {
  return std::hypot(point.x - 0.55, point.y) - 0.14;
}

[[nodiscard]] bool route_uses_detour(const qrics::planning::PlannedRoute& route) {
  return std::ranges::any_of(route.waypoints, [](const qrics::planning::RouteWaypoint& waypoint) {
    return waypoint.is_detour;
  });
}

}  // namespace

int main() {
  qrics::planning::RoutePlanningConfig config{};
  config.robot_radius_m = 0.22;
  config.safety_margin_m = 0.06;
  config.grid_resolution_m = 0.05;

  const auto route = qrics::planning::plan_task_route(
      make_blocked_scene(),
      std::vector<qrics::planning::RouteTarget>{
          qrics::planning::RouteTarget{"A", qrics::common::Vec3{1.40, 0.0, 0.35}, 0.0}},
      config);
  if (!route.ok) {
    return 1;
  }
  if (route.value.original_target_count != 1 || route.value.blocked_object_count != 1) {
    return 2;
  }
  if (!route.value.used_graph_search || route.value.detour_waypoint_count <= 0 ||
      !route_uses_detour(route.value)) {
    return 3;
  }
  if (route.value.waypoints.empty() || route.value.waypoints.back().waypoint_id != "A") {
    return 4;
  }
  for (const auto& waypoint : route.value.waypoints) {
    if (waypoint.is_detour && std::abs(waypoint.position.y) <= 0.20) {
      return 5;
    }
    if (distance_to_obstacle(waypoint.position) <= config.robot_radius_m) {
      return 6;
    }
  }
  const std::string note_blob = route.value.notes.empty() ? "" : route.value.notes.front();
  if (note_blob.find("C++ route planner") == std::string::npos) {
    return 7;
  }
  return 0;
}