// 障碍规避：在安全门控前对路径跟踪动作进行局部调制或重规划建议

#pragma once

#include <string>

#include "qrics/control/action.hpp"
#include "qrics/simulation/observation.hpp"

namespace qrics::control {

struct ObstacleAvoidanceConfig final {
  double hard_stop_distance_m{0.25};
  double warning_distance_m{0.80};
  double lateral_escape_speed_mps{0.20};
  double forward_slowdown_scale{0.35};
};

struct ObstacleAvoidanceRequest final {
  ActionProposal proposal{};
  qrics::simulation::ObservationPacket observation{};
};

struct ObstacleAvoidanceResult final {
  ActionProposal proposal{};
  bool adjusted{false};
  bool replan_required{false};
  std::string reason{};
};

class ObstacleAvoidance {
 public:
  virtual ~ObstacleAvoidance() = default;

  [[nodiscard]] virtual ObstacleAvoidanceResult apply(
      const ObstacleAvoidanceRequest& request) const = 0;
};

class SimpleObstacleAvoidance final : public ObstacleAvoidance {
 public:
  explicit SimpleObstacleAvoidance(ObstacleAvoidanceConfig config = {});

  [[nodiscard]] ObstacleAvoidanceResult apply(
      const ObstacleAvoidanceRequest& request) const override;

 private:
  ObstacleAvoidanceConfig config_{};
};

}  // namespace qrics::control