#include "qrics/simulation/local_simulation_adapter.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace qrics::simulation {

namespace {

[[nodiscard]] qrics::common::Error make_error(std::string code, std::string message) {
  return qrics::common::Error{std::move(code), std::move(message)};
}

struct ObstacleDistance final {
  double clearance{std::numeric_limits<double>::infinity()};
  qrics::common::Vec3 nearest_point{};
};

[[nodiscard]] double positive_or(double value, double fallback) {
  return value > 0.0 ? value : fallback;
}

[[nodiscard]] ObstacleDistance obstacle_distance(const scenario::SceneObstacle& obstacle,
                                                 const qrics::common::Vec3& position) {
  const auto& center = obstacle.pose.position;
  if (obstacle.geometry_type == scenario::SceneGeometryType::Box) {
    const double half_x =
        std::max(0.005, positive_or(obstacle.size_m.x, obstacle.radius_m * 2.0) * 0.5);
    const double half_y =
        std::max(0.005, positive_or(obstacle.size_m.y, obstacle.radius_m * 2.0) * 0.5);
    const double half_z = std::max(0.005, positive_or(obstacle.size_m.z, obstacle.height_m) * 0.5);
    const double clamped_x = std::clamp(position.x, center.x - half_x, center.x + half_x);
    const double clamped_y = std::clamp(position.y, center.y - half_y, center.y + half_y);
    const double clamped_z = std::clamp(position.z, center.z - half_z, center.z + half_z);
    const double dx = position.x - clamped_x;
    const double dy = position.y - clamped_y;
    const double dz = position.z - clamped_z;
    return ObstacleDistance{std::sqrt((dx * dx) + (dy * dy) + (dz * dz)),
                            qrics::common::Vec3{clamped_x, clamped_y, clamped_z}};
  }

  double dx = center.x - position.x;
  double dy = center.y - position.y;
  double dz = center.z - position.z;
  if (obstacle.geometry_type == scenario::SceneGeometryType::Cylinder) {
    const double half_height = std::max(0.0, obstacle.height_m) * 0.5;
    const double clamped_z = std::clamp(position.z, center.z - half_height, center.z + half_height);
    dz = center.z - clamped_z;
  }
  const double center_distance = std::sqrt((dx * dx) + (dy * dy) + (dz * dz));
  const double radius = std::max(0.0, obstacle.radius_m);
  const double clearance = std::max(0.0, center_distance - radius);
  const double scale = center_distance <= 1.0e-9 ? 0.0 : radius / center_distance;
  return ObstacleDistance{clearance,
                          qrics::common::Vec3{center.x - (dx * scale), center.y - (dy * scale),
                                              center.z - (dz * scale)}};
}

[[nodiscard]] bool is_body_velocity_action(const control::SafeAction& action) {
  return action.action_type == control::ActionType::BodyVelocity;
}

[[nodiscard]] bool is_stop_like_action(const control::SafeAction& action) {
  return action.action_type == control::ActionType::Stop ||
         action.action_type == control::ActionType::SafeStand ||
         action.action_type == control::ActionType::Replan ||
         action.decision == control::SafetyDecision::EmergencyStop ||
         action.decision == control::SafetyDecision::SafeStand ||
         action.decision == control::SafetyDecision::Replan;
}

}  // namespace

std::string to_string(LocalBackendKind kind) {
  switch (kind) {
    case LocalBackendKind::Minimal:
      return "minimal";
    case LocalBackendKind::MuJoCo:
      return "mujoco";
    case LocalBackendKind::Webots:
      return "webots";
    case LocalBackendKind::IsaacLab:
      return "isaac_lab";
  }
  return "unknown";
}

