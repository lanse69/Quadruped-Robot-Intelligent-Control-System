// 地形感知步态生成器：将安全门控前的机体速度建议转换为步态提示与足端相位证据

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/simulation/observation.hpp"

namespace qrics::control {

struct GaitGeneratorConfig final {
  double nominal_body_height_m{0.35};
  double stand_frequency_hz{0.0};
  double crawl_frequency_hz{0.85};
  double cautious_trot_frequency_hz{1.15};
  double trot_frequency_hz{1.55};
  double max_frequency_hz{2.10};
  double min_walk_speed_mps{0.035};
  double max_stride_length_m{0.18};
  double max_lateral_stride_m{0.10};
  double max_swing_height_m{0.055};
  double crawl_duty_factor{0.78};
  double trot_duty_factor{0.58};
  double cautious_duty_factor{0.66};
  double body_height_drop_on_cautious_terrain_m{0.025};
};

struct GaitGeneratorRequest final {
  std::string run_id{};
  std::string task_node_id{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::Vec3 desired_body_velocity{};
  double desired_yaw_rate_radps{0.0};
  qrics::simulation::RobotState robot_state{};
  qrics::simulation::ObservationPacket observation{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct GaitGeneratorResult final {
  LocomotionHint hint{};
  std::vector<JointCommand> joint_position_hints{};
  std::string reason{};
};

class GaitGenerator {
 public:
  virtual ~GaitGenerator() = default;

  [[nodiscard]] virtual qrics::common::Result<GaitGeneratorResult> generate(
      const GaitGeneratorRequest& request) const = 0;
};

class TerrainAwareGaitGenerator final : public GaitGenerator {
 public:
  explicit TerrainAwareGaitGenerator(GaitGeneratorConfig config = {});

  [[nodiscard]] qrics::common::Result<GaitGeneratorResult> generate(
      const GaitGeneratorRequest& request) const override;

  [[nodiscard]] const GaitGeneratorConfig& config() const noexcept {
    return config_;
  }

 private:
  [[nodiscard]] GaitType select_gait(qrics::simulation::TerrainClass terrain, double speed_mps,
                                     double yaw_rate_radps) const noexcept;
  [[nodiscard]] double gait_frequency_hz(GaitType gait, qrics::simulation::TerrainClass terrain,
                                         double speed_mps) const noexcept;
  [[nodiscard]] double duty_factor(GaitType gait) const noexcept;
  [[nodiscard]] double body_height_m(GaitType gait,
                                     qrics::simulation::TerrainClass terrain) const noexcept;
  struct GaitTiming final {
    double normalized_phase{0.0};
    double duty_factor{1.0};
  };

  [[nodiscard]] std::vector<FootstepTarget> foot_targets(GaitType gait, GaitTiming timing,
                                                         const qrics::common::Vec3& velocity,
                                                         double yaw_rate_radps) const;
  [[nodiscard]] static std::vector<JointCommand> joint_hints(
      GaitType gait, const std::vector<FootstepTarget>& feet);

  GaitGeneratorConfig config_{};
};

[[nodiscard]] std::string to_string(GaitType gait_type);
[[nodiscard]] std::string to_string(FootPhase foot_phase);

}  // namespace qrics::control