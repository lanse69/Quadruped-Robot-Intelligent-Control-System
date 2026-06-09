// C++ 核心全局路径规划器实现

#include "qrics/planning/route_planner.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <numbers>
#include <optional>
#include <queue>
#include <string>
#include <unordered_map>
#include <utility>

namespace qrics::planning {

namespace {

struct Bounds final {
  double min_x{0.0};
  double max_x{0.0};
  double min_y{0.0};
  double max_y{0.0};
};

struct Cell final {
  int x{0};
  int y{0};

  friend bool operator==(const Cell& lhs, const Cell& rhs) noexcept {
    return lhs.x == rhs.x && lhs.y == rhs.y;
  }
};

struct CellHash final {
  [[nodiscard]] std::size_t operator()(const Cell& cell) const noexcept {
    const auto x = static_cast<std::uint64_t>(static_cast<std::uint32_t>(cell.x));
    const auto y = static_cast<std::uint64_t>(static_cast<std::uint32_t>(cell.y));
    return static_cast<std::size_t>((x << 32U) ^ y);
  }
};

struct QueueNode final {
  Cell cell{};
  double priority{0.0};

  friend bool operator<(const QueueNode& lhs, const QueueNode& rhs) noexcept {
    return lhs.priority > rhs.priority;
  }
};

using SearchFrontier = std::priority_queue<QueueNode>;
using CellParents = std::unordered_map<Cell, Cell, CellHash>;
using CellCosts = std::unordered_map<Cell, double, CellHash>;

struct PlanarPoint final {
  double x{0.0};
  double y{0.0};
};

struct CellSegment final {
  Cell start{};
  Cell goal{};
};

struct RequestedSegment final {
  qrics::common::Vec3 start{};
  qrics::common::Vec3 goal{};
};

[[nodiscard]] qrics::common::Error make_error(std::string code, std::string message) {
  return qrics::common::Error{std::move(code), std::move(message)};
}

[[nodiscard]] double sqr(double value) noexcept {
  return value * value;
}

[[nodiscard]] double planar_distance(const qrics::common::Vec3& lhs,
                                     const qrics::common::Vec3& rhs) noexcept {
  return std::sqrt(sqr(rhs.x - lhs.x) + sqr(rhs.y - lhs.y));
}

[[nodiscard]] double distance_point_to_segment(const PlanarPoint& point,
                                               const PlanarPoint& segment_start,
                                               const PlanarPoint& segment_end) noexcept {
  const double vx = segment_end.x - segment_start.x;
  const double vy = segment_end.y - segment_start.y;
  const double wx = point.x - segment_start.x;
  const double wy = point.y - segment_start.y;
  const double denom = (vx * vx) + (vy * vy);
  const double t = denom <= 1.0e-12 ? 0.0 : std::clamp(((wx * vx) + (wy * vy)) / denom, 0.0, 1.0);
  const double cx = segment_start.x + (t * vx);
  const double cy = segment_start.y + (t * vy);
  return std::sqrt(sqr(point.x - cx) + sqr(point.y - cy));
}

[[nodiscard]] bool point_in_polygon(const std::vector<qrics::common::Vec3>& polygon, double x,
                                    double y) {
  if (polygon.size() < 3U) {
    return false;
  }
  bool inside = false;
  for (std::size_t i = 0U, j = polygon.size() - 1U; i < polygon.size(); j = i++) {
    const auto& pi = polygon[i];
    const auto& pj = polygon[j];
    const bool intersects = ((pi.y > y) != (pj.y > y)) &&
                            (x < ((pj.x - pi.x) * (y - pi.y) / ((pj.y - pi.y) + 1.0e-12)) + pi.x);
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
}

[[nodiscard]] double polygon_clearance(const std::vector<qrics::common::Vec3>& polygon, double x,
                                       double y) {
  if (polygon.empty()) {
    return std::numeric_limits<double>::infinity();
  }
  if (point_in_polygon(polygon, x, y)) {
    return 0.0;
  }
  double best = std::numeric_limits<double>::infinity();
  for (std::size_t i = 0U; i < polygon.size(); ++i) {
    const auto& a = polygon[i];
    const auto& b = polygon[(i + 1U) % polygon.size()];
    best = std::min(best, distance_point_to_segment(PlanarPoint{x, y}, PlanarPoint{a.x, a.y},
                                                    PlanarPoint{b.x, b.y}));
  }
  return best;
}

[[nodiscard]] double positive_or(double value, double fallback) noexcept {
  return value > 0.0 ? value : fallback;
}

[[nodiscard]] double obstacle_clearance(const qrics::scenario::SceneObstacle& obstacle, double x,
                                        double y) {
  const auto& center = obstacle.pose.position;
  if (obstacle.geometry_type == qrics::scenario::SceneGeometryType::Box) {
    const double half_x =
        std::max(0.005, positive_or(obstacle.size_m.x, obstacle.radius_m * 2.0) * 0.5);
    const double half_y =
        std::max(0.005, positive_or(obstacle.size_m.y, obstacle.radius_m * 2.0) * 0.5);
    const double clamped_x = std::clamp(x, center.x - half_x, center.x + half_x);
    const double clamped_y = std::clamp(y, center.y - half_y, center.y + half_y);
    return std::sqrt(sqr(x - clamped_x) + sqr(y - clamped_y));
  }
  const double radius = std::max(0.0, obstacle.radius_m);
  return std::max(0.0, std::sqrt(sqr(x - center.x) + sqr(y - center.y)) - radius);
}

[[nodiscard]] double clearance_to_blockers(const qrics::scenario::SceneProfile& scene, double x,
                                           double y) {
  double best = std::numeric_limits<double>::infinity();
  for (const auto& obstacle : scene.obstacles) {
    best = std::min(best, obstacle_clearance(obstacle, x, y));
  }
  for (const auto& zone : scene.forbidden_zones) {
    best = std::min(best, polygon_clearance(zone.polygon, x, y));
  }
  return best;
}

[[nodiscard]] bool point_blocked(const qrics::scenario::SceneProfile& scene,
                                 const RoutePlanningConfig& config, double x, double y) {
  const double required_clearance = config.robot_radius_m + config.safety_margin_m;
  return clearance_to_blockers(scene, x, y) <= required_clearance;
}

[[nodiscard]] bool segment_blocked(const qrics::scenario::SceneProfile& scene,
                                   const RoutePlanningConfig& config,
                                   const qrics::common::Vec3& start,
                                   const qrics::common::Vec3& goal) {
  const double distance = planar_distance(start, goal);
  const int sample_count = std::max(
      1, static_cast<int>(std::ceil(distance / std::max(0.005, config.max_segment_sample_step_m))));
  for (int i = 0; i <= sample_count; ++i) {
    const double t = static_cast<double>(i) / static_cast<double>(sample_count);
    const double x = start.x + ((goal.x - start.x) * t);
    const double y = start.y + ((goal.y - start.y) * t);
    if (point_blocked(scene, config, x, y)) {
      return true;
    }
  }
  return false;
}

void extend_bounds(Bounds& bounds, const qrics::common::Vec3& point) noexcept {
  bounds.min_x = std::min(bounds.min_x, point.x);
  bounds.max_x = std::max(bounds.max_x, point.x);
  bounds.min_y = std::min(bounds.min_y, point.y);
  bounds.max_y = std::max(bounds.max_y, point.y);
}

[[nodiscard]] Bounds compute_bounds(const qrics::scenario::SceneProfile& scene,
                                    const std::vector<RouteTarget>& targets,
                                    const RoutePlanningConfig& config,
                                    const qrics::common::Vec3& start) {
  Bounds bounds{start.x, start.x, start.y, start.y};
  for (const auto& target : targets) {
    extend_bounds(bounds, target.position);
  }
  for (const auto& obstacle : scene.obstacles) {
    extend_bounds(bounds, obstacle.pose.position);
  }
  for (const auto& zone : scene.forbidden_zones) {
    for (const auto& point : zone.polygon) {
      extend_bounds(bounds, point);
    }
  }
  const double padding =
      std::max(config.search_padding_m, (config.robot_radius_m + config.safety_margin_m) * 2.0);
  bounds.min_x -= padding;
  bounds.max_x += padding;
  bounds.min_y -= padding;
  bounds.max_y += padding;
  return bounds;
}

[[nodiscard]] Cell to_cell(const Bounds& bounds, const RoutePlanningConfig& config,
                           const qrics::common::Vec3& point) {
  return Cell{static_cast<int>(std::llround((point.x - bounds.min_x) / config.grid_resolution_m)),
              static_cast<int>(std::llround((point.y - bounds.min_y) / config.grid_resolution_m))};
}

[[nodiscard]] qrics::common::Vec3 to_point(const Bounds& bounds, const RoutePlanningConfig& config,
                                           const Cell& cell, double z) {
  return qrics::common::Vec3{
      bounds.min_x + (static_cast<double>(cell.x) * config.grid_resolution_m),
      bounds.min_y + (static_cast<double>(cell.y) * config.grid_resolution_m), z};
}

[[nodiscard]] bool in_bounds(const Bounds& bounds, const RoutePlanningConfig& config,
                             const Cell& cell) {
  const qrics::common::Vec3 point = to_point(bounds, config, cell, 0.0);
  return point.x >= bounds.min_x && point.x <= bounds.max_x && point.y >= bounds.min_y &&
         point.y <= bounds.max_y;
}

[[nodiscard]] double heuristic(const Cell& lhs, const Cell& rhs) noexcept {
  return std::hypot(static_cast<double>(rhs.x - lhs.x), static_cast<double>(rhs.y - lhs.y));
}

[[nodiscard]] std::vector<Cell> neighbors(const Cell& cell) {
  std::vector<Cell> out;
  out.reserve(8U);
  for (int dx = -1; dx <= 1; ++dx) {
    for (int dy = -1; dy <= 1; ++dy) {
      if (dx == 0 && dy == 0) {
        continue;
      }
      out.push_back(Cell{cell.x + dx, cell.y + dy});
    }
  }
  return out;
}

[[nodiscard]] bool cell_unblocked(const qrics::scenario::SceneProfile& scene,
                                  const RoutePlanningConfig& config, const Bounds& bounds,
                                  const Cell& candidate) {
  if (!in_bounds(bounds, config, candidate)) {
    return false;
  }
  const auto point = to_point(bounds, config, candidate, 0.0);
  return !point_blocked(scene, config, point.x, point.y);
}

void append_ring_cells(std::vector<Cell>& cells, const Cell& center, int radius) {
  for (int dx = -radius; dx <= radius; ++dx) {
    cells.push_back(Cell{center.x + dx, center.y - radius});
    cells.push_back(Cell{center.x + dx, center.y + radius});
  }
  for (int dy = -radius + 1; dy < radius; ++dy) {
    cells.push_back(Cell{center.x - radius, center.y + dy});
    cells.push_back(Cell{center.x + radius, center.y + dy});
  }
}

[[nodiscard]] std::vector<Cell> ring_cells(const Cell& center, int radius) {
  std::vector<Cell> cells;
  cells.reserve(static_cast<std::size_t>(std::max(0, radius)) * 8U);
  append_ring_cells(cells, center, radius);
  return cells;
}

[[nodiscard]] std::optional<Cell> first_unblocked_cell(const qrics::scenario::SceneProfile& scene,
                                                       const RoutePlanningConfig& config,
                                                       const Bounds& bounds,
                                                       const std::vector<Cell>& candidates) {
  for (const Cell& candidate : candidates) {
    if (cell_unblocked(scene, config, bounds, candidate)) {
      return candidate;
    }
  }
  return std::nullopt;
}

[[nodiscard]] int max_search_radius(const Bounds& bounds, const RoutePlanningConfig& config) {
  const double span = std::max(bounds.max_x - bounds.min_x, bounds.max_y - bounds.min_y);
  return static_cast<int>(std::ceil(span / std::max(1.0e-9, config.grid_resolution_m)));
}

[[nodiscard]] std::optional<Cell> nearest_unblocked_cell(const qrics::scenario::SceneProfile& scene,
                                                         const RoutePlanningConfig& config,
                                                         const Bounds& bounds,
                                                         const Cell& requested) {
  if (cell_unblocked(scene, config, bounds, requested)) {
    return requested;
  }

  const int max_radius = max_search_radius(bounds, config);
  for (int radius = 1; radius <= max_radius; ++radius) {
    const auto safe_cell =
        first_unblocked_cell(scene, config, bounds, ring_cells(requested, radius));
    if (safe_cell.has_value()) {
      return safe_cell;
    }
  }
  return std::nullopt;
}

[[nodiscard]] double traversal_penalty(const qrics::scenario::SceneProfile& scene,
                                       const RoutePlanningConfig& config, double x, double y) {
  const double clearance = clearance_to_blockers(scene, x, y);
  const double required = config.robot_radius_m + config.safety_margin_m;
  if (!std::isfinite(clearance)) {
    return 0.0;
  }
  if (clearance <= required) {
    return 1'000.0;
  }
  const double caution = required * 2.2;
  if (clearance >= caution) {
    return 0.0;
  }
  return (caution - clearance) / std::max(1.0e-9, caution);
}

[[nodiscard]] std::vector<qrics::common::Vec3> reconstruct_path(const Bounds& bounds,
                                                                const RoutePlanningConfig& config,
                                                                const CellSegment& segment,
                                                                const CellParents& came_from,
                                                                double z) {
  std::vector<qrics::common::Vec3> reversed;
  Cell current = segment.goal;
  reversed.push_back(to_point(bounds, config, current, z));
  while (!(current == segment.start)) {
    const auto found = came_from.find(current);
    if (found == came_from.end()) {
      break;
    }
    current = found->second;
    reversed.push_back(to_point(bounds, config, current, z));
  }
  std::reverse(reversed.begin(), reversed.end());
  return reversed;
}

[[nodiscard]] std::vector<qrics::common::Vec3> simplify_path(
    const qrics::scenario::SceneProfile& scene, const RoutePlanningConfig& config,
    const std::vector<qrics::common::Vec3>& path) {
  if (path.size() <= 2U) {
    return path;
  }
  std::vector<qrics::common::Vec3> simplified;
  simplified.push_back(path.front());
  std::size_t anchor = 0U;
  while (anchor + 1U < path.size()) {
    std::size_t best = anchor + 1U;
    for (std::size_t candidate = path.size() - 1U; candidate > anchor + 1U; --candidate) {
      if (!segment_blocked(scene, config, path[anchor], path[candidate])) {
        best = candidate;
        break;
      }
    }
    simplified.push_back(path[best]);
    anchor = best;
  }
  return simplified;
}

void insert_requested_start(std::vector<qrics::common::Vec3>& path,
                            const qrics::common::Vec3& requested_start) {
  if (planar_distance(path.front(), requested_start) > 1.0e-6) {
    path.insert(path.begin(), requested_start);
  }
}

void append_requested_goal(std::vector<qrics::common::Vec3>& path,
                           const qrics::common::Vec3& requested_goal) {
  if (planar_distance(path.back(), requested_goal) > 1.0e-6) {
    path.push_back(requested_goal);
  }
}

[[nodiscard]] std::vector<qrics::common::Vec3> build_segment_path(
    const qrics::scenario::SceneProfile& scene, const RoutePlanningConfig& config,
    const Bounds& bounds, const CellSegment& safe_segment, const CellParents& came_from,
    const RequestedSegment& requested_segment) {
  auto path = simplify_path(
      scene, config,
      reconstruct_path(bounds, config, safe_segment, came_from, requested_segment.goal.z));
  if (path.empty()) {
    return {};
  }
  insert_requested_start(path, requested_segment.start);
  append_requested_goal(path, requested_segment.goal);
  return path;
}

[[nodiscard]] double movement_cost(const Cell& current, const Cell& next) noexcept {
  const bool diagonal = next.x != current.x && next.y != current.y;
  return diagonal ? std::numbers::sqrt2 : 1.0;
}

[[nodiscard]] bool has_better_cost(const CellCosts& cost_so_far, const Cell& cell,
                                   double new_cost) {
  const auto old_cost = cost_so_far.find(cell);
  return old_cost == cost_so_far.end() || new_cost < old_cost->second;
}

void enqueue_neighbor(const Cell& current, const Cell& next, const Cell& goal,
                      SearchFrontier& frontier, CellParents& came_from, CellCosts& cost_so_far,
                      double new_cost) {
  cost_so_far[next] = new_cost;
  frontier.push(QueueNode{next, new_cost + heuristic(next, goal)});
  came_from[next] = current;
}

void try_enqueue_neighbor(const qrics::scenario::SceneProfile& scene,
                          const RoutePlanningConfig& config, const Bounds& bounds,
                          const Cell& current, const Cell& next, const Cell& goal,
                          SearchFrontier& frontier, CellParents& came_from,
                          CellCosts& cost_so_far) {
  if (!cell_unblocked(scene, config, bounds, next)) {
    return;
  }
  const auto next_point = to_point(bounds, config, next, 0.0);
  const double new_cost = cost_so_far[current] + movement_cost(current, next) +
                          traversal_penalty(scene, config, next_point.x, next_point.y);
  if (!has_better_cost(cost_so_far, next, new_cost)) {
    return;
  }
  enqueue_neighbor(current, next, goal, frontier, came_from, cost_so_far, new_cost);
}

[[nodiscard]] std::vector<qrics::common::Vec3> graph_search_segment(
    const qrics::scenario::SceneProfile& scene, const RoutePlanningConfig& config,
    const Bounds& bounds, const RequestedSegment& requested_segment) {
  const Cell start_cell = to_cell(bounds, config, requested_segment.start);
  const Cell goal_cell = to_cell(bounds, config, requested_segment.goal);
  const auto safe_start = nearest_unblocked_cell(scene, config, bounds, start_cell);
  const auto safe_goal = nearest_unblocked_cell(scene, config, bounds, goal_cell);
  if (!safe_start.has_value() || !safe_goal.has_value()) {
    return {};
  }

  SearchFrontier frontier;
  CellParents came_from;
  CellCosts cost_so_far;
  frontier.push(QueueNode{*safe_start, 0.0});
  cost_so_far[*safe_start] = 0.0;

  int expanded = 0;
  while (!frontier.empty() && expanded < config.max_expanded_nodes) {
    const Cell current = frontier.top().cell;
    frontier.pop();
    ++expanded;
    if (current == *safe_goal) {
      return build_segment_path(scene, config, bounds, CellSegment{*safe_start, *safe_goal},
                                came_from, requested_segment);
    }
    for (const Cell& next : neighbors(current)) {
      try_enqueue_neighbor(scene, config, bounds, current, next, *safe_goal, frontier, came_from,
                           cost_so_far);
    }
  }
  return {};
}

[[nodiscard]] int blocked_object_count(const qrics::scenario::SceneProfile& scene) {
  return static_cast<int>(scene.obstacles.size() + scene.forbidden_zones.size());
}

void append_path_segment(PlannedRoute& route, const std::vector<qrics::common::Vec3>& segment,
                         const RouteTarget& target) {
  if (segment.empty()) {
    route.waypoints.push_back(
        RouteWaypoint{target.target_id, target.position, target.dwell_time_s, false, true});
    return;
  }
  const std::size_t first_intermediate = 1U;
  for (std::size_t i = first_intermediate; i < segment.size(); ++i) {
    const bool is_last = i + 1U == segment.size();
    if (is_last) {
      route.waypoints.push_back(
          RouteWaypoint{target.target_id, target.position, target.dwell_time_s, false, true});
    } else {
      RouteWaypoint via{};
      via.waypoint_id = "via_" + std::to_string(route.detour_waypoint_count + 1);
      via.position = segment[i];
      via.dwell_time_s = 0.0;
      via.is_detour = true;
      via.is_task_target = false;
      route.waypoints.push_back(via);
      ++route.detour_waypoint_count;
    }
  }
}

void accumulate_distance(PlannedRoute& route, const qrics::common::Vec3& start) {
  qrics::common::Vec3 cursor = start;
  route.total_distance_m = 0.0;
  for (const auto& waypoint : route.waypoints) {
    route.total_distance_m += planar_distance(cursor, waypoint.position);
    cursor = waypoint.position;
  }
}

}  // namespace

qrics::common::Result<PlannedRoute> plan_task_route(const qrics::scenario::SceneProfile& scene,
                                                    const std::vector<RouteTarget>& targets,
                                                    const RoutePlanningConfig& config,
                                                    const qrics::common::Vec3& start) {
  if (config.grid_resolution_m <= 0.0) {
    return qrics::common::Result<PlannedRoute>::failure(
        {make_error("ROUTE_GRID_INVALID", "Route planner grid_resolution_m must be positive")});
  }
  PlannedRoute route{};
  route.original_target_count = static_cast<int>(targets.size());
  route.blocked_object_count = blocked_object_count(scene);
  if (targets.empty()) {
    route.notes.emplace_back("C++ route planner received empty task path");
    return qrics::common::Result<PlannedRoute>::success(std::move(route));
  }

  const Bounds bounds = compute_bounds(scene, targets, config, start);
  qrics::common::Vec3 cursor = start;
  for (const auto& target : targets) {
    if (!segment_blocked(scene, config, cursor, target.position)) {
      route.waypoints.push_back(
          RouteWaypoint{target.target_id, target.position, target.dwell_time_s, false, true});
      cursor = target.position;
      continue;
    }

    route.used_graph_search = true;
    auto segment =
        graph_search_segment(scene, config, bounds, RequestedSegment{cursor, target.position});
    if (segment.empty()) {
      route.notes.emplace_back("C++ route planner could not find detour for target " +
                               target.target_id +
                               "; falling back to direct safety-monitored segment");
      route.waypoints.push_back(
          RouteWaypoint{target.target_id, target.position, target.dwell_time_s, false, true});
      cursor = target.position;
      continue;
    }
    route.notes.emplace_back("C++ route planner inserted detour before target " + target.target_id);
    append_path_segment(route, segment, target);
    cursor = target.position;
  }
  accumulate_distance(route, start);
  if (route.detour_waypoint_count == 0) {
    route.notes.emplace_back("C++ route planner accepted direct task segments");
  }
  return qrics::common::Result<PlannedRoute>::success(std::move(route));
}

}  // namespace qrics::planning