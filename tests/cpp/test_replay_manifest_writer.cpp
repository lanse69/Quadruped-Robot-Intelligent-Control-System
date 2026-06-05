#include <string>

#include "qrics/replay/replay_manifest_writer.hpp"

namespace {

[[nodiscard]] qrics::safety::SafetyEvent make_collision_event() {
  qrics::safety::SafetyEvent event{};
  event.event_id = "safety_collision_001";
  event.run_id = "run_writer";
  event.timestamp_ns = 2500;
  event.severity = qrics::safety::Severity::Critical;
  event.trigger_type = qrics::safety::TriggerType::CollisionRisk;
  event.violation_list.emplace_back("nearest obstacle inside replan threshold");
  event.action_taken = qrics::safety::SafetyActionTaken::Replan;
  return event;
}

}  // namespace

int main() {
  qrics::replay::ReplayManifestWriterConfig config{};
  config.manifest_id = "manifest_run_writer";
  config.run_id = "run_writer";
  config.scene_ref = qrics::common::ResourceRef{"scene_typed_obstacles", "0.4.0"};
  config.policy_ref = qrics::common::ResourceRef{"policy_demo", "0.1.0"};
  config.segment_id = "segment_0001";
  config.artifact_uri = "object://replay/run_writer/segment_0001.jsonl";
  config.created_at_ns = 1000;
  config.segment_start_time_ns = 1000;

  auto writer_result = qrics::replay::ReplayManifestWriter::create(config);
  if (!writer_result.ok) {
    return 1;
  }
  auto writer = writer_result.value;
  const auto keyframe_result = writer.record_safety_event(make_collision_event());
  if (!keyframe_result.ok) {
    return 2;
  }
  if (keyframe_result.value.replay_segment_ref.id != "segment_0001") {
    return 3;
  }

  const auto manifest_result = writer.finalize(4000);
  if (!manifest_result.ok) {
    return 4;
  }
  const auto& manifest = manifest_result.value;
  if (manifest.segments.size() != 1U || manifest.keyframes.size() != 1U) {
    return 5;
  }
  if (manifest.segments.front().end_time_ns != 4000) {
    return 6;
  }
  const std::string serialized = qrics::replay::serialize_replay_manifest_json(manifest);
  if (serialized.find("safety_collision_001") == std::string::npos) {
    return 7;
  }
  if (serialized.find("nearest obstacle inside replan threshold") == std::string::npos) {
    return 8;
  }

  auto bad_event = make_collision_event();
  bad_event.run_id = "other_run";
  if (writer.record_safety_event(bad_event).ok) {
    return 9;
  }
  return 0;
}