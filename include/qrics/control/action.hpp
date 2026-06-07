// 动作建议、安全动作与步态提示模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::control {

enum class ActionType : std::uint8_t {
  JointPosition,
  JointVelocity,
  BodyVelocity,
  Stop,
  SafeStand,
  Replan
};

struct JointCommand final {
  std::string joint_name{};
  double target_position_rad{0.0};
  double target_velocity_radps{0.0};
  double target_torque_nm{0.0};
};

enum class GaitType : std::uint8_t { Stand, Crawl, Trot, CautiousTrot, Recovery };

enum class FootPhase : std::uint8_t { Stance, Swing };

struct FootstepTarget final {
  std::string foot_name{};
  FootPhase phase{FootPhase::Stance};
  qrics::common::Vec3 nominal_position_body{};
  qrics::common::Vec3 target_position_body{};
  double phase_in_cycle{0.0};
  double duty_factor{0.0};
};

struct LocomotionHint final {
  bool enabled{false};
  GaitType gait_type{GaitType::Stand};
  std::string gait_name{"stand"};
  double normalized_phase{0.0};
  double step_frequency_hz{0.0};
  double stride_length_m{0.0};
  double lateral_stride_m{0.0};
  double swing_height_m{0.0};
  double duty_factor{1.0};
  double body_height_m{0.35};
  std::vector<FootstepTarget> feet{};
};

struct ActionProposal final {
  std::string proposal_id{};
  qrics::common::ResourceRef policy_ref{};
  std::string task_node_id{};
  ActionType action_type{ActionType::BodyVelocity};
  std::vector<JointCommand> joint_commands{};
  qrics::common::Vec3 desired_body_velocity{};
  double desired_yaw_rate_radps{0.0};
  LocomotionHint locomotion_hint{};
  double confidence{1.0};
  qrics::common::TimestampNs timestamp_ns{0};
};

enum class SafetyDecision : std::uint8_t {
  Accepted,
  Clipped,
  Rejected,
  EmergencyStop,
  SafeStand,
  Replan
};

struct SafeAction final {
  std::string action_id{};
  std::string source_proposal_id{};
  ActionType action_type{ActionType::Stop};
  std::vector<JointCommand> joint_commands{};
  qrics::common::Vec3 body_velocity{};
  double yaw_rate_radps{0.0};
  LocomotionHint locomotion_hint{};
  SafetyDecision decision{SafetyDecision::Rejected};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

}  // namespace qrics::control