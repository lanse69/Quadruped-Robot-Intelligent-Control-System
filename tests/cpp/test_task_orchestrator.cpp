#include <string>
#include <vector>

#include "qrics/task/task_orchestrator_service.hpp"

namespace {

[[nodiscard]] qrics::task::Waypoint make_waypoint(const std::string& waypoint_id,
                                                  const std::string& terrain_hint) {
  qrics::task::Waypoint waypoint{};
  waypoint.waypoint_id = waypoint_id;
  waypoint.terrain_hint = terrain_hint;
  return waypoint;
}

[[nodiscard]] qrics::task::TaskParseContext make_context(const std::string& task_id) {
  qrics::task::TaskParseContext context{};
  context.task_id = task_id;
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

void add_checkpoint(qrics::scenario::SceneProfile& scene, const std::string& checkpoint_id) {
  qrics::scenario::Checkpoint checkpoint{};
  checkpoint.checkpoint_id = checkpoint_id;
  scene.checkpoints.push_back(checkpoint);
}

[[nodiscard]] qrics::scenario::SceneProfile make_scene() {
  qrics::scenario::SceneProfile scene{};
  scene.scene_id = "scene_mixed";
  scene.version = "0.1.0";
  add_checkpoint(scene, "checkpoint_a");
  add_checkpoint(scene, "checkpoint_b");
  add_checkpoint(scene, "home_platform");

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

  return {flat, gravel};
}

struct SubmissionFixtureInput final {
  std::string task_id{};
  std::string source_text{};
};

[[nodiscard]] qrics::task::TaskSubmissionRequest make_request(const SubmissionFixtureInput& input) {
  qrics::task::TaskSubmissionRequest request{};
  request.source_text = input.source_text;
  request.parse_context = make_context(input.task_id);
  request.scene_profile = make_scene();
  request.policy_candidates = make_policy_candidates();
  request.operator_id = "operator_a";
  request.submitted_at_ns = 1000;
  return request;
}

[[nodiscard]] qrics::task::TaskConfirmationRequest make_confirmation(const std::string& task_id) {
  qrics::task::TaskConfirmationRequest request{};
  request.task_id = task_id;
  request.operator_id = "operator_a";
  request.confirmed_at_ns = 1200;
  return request;
}

[[nodiscard]] qrics::task::TaskHandoffRequest make_handoff(const std::string& task_id) {
  qrics::task::TaskHandoffRequest request{};
  request.task_id = task_id;
  request.operator_id = "operator_a";
  request.handed_off_at_ns = 1300;
  return request;
}

struct CancellationFixtureInput final {
  std::string task_id{};
  std::string reason{};
};

[[nodiscard]] qrics::task::TaskCancellationRequest make_cancellation(
    const CancellationFixtureInput& input) {
  qrics::task::TaskCancellationRequest request{};
  request.task_id = input.task_id;
  request.operator_id = "operator_a";
  request.reason = input.reason;
  request.cancelled_at_ns = 1400;
  return request;
}

[[nodiscard]] qrics::task::TaskOrchestratorService make_service(
    const qrics::task::TaskUnderstandingPipeline& pipeline, qrics::task::TaskSessionStore& store) {
  return qrics::task::TaskOrchestratorService{pipeline, store};
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
  qrics::task::InMemoryTaskSessionStore store{};
  const auto service = make_service(pipeline, store);

  auto submitted = service.submit(
      make_request(SubmissionFixtureInput{"task_orch_001", "巡检A，再巡检B并驻留3秒"}));
  if (!submitted.ok || submitted.value.state != qrics::task::TaskLifecycleState::PreviewReady) {
    return 1;
  }
  if (!submitted.value.has_understanding_result) {
    return 2;
  }
  if (submitted.value.events.size() != 3U) {
    return 3;
  }
  if (submitted.value.events[0].type != qrics::task::TaskLifecycleEventType::Submitted ||
      submitted.value.events[1].type != qrics::task::TaskLifecycleEventType::UnderstandingStarted ||
      submitted.value.events[2].type != qrics::task::TaskLifecycleEventType::PreviewGenerated) {
    return 4;
  }
  if (submitted.value.understanding_result.task_script.waypoints[1].dwell_time_s != 3.0) {
    return 5;
  }

  auto premature_handoff = service.handoff(make_handoff("task_orch_001"));
  if (premature_handoff.ok) {
    return 6;
  }

  auto confirmed = service.confirm(make_confirmation("task_orch_001"));
  if (!confirmed.ok || confirmed.value.state != qrics::task::TaskLifecycleState::Confirmed) {
    return 7;
  }
  if (confirmed.value.understanding_result.task_script.status !=
      qrics::task::TaskStatus::Confirmed) {
    return 8;
  }

  auto handed_off = service.handoff(make_handoff("task_orch_001"));
  if (!handed_off.ok || handed_off.value.state != qrics::task::TaskLifecycleState::HandedOff) {
    return 9;
  }
  if (handed_off.value.understanding_result.task_script.status !=
      qrics::task::TaskStatus::HandedOff) {
    return 10;
  }

  auto cancel_terminal =
      service.cancel(make_cancellation(CancellationFixtureInput{"task_orch_001", "late cancel"}));
  if (cancel_terminal.ok) {
    return 11;
  }

  auto rejected = service.submit(make_request(SubmissionFixtureInput{"task_orch_002", "去未知点"}));
  if (!rejected.ok || rejected.value.state != qrics::task::TaskLifecycleState::Rejected) {
    return 12;
  }
  if (rejected.value.rejection_errors.empty()) {
    return 13;
  }

  auto cancellable = service.submit(make_request(SubmissionFixtureInput{"task_orch_003", "巡检A"}));
  if (!cancellable.ok || cancellable.value.state != qrics::task::TaskLifecycleState::PreviewReady) {
    return 14;
  }
  auto cancelled = service.cancel(
      make_cancellation(CancellationFixtureInput{"task_orch_003", "operator cancelled"}));
  if (!cancelled.ok || cancelled.value.state != qrics::task::TaskLifecycleState::Cancelled) {
    return 15;
  }

  auto missing = service.confirm(make_confirmation("task_missing"));
  if (missing.ok) {
    return 16;
  }

  return 0;
}