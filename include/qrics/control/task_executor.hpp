// 任务执行器占位实现接口

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/control_loop.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/control/policy_runtime.hpp"
#include "qrics/safety/safety_shield.hpp"
#include "qrics/simulation/simulation_adapter.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct TaskExecutorStartRequest final {
  std::string run_id{};
  qrics::task::TaskGraph task_graph{};
  std::vector<TaskWaypointContext> waypoints{};
  qrics::common::ResourceRef default_policy_ref{};
  qrics::common::TimestampNs started_at_ns{0};
};

struct TaskExecutorStepRequest final {
  qrics::safety::SafetyContext safety_context{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct TaskExecutorStepResult final {
  TaskExecutionSnapshot snapshot{};
  bool control_loop_invoked{false};
  bool adapter_stepped{false};
  std::vector<qrics::safety::SafetyEvent> safety_events{};
};

class TaskExecutor final {
 public:
  TaskExecutor(qrics::simulation::SimulationAdapter& adapter,
               const qrics::safety::SafetyShield& safety_shield,
               const PolicyRuntime& policy_runtime);

  [[nodiscard]] qrics::common::Result<TaskExecutionSnapshot> start(
      const TaskExecutorStartRequest& request);

  [[nodiscard]] qrics::common::Result<TaskExecutorStepResult> step_once(
      const TaskExecutorStepRequest& request);

  [[nodiscard]] const TaskExecutionSnapshot& snapshot() const noexcept {
    return snapshot_;
  }

 private:
  qrics::simulation::SimulationAdapter& adapter_;
  ControlLoop control_loop_;
  const PolicyRuntime& policy_runtime_;
  TaskExecutionSnapshot snapshot_{};
  std::vector<TaskWaypointContext> waypoints_{};
  qrics::common::ResourceRef default_policy_ref_{};
};

}  // namespace qrics::control