// 任务执行器占位实现

#include "qrics/control/task_executor.hpp"

#include <algorithm>
#include <cstdint>
#include <string>
#include <utility>

namespace qrics::control {

namespace {

constexpr qrics::common::TimestampNs kNanosecondsPerSecond{1000000000};

[[nodiscard]] qrics::common::Result<TaskExecutionSnapshot> fail_snapshot(
    const std::string& code, const std::string& message) {
  return qrics::common::Result<TaskExecutionSnapshot>::failure(
      {qrics::common::Error{code, message}});
}

[[nodiscard]] qrics::common::Result<TaskExecutorStepResult> fail_step(const std::string& code,
                                                                      const std::string& message) {
  return qrics::common::Result<TaskExecutorStepResult>::failure(
      {qrics::common::Error{code, message}});
}

[[nodiscard]] const qrics::task::TaskNode* find_node(const qrics::task::TaskGraph& graph,
                                                     const std::string& node_id) {
  const auto found = std::find_if(graph.nodes.begin(), graph.nodes.end(),
                                  [&node_id](const auto& node) { return node.node_id == node_id; });
  if (found == graph.nodes.end()) {
    return nullptr;
  }
  return &(*found);
}

[[nodiscard]] TaskNodeExecutionSnapshot* find_node_snapshot(TaskExecutionSnapshot& snapshot,
                                                            const std::string& node_id) {
  const auto found = std::find_if(
      snapshot.node_snapshots.begin(), snapshot.node_snapshots.end(),
      [&node_id](const auto& node_snapshot) { return node_snapshot.node_id == node_id; });
  if (found == snapshot.node_snapshots.end()) {
    return nullptr;
  }
  return &(*found);
}

[[nodiscard]] const TaskWaypointContext* find_waypoint(
    const std::vector<TaskWaypointContext>& waypoints, const std::string& waypoint_id) {
  const auto found =
      std::find_if(waypoints.begin(), waypoints.end(),
                   [&waypoint_id](const auto& item) { return item.waypoint_id == waypoint_id; });
  if (found == waypoints.end()) {
    return nullptr;
  }
  return &(*found);
}

[[nodiscard]] std::string next_node_id(const qrics::task::TaskGraph& graph,
                                       const std::string& node_id) {
  const auto found =
      std::find_if(graph.edges.begin(), graph.edges.end(),
                   [&node_id](const auto& edge) { return edge.from_node_id == node_id; });
  if (found == graph.edges.end()) {
    return {};
  }
  return found->to_node_id;
}

void finish_node(TaskExecutionSnapshot& snapshot, TaskNodeExecutionSnapshot& node_snapshot,
                 TaskNodeExecutionState state, const std::string& reason,
                 qrics::common::TimestampNs timestamp_ns) {
  if (node_snapshot.state != TaskNodeExecutionState::Succeeded &&
      state == TaskNodeExecutionState::Succeeded) {
    ++snapshot.completed_node_count;
  }
  node_snapshot.state = state;
  node_snapshot.reason = reason;
  node_snapshot.finished_at_ns = timestamp_ns;
  snapshot.updated_at_ns = timestamp_ns;
}

void mark_running_if_needed(TaskNodeExecutionSnapshot& node_snapshot,
                            qrics::common::TimestampNs timestamp_ns) {
  if (node_snapshot.state != TaskNodeExecutionState::Pending) {
    return;
  }
  node_snapshot.state = TaskNodeExecutionState::Running;
  node_snapshot.started_at_ns = timestamp_ns;
}

void advance_after_success(TaskExecutionSnapshot& snapshot,
                           qrics::common::TimestampNs timestamp_ns) {
  const auto next = next_node_id(snapshot.task_graph, snapshot.current_node_id);
  if (next.empty()) {
    snapshot.run_state = ControlRunState::Succeeded;
    snapshot.reason = "Task execution completed";
    snapshot.current_node_id.clear();
    snapshot.updated_at_ns = timestamp_ns;
    return;
  }
  snapshot.current_node_id = next;
  snapshot.updated_at_ns = timestamp_ns;
}

[[nodiscard]] bool should_pause_for_safety(const qrics::safety::SafetyEvaluation& evaluation) {
  const auto decision = evaluation.safe_action.decision;
  if (decision == SafetyDecision::EmergencyStop || decision == SafetyDecision::SafeStand) {
    return true;
  }
  return std::any_of(evaluation.events.begin(), evaluation.events.end(), [](const auto& event) {
    return event.trigger_type == qrics::safety::TriggerType::ManualOverride ||
           event.trigger_type == qrics::safety::TriggerType::EmergencyStop;
  });
}

[[nodiscard]] qrics::common::TimestampNs dwell_duration_ns(double dwell_time_s) noexcept {
  if (dwell_time_s <= 0.0) {
    return 0;
  }
  return static_cast<qrics::common::TimestampNs>(dwell_time_s *
                                                 static_cast<double>(kNanosecondsPerSecond));
}

}  // namespace

TaskExecutor::TaskExecutor(qrics::simulation::SimulationAdapter& adapter,
                           const qrics::safety::SafetyShield& safety_shield,
                           const PolicyRuntime& policy_runtime)
    : adapter_(adapter), control_loop_(adapter, safety_shield), policy_runtime_(policy_runtime) {}

qrics::common::Result<TaskExecutionSnapshot> TaskExecutor::start(
    const TaskExecutorStartRequest& request) {
  if (request.run_id.empty()) {
    return fail_snapshot("RUN_ID_EMPTY", "TaskExecutorStartRequest.run_id must not be empty");
  }
  if (request.task_graph.graph_id.empty() || request.task_graph.entry_node_id.empty()) {
    return fail_snapshot("TASK_GRAPH_INVALID", "TaskGraph graph_id and entry_node_id must be set");
  }
  if (request.task_graph.nodes.empty()) {
    return fail_snapshot("TASK_GRAPH_EMPTY", "TaskGraph must contain at least one node");
  }
  if (find_node(request.task_graph, request.task_graph.entry_node_id) == nullptr) {
    return fail_snapshot("TASK_GRAPH_ENTRY_MISSING",
                         "TaskGraph entry_node_id must reference a node");
  }

  snapshot_ = TaskExecutionSnapshot{};
  snapshot_.run_id = request.run_id;
  snapshot_.task_ref = request.task_graph.task_ref;
  snapshot_.run_state = ControlRunState::Running;
  snapshot_.task_graph = request.task_graph;
  snapshot_.current_node_id = request.task_graph.entry_node_id;
  snapshot_.reason = "Task execution started";
  snapshot_.started_at_ns = request.started_at_ns;
  snapshot_.updated_at_ns = request.started_at_ns;
  waypoints_ = request.waypoints;
  default_policy_ref_ = request.default_policy_ref;

  snapshot_.node_snapshots.reserve(snapshot_.task_graph.nodes.size());
  for (const auto& node : snapshot_.task_graph.nodes) {
    TaskNodeExecutionSnapshot node_snapshot{};
    node_snapshot.node_id = node.node_id;
    node_snapshot.node_type = node.type;
    snapshot_.node_snapshots.push_back(std::move(node_snapshot));
  }

  return qrics::common::Result<TaskExecutionSnapshot>::success(snapshot_);
}

qrics::common::Result<TaskExecutorStepResult> TaskExecutor::step_once(
    const TaskExecutorStepRequest& request) {
  TaskExecutorStepResult result{};
  result.snapshot = snapshot_;

  if (snapshot_.run_state != ControlRunState::Running) {
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::success(std::move(result));
  }

  const auto* node = find_node(snapshot_.task_graph, snapshot_.current_node_id);
  if (node == nullptr) {
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "Current task node is missing";
    snapshot_.updated_at_ns = request.timestamp_ns;
    result.snapshot = snapshot_;
    return fail_step("TASK_NODE_MISSING", snapshot_.reason);
  }

  auto* node_snapshot = find_node_snapshot(snapshot_, node->node_id);
  if (node_snapshot == nullptr) {
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "Current task node snapshot is missing";
    snapshot_.updated_at_ns = request.timestamp_ns;
    result.snapshot = snapshot_;
    return fail_step("TASK_NODE_SNAPSHOT_MISSING", snapshot_.reason);
  }

  mark_running_if_needed(*node_snapshot, request.timestamp_ns);

  auto robot_state = adapter_.robot_state();
  if (!robot_state.ok) {
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "SimulationAdapter::robot_state failed";
    snapshot_.updated_at_ns = request.timestamp_ns;
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::failure(robot_state.errors);
  }
  snapshot_.last_robot_state = robot_state.value;

  const auto* waypoint = find_waypoint(waypoints_, node->target_waypoint_id);
  TaskWaypointContext target{};
  if (waypoint != nullptr) {
    target = *waypoint;
  }

  if ((node->type == qrics::task::TaskNodeType::MoveTo ||
       node->type == qrics::task::TaskNodeType::ReturnHome) &&
      target.waypoint_id.empty()) {
    finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Failed,
                "Target waypoint is missing", request.timestamp_ns);
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "Target waypoint is missing";
    result.snapshot = snapshot_;
    return fail_step("TARGET_WAYPOINT_MISSING", snapshot_.reason);
  }

