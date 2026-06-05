// 本机仿真后端枚举、运行配置与轻量 C++ 适配器

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/simulation/observation.hpp"
#include "qrics/simulation/simulation_adapter.hpp"

namespace qrics::simulation {

enum class LocalBackendKind : std::uint8_t { Minimal, MuJoCo, Webots, IsaacLab };

enum class RenderMode : std::uint8_t { None, Viewer, Offscreen };

struct LocalRuntimeProfile final {
  std::string name{"headless_fast"};
  RenderMode render_mode{RenderMode::None};
  double physics_timestep_s{0.004};
  int control_decimation{10};
  bool contact_sensor_enabled{true};
  bool imu_enabled{true};
  double max_demo_seconds{120.0};
};

struct LocalBackendDescriptor final {
  LocalBackendKind kind{LocalBackendKind::Minimal};
  std::string name{"minimal"};
  bool available_on_laptop{true};
  bool requires_external_process{false};
  bool physics_backend{false};
  bool visualization_backend{false};
  std::string runbook{};
};

[[nodiscard]] std::string to_string(LocalBackendKind kind);
[[nodiscard]] qrics::common::Result<LocalBackendKind> parse_local_backend_kind(
    const std::string& backend_name);
[[nodiscard]] std::vector<LocalBackendDescriptor> supported_local_backends();
[[nodiscard]] qrics::common::Result<LocalRuntimeProfile> get_local_runtime_profile(
    const std::string& profile_name);

struct LocalSimulationConfig final {
  LocalBackendKind backend{LocalBackendKind::Minimal};
  LocalRuntimeProfile runtime_profile{};
  std::string adapter_name{"local_cpp_sim"};
  std::string adapter_version{"0.3.0"};
  std::string schema_version{"0.3.0"};
};

class KinematicLocalSimulationAdapter final : public SimulationAdapter {
 public:
  explicit KinematicLocalSimulationAdapter(LocalSimulationConfig config = {});

  [[nodiscard]] std::string name() const override;
  [[nodiscard]] AdapterState state() const override;

  [[nodiscard]] qrics::common::Result<AdapterState> initialize(
      const AdapterConfig& config) override;
  [[nodiscard]] qrics::common::Result<AdapterState> load_scene(
      const scenario::SceneProfile& scene_profile) override;
  [[nodiscard]] qrics::common::Result<ObservationPacket> reset() override;
  [[nodiscard]] qrics::common::Result<AdapterStepResult> step(
      const control::SafeAction& action) override;
  [[nodiscard]] qrics::common::Result<ObservationPacket> observe() const override;
  [[nodiscard]] qrics::common::Result<RobotState> robot_state() const override;
  [[nodiscard]] qrics::common::Result<AdapterState> close() override;

 private:
  [[nodiscard]] static qrics::common::Result<AdapterState> invalid_state(
      const std::string& code, const std::string& message);
  [[nodiscard]] static qrics::common::Result<AdapterStepResult> invalid_step(
      const std::string& code, const std::string& message);
  [[nodiscard]] ObservationPacket make_observation() const;
  [[nodiscard]] RobotState make_robot_state() const;
  [[nodiscard]] TerrainClass terrain_class() const;
  [[nodiscard]] ObstacleState obstacle_state() const;
  [[nodiscard]] double control_dt_s() const;

  LocalSimulationConfig local_config_{};
  AdapterConfig adapter_config_{};
  scenario::SceneProfile scene_profile_{};
  AdapterState state_{AdapterState::Created};
  qrics::common::TimestampNs timestamp_ns_{0};
  qrics::common::Vec3 position_{};
  double yaw_rad_{0.0};
  qrics::common::Vec3 linear_velocity_{};
  double yaw_rate_radps_{0.0};
};

}  // namespace qrics::simulation