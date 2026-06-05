// 恢复控制器：将不稳定、跌倒和高风险状态转换为受控恢复动作建议

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct RecoveryControllerConfig final {
  double recovery_risk_threshold{0.65};
  double stand_still_risk_threshold{0.45};
};

struct RecoveryRequest final {
  qrics::task::TaskNode task_node{};
  qrics::simulation::RobotState robot_state{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct RecoveryDecision final {
  ActionProposal proposal{};
  bool recovery_required{false};
  bool terminal_recovery{false};
  std::string reason{};
};

class RecoveryController {
 public:
  virtual ~RecoveryController() = default;

  [[nodiscard]] virtual RecoveryDecision evaluate(const RecoveryRequest& request) const = 0;
};

class StabilityRecoveryController final : public RecoveryController {
 public:
  explicit StabilityRecoveryController(RecoveryControllerConfig config = {});

  [[nodiscard]] RecoveryDecision evaluate(const RecoveryRequest& request) const override;

 private:
  RecoveryControllerConfig config_{};
};

}  // namespace qrics::control