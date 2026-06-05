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

[[nodiscard]] qrics::safety::BasicSafetyShield make_default_shield() {
  return qrics::safety::BasicSafetyShield{qrics::safety::SafetyLimits{}};
}

[[nodiscard]] bool near(double lhs, double rhs) {
  return std::abs(lhs - rhs) < 1.0e-9;
}

[[nodiscard]] int test_accepted_action() {
  const auto shield = make_default_shield();
  const auto accepted = shield.evaluate(make_body_velocity_proposal(), make_context());
  if (accepted.safe_action.decision != qrics::control::SafetyDecision::Accepted) {
    return 1;
  }
  if (!accepted.events.empty()) {
    return 2;
  }
  return 0;
}

[[nodiscard]] int test_action_clipping() {
  const auto shield = make_default_shield();
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
  return 0;
}

[[nodiscard]] int test_emergency_stop() {
  const auto shield = make_default_shield();
  auto emergency_context = make_context();
  emergency_context.emergency_stop_active = true;

  const auto emergency = shield.evaluate(make_body_velocity_proposal(), emergency_context);
  if (emergency.safe_action.decision != qrics::control::SafetyDecision::EmergencyStop) {
    return 7;
  }
  if (emergency.safe_action.action_type != qrics::control::ActionType::Stop) {
    return 8;
  }
  return 0;
}

[[nodiscard]] int test_safe_stand_for_fallen_state() {
  const auto shield = make_default_shield();
  auto fallen_context = make_context();
  fallen_context.robot_state.stability_state = qrics::simulation::StabilityState::Fallen;

  const auto safe_stand = shield.evaluate(make_body_velocity_proposal(), fallen_context);
  if (safe_stand.safe_action.decision != qrics::control::SafetyDecision::SafeStand) {
    return 9;
  }
  if (safe_stand.safe_action.action_type != qrics::control::ActionType::SafeStand) {
    return 10;
  }
  return 0;
}

[[nodiscard]] int test_rejected_unsupported_action_type() {
  const auto shield = make_default_shield();
  auto joint = make_body_velocity_proposal();
  joint.action_type = qrics::control::ActionType::JointPosition;

  const auto rejected = shield.evaluate(joint, make_context());
  if (rejected.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 11;
  }
  if (rejected.events.empty()) {
    return 12;
  }
  return 0;
}

[[nodiscard]] int test_invalid_limits_rejection() {
  const qrics::safety::BasicSafetyShield invalid_shield{
      qrics::safety::SafetyLimits{0.0, 1.0, 0.8, false}};
  const auto invalid_result =
      invalid_shield.evaluate(make_body_velocity_proposal(), make_context());
  if (invalid_result.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 13;
  }
  if (invalid_result.events.empty()) {
    return 14;
  }
  return 0;
}

[[nodiscard]] int test_manual_override_rejection() {
  const auto shield = make_default_shield();
  auto manual_context = make_context();
  manual_context.manual_override_active = true;
  manual_context.override_command.command_type = qrics::safety::OverrideCommandType::ManualControl;

  const auto manual_result = shield.evaluate(make_body_velocity_proposal(), manual_context);
  if (manual_result.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 15;
  }
  if (manual_result.events.empty()) {
    return 16;
  }
  if (manual_result.events.front().action_taken !=
      qrics::safety::SafetyActionTaken::ManualControl) {
    return 16;
  }
  return 0;
}

[[nodiscard]] qrics::safety::SafetyContext make_collision_context() {
  auto collision_context = make_context();
  collision_context.observation.observation_id = "obs_collision";
  collision_context.observation.imu.source_quality = qrics::simulation::SourceQuality::Direct;
  collision_context.observation.obstacle_state.obstacle_detected = true;
  collision_context.observation.obstacle_state.nearest_distance_m = 0.10;
  collision_context.observation.obstacle_state.source_quality =
      qrics::simulation::SourceQuality::Direct;
  return collision_context;
}

[[nodiscard]] int test_collision_replan() {
  const auto shield = make_default_shield();
  const auto collision_result =
      shield.evaluate(make_body_velocity_proposal(), make_collision_context());
  if (collision_result.safe_action.decision != qrics::control::SafetyDecision::Replan) {
    return 17;
  }
  if (collision_result.events.empty()) {
    return 18;
  }
  if (collision_result.events.front().trigger_type != qrics::safety::TriggerType::CollisionRisk) {
    return 18;
  }
  return 0;
}

[[nodiscard]] qrics::safety::SafetyContext make_forbidden_zone_context() {
  auto forbidden_context = make_context();
  forbidden_context.robot_state.pose.position.x = 0.5;
  forbidden_context.robot_state.pose.position.y = 0.5;
  qrics::scenario::ForbiddenZone forbidden{};
  forbidden.zone_id = "low_friction_forbidden";
  forbidden.polygon = {qrics::common::Vec3{0.0, 0.0, 0.0}, qrics::common::Vec3{1.0, 0.0, 0.0},
                       qrics::common::Vec3{1.0, 1.0, 0.0}, qrics::common::Vec3{0.0, 1.0, 0.0}};
  forbidden_context.forbidden_zones.push_back(forbidden);
  return forbidden_context;
}

[[nodiscard]] int test_forbidden_zone_replan() {
  const auto shield = make_default_shield();
  const auto forbidden_result =
      shield.evaluate(make_body_velocity_proposal(), make_forbidden_zone_context());
  if (forbidden_result.safe_action.decision != qrics::control::SafetyDecision::Replan) {
    return 19;
  }
  if (forbidden_result.events.empty()) {
    return 20;
  }
  if (forbidden_result.events.front().trigger_type != qrics::safety::TriggerType::ForbiddenZone) {
    return 20;
  }
  return 0;
}

[[nodiscard]] qrics::safety::SafetyContext make_missing_observation_context() {
  auto missing_observation_context = make_context();
  missing_observation_context.require_observation = true;
  missing_observation_context.observation.observation_id = "obs_missing";
  missing_observation_context.observation.imu.source_quality =
      qrics::simulation::SourceQuality::Missing;
  missing_observation_context.observation.obstacle_state.source_quality =
      qrics::simulation::SourceQuality::Direct;
  return missing_observation_context;
}

[[nodiscard]] int test_missing_observation_rejection() {
  const auto shield = make_default_shield();
  const auto missing_result =
      shield.evaluate(make_body_velocity_proposal(), make_missing_observation_context());
  if (missing_result.safe_action.decision != qrics::control::SafetyDecision::Rejected) {
    return 21;
  }
  if (missing_result.events.empty()) {
    return 22;
  }
  if (missing_result.events.front().trigger_type !=
      qrics::safety::TriggerType::ObservationMissing) {
    return 22;
  }
  return 0;
}

}  // namespace

int main() {
  if (const int result = test_accepted_action(); result != 0) {
    return result;
  }
  if (const int result = test_action_clipping(); result != 0) {
    return result;
  }
  if (const int result = test_emergency_stop(); result != 0) {
    return result;
  }
  if (const int result = test_safe_stand_for_fallen_state(); result != 0) {
    return result;
  }
  if (const int result = test_rejected_unsupported_action_type(); result != 0) {
    return result;
  }
  if (const int result = test_invalid_limits_rejection(); result != 0) {
    return result;
  }
  if (const int result = test_manual_override_rejection(); result != 0) {
    return result;
  }
  if (const int result = test_collision_replan(); result != 0) {
    return result;
  }
  if (const int result = test_forbidden_zone_replan(); result != 0) {
    return result;
  }
  if (const int result = test_missing_observation_rejection(); result != 0) {
    return result;
  }
  return 0;
}