#include "qrics/events/event_sink.hpp"
#include "qrics/monitoring/alert_event.hpp"
#include "qrics/monitoring/telemetry.hpp"

namespace {

[[nodiscard]] qrics::control::TaskExecutionSnapshot make_snapshot() {
  qrics::control::TaskExecutionSnapshot snapshot{};
  snapshot.run_id = "run_event_sink";
  snapshot.run_state = qrics::control::ControlRunState::Running;
  snapshot.current_node_id = "node_move_A";
  snapshot.completed_node_count = 1;
  snapshot.control_step_count = 3;
  snapshot.last_robot_state.risk_score = 0.2;
  snapshot.reason = "control loop running";
  snapshot.updated_at_ns = 1000;
  return snapshot;
}

[[nodiscard]] qrics::safety::SafetyEvent make_safety_event() {
  qrics::safety::SafetyEvent event{};
  event.event_id = "safety_001";
  event.run_id = "run_event_sink";
  event.timestamp_ns = 1200;
  event.severity = qrics::safety::Severity::Warning;
  event.trigger_type = qrics::safety::TriggerType::VelocityLimit;
  event.violation_list.emplace_back("velocity clipped");
  event.action_taken = qrics::safety::SafetyActionTaken::ClipAction;
  return event;
}

}  // namespace

int main() {
  qrics::events::InMemoryEventSink sink{};

  const auto telemetry = qrics::monitoring::make_control_telemetry_frame(
      make_snapshot(), qrics::simulation::AdapterState::Running);
  auto appended_telemetry =
      sink.append(qrics::monitoring::make_event_record_from_telemetry(telemetry));
  if (!appended_telemetry.ok) {
    return 1;
  }

  const auto alert = qrics::monitoring::make_alert_from_safety_event(make_safety_event());
  auto appended_alert = sink.append(qrics::monitoring::make_event_record_from_alert(alert));
  if (!appended_alert.ok) {
    return 2;
  }

  qrics::events::EventQuery telemetry_query{};
  telemetry_query.run_id = "run_event_sink";
  telemetry_query.has_event_type = true;
  telemetry_query.event_type = qrics::events::EventType::Telemetry;
  const auto telemetry_events = sink.query(telemetry_query);
  if (!telemetry_events.ok || telemetry_events.value.size() != 1U) {
    return 3;
  }
  if (telemetry_events.value.front().message != "control loop running") {
    return 4;
  }

  qrics::events::EventQuery window_query{};
  window_query.run_id = "run_event_sink";
  window_query.has_start_time = true;
  window_query.start_time_ns = 1100;
  window_query.has_end_time = true;
  window_query.end_time_ns = 1300;
  const auto window_events = sink.query(window_query);
  if (!window_events.ok || window_events.value.size() != 1U) {
    return 5;
  }
  if (window_events.value.front().event_type != qrics::events::EventType::Alert) {
    return 6;
  }

  qrics::events::EventRecord invalid{};
  invalid.event_id = "event_invalid";
  invalid.timestamp_ns = 1;
  if (sink.append(invalid).ok) {
    return 7;
  }

  return 0;
}