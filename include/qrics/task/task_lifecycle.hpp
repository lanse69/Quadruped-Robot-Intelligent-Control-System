// 任务运行状态模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/task_understanding_pipeline.hpp"

namespace qrics::task {

enum class TaskLifecycleState : std::uint8_t {
  Received,
  Understanding,
  PreviewReady,
  Rejected,
  Confirmed,
  HandedOff,
  Cancelled,
  Failed
};

enum class TaskLifecycleEventType : std::uint8_t {
  Submitted,
  UnderstandingStarted,
  PreviewGenerated,
  Rejected,
  Confirmed,
  HandedOff,
  Cancelled,
  Failed
};

struct TaskLifecycleEvent final {
  TaskLifecycleEventType type{TaskLifecycleEventType::Submitted};
  TaskLifecycleState from_state{TaskLifecycleState::Received};
  TaskLifecycleState to_state{TaskLifecycleState::Received};
  std::string task_id{};
  std::string actor_id{};
  std::string reason{};
  qrics::common::TimestampNs occurred_at_ns{0};
};

struct TaskSession final {
  std::string task_id{};
  std::string source_text{};
  TaskLifecycleState state{TaskLifecycleState::Received};
  TaskUnderstandingResult understanding_result{};
  bool has_understanding_result{false};
  bool operator_confirmation_required{true};
  std::vector<TaskLifecycleEvent> events{};
  std::vector<qrics::common::Error> rejection_errors{};
};

}  // namespace qrics::task