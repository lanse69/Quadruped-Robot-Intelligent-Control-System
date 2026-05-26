// 任务理解流水线

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/task/constraint_engine.hpp"
#include "qrics/task/execution_preview.hpp"
#include "qrics/task/policy_selector.hpp"
#include "qrics/task/task_catalog.hpp"
#include "qrics/task/task_graph_planner.hpp"
#include "qrics/task/task_parser.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

struct TaskUnderstandingResult final {
  TaskScript task_script{};
  ConstraintCheckResult constraint_result{};
  std::vector<PolicySelection> policy_selections{};
  TaskGraph task_graph{};
  ExecutionPreview execution_preview{};
};

class TaskUnderstandingPipeline final {
 public:
  TaskUnderstandingPipeline(const TaskParser& parser, const ConstraintEngine& constraint_engine,
                            const PolicySelector& policy_selector,
                            const TaskGraphPlanner& task_graph_planner,
                            const ExplanationService& explanation_service);

  [[nodiscard]] qrics::common::Result<TaskUnderstandingResult> understand(
      const std::string& source_text, const TaskParseContext& context,
      const qrics::scenario::SceneProfile& scene_profile,
      const std::vector<PolicyCandidate>& policy_candidates) const;

 private:
  const TaskParser& parser_;
  const ConstraintEngine& constraint_engine_;
  const PolicySelector& policy_selector_;
  const TaskGraphPlanner& task_graph_planner_;
  const ExplanationService& explanation_service_;
};

}  // namespace qrics::task