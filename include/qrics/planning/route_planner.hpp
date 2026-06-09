// C++ 核心全局路径规划器：根据机器人占地半径、障碍物和禁行区生成任务执行路线。

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/scenario/scene_profile.hpp"

namespace qrics::planning {

struct RoutePlanningConfig final {
  double robot_radius_m{0.34};
  double safety_margin_m{0.08};
  double grid_resolution_m{0.06};
  double search_padding_m{0.90};
  double max_segment_sample_step_m{0.025};
  int max_expanded_nodes{80'000};
};

struct RouteTarget final {
  std::string target_id{};
  qrics::common::Vec3 position{};
  double dwell_time_s{0.0};
};

struct RouteWaypoint final {
  std::string waypoint_id{};
  qrics::common::Vec3 position{};
  double dwell_time_s{0.0};
  bool is_detour{false};
  bool is_task_target{true};
};

struct PlannedRoute final {
  std::vector<RouteWaypoint> waypoints{};
  std::vector<std::string> notes{};
  int original_target_count{0};
  int detour_waypoint_count{0};
  int blocked_object_count{0};
  double total_distance_m{0.0};
  bool used_graph_search{false};
};

[[nodiscard]] qrics::common::Result<PlannedRoute> plan_task_route(
    const qrics::scenario::SceneProfile& scene, const std::vector<RouteTarget>& targets,
    const RoutePlanningConfig& config = {},
    const qrics::common::Vec3& start = qrics::common::Vec3{0.0, 0.0, 0.35});

}  // namespace qrics::planning