#include <string>

#include "qrics/control/task_executor.hpp"

namespace {

class FakeAdapter final : public qrics::simulation::SimulationAdapter {
 public:
  [[nodiscard]] std::string name() const override {
    return "fake_adapter";
  }
  [[nodiscard]] qrics::simulation::AdapterState state() const override {
    return state_;
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> initialize(
      const qrics::simulation::AdapterConfig& /*config*/) override {
    state_ = qrics::simulation::AdapterState::Initialized;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> load_scene(
      const qrics::scenario::SceneProfile& /*scene_profile*/) override {
    state_ = qrics::simulation::AdapterState::SceneLoaded;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::ObservationPacket> reset() override {
    state_ = qrics::simulation::AdapterState::Running;
    robot_state_ = qrics::simulation::RobotState{};
    robot_state_.stability_state = qrics::simulation::StabilityState::Stable;
    return qrics::common::Result<qrics::simulation::ObservationPacket>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterStepResult> step(
      const qrics::control::SafeAction& action) override {
    ++step_count_;
    last_action_ = action;
    if (action.action_type == qrics::control::ActionType::BodyVelocity) {
      robot_state_.pose.position.x += action.body_velocity.x;
      robot_state_.pose.position.y += action.body_velocity.y;
      robot_state_.pose.position.z += action.body_velocity.z;
    }
    qrics::simulation::AdapterStepResult result{};
    result.robot_state = robot_state_;
    result.state = state_;
    return qrics::common::Result<qrics::simulation::AdapterStepResult>::success(result);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::ObservationPacket> observe()
      const override {
    return qrics::common::Result<qrics::simulation::ObservationPacket>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::RobotState> robot_state() const override {
    return qrics::common::Result<qrics::simulation::RobotState>::success(robot_state_);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> close() override {
    state_ = qrics::simulation::AdapterState::Stopped;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

  [[nodiscard]] int step_count() const noexcept {
    return step_count_;
  }

 private:
  qrics::simulation::AdapterState state_{qrics::simulation::AdapterState::Created};
  qrics::simulation::RobotState robot_state_{};
  qrics::control::SafeAction last_action_{};
  int step_count_{0};
};

[[nodiscard]] qrics::task::TaskGraph make_graph() {
  qrics::task::TaskGraph graph{};
  graph.graph_id = "graph_task_001_0.1.0";
  graph.task_ref = qrics::common::ResourceRef{"task_001", "0.1.0"};
  graph.entry_node_id = "node_1_move_to_A";
  graph.terminal_node_id = "node_terminal_stop";

  qrics::task::TaskNode move{};
  move.node_id = "node_1_move_to_A";
  move.type = qrics::task::TaskNodeType::MoveTo;
  move.target_waypoint_id = "A";
  move.policy_tag = "flat_navigation_policy";

  qrics::task::TaskNode dwell{};
  dwell.node_id = "node_2_dwell_A";
  dwell.type = qrics::task::TaskNodeType::Dwell;
  dwell.target_waypoint_id = "A";
  dwell.policy_tag = "flat_navigation_policy";

  qrics::task::TaskNode stop{};
  stop.node_id = "node_terminal_stop";
  stop.type = qrics::task::TaskNodeType::Stop;

  graph.nodes = {move, dwell, stop};
  graph.edges.push_back(qrics::task::TaskEdge{move.node_id, dwell.node_id, "completed"});
  graph.edges.push_back(qrics::task::TaskEdge{dwell.node_id, stop.node_id, "completed"});
  return graph;
}

[[nodiscard]] qrics::control::TaskExecutorStartRequest make_start_request() {
  qrics::control::TaskExecutorStartRequest request{};
  request.run_id = "run_task_executor";
  request.task_graph = make_graph();
  qrics::control::TaskWaypointContext waypoint{};
  waypoint.waypoint_id = "A";
  waypoint.pose.position.x = 1.0;
  waypoint.dwell_time_s = 1.0;
  request.waypoints.push_back(waypoint);
  request.default_policy_ref = qrics::common::ResourceRef{"policy_flat", "0.1.0"};
  request.started_at_ns = 0;
  return request;
}

}  // namespace

int main() {
  FakeAdapter adapter{};
  const auto initialized = adapter.initialize({});
  if (!initialized.ok) {
    return 20;
  }
  const auto reset = adapter.reset();
  if (!reset.ok) {
    return 21;
  }

  qrics::safety::SafetyLimits limits{};
  limits.max_linear_velocity_mps = 1.0;
  limits.max_yaw_rate_radps = 1.0;
  qrics::safety::BasicSafetyShield safety_shield{limits};
  qrics::control::SimpleLocalPlanner planner{};
  qrics::control::RuleBasedPolicyRuntime runtime{planner};
  qrics::control::TaskExecutor executor{adapter, safety_shield, runtime};

  const auto started = executor.start(make_start_request());
  if (!started.ok) {
    return 1;
  }
  if (started.value.run_state != qrics::control::ControlRunState::Running) {
    return 2;
  }
  if (started.value.current_node_id != "node_1_move_to_A") {
    return 3;
  }

  qrics::control::TaskExecutorStepRequest step_request{};
  step_request.safety_context.robot_state.stability_state =
      qrics::simulation::StabilityState::Stable;
  step_request.safety_context.robot_state.risk_score = 0.0;

  qrics::common::TimestampNs now = 0;
  qrics::control::TaskExecutorStepResult last_step{};
  for (int i = 0; i < 10; ++i) {
    now += 1000000000;
    step_request.timestamp_ns = now;
    auto step = executor.step_once(step_request);
    if (!step.ok) {
      return 4;
    }
    last_step = step.value;
    if (last_step.snapshot.run_state == qrics::control::ControlRunState::Succeeded) {
      break;
    }
  }

  if (last_step.snapshot.run_state != qrics::control::ControlRunState::Succeeded) {
    return 5;
  }
  if (last_step.snapshot.completed_node_count != 3) {
    return 6;
  }
  if (adapter.step_count() < 2) {
    return 7;
  }

  FakeAdapter paused_adapter{};
  const auto paused_initialized = paused_adapter.initialize({});
  if (!paused_initialized.ok) {
    return 22;
  }
  const auto paused_reset = paused_adapter.reset();
  if (!paused_reset.ok) {
    return 23;
  }
  qrics::control::TaskExecutor paused_executor{paused_adapter, safety_shield, runtime};
  const auto paused_started = paused_executor.start(make_start_request());
  if (!paused_started.ok) {
    return 8;
  }
  qrics::control::TaskExecutorStepRequest paused_step_request{};
  paused_step_request.timestamp_ns = 1000000000;
  paused_step_request.safety_context.manual_override_active = true;
  auto paused_step = paused_executor.step_once(paused_step_request);
  if (!paused_step.ok) {
    return 9;
  }
  if (paused_step.value.snapshot.run_state != qrics::control::ControlRunState::Paused) {
    return 10;
  }
  if (paused_step.value.adapter_stepped) {
    return 11;
  }
  if (paused_step.value.safety_events.empty()) {
    return 12;
  }

  return 0;
}