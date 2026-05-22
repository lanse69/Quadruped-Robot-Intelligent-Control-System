// 执行预览生成器

#include <sstream>
#include <string>
#include <utility>

#include "qrics/task/execution_preview.hpp"

namespace qrics::task {

namespace {

[[nodiscard]] std::string join_policy_reasons(const std::vector<PolicySelection>& selections) {
  std::ostringstream stream{};
  for (const auto& selection : selections) {
    if (stream.tellp() > 0) {
      stream << "; ";
    }
    stream << selection.policy_tag << " -> " << selection.reason;
  }
  return stream.str();
}

[[nodiscard]] std::string make_risk_summary(const ConstraintCheckResult& constraint_result) {
  if (!constraint_result.conflict_list.empty()) {
    std::ostringstream stream{};
    stream << "Rejected conflicts: ";
    for (const auto& conflict : constraint_result.conflict_list) {
      stream << conflict << "; ";
    }
    return stream.str();
  }
  if (!constraint_result.clipped_fields.empty()) {
    std::ostringstream stream{};
    stream << "Replan or clipping required for fields: ";
    for (const auto& field : constraint_result.clipped_fields) {
      stream << field << "; ";
    }
    return stream.str();
  }
  return "No blocking constraint conflict detected by basic rule set";
}

}  // namespace

qrics::common::Result<ExecutionPreview> BasicExplanationService::make_preview(
    const TaskScript& task_script, const TaskGraph& task_graph,
    const ConstraintCheckResult& constraint_result,
    const std::vector<PolicySelection>& selections) const {
  if (task_graph.graph_id.empty()) {
    return qrics::common::Result<ExecutionPreview>::failure(
        {qrics::common::Error{"GRAPH_ID_EMPTY", "TaskGraph.graph_id must not be empty"}});
  }

  ExecutionPreview preview{};
  preview.preview_id = "preview_" + task_script.task_id + "_" + task_script.version;
  preview.task_ref = qrics::common::ResourceRef{task_script.task_id, task_script.version};
  preview.graph_ref = qrics::common::ResourceRef{task_graph.graph_id, task_script.version};
  preview.selected_policy_reason = join_policy_reasons(selections);
  preview.risk_summary = make_risk_summary(constraint_result);
  preview.operator_action_required = task_script.constraints.require_operator_confirmation;

  return qrics::common::Result<ExecutionPreview>::success(std::move(preview));
}

}  // namespace qrics::task