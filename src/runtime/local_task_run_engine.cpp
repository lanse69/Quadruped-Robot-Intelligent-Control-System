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
#include "qrics/planning/route_planner.hpp"
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

[[nodiscard]] const char* json_bool(bool value) noexcept {
  return value ? "true" : "false";
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

[[nodiscard]] qrics::task::TaskNodeType task_node_type_for_target(const LocalTaskTarget& target,
                                                                  int target_index) {
  if (target.is_route_detour || !target.is_task_target) {
    return qrics::task::TaskNodeType::MoveTo;
  }
  if (target_index == 0 && target.target_id == "platform") {
    return qrics::task::TaskNodeType::ReturnHome;
  }
  return qrics::task::TaskNodeType::MoveTo;
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
    move.type = task_node_type_for_target(target, index);
    move.target_waypoint_id = target.target_id;
    move.policy_tag = "cpp_local_nav";
    move.fallback_action = qrics::task::FallbackAction::Replan;
    graph.nodes.push_back(move);
    if (!previous.empty()) {
      graph.edges.push_back(qrics::task::TaskEdge{previous, move.node_id, "completed"});
    }
    previous = move.node_id;

    if (target.is_task_target && !target.is_route_detour && target.dwell_time_s > 0.0) {
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

[[nodiscard]] double planar_distance(const qrics::common::Vec3& lhs,
                                     const qrics::common::Vec3& rhs) noexcept {
  const double dx = rhs.x - lhs.x;
  const double dy = rhs.y - lhs.y;
  return std::sqrt((dx * dx) + (dy * dy));
}

[[nodiscard]] qrics::common::Vec3 normalized_target_position(const LocalTaskTarget& target) {
  qrics::common::Vec3 position = target.position;
  if (position.z == 0.0) {
    position.z = 0.35;
  }
  return position;
}

[[nodiscard]] int estimate_required_step_count(const std::vector<LocalTaskTarget>& task_path,
                                               double control_dt_s) {
  if (task_path.empty() || control_dt_s <= 0.0) {
    return 1;
  }

  qrics::common::Vec3 cursor{0.0, 0.0, 0.35};
  double route_distance_m = 0.0;
  int dwell_steps = 0;
  for (const auto& target : task_path) {
    const auto target_position = normalized_target_position(target);
    route_distance_m += planar_distance(cursor, target_position);
    if (target.is_task_target && !target.is_route_detour && target.dwell_time_s > 0.0) {
      dwell_steps += static_cast<int>(std::ceil(target.dwell_time_s / control_dt_s));
    }
    cursor = target_position;
  }

  // Local C++ kinematic execution is intentionally conservative because the path tracker slows down
  // near waypoints and the terrain/gait model reduces forward progress on non-flat terrain.
  constexpr double kConservativeEffectiveSpeedMps = 0.16;
  const int transit_steps = static_cast<int>(std::ceil(
      route_distance_m / std::max(1.0e-6, kConservativeEffectiveSpeedMps * control_dt_s)));
  const int stabilization_steps = static_cast<int>(task_path.size()) * 16;
  return std::max(1, transit_steps + dwell_steps + stabilization_steps);
}

[[nodiscard]] int effective_step_limit(const LocalTaskRunRequest& request,
                                       const std::vector<LocalTaskTarget>& execution_path,
                                       double control_dt_s) {
  const int requested = std::max(1, request.max_steps);
  if (!request.auto_extend_task_steps) {
    return requested;
  }
  const int estimated = estimate_required_step_count(execution_path, control_dt_s);
  const int upper_bound = std::max(requested, request.max_auto_extended_steps);
  return std::clamp(std::max(requested, estimated), requested, upper_bound);
}

[[nodiscard]] const qrics::task::TaskNode* find_graph_node(const qrics::task::TaskGraph& graph,
                                                           const std::string& node_id) {
  const auto found = std::find_if(graph.nodes.begin(), graph.nodes.end(),
                                  [&node_id](const auto& node) { return node.node_id == node_id; });
  return found == graph.nodes.end() ? nullptr : &(*found);
}

[[nodiscard]] int count_task_targets(const std::vector<LocalTaskTarget>& task_path) {
  return static_cast<int>(std::count_if(task_path.begin(), task_path.end(), [](const auto& target) {
    return target.is_task_target && !target.is_route_detour;
  }));
}

[[nodiscard]] std::vector<qrics::planning::RouteTarget> make_planning_targets(
    const std::vector<LocalTaskTarget>& task_path) {
  std::vector<qrics::planning::RouteTarget> targets;
  targets.reserve(task_path.size());
  for (const auto& target : task_path) {
    targets.push_back(qrics::planning::RouteTarget{
        target.target_id, normalized_target_position(target), target.dwell_time_s});
  }
  return targets;
}

[[nodiscard]] std::vector<LocalTaskTarget> make_execution_path(
    const qrics::planning::PlannedRoute& planned_route) {
  std::vector<LocalTaskTarget> task_path;
  task_path.reserve(planned_route.waypoints.size());
  for (const auto& waypoint : planned_route.waypoints) {
    task_path.push_back(LocalTaskTarget{waypoint.waypoint_id, waypoint.position,
                                        waypoint.dwell_time_s, waypoint.is_detour,
                                        waypoint.is_task_target});
  }
  return task_path;
}

[[nodiscard]] std::vector<LocalTaskRouteWaypoint> make_route_summary_waypoints(
    const qrics::planning::PlannedRoute& planned_route) {
  std::vector<LocalTaskRouteWaypoint> waypoints;
  waypoints.reserve(planned_route.waypoints.size());
  for (const auto& waypoint : planned_route.waypoints) {
    waypoints.push_back(LocalTaskRouteWaypoint{waypoint.waypoint_id, waypoint.position,
                                               waypoint.dwell_time_s, waypoint.is_detour,
                                               waypoint.is_task_target});
  }
  return waypoints;
}

[[nodiscard]] const LocalTaskTarget* find_target(const std::vector<LocalTaskTarget>& task_path,
                                                 const std::string& target_id) {
  const auto found =
      std::find_if(task_path.begin(), task_path.end(),
                   [&target_id](const auto& item) { return item.target_id == target_id; });
  return found == task_path.end() ? nullptr : &(*found);
}

[[nodiscard]] bool node_targets_task_waypoint(qrics::task::TaskNodeType type) noexcept {
  return type == qrics::task::TaskNodeType::MoveTo || type == qrics::task::TaskNodeType::ReturnHome;
}

void fill_route_from_snapshot(LocalTaskRunSummary& summary,
                              const qrics::control::TaskExecutionSnapshot& snapshot,
                              const std::vector<LocalTaskTarget>& task_path) {
  summary.current_node_id = snapshot.current_node_id;
  summary.task_target_count = count_task_targets(task_path);
  summary.reached_target_count = 0;
  for (const auto& node : snapshot.node_snapshots) {
    if (!node_targets_task_waypoint(node.node_type) ||
        node.state != qrics::control::TaskNodeExecutionState::Succeeded) {
      continue;
    }
    const auto* graph_node = find_graph_node(snapshot.task_graph, node.node_id);
    if (graph_node == nullptr) {
      continue;
    }
    const auto* target = find_target(task_path, graph_node->target_waypoint_id);
    if (target != nullptr && target->is_task_target && !target->is_route_detour) {
      ++summary.reached_target_count;
    }
  }
  if (summary.task_target_count <= 0) {
    summary.route_progress_ratio = 0.0;
    summary.route_completed = snapshot.run_state == qrics::control::ControlRunState::Succeeded;
  } else {
    summary.route_progress_ratio = std::clamp(static_cast<double>(summary.reached_target_count) /
                                                  static_cast<double>(summary.task_target_count),
                                              0.0, 1.0);
    summary.route_completed = summary.reached_target_count >= summary.task_target_count &&
                              snapshot.run_state == qrics::control::ControlRunState::Succeeded;
  }

  summary.active_target_id.clear();
  summary.target_distance_m = 0.0;
  const auto* current_node = find_graph_node(snapshot.task_graph, snapshot.current_node_id);
  if (current_node != nullptr && node_targets_task_waypoint(current_node->type)) {
    summary.active_target_id = current_node->target_waypoint_id;
    const auto* target = find_target(task_path, current_node->target_waypoint_id);
    if (target != nullptr) {
      summary.target_distance_m = planar_distance(snapshot.last_robot_state.pose.position,
                                                  normalized_target_position(*target));
    }
    return;
  }
  if (summary.route_completed && !task_path.empty()) {
    const auto found = std::find_if(task_path.rbegin(), task_path.rend(), [](const auto& target) {
      return target.is_task_target && !target.is_route_detour;
    });
    summary.active_target_id =
        found == task_path.rend() ? task_path.back().target_id : found->target_id;
  }
}

void fill_summary_from_snapshot(LocalTaskRunSummary& summary,
                                const qrics::control::TaskExecutionSnapshot& snapshot) {
  summary.state = state_to_string(snapshot.run_state);
  summary.reason = snapshot.reason;
  summary.current_node_id = snapshot.current_node_id;
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
  std::string gait_name{};
  double gait_phase{0.0};
  double gait_step_frequency_hz{0.0};
  int swing_foot_count{0};
  int stance_foot_count{0};
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
  frame.gait_name = summary.gait_name;
  frame.gait_phase = summary.gait_phase;
  frame.gait_step_frequency_hz = summary.gait_step_frequency_hz;
  frame.swing_foot_count = summary.swing_foot_count;
  frame.stance_foot_count = summary.stance_foot_count;
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
      << ",\"gait_name\":" << quote(frame.gait_name) << ",\"gait_phase\":" << frame.gait_phase
      << ",\"gait_step_frequency_hz\":" << frame.gait_step_frequency_hz
      << ",\"swing_foot_count\":" << frame.swing_foot_count
      << ",\"stance_foot_count\":" << frame.stance_foot_count
      << ",\"executed_step_count\":" << frame.executed_step_count
      << ",\"adapter_step_count\":" << frame.adapter_step_count
      << ",\"completed_node_count\":" << frame.completed_node_count
      << ",\"state\":" << quote(frame.state) << "}\n";
}

void fill_gait_from_safe_action(LocalTaskRunSummary& summary,
                                const qrics::control::SafeAction& action) {
  const auto& hint = action.locomotion_hint;
  if (!hint.enabled) {
    return;
  }
  summary.gait_name = hint.gait_name;
  summary.gait_phase = hint.normalized_phase;
  summary.gait_step_frequency_hz = hint.step_frequency_hz;
  summary.joint_command_count = static_cast<int>(action.joint_commands.size());
  summary.swing_foot_count = 0;
  summary.stance_foot_count = 0;
  for (const auto& foot : hint.feet) {
    if (foot.phase == qrics::control::FootPhase::Swing) {
      ++summary.swing_foot_count;
    } else {
      ++summary.stance_foot_count;
    }
  }
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
    bundle_out << R"("control_chain":["RoutePlanner","TaskGraph","TaskExecutor","PolicyRuntime",)"
                  R"("LocalPlanner","GaitGenerator","SafetyShield","SimulationAdapter"],)";
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

namespace {

using LocalTaskRoutePlan = qrics::planning::PlannedRoute;

[[nodiscard]] qrics::common::Result<bool> validate_local_task_request(
    const LocalTaskRunRequest& request) {
  if (request.run_id.empty()) {
    return qrics::common::Result<bool>::failure(
        {make_error("RUN_ID_EMPTY", "LocalTaskRunRequest.run_id must not be empty")});
  }
  if (request.max_steps <= 0) {
    return qrics::common::Result<bool>::failure(
        {make_error("STEP_LIMIT_INVALID", "LocalTaskRunRequest.max_steps must be positive")});
  }
  return qrics::common::Result<bool>::success(true);
}

[[nodiscard]] qrics::common::Result<LocalTaskRoutePlan> plan_local_task_route(
    const LocalTaskRunRequest& request) {
  return qrics::planning::plan_task_route(request.scene, make_planning_targets(request.task_path),
                                          qrics::planning::RoutePlanningConfig{},
                                          qrics::common::Vec3{0.0, 0.0, 0.35});
}

[[nodiscard]] qrics::simulation::LocalSimulationConfig make_local_simulation_config(
    const LocalTaskRunRequest& request,
    const qrics::simulation::LocalRuntimeProfile& runtime_profile) {
  qrics::simulation::LocalSimulationConfig sim_config{};
  sim_config.backend = request.backend;
  sim_config.runtime_profile = runtime_profile;
  sim_config.adapter_name = "cpp_core_runtime";
  return sim_config;
}

[[nodiscard]] qrics::common::Result<bool> prepare_local_adapter(
    qrics::simulation::KinematicLocalSimulationAdapter& adapter,
    const qrics::scenario::SceneProfile& scene) {
  const auto initialized =
      adapter.initialize(qrics::simulation::AdapterConfig{"cpp_core_runtime", "0.4.0", "0.4.0"});
  if (!initialized.ok) {
    return qrics::common::Result<bool>::failure(initialized.errors);
  }

  const auto loaded = adapter.load_scene(scene);
  if (!loaded.ok) {
    return qrics::common::Result<bool>::failure(loaded.errors);
  }

  const auto reset = adapter.reset();
  if (!reset.ok) {
    return qrics::common::Result<bool>::failure(reset.errors);
  }
  return qrics::common::Result<bool>::success(true);
}

[[nodiscard]] qrics::safety::SafetyLimits make_local_safety_limits(
    const LocalTaskRunRequest& request) {
  qrics::safety::SafetyLimits limits{};
  limits.min_obstacle_distance_m = request.min_obstacle_distance_m;
  limits.max_linear_velocity_mps = request.max_linear_velocity_mps;
  limits.max_yaw_rate_radps = request.max_yaw_rate_radps;
  limits.allow_joint_commands = false;
  return limits;
}

[[nodiscard]] qrics::control::TaskExecutorStartRequest make_executor_start_request(
    const LocalTaskRunRequest& request, const std::vector<LocalTaskTarget>& execution_path) {
  qrics::control::TaskExecutorStartRequest start{};
  start.run_id = request.run_id;
  start.task_graph = make_task_graph(request.run_id, execution_path);
  start.waypoints = make_waypoint_contexts(execution_path);
  start.default_policy_ref = request.policy_ref;
  start.started_at_ns = request.started_at_ns;
  return start;
}

[[nodiscard]] LocalTaskRunSummary make_started_summary(
    const LocalTaskRunRequest& request,
    const qrics::simulation::LocalRuntimeProfile& runtime_profile,
    const LocalTaskRoutePlan& planned_route, const std::vector<LocalTaskTarget>& execution_path,
    const qrics::control::TaskExecutionSnapshot& start_snapshot) {
  const double control_dt_s =
      runtime_profile.physics_timestep_s * static_cast<double>(runtime_profile.control_decimation);

  LocalTaskRunSummary summary{};
  summary.run_id = request.run_id;
  summary.backend = qrics::simulation::to_string(request.backend);
  summary.runtime_profile = request.runtime_profile;
  summary.scene_id = request.scene.scene_id;
  summary.scene_version = request.scene.version;
  summary.requested_step_limit = request.max_steps;
  summary.estimated_required_step_count =
      estimate_required_step_count(execution_path, control_dt_s);
  summary.effective_step_limit = effective_step_limit(request, execution_path, control_dt_s);
  summary.auto_extended_task_steps =
      request.auto_extend_task_steps && summary.effective_step_limit > summary.requested_step_limit;
  summary.task_target_count = count_task_targets(execution_path);
  summary.planned_route = make_route_summary_waypoints(planned_route);
  summary.route_notes = planned_route.notes;
  summary.planned_route_waypoint_count = static_cast<int>(summary.planned_route.size());
  summary.detour_waypoint_count = planned_route.detour_waypoint_count;
  summary.blocked_object_count = planned_route.blocked_object_count;
  summary.route_used_graph_search = planned_route.used_graph_search;
  summary.scene_obstacle_count = static_cast<int>(request.scene.obstacles.size());
  summary.scene_checkpoint_count = static_cast<int>(request.scene.checkpoints.size());
  summary.scene_forbidden_zone_count = static_cast<int>(request.scene.forbidden_zones.size());
  fill_summary_from_snapshot(summary, start_snapshot);
  fill_route_from_snapshot(summary, start_snapshot, execution_path);
  return summary;
}

void append_step_safety_events(LocalTaskRunSummary& summary,
                               const std::vector<qrics::safety::SafetyEvent>& safety_events,
                               int step_index) {
  for (const auto& event : safety_events) {
    summary.safety_events.push_back(event);
    summary.keyframes.push_back("safety_step_" + std::to_string(step_index) + ":" +
                                trigger_to_string(event.trigger_type));
  }
}

[[nodiscard]] qrics::control::TaskExecutorStepRequest make_step_request(
    const LocalTaskRunRequest& request, qrics::common::TimestampNs timestamp_ns) {
  qrics::control::TaskExecutorStepRequest step{};
  step.timestamp_ns = timestamp_ns;
  step.safety_context.require_observation = request.require_observation;
  step.safety_context.forbidden_zones = request.scene.forbidden_zones;
  return step;
}

[[nodiscard]] qrics::common::Result<bool> run_control_steps(
    qrics::control::TaskExecutor& executor, const LocalTaskRunRequest& request,
    const qrics::simulation::LocalRuntimeProfile& runtime_profile,
    const std::vector<LocalTaskTarget>& execution_path, LocalTaskRunSummary& summary,
    std::vector<CoreTelemetryFrame>& telemetry_frames) {
  qrics::common::TimestampNs timestamp_ns = request.started_at_ns;
  const auto control_dt_ns = static_cast<qrics::common::TimestampNs>(
      runtime_profile.physics_timestep_s * static_cast<double>(runtime_profile.control_decimation) *
      static_cast<double>(kNanosecondsPerSecond));

  for (int step_index = 0; step_index < summary.effective_step_limit; ++step_index) {
    timestamp_ns += std::max<qrics::common::TimestampNs>(1, control_dt_ns);
    auto stepped = executor.step_once(make_step_request(request, timestamp_ns));
    if (!stepped.ok) {
      return qrics::common::Result<bool>::failure(stepped.errors);
    }

    summary.adapter_step_count += stepped.value.adapter_stepped ? 1 : 0;
    append_step_safety_events(summary, stepped.value.safety_events, step_index);
    fill_summary_from_snapshot(summary, stepped.value.snapshot);
    fill_route_from_snapshot(summary, stepped.value.snapshot, execution_path);
    fill_gait_from_safe_action(summary, stepped.value.last_safe_action);
    append_telemetry_frame(summary, telemetry_frames);

    if (stepped.value.snapshot.run_state != qrics::control::ControlRunState::Running) {
      break;
    }
  }
  return qrics::common::Result<bool>::success(true);
}

void refresh_observation_summary(const qrics::simulation::KinematicLocalSimulationAdapter& adapter,
                                 LocalTaskRunSummary& summary,
                                 std::vector<CoreTelemetryFrame>& telemetry_frames) {
  const auto observed = adapter.observe();
  if (!observed.ok) {
    return;
  }

  summary.obstacle_detected = observed.value.obstacle_state.obstacle_detected;
  summary.nearest_obstacle_distance_m = observed.value.obstacle_state.nearest_distance_m;
  summary.terrain_class = terrain_to_string(observed.value.terrain_class);
  if (!telemetry_frames.empty()) {
    telemetry_frames.back().obstacle_detected = summary.obstacle_detected;
    telemetry_frames.back().nearest_obstacle_distance_m = summary.nearest_obstacle_distance_m;
    telemetry_frames.back().terrain_class = summary.terrain_class;
  }
}

[[nodiscard]] std::vector<LocalTaskTarget>::const_reverse_iterator find_final_task_target(
    const std::vector<LocalTaskTarget>& execution_path) {
  return std::find_if(execution_path.rbegin(), execution_path.rend(), [](const auto& target) {
    return target.is_task_target && !target.is_route_detour;
  });
}

void pin_completed_summary_to_final_target(const std::vector<LocalTaskTarget>& execution_path,
                                           LocalTaskRunSummary& summary,
                                           std::vector<CoreTelemetryFrame>& telemetry_frames) {
  if (!summary.route_completed || execution_path.empty()) {
    return;
  }

  const auto final_target = find_final_task_target(execution_path);
  if (final_target == execution_path.rend()) {
    return;
  }

  summary.base_position = normalized_target_position(*final_target);
  summary.active_target_id = final_target->target_id;
  summary.target_distance_m = 0.0;
  if (!telemetry_frames.empty()) {
    telemetry_frames.back().base_position = summary.base_position;
    telemetry_frames.back().state = summary.state;
  }
}

class ScopedLocalAdapterSession final {
 public:
  explicit ScopedLocalAdapterSession(qrics::simulation::KinematicLocalSimulationAdapter& adapter)
      : adapter_{adapter} {}

  ScopedLocalAdapterSession(const ScopedLocalAdapterSession&) = delete;
  ScopedLocalAdapterSession& operator=(const ScopedLocalAdapterSession&) = delete;

  ~ScopedLocalAdapterSession() {
    if (!closed_) {
      (void)adapter_.close();
    }
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> close() {
    if (closed_) {
      return qrics::common::Result<qrics::simulation::AdapterState>::success(
          qrics::simulation::AdapterState::Stopped);
    }
    auto closed = adapter_.close();
    if (closed.ok) {
      closed_ = true;
    }
    return closed;
  }

 private:
  qrics::simulation::KinematicLocalSimulationAdapter& adapter_;
  bool closed_{false};
};

}  // namespace

qrics::common::Result<LocalTaskRunSummary> plan_local_task(const LocalTaskRunRequest& request) {
  const auto validation = validate_local_task_request(request);
  if (!validation.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(validation.errors);
  }

  auto runtime_profile = qrics::simulation::get_local_runtime_profile(request.runtime_profile);
  if (!runtime_profile.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(runtime_profile.errors);
  }

  auto planned_route = plan_local_task_route(request);
  if (!planned_route.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(planned_route.errors);
  }
  const std::vector<LocalTaskTarget> execution_path = make_execution_path(planned_route.value);
  const double control_dt_s = runtime_profile.value.physics_timestep_s *
                              static_cast<double>(runtime_profile.value.control_decimation);

  LocalTaskRunSummary summary{};
  summary.run_id = request.run_id;
  summary.backend = qrics::simulation::to_string(request.backend);
  summary.runtime_profile = request.runtime_profile;
  summary.scene_id = request.scene.scene_id;
  summary.scene_version = request.scene.version;
  summary.state = "planned";
  summary.reason = "Task route planned by C++ core route planner";
  summary.current_node_id = execution_path.empty() ? "" : "move_0";
  summary.base_position = qrics::common::Vec3{0.0, 0.0, 0.35};
  summary.gait_name = "cautious_trot";
  summary.gait_step_frequency_hz = 1.8;
  summary.swing_foot_count = 2;
  summary.stance_foot_count = 2;
  summary.requested_step_limit = request.max_steps;
  summary.estimated_required_step_count =
      estimate_required_step_count(execution_path, control_dt_s);
  summary.effective_step_limit = effective_step_limit(request, execution_path, control_dt_s);
  summary.auto_extended_task_steps =
      request.auto_extend_task_steps && summary.effective_step_limit > summary.requested_step_limit;
  summary.task_target_count = count_task_targets(execution_path);
  summary.planned_route = make_route_summary_waypoints(planned_route.value);
  summary.route_notes = planned_route.value.notes;
  summary.planned_route_waypoint_count = static_cast<int>(summary.planned_route.size());
  summary.detour_waypoint_count = planned_route.value.detour_waypoint_count;
  summary.blocked_object_count = planned_route.value.blocked_object_count;
  summary.route_used_graph_search = planned_route.value.used_graph_search;
  summary.scene_obstacle_count = static_cast<int>(request.scene.obstacles.size());
  summary.scene_checkpoint_count = static_cast<int>(request.scene.checkpoints.size());
  summary.scene_forbidden_zone_count = static_cast<int>(request.scene.forbidden_zones.size());
  const auto first_target = std::find_if(
      execution_path.begin(), execution_path.end(),
      [](const auto& target) { return target.is_task_target && !target.is_route_detour; });
  if (first_target != execution_path.end()) {
    summary.active_target_id = first_target->target_id;
    summary.target_distance_m =
        planar_distance(summary.base_position, normalized_target_position(*first_target));
  }
  return qrics::common::Result<LocalTaskRunSummary>::success(std::move(summary));
}

qrics::common::Result<LocalTaskRunSummary> run_local_task(const LocalTaskRunRequest& request) {
  const auto validation = validate_local_task_request(request);
  if (!validation.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(validation.errors);
  }

  auto runtime_profile = qrics::simulation::get_local_runtime_profile(request.runtime_profile);
  if (!runtime_profile.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(runtime_profile.errors);
  }

  auto planned_route = plan_local_task_route(request);
  if (!planned_route.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(planned_route.errors);
  }
  const std::vector<LocalTaskTarget> execution_path = make_execution_path(planned_route.value);

  qrics::simulation::KinematicLocalSimulationAdapter adapter{
      make_local_simulation_config(request, runtime_profile.value)};
  const auto adapter_ready = prepare_local_adapter(adapter, request.scene);
  if (!adapter_ready.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(adapter_ready.errors);
  }
  ScopedLocalAdapterSession adapter_session{adapter};

  qrics::safety::BasicSafetyShield safety_shield{make_local_safety_limits(request)};
  qrics::control::SimpleLocalPlanner planner{};
  qrics::control::RuleBasedPolicyRuntime policy_runtime{planner};
  qrics::control::TaskExecutor executor{adapter, safety_shield, policy_runtime};

  auto started = executor.start(make_executor_start_request(request, execution_path));
  if (!started.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(started.errors);
  }

  LocalTaskRunSummary summary = make_started_summary(
      request, runtime_profile.value, planned_route.value, execution_path, started.value);
  std::vector<CoreTelemetryFrame> telemetry_frames{};
  append_telemetry_frame(summary, telemetry_frames);

  const auto steps_run = run_control_steps(executor, request, runtime_profile.value, execution_path,
                                           summary, telemetry_frames);
  if (!steps_run.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(steps_run.errors);
  }

  refresh_observation_summary(adapter, summary, telemetry_frames);
  pin_completed_summary_to_final_target(execution_path, summary, telemetry_frames);

  summary.safety_event_count = static_cast<int>(summary.safety_events.size());
  const auto closed = adapter_session.close();
  if (!closed.ok) {
    return qrics::common::Result<LocalTaskRunSummary>::failure(closed.errors);
  }
  return write_replay_evidence(std::move(summary), request, telemetry_frames);
}

void append_string_array_json(std::ostringstream& out, const std::string& field_name,
                              const std::vector<std::string>& values) {
  out << quote(field_name) << ":[";
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    out << quote(values[i]);
  }
  out << "]";
}

void append_route_json(std::ostringstream& out, const std::vector<LocalTaskRouteWaypoint>& route) {
  out << "\"planned_route\":[";
  for (std::size_t i = 0; i < route.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    const auto& waypoint = route[i];
    out << "{";
    out << "\"waypoint_id\":" << quote(waypoint.waypoint_id) << ",";
    out << "\"position\":[" << waypoint.position.x << "," << waypoint.position.y << ","
        << waypoint.position.z << "],";
    out << "\"dwell_time_s\":" << waypoint.dwell_time_s << ",";
    out << "\"is_detour\":" << json_bool(waypoint.is_detour) << ",";
    out << "\"is_task_target\":" << json_bool(waypoint.is_task_target) << "}";
  }
  out << "]";
}

void append_safety_events_json(std::ostringstream& out,
                               const std::vector<qrics::safety::SafetyEvent>& safety_events) {
  out << "\"safety_events\":[";
  for (std::size_t i = 0; i < safety_events.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    const auto& event = safety_events[i];
    out << "{";
    out << "\"event_id\":" << quote(event.event_id) << ",";
    out << "\"run_id\":" << quote(event.run_id) << ",";
    out << "\"trigger_type\":" << quote(trigger_to_string(event.trigger_type)) << ",";
    out << "\"timestamp_ns\":" << event.timestamp_ns << ",";
    append_string_array_json(out, "violations", event.violation_list);
    out << "}";
  }
  out << "]";
}

void append_nodes_json(std::ostringstream& out, const std::vector<LocalTaskRunNodeSummary>& nodes) {
  out << "\"nodes\":[";
  for (std::size_t i = 0; i < nodes.size(); ++i) {
    if (i > 0U) {
      out << ",";
    }
    const auto& node = nodes[i];
    out << "{";
    out << "\"node_id\":" << quote(node.node_id) << ",";
    out << "\"node_type\":" << quote(node.node_type) << ",";
    out << "\"state\":" << quote(node.state) << ",";
    out << "\"reason\":" << quote(node.reason) << "}";
  }
  out << "]";
}

std::string to_json(const LocalTaskRunSummary& summary) {
  std::ostringstream out;
  out << "{";
  out << "\"run_id\":" << quote(summary.run_id) << ",";
  out << "\"backend\":" << quote(summary.backend) << ",";
  out << "\"runtime_profile\":" << quote(summary.runtime_profile) << ",";
  out << "\"scene_id\":" << quote(summary.scene_id) << ",";
  out << "\"scene_version\":" << quote(summary.scene_version) << ",";
  out << "\"core_language\":" << quote(summary.core_language) << ",";
  out << "\"route_planner_engine\":" << quote(summary.route_planner_engine) << ",";
  out << "\"presentation_layer_role\":" << quote(summary.presentation_layer_role) << ",";
  out << "\"state\":" << quote(summary.state) << ",";
  out << "\"reason\":" << quote(summary.reason) << ",";
  out << "\"current_node_id\":" << quote(summary.current_node_id) << ",";
  out << "\"route_completed\":" << json_bool(summary.route_completed) << ",";
  out << "\"route_progress_ratio\":" << summary.route_progress_ratio << ",";
  out << "\"reached_target_count\":" << summary.reached_target_count << ",";
  out << "\"active_target_id\":" << quote(summary.active_target_id) << ",";
  out << "\"target_distance_m\":" << summary.target_distance_m << ",";
  out << "\"auto_extended_task_steps\":" << json_bool(summary.auto_extended_task_steps) << ",";
  out << "\"requested_step_limit\":" << summary.requested_step_limit << ",";
  out << "\"effective_step_limit\":" << summary.effective_step_limit << ",";
  out << "\"estimated_required_step_count\":" << summary.estimated_required_step_count << ",";
  out << "\"executed_step_count\":" << summary.executed_step_count << ",";
  out << "\"adapter_step_count\":" << summary.adapter_step_count << ",";
  out << "\"completed_node_count\":" << summary.completed_node_count << ",";
  out << "\"task_target_count\":" << summary.task_target_count << ",";
  out << "\"planned_route_waypoint_count\":" << summary.planned_route_waypoint_count << ",";
  out << "\"detour_waypoint_count\":" << summary.detour_waypoint_count << ",";
  out << "\"blocked_object_count\":" << summary.blocked_object_count << ",";
  out << "\"route_used_graph_search\":" << json_bool(summary.route_used_graph_search) << ",";
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
  out << "\"obstacle_detected\":" << json_bool(summary.obstacle_detected) << ",";
  out << "\"nearest_obstacle_distance_m\":" << summary.nearest_obstacle_distance_m << ",";
  out << "\"gait_name\":" << quote(summary.gait_name) << ",";
  out << "\"gait_phase\":" << summary.gait_phase << ",";
  out << "\"gait_step_frequency_hz\":" << summary.gait_step_frequency_hz << ",";
  out << "\"swing_foot_count\":" << summary.swing_foot_count << ",";
  out << "\"stance_foot_count\":" << summary.stance_foot_count << ",";
  out << "\"joint_command_count\":" << summary.joint_command_count << ",";
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
  append_route_json(out, summary.planned_route);
  out << ",";
  append_string_array_json(out, "route_notes", summary.route_notes);
  out << ",";
  append_string_array_json(out, "keyframes", summary.keyframes);
  out << ",";
  append_safety_events_json(out, summary.safety_events);
  out << ",";
  append_nodes_json(out, summary.nodes);
  out << "}";
  return out.str();
}

}  // namespace qrics::runtime