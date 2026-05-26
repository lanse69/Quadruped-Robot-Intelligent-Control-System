// 完整任务理解流水线

#include "qrics/task/task_understanding_pipeline.hpp"

#include <utility>

namespace qrics::task {

namespace {

[[nodiscard]] std::vector<qrics::common::Error> conflicts_to_errors(
    const ConstraintCheckResult& constraint_result) {
  std::vector<qrics::common::Error> errors{};
  errors.reserve(constraint_result.conflict_list.size() + constraint_result.clipped_fields.size());
  for (const auto& conflict : constraint_result.conflict_list) {
    errors.emplace_back(qrics::common::Error{"TASK_CONSTRAINT_CONFLICT", conflict});
  }
  for (const auto& clipped_field : constraint_result.clipped_fields) {
    errors.emplace_back(qrics::common::Error{"TASK_CONSTRAINT_REPLAN_REQUIRED", clipped_field});
  }
  return errors;
}

}  // namespace

TaskUnderstandingPipeline::TaskUnderstandingPipeline(const TaskParser& parser,
                                                     const ConstraintEngine& constraint_engine,
                                                     const PolicySelector& policy_selector,
                                                     const TaskGraphPlanner& task_graph_planner,
                                                     const ExplanationService& explanation_service)
    : parser_(parser),
      constraint_engine_(constraint_engine),
      policy_selector_(policy_selector),
      task_graph_planner_(task_graph_planner),
      explanation_service_(explanation_service) {}

qrics::common::Result<TaskUnderstandingResult> TaskUnderstandingPipeline::understand(
    const std::string& source_text, const TaskParseContext& context,
    const qrics::scenario::SceneProfile& scene_profile,
    const std::vector<PolicyCandidate>& policy_candidates) const {
  auto parsed = parser_.parse(source_text, context);
  if (!parsed.ok) {
    return qrics::common::Result<TaskUnderstandingResult>::failure(parsed.errors);
  }

  TaskScript task_script = parsed.value;
  task_script.status = TaskStatus::Validating;

  auto constraint_result = constraint_engine_.check(task_script, scene_profile);
  if (!constraint_result.ok) {
    return qrics::common::Result<TaskUnderstandingResult>::failure(constraint_result.errors);
  }
  if (constraint_result.value.conclusion != ConstraintConclusion::Accepted) {
    return qrics::common::Result<TaskUnderstandingResult>::failure(
        conflicts_to_errors(constraint_result.value));
  }

  std::vector<PolicySelection> policy_selections{};
  policy_selections.reserve(task_script.waypoints.size());
  for (const auto& waypoint : task_script.waypoints) {
    auto selection = policy_selector_.select(TaskNodeType::MoveTo, waypoint, policy_candidates);
    if (!selection.ok) {
      return qrics::common::Result<TaskUnderstandingResult>::failure(selection.errors);
    }
    policy_selections.push_back(selection.value);
  }

  auto graph = task_graph_planner_.plan(task_script, policy_selections);
  if (!graph.ok) {
    return qrics::common::Result<TaskUnderstandingResult>::failure(graph.errors);
  }

  auto preview = explanation_service_.make_preview(task_script, graph.value,
                                                   constraint_result.value, policy_selections);
  if (!preview.ok) {
    return qrics::common::Result<TaskUnderstandingResult>::failure(preview.errors);
  }

  task_script.status = TaskStatus::PreviewReady;

  TaskUnderstandingResult result{};
  result.task_script = std::move(task_script);
  result.constraint_result = constraint_result.value;
  result.policy_selections = std::move(policy_selections);
  result.task_graph = graph.value;
  result.execution_preview = preview.value;
  return qrics::common::Result<TaskUnderstandingResult>::success(std::move(result));
}

}  // namespace qrics::task