// 任务会话存储接口

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/task_lifecycle.hpp"

namespace qrics::task {

class TaskSessionStore {
 public:
  virtual ~TaskSessionStore() = default;

  [[nodiscard]] virtual qrics::common::Result<TaskSession> upsert(TaskSession session) = 0;
  [[nodiscard]] virtual qrics::common::Result<TaskSession> find(
      const std::string& task_id) const = 0;
};

class InMemoryTaskSessionStore final : public TaskSessionStore {
 public:
  [[nodiscard]] qrics::common::Result<TaskSession> upsert(TaskSession session) override;
  [[nodiscard]] qrics::common::Result<TaskSession> find(const std::string& task_id) const override;

 private:
  std::vector<TaskSession> sessions_{};
};

}  // namespace qrics::task