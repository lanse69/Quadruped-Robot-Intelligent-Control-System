#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/local_planner.hpp"
#include "qrics/control/policy_runtime.hpp"
#include "qrics/control/task_executor.hpp"
#include "qrics/safety/safety_event.hpp"
#include "qrics/safety/safety_shield.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/simulation/local_simulation_adapter.hpp"

namespace {

[[nodiscard]] qrics::task::TaskGraph make_task_graph() {
  qrics::task::TaskNode move{};
  move.node_id = "move_to_demo";
  move.type = qrics::task::TaskNodeType::MoveTo;
  move.target_waypoint_id = "checkpoint_a";
  move.policy_tag = "local_nav";
  move.fallback_action = qrics::task::FallbackAction::Replan;

  qrics::task::TaskGraph graph{};
  graph.graph_id = "graph_obstacle_demo";
  graph.task_ref = qrics::common::ResourceRef{"task_obstacle_demo", "0.1.0"};
  graph.nodes.push_back(move);
  graph.entry_node_id = move.node_id;
  graph.terminal_node_id = move.node_id;
  return graph;
}

[[nodiscard]] std::vector<qrics::control::TaskWaypointContext> make_waypoints() {
  qrics::control::TaskWaypointContext waypoint{};
  waypoint.waypoint_id = "checkpoint_a";
  waypoint.pose.position = qrics::common::Vec3{1.0, 0.0, 0.35};
  waypoint.dwell_time_s = 0.0;
  return {waypoint};
}

[[nodiscard]] qrics::scenario::SceneProfile make_obstacle_scene() {
  qrics::scenario::SceneObstacle obstacle{};
  obstacle.obstacle_id = "close_demo_barrel";
  obstacle.pose.position = qrics::common::Vec3{0.16, 0.0, 0.35};
  obstacle.radius_m = 0.08;
  obstacle.height_m = 0.35;

  qrics::scenario::SceneProfile profile{};
  profile.scene_id = "cpp_obstacle_mapping_scene";
  profile.version = "0.3.0";
  profile.terrain_pack = "mixed_terrain_pack";
  profile.obstacles.push_back(obstacle);
  profile.obstacle_set.push_back(obstacle.obstacle_id);
  return profile;
}

}  // namespace

int main() {
  auto runtime_profile = qrics::simulation::get_local_runtime_profile("headless_fast");
  if (!runtime_profile.ok) {
    return 1;
  }

  qrics::simulation::LocalSimulationConfig config{};
  config.backend = qrics::simulation::LocalBackendKind::MuJoCo;
  config.runtime_profile = runtime_profile.value;
  config.adapter_name = "cpp_mujoco_contract";
  qrics::simulation::KinematicLocalSimulationAdapter adapter{config};

  const auto initialized = adapter.initialize(qrics::simulation::AdapterConfig{});
  if (!initialized.ok) {
    return 2;
  }
  const auto loaded = adapter.load_scene(make_obstacle_scene());
  if (!loaded.ok) {
    return 3;
  }
  const auto reset = adapter.reset();
  if (!reset.ok) {
    return 4;
  }
  if (!reset.value.obstacle_state.obstacle_detected) {
    return 5;
  }
  if (reset.value.terrain_class != qrics::simulation::TerrainClass::Flat) {
    return 6;
  }

  qrics::safety::SafetyLimits limits{};
  limits.min_obstacle_distance_m = 0.25;
  qrics::safety::BasicSafetyShield safety_shield{limits};
  qrics::control::SimpleLocalPlanner local_planner{};
  qrics::control::RuleBasedPolicyRuntime policy_runtime{local_planner};
  qrics::control::TaskExecutor executor{adapter, safety_shield, policy_runtime};

  qrics::control::TaskExecutorStartRequest start{};
  start.run_id = "run_cpp_control_obstacle_mapping";
  start.task_graph = make_task_graph();
  start.waypoints = make_waypoints();
  start.default_policy_ref = qrics::common::ResourceRef{"local_nav", "0.3.0"};
  start.started_at_ns = 0;
  const auto started = executor.start(start);
  if (!started.ok) {
    return 7;
  }

  qrics::control::TaskExecutorStepRequest step{};
  step.timestamp_ns = 10'000'000;
  step.safety_context.require_observation = true;
  const auto stepped = executor.step_once(step);
  if (!stepped.ok) {
    return 8;
  }
  if (!stepped.value.control_loop_invoked || !stepped.value.adapter_stepped) {
    return 9;
  }
  if (stepped.value.safety_events.empty()) {
    return 10;
  }
  if (stepped.value.safety_events.front().trigger_type !=
      qrics::safety::TriggerType::CollisionRisk) {
    return 11;
  }
  if (stepped.value.safety_events.front().action_taken !=
      qrics::safety::SafetyActionTaken::Replan) {
    return 12;
  }
  if (stepped.value.snapshot.run_state != qrics::control::ControlRunState::Running) {
    return 13;
  }
  if (stepped.value.snapshot.control_step_count != 1) {
    return 14;
  }

  const auto observed = adapter.observe();
  if (!observed.ok || !observed.value.obstacle_state.obstacle_detected) {
    return 15;
  }
  if (observed.value.obstacle_state.nearest_distance_m > limits.min_obstacle_distance_m) {
    return 16;
  }

  return 0;
}