// 路径跟踪控制器：将目标航点和机器人状态转换为安全门控前的 BodyVelocity 建议

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/control/control_state.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/task/task_script.hpp"

namespace qrics::control {

struct PathTrackerConfig final {
  double target_tolerance_m{0.15};
  double slow_down_radius_m{0.75};
  double flat_speed_mps{0.55};
  double slope_speed_mps{0.35};
  double gravel_speed_mps{0.30};
  double stairs_speed_mps{0.22};
  double low_friction_speed_mps{0.18};
  double unknown_speed_mps{0.25};
  double max_yaw_rate_radps{0.7};
  bool planar_tracking{true};
};

struct PathTrackRequest final {
  qrics::task::TaskNode task_node{};
  TaskWaypointContext target{};
  qrics::simulation::RobotState robot_state{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PathTrackResult final {
  ActionProposal proposal{};
  bool target_reached{false};
  double distance_to_target_m{0.0};
  double command_speed_mps{0.0};
  std::string reason{};
};

class PathTracker {
 public:
  virtual ~PathTracker() = default;

  [[nodiscard]] virtual qrics::common::Result<PathTrackResult> track(
      const PathTrackRequest& request) const = 0;
};

class PurePursuitPathTracker final : public PathTracker {
 public:
  explicit PurePursuitPathTracker(PathTrackerConfig config = {});

  [[nodiscard]] qrics::common::Result<PathTrackResult> track(
      const PathTrackRequest& request) const override;

  [[nodiscard]] const PathTrackerConfig& config() const noexcept {
    return config_;
  }

 private:
  [[nodiscard]] double terrain_speed_limit(qrics::simulation::TerrainClass terrain) const noexcept;
  [[nodiscard]] double command_speed(double distance_m,
                                     qrics::simulation::TerrainClass terrain) const noexcept;

  PathTrackerConfig config_{};
};

}  // namespace qrics::control