// 任务脚本与任务图

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::task {

enum class TaskStatus : std::uint8_t {
  Draft,
  Parsed,
  Validating,
  Rejected,
  Planned,
  PreviewReady,
  Confirmed,
  HandedOff,
  Superseded
};

enum class FallbackAction : std::uint8_t { Stop, SafeStand, Replan, ReturnHome };

struct TaskConstraint final {
  std::vector<std::string> avoid_zone_ids{};
  double max_linear_velocity_mps{1.0};
  double max_yaw_rate_radps{1.0};
  double timeout_s{300.0};
  bool require_operator_confirmation{true};
};

struct Waypoint final {
  std::string waypoint_id{};
  qrics::common::Pose pose{};
  double dwell_time_s{0.0};
  std::string terrain_hint{};
};

struct TaskScript final {
  std::string task_id{};
  std::string version{};
  qrics::common::ResourceRef scene_ref{};
  std::string source_text{};
  std::string goal{};
  std::vector<Waypoint> waypoints{};
  TaskConstraint constraints{};
  FallbackAction fallback_action{FallbackAction::SafeStand};
  std::string parser_version{"manual"};
  TaskStatus status{TaskStatus::Draft};
};

enum class TaskNodeType : std::uint8_t { MoveTo, Dwell, Inspect, ReturnHome, Stop };

struct TaskNode final {
  std::string node_id{};
  TaskNodeType type{TaskNodeType::MoveTo};
  std::string target_waypoint_id{};
  std::string policy_tag{};
  FallbackAction fallback_action{FallbackAction::SafeStand};
};

struct TaskEdge final {
  std::string from_node_id{};
  std::string to_node_id{};
  std::string condition{};
};

struct TaskGraph final {
  std::string graph_id{};
  qrics::common::ResourceRef task_ref{};
  std::vector<TaskNode> nodes{};
  std::vector<TaskEdge> edges{};
  std::string entry_node_id{};
  std::string terminal_node_id{};
  qrics::common::Checksum checksum{};
};

}  // namespace qrics::task