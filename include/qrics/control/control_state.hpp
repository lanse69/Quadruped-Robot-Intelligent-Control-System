// 控制运行状态模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

enum class ControlRunState : std::uint8_t {
  Created,
  Running,
  Paused,
  Succeeded,
  Failed,
  Cancelled
};

enum class TaskNodeExecutionState : std::uint8_t { Pending, Running, Succeeded, Failed, Skipped };

struct TaskWaypointContext final {
  std::string waypoint_id{};
  qrics::common::Pose pose{};
  double dwell_time_s{0.0};
};

struct TaskNodeExecutionSnapshot final {
  std::string node_id{};
  qrics::task::TaskNodeType node_type{qrics::task::TaskNodeType::MoveTo};
  TaskNodeExecutionState state{TaskNodeExecutionState::Pending};
  std::string reason{};
  qrics::common::TimestampNs started_at_ns{0};
  qrics::common::TimestampNs finished_at_ns{0};
};

struct TaskExecutionSnapshot final {
  std::string run_id{};
  qrics::common::ResourceRef task_ref{};
  ControlRunState run_state{ControlRunState::Created};
  qrics::task::TaskGraph task_graph{};
  std::string current_node_id{};
  std::vector<TaskNodeExecutionSnapshot> node_snapshots{};
  qrics::simulation::RobotState last_robot_state{};
  std::string reason{};
  qrics::common::TimestampNs started_at_ns{0};
  qrics::common::TimestampNs updated_at_ns{0};
  int completed_node_count{0};
  int control_step_count{0};
};

}  // namespace qrics::control