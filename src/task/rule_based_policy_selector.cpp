// 策略候选选择器

#include <string>

#include "qrics/task/policy_selector.hpp"

namespace qrics::task {

namespace {

[[nodiscard]] std::string task_tag_for(TaskNodeType node_type) {
  switch (node_type) {
    case TaskNodeType::MoveTo:
      return "move";
    case TaskNodeType::Dwell:
      return "dwell";
    case TaskNodeType::Inspect:
      return "inspect";
    case TaskNodeType::ReturnHome:
      return "return_home";
    case TaskNodeType::Stop:
      return "stop";
  }
  return "move";
}

[[nodiscard]] bool is_executable(qrics::training::PolicyStage stage) {
  return stage == qrics::training::PolicyStage::Released ||
         stage == qrics::training::PolicyStage::Baseline;
}

[[nodiscard]] bool terrain_matches(const std::string& candidate_terrain,
                                   const std::string& terrain_hint) {
  return candidate_terrain.empty() || candidate_terrain == "any" || terrain_hint.empty() ||
         candidate_terrain == terrain_hint;
}

}  // namespace

qrics::common::Result<PolicySelection> RuleBasedPolicySelector::select(
    TaskNodeType node_type, const Waypoint& waypoint,
    const std::vector<PolicyCandidate>& candidates) const {
  const std::string required_task_tag = task_tag_for(node_type);
  for (const auto& candidate : candidates) {
    if (!is_executable(candidate.stage) || candidate.risk_flag) {
      continue;
    }
    if (candidate.task_tag != required_task_tag) {
      continue;
    }
    if (!terrain_matches(candidate.terrain_tag, waypoint.terrain_hint)) {
      continue;
    }

    PolicySelection selection{};
    selection.policy_id = candidate.policy_id;
    selection.policy_version = candidate.version;
    selection.policy_tag = candidate.policy_id + ":" + candidate.version;
    selection.reason = candidate.selection_reason.empty()
                           ? "Selected executable policy matching task and terrain"
                           : candidate.selection_reason;
    return qrics::common::Result<PolicySelection>::success(selection);
  }

  PolicySelection fallback{};
  fallback.policy_id = "placeholder_policy";
  fallback.policy_version = "0.1.0";
  fallback.policy_tag = "placeholder_policy:0.1.0";
  fallback.reason =
      "No released policy matched; use placeholder policy tag for current platform-independent "
      "stage";
  return qrics::common::Result<PolicySelection>::success(fallback);
}

}  // namespace qrics::task