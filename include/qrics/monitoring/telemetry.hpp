// 运行遥测模型

#pragma once

#include <cstdint>
#include <string>

#include "qrics/control/control_state.hpp"
#include "qrics/events/event_sink.hpp"
#include "qrics/simulation/simulation_adapter.hpp"

namespace qrics::monitoring {

enum class TelemetrySource : std::uint8_t { Control, Adapter, TaskExecutor };

struct TelemetryFrame final {
  std::string frame_id{};
  std::string run_id{};
  TelemetrySource source{TelemetrySource::Control};
  qrics::common::TimestampNs timestamp_ns{0};
  qrics::control::ControlRunState control_state{qrics::control::ControlRunState::Created};
  qrics::simulation::AdapterState adapter_state{qrics::simulation::AdapterState::Created};
  std::string current_node_id{};
  int completed_node_count{0};
  int control_step_count{0};
  double risk_score{0.0};
  std::string summary{};
};

[[nodiscard]] TelemetryFrame make_control_telemetry_frame(
    const qrics::control::TaskExecutionSnapshot& snapshot,
    qrics::simulation::AdapterState adapter_state);

[[nodiscard]] qrics::events::EventRecord make_event_record_from_telemetry(
    const TelemetryFrame& frame);

}  // namespace qrics::monitoring