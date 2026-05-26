// 内存任务会话存储

#include <algorithm>
#include <string>
#include <utility>

#include "qrics/task/task_session_store.hpp"

namespace qrics::task {

namespace {

[[nodiscard]] qrics::common::Result<TaskSession> fail(const std::string& code,
                                                      const std::string& message) {
  return qrics::common::Result<TaskSession>::failure({qrics::common::Error{code, message}});
}

}  // namespace

qrics::common::Result<TaskSession> InMemoryTaskSessionStore::upsert(TaskSession session) {
  auto existing = std::find_if(sessions_.begin(), sessions_.end(), [&session](const auto& item) {
    return item.task_id == session.task_id;
  });

  if (existing == sessions_.end()) {
    sessions_.push_back(std::move(session));
    return qrics::common::Result<TaskSession>::success(sessions_.back());
  }

  *existing = std::move(session);
  return qrics::common::Result<TaskSession>::success(*existing);
}

qrics::common::Result<TaskSession> InMemoryTaskSessionStore::find(
    const std::string& task_id) const {
  const auto existing =
      std::find_if(sessions_.begin(), sessions_.end(),
                   [&task_id](const auto& item) { return item.task_id == task_id; });

  if (existing == sessions_.end()) {
    return fail("TASK_SESSION_NOT_FOUND", "Task session does not exist: " + task_id);
  }

  return qrics::common::Result<TaskSession>::success(*existing);
}

}  // namespace qrics::task