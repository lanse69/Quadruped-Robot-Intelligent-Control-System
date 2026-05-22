// 任务理解

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/task_script.hpp"
#include "qrics/training/policy_artifact.hpp"

namespace qrics::task {

struct PolicyCandidate final {
  std::string policy_id{};
  std::string version{};
  std::string terrain_tag{"any"};
  std::string task_tag{"move"};
  qrics::training::PolicyStage stage{qrics::training::PolicyStage::Released};
  qrics::training::MetricsDigest metrics_digest{};
  bool risk_flag{false};
  std::string selection_reason{};
};

struct PolicySelection final {
  std::string policy_tag{};
  std::string policy_id{};
  std::string policy_version{};
  std::string reason{};
};

class PolicySelector {
 public:
  virtual ~PolicySelector() = default;

  [[nodiscard]] virtual qrics::common::Result<PolicySelection> select(
      TaskNodeType node_type, const Waypoint& waypoint,
      const std::vector<PolicyCandidate>& candidates) const = 0;
};

// 策略候选选择器
class RuleBasedPolicySelector final : public PolicySelector {
 public:
  [[nodiscard]] qrics::common::Result<PolicySelection> select(
      TaskNodeType node_type, const Waypoint& waypoint,
      const std::vector<PolicyCandidate>& candidates) const override;
};

}  // namespace qrics::task