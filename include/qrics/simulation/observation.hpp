// 观测与机器人状态模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::simulation {

enum class SourceQuality : std::uint8_t { Direct, Estimated, Missing };

enum class TerrainClass : std::uint8_t { Unknown, Flat, Slope, Gravel, Stairs, LowFriction };

struct ImuSample final {
  qrics::common::Vec3 linear_acceleration{};
  qrics::common::Vec3 angular_velocity{};
  qrics::common::Quaternion orientation{};
  SourceQuality source_quality{SourceQuality::Direct};
};

struct ContactState final {
  std::string foot_name{};
  bool in_contact{false};
  double normal_force_n{0.0};
};

struct ObstacleState final {
  bool obstacle_detected{false};
  double nearest_distance_m{0.0};
  qrics::common::Vec3 nearest_point{};
  SourceQuality source_quality{SourceQuality::Estimated};
};

struct ObservationPacket final {
  std::string observation_id{};
  qrics::common::TimestampNs timestamp_ns{0};
  ImuSample imu{};
  std::vector<ContactState> contacts{};
  qrics::common::Pose base_pose{};
  qrics::common::Vec3 linear_velocity{};
  qrics::common::Vec3 angular_velocity{};
  TerrainClass terrain_class{TerrainClass::Unknown};
  ObstacleState obstacle_state{};
};

enum class StabilityState : std::uint8_t { Unknown, Stable, Unstable, Fallen, Recovering };

struct RobotState final {
  qrics::common::TimestampNs timestamp_ns{0};
  qrics::common::Pose pose{};
  qrics::common::Vec3 linear_velocity{};
  qrics::common::Vec3 angular_velocity{};
  std::vector<ContactState> contacts{};
  TerrainClass terrain_class{TerrainClass::Unknown};
  StabilityState stability_state{StabilityState::Unknown};
  double risk_score{0.0};
};

}  // namespace qrics::simulation