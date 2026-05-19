// 实验运行记录

#pragma once

#include <cstdint>
#include <string>

#include "qrics/common/types.hpp"

namespace qrics::experiment {

enum class ExperimentStatus : std::uint8_t {
  Pending,
  Running,
  Succeeded,
  Failed,
  Cancelled,
  Archived
};

enum class ExperimentType : std::uint8_t { TaskExecution, Training, Evaluation, Replay };

struct ExperimentRun final {
  std::string run_id{};
  ExperimentType type{ExperimentType::TaskExecution};
  qrics::common::ResourceRef scene_ref{};
  qrics::common::ResourceRef policy_ref{};
  std::string config_hash{};
  ExperimentStatus status{ExperimentStatus::Pending};
  qrics::common::ResourceRef metric_ref{};
  qrics::common::ResourceRef replay_ref{};
  qrics::common::TimestampNs started_at_ns{0};
  qrics::common::TimestampNs finished_at_ns{0};
};

}  // namespace qrics::experiment