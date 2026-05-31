// 告警事件模型实现

#include "qrics/monitoring/alert_event.hpp"

namespace qrics::monitoring {

namespace {

[[nodiscard]] qrics::events::EventSeverity to_event_severity(qrics::safety::Severity severity) {
  switch (severity) {
    case qrics::safety::Severity::Info:
      return qrics::events::EventSeverity::Info;
    case qrics::safety::Severity::Warning:
      return qrics::events::EventSeverity::Warning;
    case qrics::safety::Severity::Error:
      return qrics::events::EventSeverity::Error;
    case qrics::safety::Severity::Critical:
      return qrics::events::EventSeverity::Critical;
  }
  return qrics::events::EventSeverity::Error;
}

[[nodiscard]] std::string first_violation_message(const qrics::safety::SafetyEvent& safety_event) {
  if (!safety_event.violation_list.empty()) {
    return safety_event.violation_list.front();
  }
  return "Safety event raised";
}

}  // namespace

AlertEvent make_alert_from_safety_event(const qrics::safety::SafetyEvent& safety_event) {
  AlertEvent alert{};
  alert.alert_id = "alert_" + safety_event.event_id;
  alert.run_id = safety_event.run_id;
  alert.alert_type = AlertType::Safety;
  alert.severity = safety_event.severity;
  alert.message = first_violation_message(safety_event);
  alert.source_event_ref = qrics::common::ResourceRef{safety_event.event_id, "0.1.0"};
  alert.timestamp_ns = safety_event.timestamp_ns;
  return alert;
}

qrics::events::EventRecord make_event_record_from_alert(const AlertEvent& alert) {
  qrics::events::EventRecord record{};
  record.event_id = "event_" + alert.alert_id;
  record.run_id = alert.run_id;
  record.event_type = qrics::events::EventType::Alert;
  record.severity = to_event_severity(alert.severity);
  record.source = "AlertManager";
  record.message = alert.message;
  record.subject_ref = alert.source_event_ref;
  record.timestamp_ns = alert.timestamp_ns;
  return record;
}

}  // namespace qrics::monitoring