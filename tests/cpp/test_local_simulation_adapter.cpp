#include "qrics/simulation/local_simulation_adapter.hpp"

namespace {

[[nodiscard]] qrics::control::SafeAction body_velocity_action() {
  qrics::control::SafeAction action{};
  action.action_id = "safe_body_velocity";
  action.action_type = qrics::control::ActionType::BodyVelocity;
  action.body_velocity = qrics::common::Vec3{0.5, 0.0, 0.0};
  action.yaw_rate_radps = 0.2;
  action.decision = qrics::control::SafetyDecision::Accepted;
  return action;
}

[[nodiscard]] qrics::scenario::SceneProfile scene() {
  qrics::scenario::SceneProfile profile{};
  profile.scene_id = "cpp_local_scene";
  profile.version = "0.3.0";
  profile.name = "C++ local backend scene";
  profile.terrain_pack = "mixed_terrain_pack";
  qrics::scenario::SceneObstacle obstacle{};
  obstacle.obstacle_id = "near_barrel";
  obstacle.pose.position = qrics::common::Vec3{0.20, 0.0, 0.35};
  obstacle.radius_m = 0.08;
  profile.obstacle_set.push_back(obstacle.obstacle_id);
  profile.obstacles.push_back(obstacle);
  return profile;
}

}  // namespace

int main() {
  const auto backend = qrics::simulation::parse_local_backend_kind("webots");
  if (!backend.ok || backend.value != qrics::simulation::LocalBackendKind::Webots) {
    return 1;
  }

  const auto profile = qrics::simulation::get_local_runtime_profile("webots_fast");
  if (!profile.ok || profile.value.control_decimation != 2) {
    return 2;
  }

  const auto descriptors = qrics::simulation::supported_local_backends();
  if (descriptors.size() < 4) {
    return 3;
  }

  qrics::simulation::KinematicLocalSimulationAdapter adapter{
      qrics::simulation::LocalSimulationConfig{qrics::simulation::LocalBackendKind::Webots,
                                               profile.value, "local_cpp_webots", "0.3.0",
                                               "0.3.0"}};
  const auto initialized = adapter.initialize({"local_cpp_webots", "0.3.0", "0.3.0"});
  if (!initialized.ok || initialized.value != qrics::simulation::AdapterState::Initialized) {
    return 4;
  }
  const auto loaded = adapter.load_scene(scene());
  if (!loaded.ok || loaded.value != qrics::simulation::AdapterState::SceneLoaded) {
    return 5;
  }
  const auto reset = adapter.reset();
  if (!reset.ok || reset.value.terrain_class != qrics::simulation::TerrainClass::Flat) {
    return 6;
  }
  if (!reset.value.obstacle_state.obstacle_detected ||
      reset.value.obstacle_state.nearest_distance_m <= 0.0) {
    return 11;
  }
  const auto before = adapter.robot_state();
  if (!before.ok) {
    return 7;
  }
  const auto stepped = adapter.step(body_velocity_action());
  if (!stepped.ok || stepped.value.robot_state.pose.position.x <= before.value.pose.position.x) {
    return 8;
  }
  if (stepped.value.robot_state.contacts.size() != 4U) {
    return 9;
  }
  if (!stepped.value.observation.obstacle_state.obstacle_detected) {
    return 12;
  }
  const auto closed = adapter.close();
  if (!closed.ok || closed.value != qrics::simulation::AdapterState::Stopped) {
    return 10;
  }
  return 0;
}