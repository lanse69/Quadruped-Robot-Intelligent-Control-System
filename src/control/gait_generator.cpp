// 地形感知步态生成器实现

#include "qrics/control/gait_generator.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numbers>
#include <string>
#include <utility>
#include <vector>

namespace qrics::control {

namespace {

constexpr double kNanosecondsPerSecond = 1'000'000'000.0;

struct FootNominal final {
  const char* name;
  qrics::common::Vec3 position;
  double phase_offset;
};

[[nodiscard]] std::array<FootNominal, 4> foot_layout_for_gait(GaitType gait) {
  if (gait == GaitType::Crawl) {
    return {FootNominal{"front_left", qrics::common::Vec3{0.22, 0.12, -0.35}, 0.00},
            FootNominal{"rear_right", qrics::common::Vec3{-0.22, -0.12, -0.35}, 0.25},
            FootNominal{"front_right", qrics::common::Vec3{0.22, -0.12, -0.35}, 0.50},
            FootNominal{"rear_left", qrics::common::Vec3{-0.22, 0.12, -0.35}, 0.75}};
  }
  return {FootNominal{"front_left", qrics::common::Vec3{0.22, 0.12, -0.35}, 0.00},
          FootNominal{"rear_right", qrics::common::Vec3{-0.22, -0.12, -0.35}, 0.00},
          FootNominal{"front_right", qrics::common::Vec3{0.22, -0.12, -0.35}, 0.50},
          FootNominal{"rear_left", qrics::common::Vec3{-0.22, 0.12, -0.35}, 0.50}};
}

[[nodiscard]] double clamp01(double value) noexcept {
  return std::clamp(value, 0.0, 1.0);
}

[[nodiscard]] double wrap01(double value) noexcept {
  const double wrapped = value - std::floor(value);
  return wrapped < 0.0 ? wrapped + 1.0 : wrapped;
}

[[nodiscard]] double planar_speed(const qrics::common::Vec3& velocity) noexcept {
  return std::sqrt((velocity.x * velocity.x) + (velocity.y * velocity.y));
}

[[nodiscard]] bool cautious_terrain(qrics::simulation::TerrainClass terrain) noexcept {
  return terrain == qrics::simulation::TerrainClass::Slope ||
         terrain == qrics::simulation::TerrainClass::Gravel ||
         terrain == qrics::simulation::TerrainClass::Stairs ||
         terrain == qrics::simulation::TerrainClass::LowFriction ||
         terrain == qrics::simulation::TerrainClass::Unknown;
}

[[nodiscard]] qrics::simulation::TerrainClass effective_terrain(
    const qrics::simulation::RobotState& robot_state,
    const qrics::simulation::ObservationPacket& observation) noexcept {
  if (observation.terrain_class != qrics::simulation::TerrainClass::Unknown) {
    return observation.terrain_class;
  }
  return robot_state.terrain_class;
}

[[nodiscard]] double swing_progress(double local_phase, double duty_factor) noexcept {
  if (local_phase <= duty_factor) {
    return 0.0;
  }
  return clamp01((local_phase - duty_factor) / std::max(1.0e-6, 1.0 - duty_factor));
}

[[nodiscard]] JointCommand joint_hint(const std::string& joint_name, double position) {
  JointCommand command{};
  command.joint_name = joint_name;
  command.target_position_rad = position;
  return command;
}

[[nodiscard]] bool foot_is_swing(const FootstepTarget& foot) noexcept {
  return foot.phase == FootPhase::Swing;
}

[[nodiscard]] std::string foot_prefix(const std::string& foot_name) {
  if (foot_name == "front_left") {
    return "fl";
  }
  if (foot_name == "front_right") {
    return "fr";
  }
  if (foot_name == "rear_left") {
    return "rl";
  }
  return "rr";
}

}  // namespace

TerrainAwareGaitGenerator::TerrainAwareGaitGenerator(GaitGeneratorConfig config)
    : config_(config) {}

qrics::common::Result<GaitGeneratorResult> TerrainAwareGaitGenerator::generate(
    const GaitGeneratorRequest& request) const {
  if (request.task_node_id.empty()) {
    return qrics::common::Result<GaitGeneratorResult>::failure({qrics::common::Error{
        "TASK_NODE_ID_EMPTY", "GaitGeneratorRequest.task_node_id must not be empty"}});
  }

  const auto terrain = effective_terrain(request.robot_state, request.observation);
  const double speed_mps = planar_speed(request.desired_body_velocity);
  const GaitType gait = select_gait(terrain, speed_mps, request.desired_yaw_rate_radps);
  const double frequency_hz = gait_frequency_hz(gait, terrain, speed_mps);
  const double duty = duty_factor(gait);
  const double phase =
      frequency_hz <= 0.0
          ? 0.0
          : wrap01((static_cast<double>(request.timestamp_ns) / kNanosecondsPerSecond) *
                   frequency_hz);

  GaitGeneratorResult result{};
  result.hint.enabled = true;
  result.hint.gait_type = gait;
  result.hint.gait_name = to_string(gait);
  result.hint.normalized_phase = phase;
  result.hint.step_frequency_hz = frequency_hz;
  result.hint.duty_factor = duty;
  result.hint.body_height_m = body_height_m(gait, terrain);
  result.hint.stride_length_m =
      std::min(config_.max_stride_length_m,
               std::abs(request.desired_body_velocity.x) / std::max(0.35, frequency_hz));
  result.hint.lateral_stride_m =
      std::min(config_.max_lateral_stride_m,
               std::abs(request.desired_body_velocity.y) / std::max(0.35, frequency_hz));
  result.hint.swing_height_m =
      gait == GaitType::Stand
          ? 0.0
          : std::min(config_.max_swing_height_m, 0.025 + 0.10 * result.hint.stride_length_m);
  result.hint.feet = foot_targets(gait, GaitTiming{phase, duty}, request.desired_body_velocity,
                                  request.desired_yaw_rate_radps);
  result.joint_position_hints = joint_hints(gait, result.hint.feet);
  result.reason = "Generate " + result.hint.gait_name + " gait from terrain-aware velocity";
  return qrics::common::Result<GaitGeneratorResult>::success(std::move(result));
}

GaitType TerrainAwareGaitGenerator::select_gait(qrics::simulation::TerrainClass terrain,
                                                double speed_mps,
                                                double yaw_rate_radps) const noexcept {
  if (speed_mps < config_.min_walk_speed_mps && std::abs(yaw_rate_radps) < 0.05) {
    return GaitType::Stand;
  }
  if (terrain == qrics::simulation::TerrainClass::Stairs ||
      terrain == qrics::simulation::TerrainClass::LowFriction || speed_mps < 0.12) {
    return GaitType::Crawl;
  }
  if (terrain == qrics::simulation::TerrainClass::Slope ||
      terrain == qrics::simulation::TerrainClass::Gravel ||
      terrain == qrics::simulation::TerrainClass::Unknown) {
    return GaitType::CautiousTrot;
  }
  return GaitType::Trot;
}

double TerrainAwareGaitGenerator::gait_frequency_hz(GaitType gait,
                                                    qrics::simulation::TerrainClass terrain,
                                                    double speed_mps) const noexcept {
  if (gait == GaitType::Stand) {
    return 0.0;
  }

  const double base = [this, gait]() noexcept {
    switch (gait) {
      case GaitType::Crawl:
      case GaitType::Recovery:
        return config_.crawl_frequency_hz;
      case GaitType::CautiousTrot:
        return config_.cautious_trot_frequency_hz;
      case GaitType::Trot:
        return config_.trot_frequency_hz;
      case GaitType::Stand:
        return config_.stand_frequency_hz;
    }
    return config_.crawl_frequency_hz;
  }();
  const double speed_boost = std::clamp(speed_mps * 0.75, 0.0, 0.45);
  const double terrain_scale = cautious_terrain(terrain) ? 0.88 : 1.0;
  return std::clamp((base + speed_boost) * terrain_scale, 0.30, config_.max_frequency_hz);
}

double TerrainAwareGaitGenerator::duty_factor(GaitType gait) const noexcept {
  switch (gait) {
    case GaitType::Stand:
      return 1.0;
    case GaitType::Crawl:
      return std::clamp(config_.crawl_duty_factor, 0.55, 0.90);
    case GaitType::CautiousTrot:
    case GaitType::Recovery:
      return std::clamp(config_.cautious_duty_factor, 0.55, 0.82);
    case GaitType::Trot:
      return std::clamp(config_.trot_duty_factor, 0.50, 0.75);
  }
  return 1.0;
}

double TerrainAwareGaitGenerator::body_height_m(
    GaitType gait, qrics::simulation::TerrainClass terrain) const noexcept {
  if (gait == GaitType::Stand) {
    return config_.nominal_body_height_m;
  }
  const double terrain_drop =
      cautious_terrain(terrain) ? config_.body_height_drop_on_cautious_terrain_m : 0.0;
  return std::max(0.25, config_.nominal_body_height_m - terrain_drop);
}

std::vector<FootstepTarget> TerrainAwareGaitGenerator::foot_targets(
    GaitType gait, GaitTiming timing, const qrics::common::Vec3& velocity,
    double yaw_rate_radps) const {
  std::vector<FootstepTarget> feet;
  feet.reserve(4);
  const double forward_stride =
      std::clamp(velocity.x * 0.28, -config_.max_stride_length_m, config_.max_stride_length_m);
  const double lateral_stride =
      std::clamp(velocity.y * 0.22, -config_.max_lateral_stride_m, config_.max_lateral_stride_m);
  const double turn_stride = std::clamp(yaw_rate_radps * 0.035, -0.035, 0.035);
  const double swing_height = gait == GaitType::Stand ? 0.0 : config_.max_swing_height_m;

  for (const auto& foot : foot_layout_for_gait(gait)) {
    const double local_phase = wrap01(timing.normalized_phase + foot.phase_offset);
    const bool swing = gait != GaitType::Stand && local_phase > timing.duty_factor;
    const double swing_s = swing_progress(local_phase, timing.duty_factor);
    const double swing_lift = std::sin(std::numbers::pi * swing_s) * swing_height;
    const double direction = foot.position.x >= 0.0 ? 1.0 : -1.0;
    const double lateral_sign = foot.position.y >= 0.0 ? 1.0 : -1.0;

    FootstepTarget target{};
    target.foot_name = foot.name;
    target.phase = swing ? FootPhase::Swing : FootPhase::Stance;
    target.nominal_position_body = foot.position;
    target.target_position_body = foot.position;
    target.target_position_body.x +=
        swing ? forward_stride * (swing_s - 0.5) : -0.25 * forward_stride;
    target.target_position_body.y += lateral_stride + (turn_stride * direction * lateral_sign);
    target.target_position_body.z += swing_lift;
    target.phase_in_cycle = local_phase;
    target.duty_factor = timing.duty_factor;
    feet.push_back(std::move(target));
  }
  return feet;
}

std::vector<JointCommand> TerrainAwareGaitGenerator::joint_hints(
    GaitType gait, const std::vector<FootstepTarget>& feet) {
  std::vector<JointCommand> hints;
  hints.reserve(12);
  const bool stand = gait == GaitType::Stand;
  for (const auto& foot : feet) {
    const std::string prefix = foot_prefix(foot.foot_name);
    const bool left_side = foot.foot_name == "front_left" || foot.foot_name == "rear_left";
    const bool front = foot.foot_name == "front_left" || foot.foot_name == "front_right";
    const bool swing = foot_is_swing(foot);
    const double hip_nominal = left_side ? 0.10 : -0.10;
    const double thigh_nominal = front ? 0.65 : 0.70;
    const double calf_nominal = front ? -1.25 : -1.30;
    const double hip_delta = std::clamp(foot.target_position_body.y * 0.35, -0.08, 0.08);
    const double phase_shape =
        swing ? std::sin(std::numbers::pi * swing_progress(foot.phase_in_cycle, foot.duty_factor))
              : 0.0;
    hints.push_back(joint_hint(prefix + "_hip_joint", hip_nominal + hip_delta));
    hints.push_back(
        joint_hint(prefix + "_thigh_joint", thigh_nominal + (stand ? 0.0 : 0.16 * phase_shape)));
    hints.push_back(
        joint_hint(prefix + "_calf_joint", calf_nominal - (stand ? 0.0 : 0.10 * phase_shape)));
  }
  return hints;
}

std::string to_string(GaitType gait_type) {
  switch (gait_type) {
    case GaitType::Stand:
      return "stand";
    case GaitType::Crawl:
      return "crawl";
    case GaitType::Trot:
      return "trot";
    case GaitType::CautiousTrot:
      return "cautious_trot";
    case GaitType::Recovery:
      return "recovery";
  }
  return "unknown";
}

std::string to_string(FootPhase foot_phase) {
  switch (foot_phase) {
    case FootPhase::Stance:
      return "stance";
    case FootPhase::Swing:
      return "swing";
  }
  return "unknown";
}

}  // namespace qrics::control