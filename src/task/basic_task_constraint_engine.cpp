// 任务约束检查器

#include <algorithm>
#include <cstddef>
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

[[nodiscard]] bool scene_has_checkpoint(const qrics::scenario::SceneProfile& scene_profile,
                                        const std::string& checkpoint_id) {
  return std::any_of(scene_profile.checkpoints.begin(), scene_profile.checkpoints.end(),
                     [&checkpoint_id](const qrics::scenario::Checkpoint& checkpoint) {
                       return checkpoint.checkpoint_id == checkpoint_id;
                     });
}

[[nodiscard]] bool contains_duplicate(const std::vector<std::string>& values,
                                      const std::string& value, std::size_t before_index) {
  const auto end = values.begin() + static_cast<std::ptrdiff_t>(before_index);
  return std::find(values.begin(), end, value) != end;
}

void add_task_identity_conflicts(const TaskScript& task_script,
                                 const qrics::scenario::SceneProfile& scene_profile,
                                 ConstraintCheckResult& result) {
  if (task_script.task_id.empty()) {
    result.conflict_list.emplace_back("TaskScript.task_id is empty");
  }
  if (task_script.version.empty()) {
    result.conflict_list.emplace_back("TaskScript.version is empty");
  }
  if (task_script.scene_ref.id.empty() || task_script.scene_ref.version.empty()) {
    result.conflict_list.emplace_back("TaskScript.scene_ref is empty");
  }
  if (!scene_profile.scene_id.empty() && task_script.scene_ref.id != scene_profile.scene_id) {
    result.conflict_list.emplace_back(
        "TaskScript.scene_ref.id does not match SceneProfile.scene_id");
  }
  if (!scene_profile.version.empty() && task_script.scene_ref.version != scene_profile.version) {
    result.conflict_list.emplace_back(
        "TaskScript.scene_ref.version does not match SceneProfile.version");
  }
  if (task_script.goal.empty()) {
    result.conflict_list.emplace_back("TaskScript.goal is empty");
  }
  if (task_script.waypoints.empty()) {
    result.conflict_list.emplace_back("TaskScript.waypoints is empty");
  }
}

void add_waypoint_conflicts(const TaskScript& task_script,
                            const qrics::scenario::SceneProfile& scene_profile,
                            ConstraintCheckResult& result) {
  for (const auto& waypoint : task_script.waypoints) {
    if (waypoint.waypoint_id.empty()) {
      result.conflict_list.emplace_back("Waypoint.waypoint_id is empty");
      continue;
    }
    if (!scene_profile.scene_id.empty() &&
        !scene_has_checkpoint(scene_profile, waypoint.waypoint_id)) {
      result.conflict_list.emplace_back("Waypoint does not exist in SceneProfile.checkpoints: " +
                                        waypoint.waypoint_id);
    }
  }
}

void add_motion_constraint_conflicts(const TaskConstraint& constraints,
                                     ConstraintCheckResult& result) {
  if (constraints.max_linear_velocity_mps <= 0.0) {
    result.conflict_list.emplace_back("max_linear_velocity_mps must be positive");
  }
  if (constraints.max_linear_velocity_mps > 1.0) {
    result.clipped_fields.emplace_back("max_linear_velocity_mps");
  }
  if (constraints.max_yaw_rate_radps <= 0.0) {
    result.conflict_list.emplace_back("max_yaw_rate_radps must be positive");
  }
  if (constraints.max_yaw_rate_radps > 1.0) {
    result.clipped_fields.emplace_back("max_yaw_rate_radps");
  }
  if (constraints.timeout_s <= 0.0) {
    result.conflict_list.emplace_back("timeout_s must be positive");
  }
}

void add_avoid_zone_conflicts(const TaskConstraint& constraints,
                              const qrics::scenario::SceneProfile& scene_profile,
                              ConstraintCheckResult& result) {
  for (std::size_t index = 0U; index < constraints.avoid_zone_ids.size(); ++index) {
    const auto& zone_id = constraints.avoid_zone_ids[index];
    if (zone_id.empty()) {
      result.conflict_list.emplace_back("avoid_zone_id is empty");
      continue;
    }
    if (contains_duplicate(constraints.avoid_zone_ids, zone_id, index)) {
      result.conflict_list.emplace_back("avoid_zone_id is duplicated: " + zone_id);
    }
    if (!scene_profile.scene_id.empty() && !scene_has_zone(scene_profile, zone_id)) {
      result.conflict_list.emplace_back("Avoid zone does not exist in SceneProfile: " + zone_id);
    }
  }
}

void apply_conclusion(ConstraintCheckResult& result) {
  if (!result.conflict_list.empty()) {
    result.conclusion = ConstraintConclusion::Rejected;
    result.replan_required = false;
    return;
  }

  if (!result.clipped_fields.empty()) {
    result.conclusion = ConstraintConclusion::ReplanRequired;
    result.replan_required = true;
  }
}

}  // namespace

qrics::common::Result<ConstraintCheckResult> BasicTaskConstraintEngine::check(
    const TaskScript& task_script, const qrics::scenario::SceneProfile& scene_profile) const {
  ConstraintCheckResult result{};
  result.conclusion = ConstraintConclusion::Accepted;

  add_task_identity_conflicts(task_script, scene_profile, result);
  add_waypoint_conflicts(task_script, scene_profile, result);
  add_motion_constraint_conflicts(task_script.constraints, result);
  add_avoid_zone_conflicts(task_script.constraints, scene_profile, result);
  apply_conclusion(result);

  return qrics::common::Result<ConstraintCheckResult>::success(std::move(result));
}

}  // namespace qrics::task