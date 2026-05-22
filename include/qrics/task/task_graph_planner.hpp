// 任务理解

#pragma once

#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/policy_selector.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

class TaskGraphPlanner {
 public:
  virtual ~TaskGraphPlanner() = default;

  [[nodiscard]] virtual qrics::common::Result<TaskGraph> plan(
      const TaskScript& task_script, const std::vector<PolicySelection>& selections) const = 0;
};

// 顺序任务图规划器
class SequentialTaskGraphPlanner final : public TaskGraphPlanner {
 public:
  [[nodiscard]] qrics::common::Result<TaskGraph> plan(
      const TaskScript& task_script, const std::vector<PolicySelection>& selections) const override;
};

}  // namespace qrics::task