qrics::common::Result<LocalBackendKind> parse_local_backend_kind(const std::string& backend_name) {
  if (backend_name == "minimal") {
    return qrics::common::Result<LocalBackendKind>::success(LocalBackendKind::Minimal);
  }
  if (backend_name == "mujoco") {
    return qrics::common::Result<LocalBackendKind>::success(LocalBackendKind::MuJoCo);
  }
  if (backend_name == "webots") {
    return qrics::common::Result<LocalBackendKind>::success(LocalBackendKind::Webots);
  }
  if (backend_name == "isaac_lab" || backend_name == "isaac-lab") {
    return qrics::common::Result<LocalBackendKind>::success(LocalBackendKind::IsaacLab);
  }
  return qrics::common::Result<LocalBackendKind>::failure({make_error(
      "UNKNOWN_LOCAL_BACKEND", "Unsupported local simulation backend: " + backend_name)});
}

std::vector<LocalBackendDescriptor> supported_local_backends() {
  return {
      LocalBackendDescriptor{LocalBackendKind::Minimal, "minimal", true, false, false, false,
                             "docs/runbooks/sim_backends.md"},
      LocalBackendDescriptor{LocalBackendKind::MuJoCo, "mujoco", true, false, true, true,
                             "docs/runbooks/sim_backends.md"},
      LocalBackendDescriptor{LocalBackendKind::Webots, "webots", true, true, true, true,
                             "docs/runbooks/webots_local_backend.md"},
      LocalBackendDescriptor{LocalBackendKind::IsaacLab, "isaac_lab", false, true, true, true,
                             "docs/runbooks/isaac_lab_setup.md"},
  };
}

qrics::common::Result<LocalRuntimeProfile> get_local_runtime_profile(
    const std::string& profile_name) {
  if (profile_name == "headless_fast") {
    return qrics::common::Result<LocalRuntimeProfile>::success(
        LocalRuntimeProfile{"headless_fast", RenderMode::None, 0.004, 10, true, true, 120.0});
  }
  if (profile_name == "balanced_visual") {
    return qrics::common::Result<LocalRuntimeProfile>::success(
        LocalRuntimeProfile{"balanced_visual", RenderMode::Viewer, 0.002, 10, true, true, 60.0});
  }
  if (profile_name == "rich_demo") {
    return qrics::common::Result<LocalRuntimeProfile>::success(
        LocalRuntimeProfile{"rich_demo", RenderMode::Viewer, 0.002, 10, true, true, 60.0});
  }
  if (profile_name == "webots_fast") {
    return qrics::common::Result<LocalRuntimeProfile>::success(
        LocalRuntimeProfile{"webots_fast", RenderMode::Viewer, 0.016, 2, true, true, 90.0});
  }
  return qrics::common::Result<LocalRuntimeProfile>::failure({make_error(
      "UNKNOWN_RUNTIME_PROFILE", "Unsupported local runtime profile: " + profile_name)});
}

KinematicLocalSimulationAdapter::KinematicLocalSimulationAdapter(LocalSimulationConfig config)
    : local_config_(std::move(config)) {}

std::string KinematicLocalSimulationAdapter::name() const {
  return local_config_.adapter_name + ":" + to_string(local_config_.backend);
}

AdapterState KinematicLocalSimulationAdapter::state() const {
  return state_;
}

qrics::common::Result<AdapterState> KinematicLocalSimulationAdapter::initialize(
    const AdapterConfig& config) {
  adapter_config_ = config;
  if (!config.adapter_name.empty()) {
    local_config_.adapter_name = config.adapter_name;
  }
  if (!config.adapter_version.empty()) {
    local_config_.adapter_version = config.adapter_version;
  }
  if (!config.schema_version.empty()) {
    local_config_.schema_version = config.schema_version;
  }
  state_ = AdapterState::Initialized;
  return qrics::common::Result<AdapterState>::success(state_);
}

qrics::common::Result<AdapterState> KinematicLocalSimulationAdapter::load_scene(
    const scenario::SceneProfile& scene_profile) {
  if (state_ != AdapterState::Initialized && state_ != AdapterState::SceneLoaded &&
      state_ != AdapterState::Running && state_ != AdapterState::Stopped) {
    return invalid_state("BACKEND_NOT_INITIALIZED",
                         "initialize() must be called before load_scene().");
  }
  scene_profile_ = scene_profile;
  state_ = AdapterState::SceneLoaded;
  return qrics::common::Result<AdapterState>::success(state_);
}

