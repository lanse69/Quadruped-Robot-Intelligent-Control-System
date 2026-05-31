// 告警事件模型

#pragma once

#include <cstdint>
#include <string>

#include "qrics/events/event_sink.hpp"
#include "qrics/safety/safety_event.hpp"

namespace qrics::monitoring {

enum class AlertType : std::uint8_t { Safety, ControlFailed, AdapterError, AuditWriteFailed };

struct AlertEvent final {
  std::string alert_id{};
  std::string run_id{};
  AlertType alert_type{AlertType::Safety};
  qrics::safety::Severity severity{qrics::safety::Severity::Info};
  std::string message{};
  qrics::common::ResourceRef source_event_ref{};
  qrics::common::TimestampNs timestamp_ns{0};
};

[[nodiscard]] AlertEvent make_alert_from_safety_event(
    const qrics::safety::SafetyEvent& safety_event);

[[nodiscard]] qrics::events::EventRecord make_event_record_from_alert(const AlertEvent& alert);

}  // namespace qrics::monitoring