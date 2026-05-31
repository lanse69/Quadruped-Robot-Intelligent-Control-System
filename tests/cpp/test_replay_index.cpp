#include "qrics/replay/keyframe_index.hpp"
#include "qrics/replay/replay_manifest.hpp"

namespace {

[[nodiscard]] qrics::safety::SafetyEvent make_safety_event() {
  qrics::safety::SafetyEvent event{};
  event.event_id = "safety_keyframe_001";
  event.run_id = "run_replay";
  event.timestamp_ns = 5000;
  event.severity = qrics::safety::Severity::Critical;
  event.trigger_type = qrics::safety::TriggerType::EmergencyStop;
  event.violation_list.emplace_back("emergency stop is active");
  event.action_taken = qrics::safety::SafetyActionTaken::Stop;
  return event;
}

[[nodiscard]] qrics::replay::ReplayManifest make_manifest() {
  qrics::replay::ReplayManifest manifest{};
  manifest.manifest_id = "manifest_run_replay";
  manifest.run_id = "run_replay";
  manifest.scene_ref = qrics::common::ResourceRef{"scene_minimal", "0.1.0"};
  manifest.policy_ref = qrics::common::ResourceRef{"policy_placeholder", "0.1.0"};
  manifest.created_at_ns = 4000;
  return manifest;
}

[[nodiscard]] qrics::replay::ReplaySegment make_segment() {
  qrics::replay::ReplaySegment segment{};
  segment.segment_id = "segment_001";
  segment.run_id = "run_replay";
  segment.artifact_uri = "file://replays/run_replay/segment_001.bin";
  segment.start_time_ns = 4000;
  segment.end_time_ns = 6000;
  return segment;
}

}  // namespace

int main() {
  qrics::replay::InMemoryKeyFrameIndex index{};
  const auto segment_ref = qrics::common::ResourceRef{"segment_001", "0.1.0"};
  const auto keyframe =
      qrics::replay::make_keyframe_from_safety_event(make_safety_event(), segment_ref);

  const auto added = index.add(keyframe);
  if (!added.ok) {
    return 1;
  }
  if (added.value.keyframe_type != qrics::replay::KeyFrameType::SafetyEvent) {
    return 2;
  }

  qrics::replay::KeyFrameQuery query{};
  query.run_id = "run_replay";
  query.has_keyframe_type = true;
  query.keyframe_type = qrics::replay::KeyFrameType::SafetyEvent;
  query.has_start_time = true;
  query.start_time_ns = 4500;
  query.has_end_time = true;
  query.end_time_ns = 5500;
  const auto queried = index.query(query);
  if (!queried.ok || queried.value.size() != 1U) {
    return 3;
  }
  if (queried.value.front().summary != "emergency stop is active") {
    return 4;
  }

  auto manifest_result = qrics::replay::append_replay_segment(make_manifest(), make_segment());
  if (!manifest_result.ok || manifest_result.value.segments.size() != 1U) {
    return 5;
  }
  manifest_result = qrics::replay::append_keyframe(manifest_result.value, keyframe);
  if (!manifest_result.ok || manifest_result.value.keyframes.size() != 1U) {
    return 6;
  }

  auto wrong_segment = make_segment();
  wrong_segment.run_id = "other_run";
  if (qrics::replay::append_replay_segment(make_manifest(), wrong_segment).ok) {
    return 7;
  }

  return 0;
}