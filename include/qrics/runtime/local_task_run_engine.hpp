// C++ 本机任务运行引擎：将 TaskGraph -> TaskExecutor -> SafetyShield -> SimulationAdapter
// 闭环封装为可复用契约

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/safety/safety_event.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/simulation/local_simulation_adapter.hpp"

namespace qrics::runtime {

struct LocalTaskTarget final {
  std::string target_id{};
  qrics::common::Vec3 position{};
  double dwell_time_s{0.0};
};

struct LocalTaskRunRequest final {
  std::string run_id{"cpp_run"};
  qrics::simulation::LocalBackendKind backend{qrics::simulation::LocalBackendKind::Minimal};
  std::string runtime_profile{"headless_fast"};
  qrics::scenario::SceneProfile scene{};
  std::vector<LocalTaskTarget> task_path{};
  qrics::common::ResourceRef policy_ref{"cpp_local_nav", "0.1.0"};
  int max_steps{120};
  double min_obstacle_distance_m{0.25};
  double max_linear_velocity_mps{0.65};
  double max_yaw_rate_radps{0.9};
  bool require_observation{true};
  qrics::common::TimestampNs started_at_ns{0};
  std::string evidence_dir{};
};

struct LocalTaskRunNodeSummary final {
  std::string node_id{};
  std::string node_type{};
  std::string state{};
  std::string reason{};
};

struct LocalTaskRunSummary final {
  std::string run_id{};
  std::string backend{};
  std::string runtime_profile{};
  std::string scene_id{};
  std::string scene_version{};
  std::string state{};
  std::string reason{};
  int requested_step_limit{0};
  int executed_step_count{0};
  int adapter_step_count{0};
  int completed_node_count{0};
  int task_target_count{0};
  int scene_obstacle_count{0};
  int scene_checkpoint_count{0};
  int scene_forbidden_zone_count{0};
  int safety_event_count{0};
  qrics::common::TimestampNs sim_time_ns{0};
  qrics::common::Vec3 base_position{};
  double risk_score{0.0};
  std::string stability_state{};
  std::string terrain_class{};
  bool obstacle_detected{false};
  double nearest_obstacle_distance_m{0.0};
  std::string gait_name{};
  double gait_phase{0.0};
  double gait_step_frequency_hz{0.0};
  int swing_foot_count{0};
  int stance_foot_count{0};
  std::string replay_manifest_uri{};
  std::string replay_manifest_path{};
  std::string replay_segment_uri{};
  std::string replay_segment_path{};
  int replay_keyframe_count{0};
  std::string telemetry_uri{};
  std::string telemetry_path{};
  int telemetry_frame_count{0};
  std::string audit_uri{};
  std::string audit_path{};
  int audit_event_count{0};
  std::string evidence_bundle_uri{};
  std::string evidence_bundle_path{};
  std::vector<std::string> keyframes{};
  std::vector<qrics::safety::SafetyEvent> safety_events{};
  std::vector<LocalTaskRunNodeSummary> nodes{};
};

[[nodiscard]] qrics::common::Result<LocalTaskRunSummary> run_local_task(
    const LocalTaskRunRequest& request);

[[nodiscard]] qrics::scenario::SceneProfile make_default_local_demo_scene(
    const std::string& scene_id, const std::string& version, const std::string& terrain_pack);

[[nodiscard]] std::string to_json(const LocalTaskRunSummary& summary);

}  // namespace qrics::runtime