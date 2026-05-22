// 中文规则解析器

#include <algorithm>
#include <cstddef>
#include <regex>
#include <string>
#include <utility>
#include <vector>

#include "qrics/task/task_parser.hpp"

namespace qrics::task {

namespace {

struct WaypointMatch final {
  std::size_t position{0U};
  Waypoint waypoint{};
};

[[nodiscard]] bool contains_any(const std::string& text, const std::vector<std::string>& tokens) {
  return std::any_of(tokens.begin(), tokens.end(), [&text](const std::string& token) {
    return text.find(token) != std::string::npos;
  });
}

[[nodiscard]] FallbackAction infer_fallback_action(const std::string& source_text,
                                                   FallbackAction default_action) {
  if (contains_any(source_text, {"重新规划", "重规划", "绕行"})) {
    return FallbackAction::Replan;
  }
  if (contains_any(source_text, {"回到平台", "返回平台", "回到起点", "返回起点", "回家"})) {
    return FallbackAction::ReturnHome;
  }
  if (contains_any(source_text, {"停止", "停车"})) {
    return FallbackAction::Stop;
  }
  return default_action;
}

[[nodiscard]] std::vector<std::string> extract_avoid_zones(const std::string& source_text,
                                                           const TaskParseContext& context) {
  std::vector<std::string> zone_ids{};
  if (!contains_any(source_text, {"避开", "绕开", "不要进入", "禁止进入", "禁行"})) {
    return zone_ids;
  }

  for (const auto& zone_alias : context.avoid_zone_aliases) {
    if (!zone_alias.alias.empty() && source_text.find(zone_alias.alias) != std::string::npos) {
      zone_ids.push_back(zone_alias.zone_id);
    }
  }
  return zone_ids;
}

[[nodiscard]] double extract_dwell_time_s(const std::string& source_text) {
  const std::regex dwell_regex{"(?:驻留|停留|等待|待命)[^0-9一二三四五六七八九十]*([0-9]+)\\s*秒"};
  std::smatch match{};
  if (std::regex_search(source_text, match, dwell_regex) && match.size() > 1U) {
    return std::stod(match[1].str());
  }
  return 0.0;
}

[[nodiscard]] std::vector<Waypoint> extract_waypoints(const std::string& source_text,
                                                      const TaskParseContext& context) {
  std::vector<WaypointMatch> matches{};
  for (const auto& named_waypoint : context.named_waypoints) {
    if (named_waypoint.alias.empty()) {
      continue;
    }
    const auto position = source_text.find(named_waypoint.alias);
    if (position != std::string::npos) {
      matches.push_back(WaypointMatch{position, named_waypoint.waypoint});
    }
  }

  std::sort(matches.begin(), matches.end(), [](const WaypointMatch& lhs, const WaypointMatch& rhs) {
    return lhs.position < rhs.position;
  });

  std::vector<Waypoint> waypoints{};
  waypoints.reserve(matches.size());
  for (const auto& match : matches) {
    waypoints.push_back(match.waypoint);
  }

  if (!waypoints.empty()) {
    const double dwell_time_s = extract_dwell_time_s(source_text);
    waypoints.back().dwell_time_s = dwell_time_s;
  }
  return waypoints;
}

[[nodiscard]] std::vector<qrics::common::Error> validate_context(const std::string& source_text,
                                                                 const TaskParseContext& context) {
  std::vector<qrics::common::Error> errors{};
  if (source_text.empty()) {
    errors.push_back(qrics::common::Error{"TASK_TEXT_EMPTY", "Task source text must not be empty"});
  }
  if (context.task_id.empty()) {
    errors.push_back(
        qrics::common::Error{"TASK_ID_EMPTY", "TaskParseContext.task_id must not be empty"});
  }
  if (context.scene_ref.id.empty() || context.scene_ref.version.empty()) {
    errors.push_back(
        qrics::common::Error{"SCENE_REF_EMPTY", "TaskParseContext.scene_ref must not be empty"});
  }
  if (context.named_waypoints.empty()) {
    errors.push_back(qrics::common::Error{"WAYPOINT_CATALOG_EMPTY",
                                          "TaskParseContext.named_waypoints must not be empty"});
  }
  return errors;
}

}  // namespace

qrics::common::Result<TaskScript> RuleBasedChineseTaskParser::parse(
    const std::string& source_text, const TaskParseContext& context) const {
  auto errors = validate_context(source_text, context);
  if (!errors.empty()) {
    return qrics::common::Result<TaskScript>::failure(std::move(errors));
  }

  TaskScript task_script{};
  task_script.task_id = context.task_id;
  task_script.version = context.task_version;
  task_script.scene_ref = context.scene_ref;
  task_script.source_text = source_text;
  task_script.goal = source_text;
  task_script.parser_version = "rule-based-zh-0.1.0";
  task_script.status = TaskStatus::Parsed;
  task_script.fallback_action = infer_fallback_action(source_text, context.default_fallback_action);
  task_script.constraints.avoid_zone_ids = extract_avoid_zones(source_text, context);
  task_script.waypoints = extract_waypoints(source_text, context);

  if (task_script.waypoints.empty()) {
    return qrics::common::Result<TaskScript>::failure({qrics::common::Error{
        "NO_WAYPOINT_MATCHED", "No named waypoint alias was matched in task text"}});
  }

  return qrics::common::Result<TaskScript>::success(std::move(task_script));
}

}  // namespace qrics::task