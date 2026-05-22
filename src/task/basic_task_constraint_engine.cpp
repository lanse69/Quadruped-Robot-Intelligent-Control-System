// 任务约束检查器

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

#include "qrics/task/constraint_engine.hpp"

namespace qrics::task {

namespace {

[[nodiscard]] bool scene_has_zone(const qrics::scenario::SceneProfile& scene_profile,
                                  const std::string& zone_id) {
  return std::any_of(
      scene_profile.forbidden_zones.begin(), scene_profile.forbidden_zones.end(),
      [&zone_id](const qrics::scenario::ForbiddenZone& zone) { return zone.zone_id == zone_id; });
}

}  // namespace

qrics::common::Result<ConstraintCheckResult> BasicTaskConstraintEngine::check(
    const TaskScript& task_script, const qrics::scenario::SceneProfile& scene_profile) const {
  ConstraintCheckResult result{};
  result.conclusion = ConstraintConclusion::Accepted;

  if (task_script.task_id.empty()) {
    result.conflict_list.emplace_back("TaskScript.task_id is empty");
  }
  if (task_script.version.empty()) {
    result.conflict_list.emplace_back("TaskScript.version is empty");
  }
  if (task_script.scene_ref.id.empty() || task_script.scene_ref.version.empty()) {
    result.conflict_list.emplace_back("TaskScript.scene_ref is empty");
  }
  if (task_script.waypoints.empty()) {
    result.conflict_list.emplace_back("TaskScript.waypoints is empty");
  }

  for (const auto& waypoint : task_script.waypoints) {
    if (waypoint.waypoint_id.empty()) {
      result.conflict_list.emplace_back("Waypoint.waypoint_id is empty");
    }
  }

  if (task_script.constraints.max_linear_velocity_mps <= 0.0) {
    result.conflict_list.emplace_back("max_linear_velocity_mps must be positive");
  }
  if (task_script.constraints.max_linear_velocity_mps > 1.0) {
    result.clipped_fields.emplace_back("max_linear_velocity_mps");
  }
  if (task_script.constraints.max_yaw_rate_radps <= 0.0) {
    result.conflict_list.emplace_back("max_yaw_rate_radps must be positive");
  }
  if (task_script.constraints.max_yaw_rate_radps > 1.0) {
    result.clipped_fields.emplace_back("max_yaw_rate_radps");
  }

  if (!scene_profile.scene_id.empty()) {
    for (const auto& zone_id : task_script.constraints.avoid_zone_ids) {
      if (!scene_has_zone(scene_profile, zone_id)) {
        result.conflict_list.emplace_back("Avoid zone does not exist in SceneProfile: " + zone_id);
      }
    }
  }

  if (!result.conflict_list.empty()) {
    result.conclusion = ConstraintConclusion::Rejected;
    result.replan_required = false;
  } else if (!result.clipped_fields.empty()) {
    result.conclusion = ConstraintConclusion::ReplanRequired;
    result.replan_required = true;
  }

  return qrics::common::Result<ConstraintCheckResult>::success(std::move(result));
}

}  // namespace qrics::task