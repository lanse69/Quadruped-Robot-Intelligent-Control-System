// 动作建议与安全动作模型

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

struct ActionProposal final {
  std::string proposal_id{};
  qrics::common::ResourceRef policy_ref{};
  std::string task_node_id{};
  ActionType action_type{ActionType::BodyVelocity};
  std::vector<JointCommand> joint_commands{};
  qrics::common::Vec3 desired_body_velocity{};
  double desired_yaw_rate_radps{0.0};
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
  SafetyDecision decision{SafetyDecision::Rejected};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

}  // namespace qrics::control