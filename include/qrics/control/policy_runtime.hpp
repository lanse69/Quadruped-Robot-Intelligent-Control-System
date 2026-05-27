// 策略运行时接口与规则占位实现声明

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/control/local_planner.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct PolicyRuntimeRequest final {
  std::string run_id{};
  qrics::common::ResourceRef policy_ref{};
  qrics::task::TaskNode task_node{};
  TaskWaypointContext target{};
  qrics::simulation::RobotState robot_state{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyRuntimeResult final {
  ActionProposal proposal{};
  bool target_reached{false};
  std::string reason{};
};

class PolicyRuntime {
 public:
  virtual ~PolicyRuntime() = default;

  [[nodiscard]] virtual qrics::common::Result<PolicyRuntimeResult> infer(
      const PolicyRuntimeRequest& request) const = 0;
};

class RuleBasedPolicyRuntime final : public PolicyRuntime {
 public:
  explicit RuleBasedPolicyRuntime(const LocalPlanner& local_planner);

  [[nodiscard]] qrics::common::Result<PolicyRuntimeResult> infer(
      const PolicyRuntimeRequest& request) const override;

 private:
  const LocalPlanner& local_planner_;
};

}  // namespace qrics::control