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
  bool auto_extend_task_steps{false};
  int max_auto_extended_steps{1200};
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
  double route_progress_ratio{0.0};
  double target_distance_m{0.0};
  qrics::common::TimestampNs sim_time_ns{0};
  double risk_score{0.0};
  double nearest_obstacle_distance_m{0.0};
  double gait_phase{0.0};
  double gait_step_frequency_hz{0.0};
  qrics::common::Vec3 base_position{};
  std::vector<std::string> keyframes{};
  std::vector<qrics::safety::SafetyEvent> safety_events{};
  std::vector<LocalTaskRunNodeSummary> nodes{};
  std::string run_id{};
  std::string backend{};
  std::string runtime_profile{};
  std::string scene_id{};
  std::string scene_version{};
  std::string state{};
  std::string reason{};
  std::string current_node_id{};
  std::string active_target_id{};
  std::string stability_state{};
  std::string terrain_class{};
  std::string gait_name{};
  std::string replay_manifest_uri{};
  std::string replay_manifest_path{};
  std::string replay_segment_uri{};
  std::string replay_segment_path{};
  std::string telemetry_uri{};
  std::string telemetry_path{};
  std::string audit_uri{};
  std::string audit_path{};
  std::string evidence_bundle_uri{};
  std::string evidence_bundle_path{};
  int reached_target_count{0};
  int requested_step_limit{0};
  int effective_step_limit{0};
  int estimated_required_step_count{0};
  int executed_step_count{0};
  int adapter_step_count{0};
  int completed_node_count{0};
  int task_target_count{0};
  int scene_obstacle_count{0};
  int scene_checkpoint_count{0};
  int scene_forbidden_zone_count{0};
  int safety_event_count{0};
  int swing_foot_count{0};
  int stance_foot_count{0};
  int joint_command_count{0};
  int replay_keyframe_count{0};
  int telemetry_frame_count{0};
  int audit_event_count{0};
  bool route_completed{false};
  bool auto_extended_task_steps{false};
  bool obstacle_detected{false};
};

[[nodiscard]] qrics::common::Result<LocalTaskRunSummary> run_local_task(
    const LocalTaskRunRequest& request);

[[nodiscard]] qrics::scenario::SceneProfile make_default_local_demo_scene(
    const std::string& scene_id, const std::string& version, const std::string& terrain_pack);

[[nodiscard]] std::string to_json(const LocalTaskRunSummary& summary);

}  // namespace qrics::runtime