// 任务理解

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/task/task_catalog.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

class TaskParser {
 public:
  virtual ~TaskParser() = default;

  [[nodiscard]] virtual qrics::common::Result<TaskScript> parse(
      const std::string& source_text, const TaskParseContext& context) const = 0;
};

// 中文规则解析器
class RuleBasedChineseTaskParser final : public TaskParser {
 public:
  [[nodiscard]] qrics::common::Result<TaskScript> parse(
      const std::string& source_text, const TaskParseContext& context) const override;
};

}  // namespace qrics::task