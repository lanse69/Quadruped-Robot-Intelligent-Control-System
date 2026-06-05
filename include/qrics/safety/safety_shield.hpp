// 安全门控接口与占位实现

#pragma once

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#include "qrics/control/action.hpp"
#include "qrics/safety/safety_event.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/simulation/observation.hpp"

namespace qrics::safety {

struct SafetyLimits final {
  double max_linear_velocity_mps{1.0};
  double max_yaw_rate_radps{1.0};
  double max_risk_score{0.8};
  bool allow_joint_commands{false};
  double min_obstacle_distance_m{0.25};
};

struct SafetyContext final {
  std::string run_id{};
  qrics::simulation::RobotState robot_state{};
  qrics::simulation::ObservationPacket observation{};
  std::vector<qrics::scenario::ForbiddenZone> forbidden_zones{};
  bool require_observation{false};
  bool emergency_stop_active{false};
  bool manual_override_active{false};
  OverrideCommand override_command{};
};

struct SafetyEvaluation final {
  qrics::control::SafeAction safe_action{};
  std::vector<SafetyEvent> events{};
};

class SafetyShield {
 public:
  virtual ~SafetyShield() = default;

  [[nodiscard]] virtual SafetyEvaluation evaluate(const qrics::control::ActionProposal& proposal,
                                                  const SafetyContext& context) const = 0;
};

class BasicSafetyShield : public SafetyShield {
 public:
  explicit BasicSafetyShield(const SafetyLimits& limits) : limits_(limits) {}

  [[nodiscard]] SafetyEvaluation evaluate(const qrics::control::ActionProposal& proposal,
                                          const SafetyContext& context) const override {
    if (!limits_are_valid()) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Rejected,
                                  qrics::control::ActionType::Stop, TriggerType::ActionLimit,
                                  SafetyActionTaken::Stop, "Invalid safety limits");
    }

