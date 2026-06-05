#include "qrics/control/recovery_controller.hpp"

namespace {

[[nodiscard]] qrics::control::RecoveryRequest make_request(
    qrics::simulation::StabilityState stability, double risk_score = 0.0) {
  qrics::control::RecoveryRequest request{};
  request.task_node.node_id = "node_move_A";
  request.policy_ref = qrics::common::ResourceRef{"policy", "0.1.0"};
  request.robot_state.stability_state = stability;
  request.robot_state.risk_score = risk_score;
  request.timestamp_ns = 1000;
  return request;
}

}  // namespace

int main() {
  qrics::control::StabilityRecoveryController controller{};

  const auto stable = controller.evaluate(make_request(qrics::simulation::StabilityState::Stable));
  if (stable.recovery_required) {
    return 1;
  }

  const auto fallen = controller.evaluate(make_request(qrics::simulation::StabilityState::Fallen));
  if (!fallen.recovery_required || !fallen.terminal_recovery) {
    return 2;
  }
  if (fallen.proposal.action_type != qrics::control::ActionType::SafeStand) {
    return 3;
  }

  const auto elevated =
      controller.evaluate(make_request(qrics::simulation::StabilityState::Stable, 0.50));
  if (!elevated.recovery_required) {
    return 4;
  }
  if (elevated.proposal.action_type != qrics::control::ActionType::Stop) {
    return 5;
  }

  const auto high_risk =
      controller.evaluate(make_request(qrics::simulation::StabilityState::Stable, 0.80));
  if (!high_risk.recovery_required) {
    return 6;
  }
  if (high_risk.proposal.action_type != qrics::control::ActionType::SafeStand) {
    return 7;
  }

  return 0;
}