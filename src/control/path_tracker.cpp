// 路径跟踪控制器实现

#include "qrics/control/path_tracker.hpp"

#include <algorithm>
#include <cmath>
#include <string>
#include <utility>

namespace qrics::control {

namespace {

[[nodiscard]] qrics::common::Result<PathTrackResult> fail(const std::string& code,
                                                          const std::string& message) {
  return qrics::common::Result<PathTrackResult>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] double clamp_positive(double value, double fallback) noexcept {
  return value > 0.0 ? value : fallback;
}

[[nodiscard]] double xy_distance(const qrics::common::Vec3& lhs,
                                 const qrics::common::Vec3& rhs) noexcept {
  const double dx = rhs.x - lhs.x;
  const double dy = rhs.y - lhs.y;
  return std::sqrt((dx * dx) + (dy * dy));
}

[[nodiscard]] double xyz_distance(const qrics::common::Vec3& lhs,
                                  const qrics::common::Vec3& rhs) noexcept {
  const double dx = rhs.x - lhs.x;
  const double dy = rhs.y - lhs.y;
  const double dz = rhs.z - lhs.z;
  return std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
}

[[nodiscard]] ActionProposal base_proposal(const PathTrackRequest& request,
                                           ActionType action_type) {
  ActionProposal proposal{};
  proposal.proposal_id = "path_" + request.task_node.node_id;
  proposal.policy_ref = request.policy_ref;
  proposal.task_node_id = request.task_node.node_id;
  proposal.action_type = action_type;
  proposal.confidence = 1.0;
  proposal.timestamp_ns = request.timestamp_ns;
  return proposal;
}

}  // namespace

PurePursuitPathTracker::PurePursuitPathTracker(PathTrackerConfig config) : config_(config) {}

qrics::common::Result<PathTrackResult> PurePursuitPathTracker::track(
    const PathTrackRequest& request) const {
  if (request.task_node.node_id.empty()) {
    return fail("TASK_NODE_ID_EMPTY", "PathTrackRequest.task_node.node_id must not be empty");
  }
  if (request.target.waypoint_id.empty()) {
    return fail("TARGET_WAYPOINT_EMPTY", "Path tracking requires a target waypoint");
  }

  PathTrackResult result{};
  const auto& current = request.robot_state.pose.position;
  const auto& target = request.target.pose.position;
  result.distance_to_target_m =
      config_.planar_tracking ? xy_distance(current, target) : xyz_distance(current, target);
  result.target_reached = result.distance_to_target_m <= config_.target_tolerance_m;
  result.proposal =
      base_proposal(request, result.target_reached ? ActionType::Stop : ActionType::BodyVelocity);

  if (result.target_reached) {
    result.reason = "Target waypoint reached by path tracker";
    return qrics::common::Result<PathTrackResult>::success(std::move(result));
  }

  const double dx = target.x - current.x;
  const double dy = target.y - current.y;
  const double dz = config_.planar_tracking ? 0.0 : target.z - current.z;
  const double norm = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
  if (norm <= 1.0e-9) {
    result.proposal.action_type = ActionType::Stop;
    result.target_reached = true;
    result.reason = "Target waypoint reached by zero-distance guard";
    return qrics::common::Result<PathTrackResult>::success(std::move(result));
  }

  result.command_speed_mps =
      command_speed(result.distance_to_target_m, request.robot_state.terrain_class);
  result.proposal.desired_body_velocity = qrics::common::Vec3{
      result.command_speed_mps * dx / norm,
      result.command_speed_mps * dy / norm,
      result.command_speed_mps * dz / norm,
  };

  // 当前无完整 yaw 反解工具，先采用横向误差到 yaw rate 的保守比例控制，后续可替换为姿态反馈控制器。
  const double raw_yaw_rate = std::clamp(dy, -1.0, 1.0) * config_.max_yaw_rate_radps;
  result.proposal.desired_yaw_rate_radps =
      std::clamp(raw_yaw_rate, -config_.max_yaw_rate_radps, config_.max_yaw_rate_radps);
  result.reason = "Track waypoint with terrain-aware velocity command";
  return qrics::common::Result<PathTrackResult>::success(std::move(result));
}

double PurePursuitPathTracker::terrain_speed_limit(
    qrics::simulation::TerrainClass terrain) const noexcept {
  switch (terrain) {
    case qrics::simulation::TerrainClass::Flat:
      return clamp_positive(config_.flat_speed_mps, 0.55);
    case qrics::simulation::TerrainClass::Slope:
      return clamp_positive(config_.slope_speed_mps, 0.35);
    case qrics::simulation::TerrainClass::Gravel:
      return clamp_positive(config_.gravel_speed_mps, 0.30);
    case qrics::simulation::TerrainClass::Stairs:
      return clamp_positive(config_.stairs_speed_mps, 0.22);
    case qrics::simulation::TerrainClass::LowFriction:
      return clamp_positive(config_.low_friction_speed_mps, 0.18);
    case qrics::simulation::TerrainClass::Unknown:
      return clamp_positive(config_.unknown_speed_mps, 0.25);
  }
  return clamp_positive(config_.unknown_speed_mps, 0.25);
}

double PurePursuitPathTracker::command_speed(
    double distance_m, qrics::simulation::TerrainClass terrain) const noexcept {
  const double speed_limit = terrain_speed_limit(terrain);
  const double slow_radius = clamp_positive(config_.slow_down_radius_m, config_.target_tolerance_m);
  const double scale = std::clamp(distance_m / slow_radius, 0.20, 1.0);
  return speed_limit * scale;
}

}  // namespace qrics::control