    if (context.emergency_stop_active ||
        context.override_command.command_type == OverrideCommandType::EmergencyStop) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::EmergencyStop,
                                  qrics::control::ActionType::Stop, TriggerType::EmergencyStop,
                                  SafetyActionTaken::Stop, "Emergency stop is active");
    }

    if (context.manual_override_active ||
        context.override_command.command_type == OverrideCommandType::ManualControl) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Rejected,
                                  qrics::control::ActionType::Stop, TriggerType::ManualOverride,
                                  SafetyActionTaken::ManualControl,
                                  "Manual control is active; automatic action is blocked");
    }

    if (context.override_command.command_type == OverrideCommandType::SafeStand) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::SafeStand,
                                  qrics::control::ActionType::SafeStand,
                                  TriggerType::ManualOverride, SafetyActionTaken::SafeStand,
                                  "Operator requested SafeStand");
    }

    if (requires_safe_stand(context.robot_state)) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::SafeStand,
                                  qrics::control::ActionType::SafeStand,
                                  TriggerType::OrientationLimit, SafetyActionTaken::SafeStand,
                                  "Robot state requires SafeStand");
    }

    if (observation_missing(context)) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Rejected,
                                  qrics::control::ActionType::Stop, TriggerType::ObservationMissing,
                                  SafetyActionTaken::Stop,
                                  "Required observation packet is missing or degraded");
    }

    if (collision_risk(context)) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Replan,
                                  qrics::control::ActionType::Replan, TriggerType::CollisionRisk,
                                  SafetyActionTaken::Replan,
                                  "Obstacle distance violates collision safety threshold");
    }

    if (inside_forbidden_zone(context)) {
      return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Replan,
                                  qrics::control::ActionType::Replan, TriggerType::ForbiddenZone,
                                  SafetyActionTaken::Replan,
                                  "Robot pose is inside a forbidden zone");
    }

    switch (proposal.action_type) {
      case qrics::control::ActionType::BodyVelocity:
        return make_body_velocity_result(proposal, context);
      case qrics::control::ActionType::Stop:
      case qrics::control::ActionType::SafeStand:
      case qrics::control::ActionType::Replan:
        return make_direct_safe_action(proposal);
      case qrics::control::ActionType::JointPosition:
      case qrics::control::ActionType::JointVelocity:
        if (limits_.allow_joint_commands) {
          return make_direct_safe_action(proposal);
        }
        return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Rejected,
                                    qrics::control::ActionType::Stop, TriggerType::ActionLimit,
                                    SafetyActionTaken::Stop,
                                    "Joint commands are disabled by SafetyLimits");
    }

    return make_terminal_result(proposal, context, qrics::control::SafetyDecision::Rejected,
                                qrics::control::ActionType::Stop, TriggerType::ActionLimit,
                                SafetyActionTaken::Stop, "Unsupported action type");
  }

 private:
  [[nodiscard]] bool limits_are_valid() const noexcept {
    return limits_.max_linear_velocity_mps > 0.0 && limits_.max_yaw_rate_radps > 0.0 &&
           limits_.max_risk_score >= 0.00 && limits_.max_risk_score <= 1.0 &&
           limits_.min_obstacle_distance_m > 0.0;
  }

  [[nodiscard]] bool requires_safe_stand(
      const qrics::simulation::RobotState& robot_state) const noexcept {
    return robot_state.stability_state == qrics::simulation::StabilityState::Fallen ||
           robot_state.stability_state == qrics::simulation::StabilityState::Unstable ||
           robot_state.risk_score > limits_.max_risk_score;
  }

  [[nodiscard]] static bool observation_missing(const SafetyContext& context) noexcept {
    if (!context.require_observation) {
      return false;
    }
    return context.observation.observation_id.empty() ||
           context.observation.imu.source_quality == qrics::simulation::SourceQuality::Missing ||
           context.observation.obstacle_state.source_quality ==
               qrics::simulation::SourceQuality::Missing;
  }

  [[nodiscard]] bool collision_risk(const SafetyContext& context) const noexcept {
    const auto& obstacle = context.observation.obstacle_state;
    return obstacle.obstacle_detected && obstacle.nearest_distance_m > 0.0 &&
           obstacle.nearest_distance_m <= limits_.min_obstacle_distance_m;
  }

  [[nodiscard]] static bool point_inside_polygon(
      const qrics::common::Vec3& point, const std::vector<qrics::common::Vec3>& polygon) noexcept {
    if (polygon.size() < 3) {
      return false;
    }

    bool inside = false;
    std::size_t previous = polygon.size() - 1;
    for (std::size_t current = 0; current < polygon.size(); ++current) {
      const auto& lhs = polygon[current];
      const auto& rhs = polygon[previous];
      const bool crosses_y = (lhs.y > point.y) != (rhs.y > point.y);
      const double denominator = rhs.y - lhs.y;
      if (crosses_y && std::abs(denominator) > 1.0e-12) {
        const double x_intersection = ((rhs.x - lhs.x) * (point.y - lhs.y) / denominator) + lhs.x;
        if (point.x < x_intersection) {
          inside = !inside;
        }
      }
      previous = current;
    }
    return inside;
  }

  [[nodiscard]] static bool inside_forbidden_zone(const SafetyContext& context) noexcept {
    return std::any_of(context.forbidden_zones.begin(), context.forbidden_zones.end(),
                       [&context](const auto& zone) {
                         return point_inside_polygon(context.robot_state.pose.position,
                                                     zone.polygon);
                       });
  }

  [[nodiscard]] static qrics::control::SafeAction base_action(
      const qrics::control::ActionProposal& proposal) {
    qrics::control::SafeAction action{};
    action.action_id = "safe_" + proposal.proposal_id;
    action.source_proposal_id = proposal.proposal_id;
    action.timestamp_ns = proposal.timestamp_ns;
    return action;
  }

  [[nodiscard]] static SafetyEvent make_event(const qrics::control::ActionProposal& proposal,
                                              const SafetyContext& context, Severity severity,
                                              TriggerType trigger_type,
                                              SafetyActionTaken action_taken,
                                              std::string violation) {
    SafetyEvent event{};
    event.event_id = "event_" + proposal.proposal_id;
    event.run_id = context.run_id;
    event.timestamp_ns = proposal.timestamp_ns;
    event.severity = severity;
    event.trigger_type = trigger_type;
    event.violation_list.push_back(std::move(violation));
    event.action_taken = action_taken;
    event.operator_ack = false;
    return event;
  }

  [[nodiscard]] static SafetyEvaluation make_terminal_result(
      const qrics::control::ActionProposal& proposal, const SafetyContext& context,
      qrics::control::SafetyDecision decision, qrics::control::ActionType action_type,
      TriggerType trigger_type, SafetyActionTaken action_taken, std::string reason) {
    SafetyEvaluation evaluation{};
    evaluation.safe_action = base_action(proposal);
    evaluation.safe_action.action_type = action_type;
    evaluation.safe_action.decision = decision;
    evaluation.safe_action.reason = reason;
    evaluation.events.push_back(make_event(proposal, context, Severity::Warning, trigger_type,
                                           action_taken, std::move(reason)));
    return evaluation;
  }

  [[nodiscard]] SafetyEvaluation make_body_velocity_result(
      const qrics::control::ActionProposal& proposal, const SafetyContext& context) const {
    SafetyEvaluation evaluation{};
    evaluation.safe_action = base_action(proposal);
    evaluation.safe_action.action_type = qrics::control::ActionType::BodyVelocity;
    evaluation.safe_action.body_velocity = proposal.desired_body_velocity;
    evaluation.safe_action.yaw_rate_radps = proposal.desired_yaw_rate_radps;
    evaluation.safe_action.decision = qrics::control::SafetyDecision::Accepted;
    evaluation.safe_action.reason = "Action accepted";

    const double speed =
        std::sqrt(proposal.desired_body_velocity.x * proposal.desired_body_velocity.x +
                  proposal.desired_body_velocity.y * proposal.desired_body_velocity.y +
                  proposal.desired_body_velocity.z * proposal.desired_body_velocity.z);

    bool clipped = false;

    if (speed > limits_.max_linear_velocity_mps) {
      const double scale = limits_.max_linear_velocity_mps / speed;
      evaluation.safe_action.body_velocity.x *= scale;
      evaluation.safe_action.body_velocity.y *= scale;
      evaluation.safe_action.body_velocity.z *= scale;
      clipped = true;
    }

    const double clipped_yaw = std::clamp(evaluation.safe_action.yaw_rate_radps,
                                          -limits_.max_yaw_rate_radps, limits_.max_yaw_rate_radps);
    if (clipped_yaw != evaluation.safe_action.yaw_rate_radps) {
      evaluation.safe_action.yaw_rate_radps = clipped_yaw;
      clipped = true;
    }

    if (clipped) {
      evaluation.safe_action.decision = qrics::control::SafetyDecision::Clipped;
      evaluation.safe_action.reason = "Body velocity command was clipped by SafetyLimits";
      evaluation.events.push_back(
          make_event(proposal, context, Severity::Warning, TriggerType::VelocityLimit,
                     SafetyActionTaken::ClipAction, evaluation.safe_action.reason));
    }

    return evaluation;
  }

  [[nodiscard]] static SafetyEvaluation make_direct_safe_action(
      const qrics::control::ActionProposal& proposal) {
    SafetyEvaluation evaluation{};
    evaluation.safe_action = base_action(proposal);
    evaluation.safe_action.action_type = proposal.action_type;
    evaluation.safe_action.joint_commands = proposal.joint_commands;
    evaluation.safe_action.body_velocity = proposal.desired_body_velocity;
    evaluation.safe_action.yaw_rate_radps = proposal.desired_yaw_rate_radps;
    evaluation.safe_action.decision = qrics::control::SafetyDecision::Accepted;
    evaluation.safe_action.reason = "Direct safe action accepted";
    return evaluation;
  }

  SafetyLimits limits_{};
};

}  // namespace qrics::safety