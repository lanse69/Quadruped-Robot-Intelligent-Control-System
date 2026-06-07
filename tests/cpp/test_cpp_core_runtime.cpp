#include <filesystem>
#include <string>

#include "qrics/runtime/local_task_run_engine.hpp"
#include "qrics/simulation/local_simulation_adapter.hpp"

namespace {

[[nodiscard]] qrics::runtime::LocalTaskRunRequest make_success_request() {
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
  return request;
}

[[nodiscard]] qrics::runtime::LocalTaskRunRequest make_collision_request(
    const std::filesystem::path& evidence_dir) {
  qrics::runtime::LocalTaskRunRequest request{};
  request.run_id = "cpp_runtime_collision_test";
  request.backend = qrics::simulation::LocalBackendKind::MuJoCo;
  request.runtime_profile = "headless_fast";
  request.scene = qrics::runtime::make_default_local_demo_scene("cpp_runtime_collision", "0.1.0",
                                                                "mixed_terrain_pack");
  request.task_path = {
      qrics::runtime::LocalTaskTarget{"A", qrics::common::Vec3{1.50, 0.55, 0.35}, 0.0},
  };
  request.max_steps = 10;
  request.min_obstacle_distance_m = 2.00;
  request.evidence_dir = evidence_dir.string();
  return request;
}

[[nodiscard]] bool path_exists(const std::string& path) {
  return !path.empty() && std::filesystem::exists(path);
}

[[nodiscard]] int validate_success_summary(const qrics::runtime::LocalTaskRunRequest& request,
                                           const qrics::runtime::LocalTaskRunSummary& summary) {
  if (summary.run_id != request.run_id) {
    return 2;
  }
  if (summary.backend != "mujoco") {
    return 3;
  }
  if (summary.state != "succeeded") {
    return 4;
  }
  if (summary.completed_node_count != 3) {
    return 5;
  }
  if (summary.executed_step_count <= 0 || summary.adapter_step_count <= 0) {
    return 6;
  }
  if (summary.base_position.x <= 0.30) {
    return 7;
  }
  if (summary.nodes.size() != 3U) {
    return 8;
  }
  if (summary.scene_obstacle_count != 1 || summary.scene_checkpoint_count != 3 ||
      summary.scene_forbidden_zone_count != 1 || summary.task_target_count != 2) {
    return 9;
  }
  if (summary.gait_name.empty() || summary.gait_step_frequency_hz <= 0.0 ||
      summary.swing_foot_count + summary.stance_foot_count != 4) {
    return 11;
  }
  const std::string json = qrics::runtime::to_json(summary);
  if (json.find(R"("run_id":"cpp_runtime_contract_test")") == std::string::npos) {
    return 10;
  }
  if (json.find(R"("state":"succeeded")") == std::string::npos) {
    return 12;
  }
  if (json.find(R"("gait_name":)") == std::string::npos ||
      json.find(R"("gait_step_frequency_hz":)") == std::string::npos) {
    return 26;
  }
  return 0;
}

[[nodiscard]] int validate_collision_evidence(const qrics::runtime::LocalTaskRunSummary& summary) {
  if (summary.safety_event_count <= 0) {
    return 14;
  }
  if (summary.keyframes.empty()) {
    return 15;
  }
  if (!path_exists(summary.replay_manifest_path)) {
    return 16;
  }
  if (!path_exists(summary.replay_segment_path)) {
    return 17;
  }
  if (summary.replay_keyframe_count != summary.safety_event_count) {
    return 18;
  }
  if (!path_exists(summary.telemetry_path)) {
    return 19;
  }
  if (summary.telemetry_frame_count <= 0) {
    return 20;
  }
  if (!path_exists(summary.audit_path)) {
    return 21;
  }
  if (summary.audit_event_count < summary.safety_event_count + 2) {
    return 22;
  }
  if (!path_exists(summary.evidence_bundle_path)) {
    return 23;
  }
  const std::string collision_json = qrics::runtime::to_json(summary);
  if (collision_json.find(R"("replay_manifest_path":"")") != std::string::npos) {
    return 24;
  }
  if (collision_json.find(R"("telemetry_path":"")") != std::string::npos ||
      collision_json.find(R"("audit_path":"")") != std::string::npos ||
      collision_json.find(R"("evidence_bundle_path":"")") != std::string::npos) {
    return 25;
  }
  return 0;
}

[[nodiscard]] int run_success_case() {
  const auto request = make_success_request();
  const auto summary = qrics::runtime::run_local_task(request);
  if (!summary.ok) {
    return 1;
  }
  return validate_success_summary(request, summary.value);
}

[[nodiscard]] int run_collision_evidence_case() {
  const auto evidence_dir =
      std::filesystem::temp_directory_path() / "qrics_cpp_runtime_evidence_test";
  std::filesystem::remove_all(evidence_dir);
  const auto request = make_collision_request(evidence_dir);
  const auto collision = qrics::runtime::run_local_task(request);
  if (!collision.ok) {
    std::filesystem::remove_all(evidence_dir);
    return 13;
  }
  const int validation_code = validate_collision_evidence(collision.value);
  std::filesystem::remove_all(evidence_dir);
  return validation_code;
}

}  // namespace

int main() {
  const int success_case_code = run_success_case();
  if (success_case_code != 0) {
    return success_case_code;
  }
  return run_collision_evidence_case();
}