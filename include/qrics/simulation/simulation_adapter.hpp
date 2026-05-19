// Simulation Adapter 抽象接口

#pragma once

#include <cstdint>
#include <string>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/scenario/scene_profile.hpp"
#include "qrics/simulation/observation.hpp"

namespace qrics::simulation {

enum class AdapterState : std::uint8_t {
  Created,
  Initialized,
  SceneLoaded,
  Running,
  Stopped,
  Error
};

struct AdapterConfig {
  std::string adapter_name{"placeholder"};
  std::string adapter_version{"0.1.0"};
  std::string schema_version{"0.1.0"};
};

struct AdapterStepResult final {
  ObservationPacket observation{};
  RobotState robot_state{};
  AdapterState state{AdapterState::Running};
};

class SimulationAdapter {
 public:
  virtual ~SimulationAdapter() = default;

  [[nodiscard]] virtual std::string name() const = 0;
  [[nodiscard]] virtual AdapterState state() const = 0;

  [[nodiscard]] virtual common::Result<AdapterState> initialize(const AdapterConfig& config) = 0;

  [[nodiscard]] virtual common::Result<AdapterState> load_scene(
      const scenario::SceneProfile& scene_profile) = 0;

  [[nodiscard]] virtual common::Result<ObservationPacket> reset() = 0;

  [[nodiscard]] virtual common::Result<AdapterStepResult> step(
      const control::SafeAction& action) = 0;

  [[nodiscard]] virtual common::Result<ObservationPacket> observe() const = 0;

  [[nodiscard]] virtual common::Result<RobotState> robot_state() const = 0;

  [[nodiscard]] virtual common::Result<AdapterState> close() = 0;
};

}  // namespace qrics::simulation