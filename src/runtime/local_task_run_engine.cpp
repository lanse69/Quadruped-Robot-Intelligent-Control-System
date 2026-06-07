#include "qrics/runtime/local_task_run_engine.hpp"

#include <algorithm>
#include <cmath>
#include <exception>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <utility>

#include "qrics/control/local_planner.hpp"
#include "qrics/control/policy_runtime.hpp"
#include "qrics/control/task_executor.hpp"
#include "qrics/replay/replay_manifest_writer.hpp"
#include "qrics/safety/safety_shield.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::runtime {

namespace {

constexpr qrics::common::TimestampNs kNanosecondsPerSecond{1'000'000'000};

[[nodiscard]] qrics::common::Error make_error(std::string code, std::string message) {
  return qrics::common::Error{std::move(code), std::move(message)};
}

[[nodiscard]] qrics::common::Result<LocalTaskRunSummary> fail_summary(const std::string& code,
                                                                      const std::string& message) {
  return qrics::common::Result<LocalTaskRunSummary>::failure({make_error(code, message)});
}

[[nodiscard]] std::string escape_json(const std::string& value) {
  std::ostringstream out;
  for (const char ch : value) {
    switch (ch) {
      case '"':
        out << "\\\"";
        break;
      case '\\':
        out << "\\\\";
        break;
      case '\b':
        out << "\\b";
        break;
      case '\f':
        out << "\\f";
        break;
      case '\n':
        out << "\\n";
        break;
      case '\r':
        out << "\\r";
        break;
      case '\t':
        out << "\\t";
        break;
      default:
        out << ch;
        break;
    }
  }
  return out.str();
}

[[nodiscard]] std::string quote(const std::string& value) {
  return "\"" + escape_json(value) + "\"";
}

[[nodiscard]] std::string state_to_string(qrics::control::ControlRunState state) {
  switch (state) {
    case qrics::control::ControlRunState::Created:
      return "created";
    case qrics::control::ControlRunState::Running:
      return "running";
    case qrics::control::ControlRunState::Paused:
      return "paused";
    case qrics::control::ControlRunState::Succeeded:
      return "succeeded";
    case qrics::control::ControlRunState::Failed:
      return "failed";
    case qrics::control::ControlRunState::Cancelled:
      return "cancelled";
  }
  return "unknown";
}

[[nodiscard]] std::string node_state_to_string(qrics::control::TaskNodeExecutionState state) {
  switch (state) {
    case qrics::control::TaskNodeExecutionState::Pending:
      return "pending";
    case qrics::control::TaskNodeExecutionState::Running:
      return "running";
    case qrics::control::TaskNodeExecutionState::Succeeded:
      return "succeeded";
    case qrics::control::TaskNodeExecutionState::Failed:
      return "failed";
    case qrics::control::TaskNodeExecutionState::Skipped:
      return "skipped";
  }
  return "unknown";
}

[[nodiscard]] std::string node_type_to_string(qrics::task::TaskNodeType type) {
  switch (type) {
    case qrics::task::TaskNodeType::MoveTo:
      return "move_to";
    case qrics::task::TaskNodeType::Dwell:
      return "dwell";
    case qrics::task::TaskNodeType::Inspect:
      return "inspect";
    case qrics::task::TaskNodeType::ReturnHome:
      return "return_home";
    case qrics::task::TaskNodeType::Stop:
      return "stop";
  }
  return "unknown";
}

[[nodiscard]] std::string terrain_to_string(qrics::simulation::TerrainClass terrain) {
  switch (terrain) {
    case qrics::simulation::TerrainClass::Unknown:
      return "unknown";
    case qrics::simulation::TerrainClass::Flat:
      return "flat";
    case qrics::simulation::TerrainClass::Slope:
      return "slope";
    case qrics::simulation::TerrainClass::Gravel:
      return "gravel";
    case qrics::simulation::TerrainClass::Stairs:
      return "stairs";
    case qrics::simulation::TerrainClass::LowFriction:
      return "low_friction";
  }
  return "unknown";
}

[[nodiscard]] std::string stability_to_string(qrics::simulation::StabilityState stability) {
  switch (stability) {
    case qrics::simulation::StabilityState::Unknown:
      return "unknown";
    case qrics::simulation::StabilityState::Stable:
      return "stable";
    case qrics::simulation::StabilityState::Unstable:
      return "unstable";
    case qrics::simulation::StabilityState::Fallen:
      return "fallen";
    case qrics::simulation::StabilityState::Recovering:
      return "recovering";
  }
  return "unknown";
}

[[nodiscard]] std::string trigger_to_string(qrics::safety::TriggerType trigger) {
  switch (trigger) {
    case qrics::safety::TriggerType::None:
      return "none";
    case qrics::safety::TriggerType::OrientationLimit:
      return "orientation_limit";
    case qrics::safety::TriggerType::VelocityLimit:
      return "velocity_limit";
    case qrics::safety::TriggerType::ForbiddenZone:
      return "forbidden_zone";
    case qrics::safety::TriggerType::CollisionRisk:
      return "collision_risk";
    case qrics::safety::TriggerType::EmergencyStop:
      return "emergency_stop";
    case qrics::safety::TriggerType::ManualOverride:
      return "manual_override";
    case qrics::safety::TriggerType::ObservationMissing:
      return "observation_missing";
    case qrics::safety::TriggerType::ActionLimit:
      return "action_limit";
    case qrics::safety::TriggerType::PolicyInvalid:
      return "policy_invalid";
  }
  return "unknown";
}

[[nodiscard]] qrics::task::TaskGraph make_task_graph(
    const std::string& run_id, const std::vector<LocalTaskTarget>& task_path) {
  qrics::task::TaskGraph graph{};
  graph.graph_id = "cpp_graph_" + run_id;
  graph.task_ref = qrics::common::ResourceRef{"cpp_task_" + run_id, "0.1.0"};
  graph.entry_node_id =
      task_path.empty() ? "stop_terminal" : "move_0_" + task_path.front().target_id;
  graph.terminal_node_id = "stop_terminal";

  std::string previous{};
  int index = 0;
  for (const auto& target : task_path) {
    qrics::task::TaskNode move{};
    move.node_id = "move_" + std::to_string(index) + "_" + target.target_id;
    move.type = index == 0 && target.target_id == "platform" ? qrics::task::TaskNodeType::ReturnHome
                                                             : qrics::task::TaskNodeType::MoveTo;
    move.target_waypoint_id = target.target_id;
    move.policy_tag = "cpp_local_nav";
    move.fallback_action = qrics::task::FallbackAction::Replan;
    graph.nodes.push_back(move);
    if (!previous.empty()) {
      graph.edges.push_back(qrics::task::TaskEdge{previous, move.node_id, "completed"});
    }
    previous = move.node_id;

    if (target.dwell_time_s > 0.0) {
      qrics::task::TaskNode dwell{};
      dwell.node_id = "dwell_" + std::to_string(index) + "_" + target.target_id;
      dwell.type = qrics::task::TaskNodeType::Dwell;
      dwell.target_waypoint_id = target.target_id;
      dwell.policy_tag = "cpp_local_nav";
      graph.nodes.push_back(dwell);
      graph.edges.push_back(qrics::task::TaskEdge{previous, dwell.node_id, "arrived"});
      previous = dwell.node_id;
    }
    ++index;
  }

  qrics::task::TaskNode stop{};
  stop.node_id = "stop_terminal";
  stop.type = qrics::task::TaskNodeType::Stop;
  stop.policy_tag = "cpp_local_nav";
  graph.nodes.push_back(stop);
  if (!previous.empty()) {
    graph.edges.push_back(qrics::task::TaskEdge{previous, stop.node_id, "completed"});
  }
  return graph;
}

[[nodiscard]] std::vector<qrics::control::TaskWaypointContext> make_waypoint_contexts(
    const std::vector<LocalTaskTarget>& task_path) {
  std::vector<qrics::control::TaskWaypointContext> waypoints;
  waypoints.reserve(task_path.size());
  for (const auto& target : task_path) {
    qrics::control::TaskWaypointContext waypoint{};
    waypoint.waypoint_id = target.target_id;
    waypoint.pose.position = target.position;
    waypoint.pose.position.z = target.position.z == 0.0 ? 0.35 : target.position.z;
    waypoint.dwell_time_s = target.dwell_time_s;
    waypoints.push_back(waypoint);
  }
  return waypoints;
}

void fill_summary_from_snapshot(LocalTaskRunSummary& summary,
                                const qrics::control::TaskExecutionSnapshot& snapshot) {
  summary.state = state_to_string(snapshot.run_state);
  summary.reason = snapshot.reason;
  summary.executed_step_count = snapshot.control_step_count;
  summary.completed_node_count = snapshot.completed_node_count;
  summary.sim_time_ns = snapshot.last_robot_state.timestamp_ns;
  summary.base_position = snapshot.last_robot_state.pose.position;
  summary.risk_score = snapshot.last_robot_state.risk_score;
  summary.stability_state = stability_to_string(snapshot.last_robot_state.stability_state);
  summary.terrain_class = terrain_to_string(snapshot.last_robot_state.terrain_class);

  summary.nodes.clear();
  summary.nodes.reserve(snapshot.node_snapshots.size());
  for (const auto& node : snapshot.node_snapshots) {
    summary.nodes.push_back(LocalTaskRunNodeSummary{node.node_id,
                                                    node_type_to_string(node.node_type),
                                                    node_state_to_string(node.state), node.reason});
  }
}

struct CoreTelemetryFrame final {
  qrics::common::TimestampNs timestamp_ns{0};
  qrics::common::Vec3 base_position{};
  double risk_score{0.0};
  std::string stability_state{};
  std::string terrain_class{};
  bool obstacle_detected{false};
  double nearest_obstacle_distance_m{0.0};
  int executed_step_count{0};
  int adapter_step_count{0};
  int completed_node_count{0};
  std::string state{};
};

void append_telemetry_frame(const LocalTaskRunSummary& summary,
                            std::vector<CoreTelemetryFrame>& telemetry_frames) {
  CoreTelemetryFrame frame{};
  frame.timestamp_ns = summary.sim_time_ns;
  frame.base_position = summary.base_position;
  frame.risk_score = summary.risk_score;
  frame.stability_state = summary.stability_state;
  frame.terrain_class = summary.terrain_class;
  frame.obstacle_detected = summary.obstacle_detected;
  frame.nearest_obstacle_distance_m = summary.nearest_obstacle_distance_m;
  frame.executed_step_count = summary.executed_step_count;
  frame.adapter_step_count = summary.adapter_step_count;
  frame.completed_node_count = summary.completed_node_count;
  frame.state = summary.state;
  telemetry_frames.push_back(std::move(frame));
}

void write_audit_json_line(std::ofstream& out, const std::string& event_id,
                           const std::string& run_id, qrics::common::TimestampNs timestamp_ns,
                           const std::string& action, const std::string& result,
                           const std::string& reason, const std::string& object_ref) {
  out << R"({"event_id":)" << quote(event_id) << R"(,"run_id":)" << quote(run_id)
      << R"(,"timestamp_ns":)" << timestamp_ns << R"(,"actor_id":"qrics_core_runtime",)"
      << R"("actor_role":"runtime","action":)" << quote(action) << R"(,"object_ref":)"
      << quote(object_ref) << R"(,"result":)" << quote(result) << R"(,"reason":)" << quote(reason)
      << "}\n";
}

void write_telemetry_json_line(std::ofstream& out, const std::string& run_id,
                               const CoreTelemetryFrame& frame) {
  out << "{\"run_id\":" << quote(run_id) << ",\"timestamp_ns\":" << frame.timestamp_ns
      << ",\"base_position\":[" << frame.base_position.x << "," << frame.base_position.y << ","
      << frame.base_position.z << "],\"risk_score\":" << frame.risk_score
      << ",\"stability_state\":" << quote(frame.stability_state)
      << ",\"terrain_class\":" << quote(frame.terrain_class)
      << ",\"obstacle_detected\":" << (frame.obstacle_detected ? "true" : "false")
      << ",\"nearest_obstacle_distance_m\":" << frame.nearest_obstacle_distance_m
      << ",\"executed_step_count\":" << frame.executed_step_count
      << ",\"adapter_step_count\":" << frame.adapter_step_count
      << ",\"completed_node_count\":" << frame.completed_node_count
      << ",\"state\":" << quote(frame.state) << "}\n";
}

[[nodiscard]] qrics::common::Result<LocalTaskRunSummary> write_replay_evidence(
    LocalTaskRunSummary summary, const LocalTaskRunRequest& request,
    const std::vector<CoreTelemetryFrame>& telemetry_frames) {
  if (request.evidence_dir.empty()) {
    return qrics::common::Result<LocalTaskRunSummary>::success(std::move(summary));
  }

  try {
    const std::filesystem::path evidence_dir{request.evidence_dir};
    std::filesystem::create_directories(evidence_dir);
    const auto manifest_path = evidence_dir / (request.run_id + "_core_replay_manifest.json");
    const auto segment_path = evidence_dir / (request.run_id + "_core_segment.jsonl");
    const auto telemetry_path = evidence_dir / (request.run_id + "_core_telemetry.jsonl");
    const auto audit_path = evidence_dir / (request.run_id + "_core_audit.jsonl");
    const auto bundle_path = evidence_dir / (request.run_id + "_core_evidence_bundle.json");

    qrics::replay::ReplayManifestWriterConfig config{};
    config.manifest_id = "manifest_" + request.run_id;
    config.run_id = request.run_id;
    config.scene_ref = qrics::common::ResourceRef{request.scene.scene_id, request.scene.version};
    config.policy_ref = request.policy_ref;
    config.segment_id = "segment_0001";
    config.artifact_uri = "file://" + segment_path.string();
    config.created_at_ns = request.started_at_ns;
    config.segment_start_time_ns = request.started_at_ns;

    auto writer_result = qrics::replay::ReplayManifestWriter::create(std::move(config));
    if (!writer_result.ok) {
      return qrics::common::Result<LocalTaskRunSummary>::failure(writer_result.errors);
    }
    auto writer = std::move(writer_result.value);
    for (const auto& event : summary.safety_events) {
      auto keyframe = writer.record_safety_event(event);
      if (!keyframe.ok) {
        return qrics::common::Result<LocalTaskRunSummary>::failure(keyframe.errors);
      }
    }
    const auto manifest_result = writer.finalize(summary.sim_time_ns);
    if (!manifest_result.ok) {
      return qrics::common::Result<LocalTaskRunSummary>::failure(manifest_result.errors);
    }

    std::ofstream segment_out(segment_path);
    if (!segment_out) {
      return fail_summary(
          "CORE_REPLAY_SEGMENT_WRITE_FAILED",
          "Could not open C++ replay segment for writing: " + segment_path.string());
    }
    segment_out << "{\"run_id\":" << quote(summary.run_id) << ",\"state\":" << quote(summary.state)
                << ",\"executed_step_count\":" << summary.executed_step_count
                << ",\"adapter_step_count\":" << summary.adapter_step_count
                << ",\"risk_score\":" << summary.risk_score << "}\n";
    segment_out.close();

    std::ofstream manifest_out(manifest_path);
    if (!manifest_out) {
      return fail_summary(
          "CORE_REPLAY_MANIFEST_WRITE_FAILED",
          "Could not open C++ replay manifest for writing: " + manifest_path.string());
    }
    manifest_out << qrics::replay::serialize_replay_manifest_json(manifest_result.value);
    manifest_out.close();

    std::ofstream telemetry_out(telemetry_path);
    if (!telemetry_out) {
      return fail_summary(
          "CORE_TELEMETRY_WRITE_FAILED",
          "Could not open C++ telemetry file for writing: " + telemetry_path.string());
    }
    for (const auto& frame : telemetry_frames) {
      write_telemetry_json_line(telemetry_out, request.run_id, frame);
    }
    telemetry_out.close();

    std::ofstream audit_out(audit_path);
    if (!audit_out) {
      return fail_summary("CORE_AUDIT_WRITE_FAILED",
                          "Could not open C++ audit file for writing: " + audit_path.string());
    }
    int audit_event_count = 0;
    write_audit_json_line(audit_out, "audit_" + request.run_id + "_start", request.run_id,
                          request.started_at_ns, "control.run_started", "accepted",
                          "C++ core runtime accepted TaskGraph handoff",
                          request.scene.scene_id + ":" + request.scene.version);
    ++audit_event_count;
    for (std::size_t i = 0; i < summary.safety_events.size(); ++i) {
      const auto& event = summary.safety_events[i];
      const auto trigger = trigger_to_string(event.trigger_type);
      write_audit_json_line(audit_out, "audit_" + request.run_id + "_safety_" + std::to_string(i),
                            request.run_id, event.timestamp_ns, "safety.event_recorded", "recorded",
                            trigger, event.event_id);
      ++audit_event_count;
    }
    write_audit_json_line(audit_out, "audit_" + request.run_id + "_complete", request.run_id,
                          summary.sim_time_ns, "control.run_completed", summary.state,
                          summary.reason, request.run_id);
    ++audit_event_count;
    audit_out.close();

    summary.replay_manifest_path = manifest_path.string();
    summary.replay_segment_path = segment_path.string();
    summary.replay_manifest_uri = "file://" + manifest_path.string();
    summary.replay_segment_uri = "file://" + segment_path.string();
    summary.replay_keyframe_count = static_cast<int>(manifest_result.value.keyframes.size());
    summary.telemetry_path = telemetry_path.string();
    summary.telemetry_uri = "file://" + telemetry_path.string();
    summary.telemetry_frame_count = static_cast<int>(telemetry_frames.size());
    summary.audit_path = audit_path.string();
    summary.audit_uri = "file://" + audit_path.string();
    summary.audit_event_count = audit_event_count;
    summary.evidence_bundle_path = bundle_path.string();
    summary.evidence_bundle_uri = "file://" + bundle_path.string();

    std::ofstream bundle_out(bundle_path);
    if (!bundle_out) {
      return fail_summary(
          "CORE_EVIDENCE_BUNDLE_WRITE_FAILED",
          "Could not open C++ evidence bundle for writing: " + bundle_path.string());
    }
    bundle_out << R"({"schema":"qrics.cpp_core_evidence_bundle.v1",)";
    bundle_out << R"("run_id":)" << quote(summary.run_id) << ",";
    bundle_out << R"("backend":)" << quote(summary.backend) << ",";
    bundle_out << R"("runtime_profile":)" << quote(summary.runtime_profile) << ",";
    bundle_out << R"("scene_ref":{"id":)" << quote(summary.scene_id) << R"(,"version":)"
               << quote(summary.scene_version) << "},";
    bundle_out << R"("control_chain":["TaskGraph","TaskExecutor","PolicyRuntime",)"
                  R"("LocalPlanner","SafetyShield","SimulationAdapter"],)";
    bundle_out << R"("files":{"replay_manifest":)" << quote(summary.replay_manifest_path)
               << R"(,"replay_segment":)" << quote(summary.replay_segment_path)
               << R"(,"telemetry":)" << quote(summary.telemetry_path) << R"(,"audit":)"
               << quote(summary.audit_path) << "},";
    bundle_out << R"("counts":{"telemetry_frames":)" << summary.telemetry_frame_count
               << R"(,"audit_events":)" << summary.audit_event_count << R"(,"safety_events":)"
               << summary.safety_event_count << R"(,"replay_keyframes":)"
               << summary.replay_keyframe_count << "}}";
    bundle_out.close();

    return qrics::common::Result<LocalTaskRunSummary>::success(std::move(summary));
  } catch (const std::exception& exc) {
    return fail_summary("CORE_REPLAY_EVIDENCE_WRITE_FAILED", exc.what());
  }
}
}  // namespace

qrics::scenario::SceneProfile make_default_local_demo_scene(const std::string& scene_id,
                                                            const std::string& version,
                                                            const std::string& terrain_pack) {
  qrics::scenario::SceneProfile scene{};
  scene.scene_id = scene_id.empty() ? "cpp_local_demo_scene" : scene_id;
  scene.version = version.empty() ? "0.1.0" : version;
  scene.name = "QRICS C++ local task runtime scene";
  scene.terrain_pack = terrain_pack.empty() ? "mixed_terrain_pack" : terrain_pack;
  scene.sensor_profile.imu_enabled = true;
  scene.sensor_profile.contact_sensor_enabled = true;
  scene.sensor_profile.source_quality = "direct";

  qrics::scenario::SceneObstacle box{};
  box.obstacle_id = "cpp_demo_box";
  box.geometry_type = qrics::scenario::SceneGeometryType::Box;
  box.pose.position = qrics::common::Vec3{1.20, 0.55, 0.18};
  box.size_m = qrics::common::Vec3{0.24, 0.24, 0.30};
  box.radius_m = 0.17;
  box.height_m = 0.30;
  scene.obstacles.push_back(box);
  scene.obstacle_set.push_back(box.obstacle_id);

  qrics::scenario::Checkpoint platform{};
  platform.checkpoint_id = "platform";
  platform.pose.position = qrics::common::Vec3{0.0, 0.0, 0.35};
  scene.checkpoints.push_back(platform);

  qrics::scenario::Checkpoint checkpoint_a{};
  checkpoint_a.checkpoint_id = "A";
  checkpoint_a.pose.position = qrics::common::Vec3{0.85, 0.25, 0.35};
  checkpoint_a.dwell_time_s = 0.4;
  scene.checkpoints.push_back(checkpoint_a);

  qrics::scenario::Checkpoint checkpoint_b{};
  checkpoint_b.checkpoint_id = "B";
  checkpoint_b.pose.position = qrics::common::Vec3{1.65, -0.25, 0.35};
  checkpoint_b.dwell_time_s = 0.4;
  scene.checkpoints.push_back(checkpoint_b);

  qrics::scenario::ForbiddenZone zone{};
  zone.zone_id = "low_friction_zone";
  zone.polygon = {qrics::common::Vec3{2.25, -0.80, 0.0}, qrics::common::Vec3{2.90, -0.80, 0.0},
                  qrics::common::Vec3{2.90, 0.80, 0.0}, qrics::common::Vec3{2.25, 0.80, 0.0}};
  scene.forbidden_zones.push_back(zone);
  return scene;
}

qrics::common::Result<LocalTaskRunSummary> run_local_task(const LocalTaskRunRequest& request) {
  if (request.run_id.empty()) {
    return fail_summary("RUN_ID_EMPTY", "LocalTaskRunRequest.run_id must not be empty");
  }
  if (request.max_steps <= 0) {
    return fail_summary("STEP_LIMIT_INVALID", "LocalTaskRunRequest.max_steps must be positive");
  }

  auto runtime_profile = qrics::simulation::get_local_runtime_profile(request.runtime_profile);
  if (!runtime_profile.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(runtime_profile.errors);
  }

  qrics::simulation::LocalSimulationConfig sim_config{};
  sim_config.backend = request.backend;
  sim_config.runtime_profile = runtime_profile.value;
  sim_config.adapter_name = "cpp_core_runtime";
  qrics::simulation::KinematicLocalSimulationAdapter adapter{sim_config};

  const auto initialized =
      adapter.initialize(qrics::simulation::AdapterConfig{"cpp_core_runtime", "0.4.0", "0.4.0"});
  if (!initialized.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(initialized.errors);
  }
  const auto loaded = adapter.load_scene(request.scene);
  if (!loaded.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(loaded.errors);
  }
  const auto reset = adapter.reset();
  if (!reset.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(reset.errors);
  }

  qrics::safety::SafetyLimits limits{};
  limits.min_obstacle_distance_m = request.min_obstacle_distance_m;
  limits.max_linear_velocity_mps = request.max_linear_velocity_mps;
  limits.max_yaw_rate_radps = request.max_yaw_rate_radps;
  limits.allow_joint_commands = false;
  qrics::safety::BasicSafetyShield safety_shield{limits};
  qrics::control::SimpleLocalPlanner planner{};
  qrics::control::RuleBasedPolicyRuntime policy_runtime{planner};
  qrics::control::TaskExecutor executor{adapter, safety_shield, policy_runtime};

  qrics::control::TaskExecutorStartRequest start{};
  start.run_id = request.run_id;
  start.task_graph = make_task_graph(request.run_id, request.task_path);
  start.waypoints = make_waypoint_contexts(request.task_path);
  start.default_policy_ref = request.policy_ref;
  start.started_at_ns = request.started_at_ns;
  auto started = executor.start(start);
  if (!started.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(started.errors);
  }

  LocalTaskRunSummary summary{};
  summary.run_id = request.run_id;
  summary.backend = qrics::simulation::to_string(request.backend);
  summary.runtime_profile = request.runtime_profile;
  summary.scene_id = request.scene.scene_id;
  summary.scene_version = request.scene.version;
  summary.requested_step_limit = request.max_steps;
  summary.task_target_count = static_cast<int>(request.task_path.size());
  summary.scene_obstacle_count = static_cast<int>(request.scene.obstacles.size());
  summary.scene_checkpoint_count = static_cast<int>(request.scene.checkpoints.size());
  summary.scene_forbidden_zone_count = static_cast<int>(request.scene.forbidden_zones.size());
  fill_summary_from_snapshot(summary, started.value);
  std::vector<CoreTelemetryFrame> telemetry_frames{};
  append_telemetry_frame(summary, telemetry_frames);

  qrics::common::TimestampNs timestamp_ns = request.started_at_ns;
  const auto control_dt_ns = static_cast<qrics::common::TimestampNs>(
      runtime_profile.value.physics_timestep_s *
      static_cast<double>(runtime_profile.value.control_decimation) *
      static_cast<double>(kNanosecondsPerSecond));

  for (int step_index = 0; step_index < request.max_steps; ++step_index) {
    timestamp_ns += std::max<qrics::common::TimestampNs>(1, control_dt_ns);
    qrics::control::TaskExecutorStepRequest step{};
    step.timestamp_ns = timestamp_ns;
    step.safety_context.require_observation = request.require_observation;
    step.safety_context.forbidden_zones = request.scene.forbidden_zones;
    auto stepped = executor.step_once(step);
    if (!stepped.ok) {
      return qrics::common::Result<LocalTaskRunSummary>::failure(stepped.errors);
    }

    if (stepped.value.adapter_stepped) {
      ++summary.adapter_step_count;
    }
    for (const auto& event : stepped.value.safety_events) {
      summary.safety_events.push_back(event);
      summary.keyframes.push_back("safety_step_" + std::to_string(step_index) + ":" +
                                  trigger_to_string(event.trigger_type));
    }
    fill_summary_from_snapshot(summary, stepped.value.snapshot);
    append_telemetry_frame(summary, telemetry_frames);

    if (stepped.value.snapshot.run_state != qrics::control::ControlRunState::Running) {
      break;
    }
  }

  const auto observed = adapter.observe();
  if (observed.ok) {
    summary.obstacle_detected = observed.value.obstacle_state.obstacle_detected;
    summary.nearest_obstacle_distance_m = observed.value.obstacle_state.nearest_distance_m;
    summary.terrain_class = terrain_to_string(observed.value.terrain_class);
    if (!telemetry_frames.empty()) {
      telemetry_frames.back().obstacle_detected = summary.obstacle_detected;
      telemetry_frames.back().nearest_obstacle_distance_m = summary.nearest_obstacle_distance_m;
      telemetry_frames.back().terrain_class = summary.terrain_class;
    }
  }
  summary.safety_event_count = static_cast<int>(summary.safety_events.size());
  const auto closed = adapter.close();
  if (!closed.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(closed.errors);
  }
  return write_replay_evidence(std::move(summary), request, telemetry_frames);
}

std::string to_json(const LocalTaskRunSummary& summary) {
  std::ostringstream out;
  out << "{";
  out << "\"run_id\":" << quote(summary.run_id) << ",";
  out << "\"backend\":" << quote(summary.backend) << ",";
  out << "\"runtime_profile\":" << quote(summary.runtime_profile) << ",";
  out << "\"scene_id\":" << quote(summary.scene_id) << ",";
  out << "\"scene_version\":" << quote(summary.scene_version) << ",";
  out << "\"state\":" << quote(summary.state) << ",";
  out << "\"reason\":" << quote(summary.reason) << ",";
  out << "\"requested_step_limit\":" << summary.requested_step_limit << ",";
  out << "\"executed_step_count\":" << summary.executed_step_count << ",";
  out << "\"adapter_step_count\":" << summary.adapter_step_count << ",";
  out << "\"completed_node_count\":" << summary.completed_node_count << ",";
  out << "\"task_target_count\":" << summary.task_target_count << ",";
  out << "\"scene_obstacle_count\":" << summary.scene_obstacle_count << ",";
  out << "\"scene_checkpoint_count\":" << summary.scene_checkpoint_count << ",";
  out << "\"scene_forbidden_zone_count\":" << summary.scene_forbidden_zone_count << ",";
  out << "\"safety_event_count\":" << summary.safety_event_count << ",";
  out << "\"sim_time_ns\":" << summary.sim_time_ns << ",";
  out << "\"base_position\":[" << summary.base_position.x << "," << summary.base_position.y << ","
      << summary.base_position.z << "],";
  out << "\"risk_score\":" << summary.risk_score << ",";
  out << "\"stability_state\":" << quote(summary.stability_state) << ",";
  out << "\"terrain_class\":" << quote(summary.terrain_class) << ",";
  out << "\"obstacle_detected\":" << (summary.obstacle_detected ? "true" : "false") << ",";
  out << "\"nearest_obstacle_distance_m\":" << summary.nearest_obstacle_distance_m << ",";
  out << "\"replay_manifest_uri\":" << quote(summary.replay_manifest_uri) << ",";
  out << "\"replay_manifest_path\":" << quote(summary.replay_manifest_path) << ",";
  out << "\"replay_segment_uri\":" << quote(summary.replay_segment_uri) << ",";
  out << "\"replay_segment_path\":" << quote(summary.replay_segment_path) << ",";
  out << "\"replay_keyframe_count\":" << summary.replay_keyframe_count << ",";
  out << "\"telemetry_uri\":" << quote(summary.telemetry_uri) << ",";
  out << "\"telemetry_path\":" << quote(summary.telemetry_path) << ",";
  out << "\"telemetry_frame_count\":" << summary.telemetry_frame_count << ",";
  out << "\"audit_uri\":" << quote(summary.audit_uri) << ",";
  out << "\"audit_path\":" << quote(summary.audit_path) << ",";
  out << "\"audit_event_count\":" << summary.audit_event_count << ",";
  out << "\"evidence_bundle_uri\":" << quote(summary.evidence_bundle_uri) << ",";
  out << "\"evidence_bundle_path\":" << quote(summary.evidence_bundle_path) << ",";

  out << "\"keyframes\":[";
  for (std::size_t i = 0; i < summary.keyframes.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    out << quote(summary.keyframes[i]);
  }
  out << "],";

  out << "\"safety_events\":[";
  for (std::size_t i = 0; i < summary.safety_events.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    const auto& event = summary.safety_events[i];
    out << "{";
    out << "\"event_id\":" << quote(event.event_id) << ",";
    out << "\"run_id\":" << quote(event.run_id) << ",";
    out << "\"trigger_type\":" << quote(trigger_to_string(event.trigger_type)) << ",";
    out << "\"timestamp_ns\":" << event.timestamp_ns << ",";
    out << "\"violations\":[";
    for (std::size_t j = 0; j < event.violation_list.size(); ++j) {
      if (j > 0U) {
        out << ",";
      }
      out << quote(event.violation_list[j]);
    }
    out << "]}";
  }
  out << "],";

  out << "\"nodes\":[";
  for (std::size_t i = 0; i < summary.nodes.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    const auto& node = summary.nodes[i];
    out << "{";
    out << "\"node_id\":" << quote(node.node_id) << ",";
    out << "\"node_type\":" << quote(node.node_type) << ",";
    out << "\"state\":" << quote(node.state) << ",";
    out << "\"reason\":" << quote(node.reason) << "}";
  }
  out << "]";
  out << "}";
  return out.str();
}

}  // namespace qrics::runtime