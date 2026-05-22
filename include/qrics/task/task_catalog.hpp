// 任务理解

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

struct NamedWaypoint final {
  std::string alias{};
  Waypoint waypoint{};
};

struct AvoidZoneAlias final {
  std::string alias{};
  std::string zone_id{};
};

// 解析任务前的上下文
struct TaskParseContext final {
  std::string task_id{};
  std::string task_version{"0.1.0"};
  qrics::common::ResourceRef scene_ref{};
  std::vector<NamedWaypoint> named_waypoints{};
  std::vector<AvoidZoneAlias> avoid_zone_aliases{};
  FallbackAction default_fallback_action{FallbackAction::SafeStand};
};

}  // namespace qrics::task