// 局部规划接口与占位实现声明

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct LocalPlanRequest final {
  qrics::task::TaskNode task_node{};
  TaskWaypointContext target{};
  qrics::simulation::RobotState robot_state{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct LocalPlan final {
  ActionProposal proposal{};
  bool target_reached{false};
  std::string reason{};
};

class LocalPlanner {
 public:
  virtual ~LocalPlanner() = default;

  [[nodiscard]] virtual qrics::common::Result<LocalPlan> plan(
      const LocalPlanRequest& request) const = 0;
};

class SimpleLocalPlanner final : public LocalPlanner {
 public:
  [[nodiscard]] qrics::common::Result<LocalPlan> plan(
      const LocalPlanRequest& request) const override;

 private:
  double target_tolerance_m_{0.15};
  double nominal_speed_mps_{0.5};
};

}  // namespace qrics::control