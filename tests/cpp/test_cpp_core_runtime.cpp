#include <filesystem>
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
  if (summary.value.scene_obstacle_count != 1 || summary.value.scene_checkpoint_count != 3 ||
      summary.value.scene_forbidden_zone_count != 1 || summary.value.task_target_count != 2) {
    return 9;
  }

  const std::string json = qrics::runtime::to_json(summary.value);
  if (json.find(R"("run_id":"cpp_runtime_contract_test")") == std::string::npos) {
    return 10;
  }
  if (json.find(R"("state":"succeeded")") == std::string::npos) {
    return 12;
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
  const auto evidence_dir =
      std::filesystem::temp_directory_path() / "qrics_cpp_runtime_evidence_test";
  std::filesystem::remove_all(evidence_dir);
  blocked.max_steps = 10;
  blocked.min_obstacle_distance_m = 2.00;
  blocked.evidence_dir = evidence_dir.string();
  const auto collision = qrics::runtime::run_local_task(blocked);
  if (!collision.ok) {
    return 13;
  }
  if (collision.value.safety_event_count <= 0) {
    return 14;
  }
  if (collision.value.keyframes.empty()) {
    return 15;
  }
  if (collision.value.replay_manifest_path.empty() ||
      !std::filesystem::exists(collision.value.replay_manifest_path)) {
    return 16;
  }
  if (collision.value.replay_segment_path.empty() ||
      !std::filesystem::exists(collision.value.replay_segment_path)) {
    return 17;
  }
  if (collision.value.replay_keyframe_count != collision.value.safety_event_count) {
    return 18;
  }
  const std::string collision_json = qrics::runtime::to_json(collision.value);
  if (collision_json.find(R"("replay_manifest_path":"")") != std::string::npos) {
    return 19;
  }
  std::filesystem::remove_all(evidence_dir);

  return 0;
}