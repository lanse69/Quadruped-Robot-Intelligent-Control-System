#include <string>

#include "qrics/runtime/local_task_run_engine.hpp"
#include "qrics/simulation/local_simulation_adapter.hpp"

int main() {
  qrics::runtime::LocalTaskRunRequest request{};
  request.run_id = "cpp_runtime_contract_test";
  request.backend = qrics::simulation::LocalBackendKind::MuJoCo;
  request.runtime_profile = "headless_fast";
  request.scene = qrics::runtime::make_default_local_demo_scene("cpp_runtime_scene", "0.1.0",
                                                                "mixed_terrain_pack");
  request.task_path = {
      qrics::runtime::LocalTaskTarget{"A", qrics::common::Vec3{0.30, 0.00, 0.35}, 0.0},
      qrics::runtime::LocalTaskTarget{"B", qrics::common::Vec3{0.55, 0.00, 0.35}, 0.0},
  };
  request.max_steps = 80;
  request.min_obstacle_distance_m = 0.05;

  const auto summary = qrics::runtime::run_local_task(request);
  if (!summary.ok) {
    return 1;
  }
  if (summary.value.run_id != request.run_id) {
    return 2;
  }
  if (summary.value.backend != "mujoco") {
    return 3;
  }
  if (summary.value.state != "succeeded") {
    return 4;
  }
  if (summary.value.completed_node_count != 3) {
    return 5;
  }
  if (summary.value.executed_step_count <= 0 || summary.value.adapter_step_count <= 0) {
    return 6;
  }
  if (summary.value.base_position.x <= 0.30) {
    return 7;
  }
  if (summary.value.nodes.size() != 3U) {
    return 8;
  }

  const std::string json = qrics::runtime::to_json(summary.value);
  if (json.find(R"("run_id":"cpp_runtime_contract_test")") == std::string::npos) {
    return 9;
  }
  if (json.find(R"("state":"succeeded")") == std::string::npos) {
    return 10;
  }

  qrics::runtime::LocalTaskRunRequest blocked{};
  blocked.run_id = "cpp_runtime_collision_test";
  blocked.backend = qrics::simulation::LocalBackendKind::MuJoCo;
  blocked.runtime_profile = "headless_fast";
  blocked.scene = qrics::runtime::make_default_local_demo_scene("cpp_runtime_collision", "0.1.0",
                                                                "mixed_terrain_pack");
  blocked.task_path = {
      qrics::runtime::LocalTaskTarget{"A", qrics::common::Vec3{1.50, 0.55, 0.35}, 0.0},
  };
  blocked.max_steps = 10;
  blocked.min_obstacle_distance_m = 2.00;
  const auto collision = qrics::runtime::run_local_task(blocked);
  if (!collision.ok) {
    return 11;
  }
  if (collision.value.safety_event_count <= 0) {
    return 12;
  }
  if (collision.value.keyframes.empty()) {
    return 13;
  }

  return 0;
}