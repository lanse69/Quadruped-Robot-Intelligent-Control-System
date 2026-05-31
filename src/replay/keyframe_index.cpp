// 关键帧索引模型实现

#include "qrics/replay/keyframe_index.hpp"

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

namespace qrics::replay {

namespace {

[[nodiscard]] qrics::common::Result<KeyFrameIndexEntry> fail_entry(const std::string& code,
                                                                   const std::string& message) {
  return qrics::common::Result<KeyFrameIndexEntry>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] bool matches_query(const KeyFrameIndexEntry& entry, const KeyFrameQuery& query) {
  if (!query.run_id.empty() && entry.run_id != query.run_id) {
    return false;
  }
  if (query.has_keyframe_type && entry.keyframe_type != query.keyframe_type) {
    return false;
  }
  if (query.has_start_time && entry.timestamp_ns < query.start_time_ns) {
    return false;
  }
  if (query.has_end_time && entry.timestamp_ns > query.end_time_ns) {
    return false;
  }
  return true;
}

[[nodiscard]] std::string first_violation_summary(const qrics::safety::SafetyEvent& safety_event) {
  if (!safety_event.violation_list.empty()) {
    return safety_event.violation_list.front();
  }
  return "Safety event keyframe";
}

}  // namespace

qrics::common::Result<KeyFrameIndexEntry> InMemoryKeyFrameIndex::add(KeyFrameIndexEntry entry) {
  if (entry.keyframe_id.empty()) {
    return fail_entry("KEYFRAME_ID_EMPTY", "KeyFrameIndexEntry.keyframe_id must not be empty");
  }
  if (entry.run_id.empty()) {
    return fail_entry("KEYFRAME_RUN_ID_EMPTY", "KeyFrameIndexEntry.run_id must not be empty");
  }
  if (entry.timestamp_ns < 0) {
    return fail_entry("KEYFRAME_TIMESTAMP_INVALID",
                      "KeyFrameIndexEntry.timestamp_ns must not be negative");
  }

  entries_.push_back(std::move(entry));
  return qrics::common::Result<KeyFrameIndexEntry>::success(entries_.back());
}

qrics::common::Result<std::vector<KeyFrameIndexEntry>> InMemoryKeyFrameIndex::query(
    const KeyFrameQuery& query) const {
  std::vector<KeyFrameIndexEntry> result{};
  std::copy_if(entries_.begin(), entries_.end(), std::back_inserter(result),
               [&query](const KeyFrameIndexEntry& entry) { return matches_query(entry, query); });
  return qrics::common::Result<std::vector<KeyFrameIndexEntry>>::success(std::move(result));
}

KeyFrameIndexEntry make_keyframe_from_safety_event(
    const qrics::safety::SafetyEvent& safety_event,
    const qrics::common::ResourceRef& replay_segment_ref) {
  KeyFrameIndexEntry entry{};
  entry.keyframe_id = "keyframe_" + safety_event.event_id;
  entry.run_id = safety_event.run_id;
  entry.keyframe_type = KeyFrameType::SafetyEvent;
  entry.timestamp_ns = safety_event.timestamp_ns;
  entry.event_ref = qrics::common::ResourceRef{safety_event.event_id, "0.1.0"};
  entry.replay_segment_ref = replay_segment_ref;
  entry.summary = first_violation_summary(safety_event);
  return entry;
}

}  // namespace qrics::replay