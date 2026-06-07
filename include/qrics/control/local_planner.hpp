// 局部规划接口与占位实现声明

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/control/gait_generator.hpp"
#include "qrics/control/obstacle_avoidance.hpp"
#include "qrics/control/path_tracker.hpp"
#include "qrics/control/recovery_controller.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct LocalPlanRequest final {
  qrics::task::TaskNode task_node{};
  TaskWaypointContext target{};
  qrics::simulation::RobotState robot_state{};
  qrics::simulation::ObservationPacket observation{};
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
  PurePursuitPathTracker path_tracker_{};
  StabilityRecoveryController recovery_controller_{};
  SimpleObstacleAvoidance obstacle_avoidance_{};
  TerrainAwareGaitGenerator gait_generator_{};
};

}  // namespace qrics::control