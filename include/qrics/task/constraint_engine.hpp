// 任务理解

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::task {

enum class ConstraintConclusion : std::uint8_t { Accepted, Rejected, ReplanRequired };

struct ConstraintCheckResult final {
  ConstraintConclusion conclusion{ConstraintConclusion::Rejected};
  std::vector<std::string> conflict_list{};
  std::vector<std::string> clipped_fields{};
  bool replan_required{false};
  std::string rule_version{"task-constraint-rules-0.1.0"};
};

class ConstraintEngine {
 public:
  virtual ~ConstraintEngine() = default;

  [[nodiscard]] virtual qrics::common::Result<ConstraintCheckResult> check(
      const TaskScript& task_script, const qrics::scenario::SceneProfile& scene_profile) const = 0;
};

// 任务约束检查器
class BasicTaskConstraintEngine final : public ConstraintEngine {
 public:
  [[nodiscard]] qrics::common::Result<ConstraintCheckResult> check(
      const TaskScript& task_script,
      const qrics::scenario::SceneProfile& scene_profile) const override;
};

}  // namespace qrics::task