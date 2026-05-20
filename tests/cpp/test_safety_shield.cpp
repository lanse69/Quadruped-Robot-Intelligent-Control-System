// Safety Shield 单元测试

#include <cmath>

#include "qrics/safety/safety_shield.hpp"

namespace {

[[nodiscard]] qrics::control::ActionProposal make_body_velocity_proposal() {
  qrics::control::ActionProposal proposal{};
  proposal.proposal_id = "proposal_body_velocity";
  proposal.action_type = qrics::control::ActionType::BodyVelocity;
  proposal.desired_body_velocity = qrics::common::Vec3{0.5, 0.0, 0.0};
  proposal.desired_yaw_rate_radps = 0.2;
  proposal.timestamp_ns = 1000;
  return proposal;
}

[[nodiscard]] qrics::safety::SafetyContext make_context() {
  qrics::safety::SafetyContext context{};
  context.run_id = "run_001";
  context.robot_state.stability_state = qrics::simulation::StabilityState::Stable;
  context.robot_state.risk_score = 0.1;
  return context;
}

[[nodiscard]] bool near(double lhs, double rhs) {
  return std::abs(lhs - rhs) < 1.0e-9;
}

}  // namespace

int main() {
  qrics::safety::BasicSafetyShield shield{qrics::safety::SafetyLimits{}};

  const auto accepted = shield.evaluate(make_body_velocity_proposal(), make_context());
  if (accepted.safe_action.decision != qrics::control::SafetyDecision::Accepted) {
    return 1;
  }
  if (!accepted.events.empty()) {
    return 2;
  }

  auto fast = make_body_velocity_proposal();
  fast.desired_body_velocity = qrics::common::Vec3{2.0, 0.0, 0.0};
  fast.desired_yaw_rate_radps = 3.0;

  const auto clipped = shield.evaluate(fast, make_context());
  if (clipped.safe_action.decision != qrics::control::SafetyDecision::Clipped) {
    return 3;
  }
  if (!near(clipped.safe_action.body_velocity.x, 1.0)) {
    return 4;
  }
  if (!near(clipped.safe_action.yaw_rate_radps, 1.0)) {
    return 5;
  }
  if (clipped.events.size() != 1) {
    return 6;
  }

  auto emergency_context = make_context();
  emergency_context.emergency_stop_active = true;

  const auto emergency = shield.evaluate(make_body_velocity_proposal(), emergency_context);
  if (emergency.safe_action.decision != qrics::control::SafetyDecision::EmergencyStop) {
    return 7;
  }
  if (emergency.safe_action.action_type != qrics::control::ActionType::Stop) {
    return 8;
  }

  auto fallen_context = make_context();
  fallen_context.robot_state.stability_state = qrics::simulation::StabilityState::Fallen;

  const auto safe_stand = shield.evaluate(make_body_velocity_proposal(), fallen_context);
  if (safe_stand.safe_action.decision != qrics::control::SafetyDecision::SafeStand) {
    return 9;
  }
  if (safe_stand.safe_action.action_type != qrics::control::ActionType::SafeStand) {
    return 10;
  }

  auto joint = make_body_velocity_proposal();
  joint.action_type = qrics::control::ActionType::JointPosition;

  const auto rejected = shield.evaluate(joint, make_context());
  if (rejected.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 11;
  }
  if (rejected.events.empty()) {
    return 12;
  }

  qrics::safety::BasicSafetyShield invalid_shield{
      qrics::safety::SafetyLimits{0.0, 1.0, 0.8, false}};
  const auto invalid_result =
      invalid_shield.evaluate(make_body_velocity_proposal(), make_context());
  if (invalid_result.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 13;
  }
  if (invalid_result.events.empty()) {
    return 14;
  }

  auto manual_context = make_context();
  manual_context.manual_override_active = true;
  manual_context.override_command.command_type = qrics::safety::OverrideCommandType::ManualControl;

  const auto manual_result = shield.evaluate(make_body_velocity_proposal(), manual_context);
  if (manual_result.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 15;
  }
  if (manual_result.events.empty() || manual_result.events.front().action_taken !=
                                          qrics::safety::SafetyActionTaken::ManualControl) {
    return 16;
  }

  return 0;
}