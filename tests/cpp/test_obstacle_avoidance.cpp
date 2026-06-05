#include <cmath>

#include "qrics/control/obstacle_avoidance.hpp"

namespace {

[[nodiscard]] bool near(double lhs, double rhs) {
  return std::abs(lhs - rhs) < 1.0e-9;
}

[[nodiscard]] qrics::control::ActionProposal make_proposal() {
  qrics::control::ActionProposal proposal{};
  proposal.proposal_id = "proposal_move";
  proposal.action_type = qrics::control::ActionType::BodyVelocity;
  proposal.desired_body_velocity.x = 0.5;
  proposal.confidence = 1.0;
  return proposal;
}

[[nodiscard]] qrics::simulation::ObservationPacket make_observation(double distance) {
  qrics::simulation::ObservationPacket observation{};
  observation.observation_id = "obs";
  observation.obstacle_state.obstacle_detected = true;
  observation.obstacle_state.nearest_distance_m = distance;
  observation.obstacle_state.nearest_point.y = 0.2;
  observation.obstacle_state.source_quality = qrics::simulation::SourceQuality::Direct;
  return observation;
}

}  // namespace

int main() {
  qrics::control::SimpleObstacleAvoidance avoidance{};

  qrics::control::ObstacleAvoidanceRequest warning{};
  warning.proposal = make_proposal();
  warning.observation = make_observation(0.50);
  const auto adjusted = avoidance.apply(warning);
  if (!adjusted.adjusted || adjusted.replan_required) {
    return 1;
  }
  if (!(adjusted.proposal.desired_body_velocity.x < warning.proposal.desired_body_velocity.x)) {
    return 2;
  }
  if (!(adjusted.proposal.desired_body_velocity.y < 0.0)) {
    return 3;
  }

  qrics::control::ObstacleAvoidanceRequest critical{};
  critical.proposal = make_proposal();
  critical.observation = make_observation(0.10);
  const auto replan = avoidance.apply(critical);
  if (!replan.adjusted || !replan.replan_required) {
    return 4;
  }
  if (replan.proposal.action_type != qrics::control::ActionType::Replan) {
    return 5;
  }
  if (!near(replan.proposal.desired_body_velocity.x, 0.0)) {
    return 6;
  }

  qrics::control::ObstacleAvoidanceRequest clear{};
  clear.proposal = make_proposal();
  clear.observation = make_observation(1.50);
  const auto unchanged = avoidance.apply(clear);
  if (unchanged.adjusted || unchanged.replan_required) {
    return 7;
  }

  return 0;
}