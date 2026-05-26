// 任务编排应用服务接口

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/task/task_catalog.hpp"
#include "qrics/task/task_session_store.hpp"
#include "qrics/task/task_understanding_pipeline.hpp"

namespace qrics::task {

struct TaskSubmissionRequest final {
  std::string source_text{};
  TaskParseContext parse_context{};
  qrics::scenario::SceneProfile scene_profile{};
  std::vector<PolicyCandidate> policy_candidates{};
  std::string operator_id{"operator"};
  qrics::common::TimestampNs submitted_at_ns{0};
};

struct TaskConfirmationRequest final {
  std::string task_id{};
  std::string operator_id{"operator"};
  qrics::common::TimestampNs confirmed_at_ns{0};
};

struct TaskHandoffRequest final {
  std::string task_id{};
  std::string operator_id{"operator"};
  qrics::common::TimestampNs handed_off_at_ns{0};
};

struct TaskCancellationRequest final {
  std::string task_id{};
  std::string operator_id{"operator"};
  std::string reason{};
  qrics::common::TimestampNs cancelled_at_ns{0};
};

class TaskOrchestratorService final {
 public:
  TaskOrchestratorService(const TaskUnderstandingPipeline& pipeline, TaskSessionStore& store);

  [[nodiscard]] qrics::common::Result<TaskSession> submit(
      const TaskSubmissionRequest& request) const;
  [[nodiscard]] qrics::common::Result<TaskSession> confirm(
      const TaskConfirmationRequest& request) const;
  [[nodiscard]] qrics::common::Result<TaskSession> handoff(const TaskHandoffRequest& request) const;
  [[nodiscard]] qrics::common::Result<TaskSession> cancel(
      const TaskCancellationRequest& request) const;

 private:
  const TaskUnderstandingPipeline& pipeline_;
  TaskSessionStore& store_;
};

}  // namespace qrics::task