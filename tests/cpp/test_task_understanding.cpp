#include <string>
#include <vector>

#include "qrics/task/task_orchestrator.hpp"

namespace {

[[nodiscard]] qrics::task::Waypoint make_waypoint(const std::string& waypoint_id,
                                                  const std::string& terrain_hint) {
  qrics::task::Waypoint waypoint{};
  waypoint.waypoint_id = waypoint_id;
  waypoint.terrain_hint = terrain_hint;
  return waypoint;
}

[[nodiscard]] qrics::task::TaskParseContext make_context() {
  qrics::task::TaskParseContext context{};
  context.task_id = "task_zh_001";
  context.task_version = "0.1.0";
  context.scene_ref = qrics::common::ResourceRef{"scene_mixed", "0.1.0"};
  context.named_waypoints = {
      qrics::task::NamedWaypoint{"A", make_waypoint("checkpoint_a", "flat")},
      qrics::task::NamedWaypoint{"B", make_waypoint("checkpoint_b", "gravel")},
      qrics::task::NamedWaypoint{"平台", make_waypoint("home_platform", "flat")}};
  context.avoid_zone_aliases = {qrics::task::AvoidZoneAlias{"低摩擦区", "zone_low_friction"}};
  context.default_fallback_action = qrics::task::FallbackAction::SafeStand;
  return context;
}

[[nodiscard]] qrics::scenario::SceneProfile make_scene() {
  qrics::scenario::SceneProfile scene{};
  scene.scene_id = "scene_mixed";
  scene.version = "0.1.0";

  qrics::scenario::ForbiddenZone forbidden_zone{};
  forbidden_zone.zone_id = "zone_low_friction";
  scene.forbidden_zones.push_back(forbidden_zone);
  return scene;
}

[[nodiscard]] std::vector<qrics::task::PolicyCandidate> make_policy_candidates() {
  qrics::task::PolicyCandidate flat{};
  flat.policy_id = "flat_nav";
  flat.version = "1.0.0";
  flat.terrain_tag = "flat";
  flat.task_tag = "move";
  flat.stage = qrics::training::PolicyStage::Released;
  flat.selection_reason = "flat terrain navigation policy is released";

  qrics::task::PolicyCandidate gravel{};
  gravel.policy_id = "gravel_nav";
  gravel.version = "1.0.0";
  gravel.terrain_tag = "gravel";
  gravel.task_tag = "move";
  gravel.stage = qrics::training::PolicyStage::Baseline;
  gravel.selection_reason = "gravel baseline policy matches terrain hint";

  qrics::task::PolicyCandidate draft{};
  draft.policy_id = "draft_nav";
  draft.version = "0.1.0";
  draft.terrain_tag = "flat";
  draft.task_tag = "move";
  draft.stage = qrics::training::PolicyStage::Draft;

  return {flat, gravel, draft};
}

}  // namespace

int main() {
  qrics::task::RuleBasedChineseTaskParser parser{};
  qrics::task::BasicTaskConstraintEngine constraint_engine{};
  qrics::task::RuleBasedPolicySelector policy_selector{};
  qrics::task::SequentialTaskGraphPlanner planner{};
  qrics::task::BasicExplanationService explanation_service{};
  qrics::task::TaskUnderstandingPipeline pipeline{parser, constraint_engine, policy_selector,
                                                  planner, explanation_service};

  const auto result =
      pipeline.understand("避开低摩擦区，先巡检A，再巡检B并驻留3秒，最后回到平台待命",
                          make_context(), make_scene(), make_policy_candidates());
  if (!result.ok) {
    return 1;
  }
  if (result.value.task_script.status != qrics::task::TaskStatus::PreviewReady) {
    return 2;
  }
  if (result.value.task_script.waypoints.size() != 3U) {
    return 3;
  }
  if (result.value.task_script.constraints.avoid_zone_ids.size() != 1U) {
    return 4;
  }
  if (result.value.task_script.fallback_action != qrics::task::FallbackAction::ReturnHome) {
    return 5;
  }
  if (result.value.task_script.waypoints[2].dwell_time_s != 3.0) {
    return 6;
  }
  if (result.value.policy_selections.size() != 3U) {
    return 7;
  }
  if (result.value.policy_selections[1].policy_id != "gravel_nav") {
    return 8;
  }
  if (result.value.task_graph.entry_node_id.empty() ||
      result.value.task_graph.terminal_node_id.empty()) {
    return 9;
  }
  if (result.value.execution_preview.selected_policy_reason.empty()) {
    return 10;
  }

  const auto rejected =
      pipeline.understand("去未知点", make_context(), make_scene(), make_policy_candidates());
  if (rejected.ok) {
    return 11;
  }

  auto invalid_scene = make_scene();
  invalid_scene.forbidden_zones.clear();
  const auto conflict = pipeline.understand("避开低摩擦区，巡检A", make_context(), invalid_scene,
                                            make_policy_candidates());
  if (conflict.ok) {
    return 12;
  }

  return 0;
}