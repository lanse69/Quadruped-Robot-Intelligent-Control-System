// 运行遥测模型实现

#include "qrics/monitoring/telemetry.hpp"

namespace qrics::monitoring {

TelemetryFrame make_control_telemetry_frame(const qrics::control::TaskExecutionSnapshot& snapshot,
                                            qrics::simulation::AdapterState adapter_state) {
  TelemetryFrame frame{};
  frame.frame_id = "telemetry_" + snapshot.run_id + "_" + std::to_string(snapshot.updated_at_ns);
  frame.run_id = snapshot.run_id;
  frame.source = TelemetrySource::TaskExecutor;
  frame.timestamp_ns = snapshot.updated_at_ns;
  frame.control_state = snapshot.run_state;
  frame.adapter_state = adapter_state;
  frame.current_node_id = snapshot.current_node_id;
  frame.completed_node_count = snapshot.completed_node_count;
  frame.control_step_count = snapshot.control_step_count;
  frame.risk_score = snapshot.last_robot_state.risk_score;
  frame.summary = snapshot.reason;
  return frame;
}

qrics::events::EventRecord make_event_record_from_telemetry(const TelemetryFrame& frame) {
  qrics::events::EventRecord record{};
  record.event_id = "event_" + frame.frame_id;
  record.run_id = frame.run_id;
  record.event_type = qrics::events::EventType::Telemetry;
  record.severity = qrics::events::EventSeverity::Info;
  record.source = "TelemetryCollector";
  record.message = frame.summary;
  record.subject_ref = qrics::common::ResourceRef{frame.frame_id, "0.1.0"};
  record.timestamp_ns = frame.timestamp_ns;
  return record;
}

}  // namespace qrics::monitoring