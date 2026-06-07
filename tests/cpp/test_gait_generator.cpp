#include <algorithm>
#include <string>

#include "qrics/control/gait_generator.hpp"

namespace {

[[nodiscard]] qrics::control::GaitGeneratorRequest make_request(
    qrics::simulation::TerrainClass terrain, const qrics::common::Vec3& velocity,
    qrics::common::TimestampNs timestamp_ns = 1'500'000'000) {
  qrics::control::GaitGeneratorRequest request{};
  request.run_id = "gait_test_run";
  request.task_node_id = "node_move";
  request.policy_ref = qrics::common::ResourceRef{"policy", "0.1.0"};
  request.desired_body_velocity = velocity;
  request.robot_state.terrain_class = terrain;
  request.observation.terrain_class = terrain;
  request.timestamp_ns = timestamp_ns;
  return request;
}

[[nodiscard]] int validate_common(const qrics::control::GaitGeneratorResult& result) {
  if (!result.hint.enabled) {
    return 10;
  }
  if (result.hint.feet.size() != 4U) {
    return 11;
  }
  if (result.joint_position_hints.size() != 12U) {
    return 12;
  }
  if (result.reason.empty()) {
    return 13;
  }
  return 0;
}

[[nodiscard]] int validate_stand(const qrics::control::GaitGeneratorResult& result) {
  if (result.hint.gait_type != qrics::control::GaitType::Stand) {
    return 30;
  }
  if (result.hint.gait_name != "stand") {
    return 31;
  }
  if (result.hint.step_frequency_hz != 0.0) {
    return 32;
  }
  const auto swing = std::count_if(result.hint.feet.begin(), result.hint.feet.end(),
                                   [](const qrics::control::FootstepTarget& foot) {
                                     return foot.phase == qrics::control::FootPhase::Swing;
                                   });
  if (swing != 0) {
    return 33;
  }
  return 0;
}

}  // namespace

int main() {
  qrics::control::TerrainAwareGaitGenerator generator{};

  const auto flat = generator.generate(
      make_request(qrics::simulation::TerrainClass::Flat, qrics::common::Vec3{0.45, 0.0, 0.0}));
  if (!flat.ok) {
    return 1;
  }
  if (const int common = validate_common(flat.value); common != 0) {
    return common;
  }
  if (flat.value.hint.gait_type != qrics::control::GaitType::Trot ||
      flat.value.hint.gait_name != "trot") {
    return 2;
  }
  if (flat.value.hint.step_frequency_hz <= 1.0) {
    return 3;
  }

  const auto low_friction = generator.generate(make_request(
      qrics::simulation::TerrainClass::LowFriction, qrics::common::Vec3{0.35, 0.0, 0.0}));
  if (!low_friction.ok) {
    return 4;
  }
  if (const int common = validate_common(low_friction.value); common != 0) {
    return common;
  }
  if (low_friction.value.hint.gait_type != qrics::control::GaitType::Crawl) {
    return 5;
  }
  if (low_friction.value.hint.duty_factor < 0.70) {
    return 6;
  }
  if (low_friction.value.hint.step_frequency_hz >= flat.value.hint.step_frequency_hz) {
    return 7;
  }

  const auto stand = generator.generate(
      make_request(qrics::simulation::TerrainClass::Flat, qrics::common::Vec3{0.0, 0.0, 0.0}));
  if (!stand.ok) {
    return 8;
  }
  if (const int common = validate_common(stand.value); common != 0) {
    return common;
  }
  if (const int stand_code = validate_stand(stand.value); stand_code != 0) {
    return stand_code;
  }

  auto invalid =
      make_request(qrics::simulation::TerrainClass::Flat, qrics::common::Vec3{0.40, 0.0, 0.0});
  invalid.task_node_id.clear();
  const auto invalid_result = generator.generate(invalid);
  if (invalid_result.ok || invalid_result.errors.empty() ||
      invalid_result.errors.front().code != "TASK_NODE_ID_EMPTY") {
    return 9;
  }

  return 0;
}