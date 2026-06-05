// 障碍规避实现

#include "qrics/control/obstacle_avoidance.hpp"

#include <algorithm>
#include <cmath>
#include <string>

namespace qrics::control {

SimpleObstacleAvoidance::SimpleObstacleAvoidance(ObstacleAvoidanceConfig config)
    : config_(config) {}

ObstacleAvoidanceResult SimpleObstacleAvoidance::apply(
    const ObstacleAvoidanceRequest& request) const {
  ObstacleAvoidanceResult result{};
  result.proposal = request.proposal;
  result.reason = "No obstacle avoidance adjustment required";

  const auto& obstacle = request.observation.obstacle_state;
  if (!obstacle.obstacle_detected || obstacle.nearest_distance_m <= 0.0 ||
      request.proposal.action_type != ActionType::BodyVelocity) {
    return result;
  }

  if (obstacle.nearest_distance_m <= config_.hard_stop_distance_m) {
    result.proposal.action_type = ActionType::Replan;
    result.proposal.desired_body_velocity = {};
    result.proposal.desired_yaw_rate_radps = 0.0;
    result.proposal.confidence = std::min(result.proposal.confidence, 0.45);
    result.adjusted = true;
    result.replan_required = true;
    result.reason = "Obstacle is inside hard stop distance; request local replan";
    return result;
  }

  if (obstacle.nearest_distance_m <= config_.warning_distance_m) {
    const double lateral_sign = obstacle.nearest_point.y >= 0.0 ? -1.0 : 1.0;
    result.proposal.desired_body_velocity.x *= config_.forward_slowdown_scale;
    result.proposal.desired_body_velocity.y += lateral_sign * config_.lateral_escape_speed_mps;
    result.proposal.desired_yaw_rate_radps += lateral_sign * 0.2;
    result.proposal.confidence = std::min(result.proposal.confidence, 0.80);
    result.adjusted = true;
    result.reason = "Obstacle warning distance reached; slow forward velocity and bias laterally";
  }

  return result;
}

}  // namespace qrics::control