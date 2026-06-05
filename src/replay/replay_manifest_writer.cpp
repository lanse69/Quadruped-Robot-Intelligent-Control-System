// C++ 回放清单写入器实现

#include "qrics/replay/replay_manifest_writer.hpp"

#include <sstream>
#include <string>
#include <utility>

namespace qrics::replay {

namespace {

template <typename T>
[[nodiscard]] qrics::common::Result<T> fail(const std::string& code, const std::string& message) {
  return qrics::common::Result<T>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] std::string escape_json(const std::string& value) {
  std::ostringstream out{};
  for (const char ch : value) {
    switch (ch) {
      case '"':
        out << "\\\"";
        break;
      case '\\':
        out << "\\\\";
        break;
      case '\n':
        out << "\\n";
        break;
      case '\r':
        out << "\\r";
        break;
      case '\t':
        out << "\\t";
        break;
      default:
        out << ch;
        break;
    }
  }
  return out.str();
}

[[nodiscard]] const char* keyframe_type_name(const KeyFrameType type) {
  switch (type) {
    case KeyFrameType::SafetyEvent:
      return "safety_event";
    case KeyFrameType::Alert:
      return "alert";
    case KeyFrameType::StateTransition:
      return "state_transition";
    case KeyFrameType::OperatorMarker:
      return "operator_marker";
  }
  return "unknown";
}

}  // namespace

qrics::common::Result<ReplayManifestWriter> ReplayManifestWriter::create(
    ReplayManifestWriterConfig config) {
  if (config.manifest_id.empty() || config.run_id.empty()) {
    return fail<ReplayManifestWriter>("REPLAY_WRITER_INVALID",
                                      "manifest_id and run_id must not be empty");
  }
  if (config.segment_id.empty() || config.artifact_uri.empty()) {
    return fail<ReplayManifestWriter>("REPLAY_SEGMENT_INVALID",
                                      "segment_id and artifact_uri must not be empty");
  }
  ReplayManifestWriter writer{};
  writer.manifest_.manifest_id = std::move(config.manifest_id);
  writer.manifest_.run_id = config.run_id;
  writer.manifest_.scene_ref = std::move(config.scene_ref);
  writer.manifest_.policy_ref = std::move(config.policy_ref);
  writer.manifest_.created_at_ns = config.created_at_ns;

  writer.segment_.segment_id = std::move(config.segment_id);
  writer.segment_.run_id = config.run_id;
  writer.segment_.artifact_uri = std::move(config.artifact_uri);
  writer.segment_.start_time_ns = config.segment_start_time_ns;
  writer.segment_.end_time_ns = config.segment_start_time_ns;
  return qrics::common::Result<ReplayManifestWriter>::success(std::move(writer));
}

qrics::common::Result<KeyFrameIndexEntry> ReplayManifestWriter::record_safety_event(
    const qrics::safety::SafetyEvent& safety_event) {
  if (safety_event.run_id != manifest_.run_id) {
    return fail<KeyFrameIndexEntry>("SAFETY_EVENT_RUN_MISMATCH",
                                    "SafetyEvent.run_id must match ReplayManifest.run_id");
  }
  const qrics::common::ResourceRef segment_ref{segment_.segment_id, "0.1.0"};
  auto entry = make_keyframe_from_safety_event(safety_event, segment_ref);
  auto manifest_result = append_keyframe(std::move(manifest_), entry);
  if (!manifest_result.ok) {
    manifest_ = ReplayManifest{};
    return fail<KeyFrameIndexEntry>(manifest_result.errors.front().code,
                                    manifest_result.errors.front().message);
  }
  manifest_ = std::move(manifest_result.value);
  if (safety_event.timestamp_ns > segment_.end_time_ns) {
    segment_.end_time_ns = safety_event.timestamp_ns;
  }
  return qrics::common::Result<KeyFrameIndexEntry>::success(std::move(entry));
}

qrics::common::Result<ReplayManifest> ReplayManifestWriter::finalize(
    qrics::common::TimestampNs segment_end_time_ns) const {
  auto manifest = manifest_;
  auto segment = segment_;
  if (segment_end_time_ns < segment.start_time_ns) {
    return fail<ReplayManifest>("REPLAY_SEGMENT_TIME_INVALID",
                                "segment_end_time_ns must be >= segment_start_time_ns");
  }
  if (segment_end_time_ns > segment.end_time_ns) {
    segment.end_time_ns = segment_end_time_ns;
  }
  return append_replay_segment(std::move(manifest), std::move(segment));
}

std::string serialize_replay_manifest_json(const ReplayManifest& manifest) {
  std::ostringstream out{};
  out << "{\n";
  out << R"(  "manifest_id": ")" << escape_json(manifest.manifest_id) << R"(",)" << '\n';
  out << R"(  "run_id": ")" << escape_json(manifest.run_id) << R"(",)" << '\n';
  out << R"(  "scene_ref": {"id": ")" << escape_json(manifest.scene_ref.id) << R"(", "version": ")"
      << escape_json(manifest.scene_ref.version) << R"("},)" << '\n';
  out << R"(  "policy_ref": {"id": ")" << escape_json(manifest.policy_ref.id)
      << R"(", "version": ")" << escape_json(manifest.policy_ref.version) << R"("},)" << '\n';
  out << R"(  "created_at_ns": )" << manifest.created_at_ns << ",\n";
  out << R"(  "segments": [)";
  for (std::size_t i = 0; i < manifest.segments.size(); ++i) {
    const auto& segment = manifest.segments[i];
    if (i > 0U) {
      out << ',';
    }
    out << R"({"segment_id": ")" << escape_json(segment.segment_id) << R"(", "artifact_uri": ")"
        << escape_json(segment.artifact_uri) << R"(", "start_time_ns": )" << segment.start_time_ns
        << R"(, "end_time_ns": )" << segment.end_time_ns << '}';
  }
  out << "],\n";
  out << R"(  "keyframes": [)";
  for (std::size_t i = 0; i < manifest.keyframes.size(); ++i) {
    const auto& keyframe = manifest.keyframes[i];
    if (i > 0U) {
      out << ',';
    }
    out << R"({"keyframe_id": ")" << escape_json(keyframe.keyframe_id) << R"(", "type": ")"
        << keyframe_type_name(keyframe.keyframe_type) << R"(", "timestamp_ns": )"
        << keyframe.timestamp_ns << R"(, "summary": ")" << escape_json(keyframe.summary) << R"("})";
  }
  out << "]\n";
  out << "}\n";
  return out.str();
}
}  // namespace qrics::replay