qrics::common::Result<ObservationPacket> KinematicLocalSimulationAdapter::reset() {
  if (state_ != AdapterState::SceneLoaded) {
    return qrics::common::Result<ObservationPacket>::failure(
        {make_error("SCENE_NOT_LOADED", "load_scene() must be called before reset().")});
  }

  timestamp_ns_ = 0;
  position_ = qrics::common::Vec3{0.0, 0.0, 0.35};
  yaw_rad_ = 0.0;
  linear_velocity_ = qrics::common::Vec3{};
  yaw_rate_radps_ = 0.0;
  state_ = AdapterState::Running;
  return qrics::common::Result<ObservationPacket>::success(make_observation());
}

qrics::common::Result<AdapterStepResult> KinematicLocalSimulationAdapter::step(
    const control::SafeAction& action) {
  if (state_ != AdapterState::Running) {
    return invalid_step("BACKEND_NOT_RUNNING", "reset() must be called before step().");
  }
  if (action.decision == control::SafetyDecision::Rejected) {
    return invalid_step("SAFE_ACTION_REJECTED", "Rejected SafeAction must not be stepped.");
  }

  const double dt_s = control_dt_s();
  if (is_stop_like_action(action)) {
    linear_velocity_ = qrics::common::Vec3{};
    yaw_rate_radps_ = 0.0;
  } else if (is_body_velocity_action(action)) {
    linear_velocity_ = action.body_velocity;
    yaw_rate_radps_ = action.yaw_rate_radps;
    position_.x += action.body_velocity.x * dt_s;
    position_.y += action.body_velocity.y * dt_s;
    position_.z = 0.35;
    yaw_rad_ += action.yaw_rate_radps * dt_s;
  } else {
    return invalid_step(
        "UNSUPPORTED_ACTION_TYPE",
        "Local simulation adapter accepts BodyVelocity, Stop, SafeStand and Replan actions.");
  }

  timestamp_ns_ += static_cast<qrics::common::TimestampNs>(dt_s * 1'000'000'000.0);
  AdapterStepResult result{};
  result.observation = make_observation();
  result.robot_state = make_robot_state();
  result.state = state_;
  return qrics::common::Result<AdapterStepResult>::success(result);
}

qrics::common::Result<ObservationPacket> KinematicLocalSimulationAdapter::observe() const {
  if (state_ != AdapterState::SceneLoaded && state_ != AdapterState::Running) {
    return qrics::common::Result<ObservationPacket>::failure(
        {make_error("BACKEND_NOT_RUNNING", "observe() requires a loaded scene.")});
  }
  return qrics::common::Result<ObservationPacket>::success(make_observation());
}

qrics::common::Result<RobotState> KinematicLocalSimulationAdapter::robot_state() const {
  if (state_ != AdapterState::SceneLoaded && state_ != AdapterState::Running) {
    return qrics::common::Result<RobotState>::failure(
        {make_error("BACKEND_NOT_RUNNING", "robot_state() requires a loaded scene.")});
  }
  return qrics::common::Result<RobotState>::success(make_robot_state());
}

qrics::common::Result<AdapterState> KinematicLocalSimulationAdapter::close() {
  state_ = AdapterState::Stopped;
  return qrics::common::Result<AdapterState>::success(state_);
}

qrics::common::Result<AdapterState> KinematicLocalSimulationAdapter::invalid_state(
    const std::string& code, const std::string& message) {
  return qrics::common::Result<AdapterState>::failure({make_error(code, message)});
}

qrics::common::Result<AdapterStepResult> KinematicLocalSimulationAdapter::invalid_step(
    const std::string& code, const std::string& message) {
  return qrics::common::Result<AdapterStepResult>::failure({make_error(code, message)});
}

ObservationPacket KinematicLocalSimulationAdapter::make_observation() const {
  const RobotState state = make_robot_state();
  ObservationPacket observation{};
  observation.observation_id = "local_obs_" + std::to_string(timestamp_ns_);
  observation.timestamp_ns = timestamp_ns_;
  observation.base_pose = state.pose;
  observation.linear_velocity = state.linear_velocity;
  observation.angular_velocity = state.angular_velocity;
  observation.contacts = state.contacts;
  observation.terrain_class = state.terrain_class;
  observation.imu.linear_acceleration = qrics::common::Vec3{0.0, 0.0, 9.81};
  observation.imu.angular_velocity = state.angular_velocity;
  observation.imu.orientation = state.pose.orientation;
  observation.imu.source_quality = local_config_.backend == LocalBackendKind::MuJoCo
                                       ? SourceQuality::Direct
                                       : SourceQuality::Estimated;
  observation.obstacle_state = obstacle_state();
  return observation;
}

RobotState KinematicLocalSimulationAdapter::make_robot_state() const {
  RobotState state{};
  state.timestamp_ns = timestamp_ns_;
  state.pose.position = position_;
  state.pose.orientation =
      qrics::common::Quaternion{std::cos(yaw_rad_ / 2.0), 0.0, 0.0, std::sin(yaw_rad_ / 2.0)};
  state.linear_velocity = linear_velocity_;
  state.angular_velocity = qrics::common::Vec3{0.0, 0.0, yaw_rate_radps_};
  state.contacts = {ContactState{"front_left", true, 25.0}, ContactState{"front_right", true, 25.0},
                    ContactState{"rear_left", true, 25.0}, ContactState{"rear_right", true, 25.0}};
  state.terrain_class = terrain_class();
  state.stability_state = StabilityState::Stable;
  state.risk_score = 0.0;
  return state;
}

TerrainClass KinematicLocalSimulationAdapter::terrain_class() const {
  const std::string& terrain = scene_profile_.terrain_pack;
  if (terrain == "flat") {
    return TerrainClass::Flat;
  }
  if (terrain == "slope") {
    return TerrainClass::Slope;
  }
  if (terrain == "gravel") {
    return TerrainClass::Gravel;
  }
  if (terrain == "stairs") {
    return TerrainClass::Stairs;
  }
  if (terrain == "low_friction") {
    return TerrainClass::LowFriction;
  }
  if (terrain == "mixed" || terrain == "mixed_terrain" || terrain == "mixed_terrain_pack") {
    if (position_.x < 0.75) {
      return TerrainClass::Flat;
    }
    if (position_.x < 1.50) {
      return TerrainClass::Gravel;
    }
    if (position_.x < 2.25) {
      return TerrainClass::Slope;
    }
    return TerrainClass::LowFriction;
  }
  return TerrainClass::Unknown;
}

ObstacleState KinematicLocalSimulationAdapter::obstacle_state() const {
  ObstacleState obstacle{};
  obstacle.source_quality = local_config_.backend == LocalBackendKind::Minimal
                                ? SourceQuality::Estimated
                                : SourceQuality::Direct;
  if (scene_profile_.obstacles.empty()) {
    return obstacle;
  }

  double nearest_clearance = std::numeric_limits<double>::infinity();
  qrics::common::Vec3 nearest_point{};
  bool found = false;
  for (const auto& candidate : scene_profile_.obstacles) {
    const ObstacleDistance distance = obstacle_distance(candidate, position_);
    if (distance.clearance < nearest_clearance) {
      nearest_clearance = distance.clearance;
      nearest_point = distance.nearest_point;
      found = true;
    }
  }

  if (!found) {
    return obstacle;
  }
  obstacle.obstacle_detected = true;
  obstacle.nearest_distance_m = nearest_clearance;
  obstacle.nearest_point = nearest_point;
  return obstacle;
}

double KinematicLocalSimulationAdapter::control_dt_s() const {
  return local_config_.runtime_profile.physics_timestep_s *
         static_cast<double>(std::max(1, local_config_.runtime_profile.control_decimation));
}

}  // namespace qrics::simulation