  PolicyRuntimeRequest runtime_request{};
  runtime_request.run_id = snapshot_.run_id;
  runtime_request.policy_ref = default_policy_ref_;
  runtime_request.task_node = *node;
  runtime_request.target = target;
  runtime_request.robot_state = snapshot_.last_robot_state;
  runtime_request.timestamp_ns = request.timestamp_ns;

  auto runtime_result = policy_runtime_.infer(runtime_request);
  if (!runtime_result.ok) {
    finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Failed, "Policy runtime failed",
                request.timestamp_ns);
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "Policy runtime failed";
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::failure(runtime_result.errors);
  }

  if ((node->type == qrics::task::TaskNodeType::MoveTo ||
       node->type == qrics::task::TaskNodeType::ReturnHome) &&
      runtime_result.value.target_reached) {
    finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Succeeded,
                runtime_result.value.reason, request.timestamp_ns);
    advance_after_success(snapshot_, request.timestamp_ns);
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::success(std::move(result));
  }

  auto safety_context = request.safety_context;
  safety_context.run_id = snapshot_.run_id;
  safety_context.robot_state = snapshot_.last_robot_state;

  result.control_loop_invoked = true;
  auto control_result = control_loop_.step_once(runtime_result.value.proposal, safety_context);
  if (!control_result.ok) {
    finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Failed, "Control loop failed",
                request.timestamp_ns);
    snapshot_.run_state = ControlRunState::Failed;
    snapshot_.reason = "Control loop failed";
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::failure(control_result.errors);
  }

  ++snapshot_.control_step_count;
  result.adapter_stepped = control_result.value.adapter_stepped;
  result.safety_events = control_result.value.safety_evaluation.events;

  if (control_result.value.adapter_stepped) {
    snapshot_.last_robot_state = control_result.value.adapter_step_result.robot_state;
  }

  const auto& evaluation = control_result.value.safety_evaluation;
  if (evaluation.safe_action.decision == SafetyDecision::Rejected) {
    snapshot_.run_state =
        should_pause_for_safety(evaluation) ? ControlRunState::Paused : ControlRunState::Failed;
    snapshot_.reason = evaluation.safe_action.reason;
    node_snapshot->reason = evaluation.safe_action.reason;
    snapshot_.updated_at_ns = request.timestamp_ns;
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::success(std::move(result));
  }

  if (should_pause_for_safety(evaluation)) {
    snapshot_.run_state = ControlRunState::Paused;
    snapshot_.reason = evaluation.safe_action.reason;
    node_snapshot->reason = evaluation.safe_action.reason;
    snapshot_.updated_at_ns = request.timestamp_ns;
    result.snapshot = snapshot_;
    return qrics::common::Result<TaskExecutorStepResult>::success(std::move(result));
  }

  if (node->type == qrics::task::TaskNodeType::Dwell) {
    const auto elapsed_ns = request.timestamp_ns - node_snapshot->started_at_ns;
    const auto target_dwell_ns = dwell_duration_ns(target.dwell_time_s);
    if (elapsed_ns >= target_dwell_ns) {
      finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Succeeded, "Dwell completed",
                  request.timestamp_ns);
      advance_after_success(snapshot_, request.timestamp_ns);
    }
  }

  if (node->type == qrics::task::TaskNodeType::Stop) {
    finish_node(snapshot_, *node_snapshot, TaskNodeExecutionState::Succeeded, "Stop completed",
                request.timestamp_ns);
    advance_after_success(snapshot_, request.timestamp_ns);
  }

  result.snapshot = snapshot_;
  return qrics::common::Result<TaskExecutorStepResult>::success(std::move(result));
}

}  // namespace qrics::control