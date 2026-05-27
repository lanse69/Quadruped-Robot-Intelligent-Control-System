#include <cmath>
#include <string>

#include "qrics/control/policy_runtime.hpp"

namespace {

[[nodiscard]] bool near(double lhs, double rhs) {
  return std::abs(lhs - rhs) < 1.0e-9;
}

[[nodiscard]] qrics::control::PolicyRuntimeRequest make_request(double robot_x) {
  qrics::control::PolicyRuntimeRequest request{};
  request.run_id = "run_policy_runtime";
  request.policy_ref = qrics::common::ResourceRef{"policy_flat", "0.1.0"};
  request.task_node.node_id = "node_1_move_to_a";
  request.task_node.type = qrics::task::TaskNodeType::MoveTo;
  request.task_node.target_waypoint_id = "A";
  request.target.waypoint_id = "A";
  request.target.pose.position.x = 1.0;
  request.robot_state.pose.position.x = robot_x;
  request.timestamp_ns = 1000;
  return request;
}

}  // namespace

int main() {
  qrics::control::SimpleLocalPlanner planner{};
  qrics::control::RuleBasedPolicyRuntime runtime{planner};

  const auto move_result = runtime.infer(make_request(0.0));
  if (!move_result.ok) {
    return 1;
  }
  if (move_result.value.target_reached) {
    return 2;
  }
  if (move_result.value.proposal.action_type != qrics::control::ActionType::BodyVelocity) {
    return 3;
  }
  if (move_result.value.proposal.desired_body_velocity.x <= 0.0) {
    return 4;
  }
  if (move_result.value.proposal.policy_ref.id != "policy_flat") {
    return 5;
  }

  const auto reached_result = runtime.infer(make_request(0.95));
  if (!reached_result.ok) {
    return 6;
  }
  if (!reached_result.value.target_reached) {
    return 7;
  }
  if (reached_result.value.proposal.action_type != qrics::control::ActionType::Stop) {
    return 8;
  }
  if (!near(reached_result.value.proposal.desired_body_velocity.x, 0.0)) {
    return 9;
  }

  auto invalid = make_request(0.0);
  invalid.run_id.clear();
  const auto invalid_result = runtime.infer(invalid);
  if (invalid_result.ok || invalid_result.errors.empty() ||
      invalid_result.errors.front().code != "RUN_ID_EMPTY") {
    return 10;
  }

  return 0;
}