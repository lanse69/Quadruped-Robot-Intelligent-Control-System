// 安全事件与人工接管模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::safety {

enum class Severity : std::uint8_t { Info, Warning, Error, Critical };

enum class TriggerType : std::uint8_t {
  None,
  OrientationLimit,
  VelocityLimit,
  CollisionRisk,
  ForbiddenZone,
  ActionLimit,
  EmergencyStop,
  ManualOverride,
  PolicyInvalid,
  ObservationMissing
};

enum class SafetyActionTaken : std::uint8_t {
  None,
  ClipAction,
  Stop,
  SafeStand,
  Replan,
  ManualControl
};

struct SafetyEvent final {
  std::string event_id{};
  std::string run_id{};
  qrics::common::TimestampNs timestamp_ns{0};
  Severity severity{Severity::Info};
  TriggerType trigger_type{TriggerType::None};
  std::vector<std::string> violation_list{};
  SafetyActionTaken action_taken{SafetyActionTaken::None};
  bool operator_ack{false};
  qrics::common::ResourceRef keyframe_ref{};
};

enum class OverrideCommandType : std::uint8_t {
  Pause,
  Resume,
  EmergencyStop,
  SafeStand,
  ManualControl
};

struct OverrideCommand final {
  std::string command_id{};
  std::string operator_id{};
  OverrideCommandType command_type{OverrideCommandType::Pause};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
  int priority{0};
};

}  // namespace qrics::safety