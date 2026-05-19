// 场景领域对象

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::scenario {

enum class SceneStatus : std::uint8_t { Draft, Validated, Baseline, Locked, Archived };

struct SensorProfile final {
  bool camera_enabled{false};
  bool depth_camera_enabled{false};
  bool lidar_enabled{false};
  bool imu_enabled{true};
  bool contact_sensor_enabled{true};
  double sample_rate_hz{100.0};
  std::string source_quality{"direct"};
};

struct RandomizationProfile final {
  bool enabled{false};
  double friction_min{0.5};
  double friction_max{1.2};
  double mass_scale_min{0.9};
  double mass_scale_max{1.1};
  double sensor_noise_std{0.0};
  std::uint64_t seed{42};
};

struct ForbiddenZone final {
  std::string zone_id{};
  std::vector<qrics::common::Vec3> polygon{};
};

struct Checkpoint final {
  std::string checkpoint_id{};
  qrics::common::Pose pose{};
  double dwell_time_s{0.0};
};

struct SceneProfile final {
  std::string scene_id{};
  std::string version{};
  std::string name{};
  std::string terrain_pack{};
  std::vector<std::string> obstacle_set{};
  std::vector<Checkpoint> checkpoints{};
  std::vector<ForbiddenZone> forbidden_zones{};
  SensorProfile sensor_profile{};
  RandomizationProfile randomization_profile{};
  qrics::common::Checksum checksum{};
  SceneStatus status{SceneStatus::Draft};
};

}  // namespace qrics::scenario