// 任务理解

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/constraint_engine.hpp"
#include "qrics/task/policy_selector.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

struct ExecutionPreview final {
  std::string preview_id{};
  qrics::common::ResourceRef task_ref{};
  qrics::common::ResourceRef graph_ref{};
  std::string selected_policy_reason{};
  std::string risk_summary{};
  bool operator_action_required{true};
  std::string preview_version{"0.1.0"};
};

class ExplanationService {
 public:
  virtual ~ExplanationService() = default;
  [[nodiscard]] virtual qrics::common::Result<ExecutionPreview> make_preview(
      const TaskScript& task_script, const TaskGraph& task_graph,
      const ConstraintCheckResult& constraint_result,
      const std::vector<PolicySelection>& selections) const = 0;
};

// 执行预览生成器
class BasicExplanationService final : public ExplanationService {
 public:
  [[nodiscard]] qrics::common::Result<ExecutionPreview> make_preview(
      const TaskScript& task_script, const TaskGraph& task_graph,
      const ConstraintCheckResult& constraint_result,
      const std::vector<PolicySelection>& selections) const override;
};

}  // namespace qrics::task