#include <cmath>

#include "qrics/control/path_tracker.hpp"

namespace {

[[nodiscard]] qrics::control::PathTrackRequest make_request(qrics::simulation::TerrainClass terrain,
                                                            double robot_x = 0.0) {
  qrics::control::PathTrackRequest request{};
  request.task_node.node_id = "node_move_A";
  request.task_node.type = qrics::task::TaskNodeType::MoveTo;
  request.task_node.target_waypoint_id = "A";
  request.target.waypoint_id = "A";
  request.target.pose.position.x = 1.0;
  request.robot_state.pose.position.x = robot_x;
  request.robot_state.terrain_class = terrain;
  request.policy_ref = qrics::common::ResourceRef{"policy", "0.1.0"};
  request.timestamp_ns = 1000;
  return request;
}

}  // namespace

int main() {
  qrics::control::PurePursuitPathTracker tracker{};

  const auto flat = tracker.track(make_request(qrics::simulation::TerrainClass::Flat));
  if (!flat.ok) {
    return 1;
  }
  if (flat.value.target_reached) {
    return 2;
  }
  if (flat.value.proposal.action_type != qrics::control::ActionType::BodyVelocity) {
    return 3;
  }
  if (flat.value.command_speed_mps <= 0.0) {
    return 4;
  }

  const auto low_friction =
      tracker.track(make_request(qrics::simulation::TerrainClass::LowFriction));
  if (!low_friction.ok) {
    return 5;
  }
  if (low_friction.value.command_speed_mps >= flat.value.command_speed_mps) {
    return 6;
  }

  const auto reached = tracker.track(make_request(qrics::simulation::TerrainClass::Flat, 0.95));
  if (!reached.ok) {
    return 7;
  }
  if (!reached.value.target_reached) {
    return 8;
  }
  if (reached.value.proposal.action_type != qrics::control::ActionType::Stop) {
    return 9;
  }

  auto invalid = make_request(qrics::simulation::TerrainClass::Flat);
  invalid.target.waypoint_id.clear();
  const auto invalid_result = tracker.track(invalid);
  if (invalid_result.ok || invalid_result.errors.empty() ||
      invalid_result.errors.front().code != "TARGET_WAYPOINT_EMPTY") {
    return 10;
  }

  return 0;
}