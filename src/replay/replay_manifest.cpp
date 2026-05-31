// 回放清单模型实现

#include "qrics/replay/replay_manifest.hpp"

#include <string>
#include <utility>

namespace qrics::replay {

namespace {

[[nodiscard]] qrics::common::Result<ReplayManifest> fail_manifest(const std::string& code,
                                                                  const std::string& message) {
  return qrics::common::Result<ReplayManifest>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] bool manifest_run_matches(const ReplayManifest& manifest, const std::string& run_id) {
  return !manifest.run_id.empty() && manifest.run_id == run_id;
}

}  // namespace

qrics::common::Result<ReplayManifest> append_replay_segment(ReplayManifest manifest,
                                                            ReplaySegment segment) {
  if (manifest.manifest_id.empty() || manifest.run_id.empty()) {
    return fail_manifest("REPLAY_MANIFEST_INVALID", "ReplayManifest id and run_id must be set");
  }
  if (segment.segment_id.empty() || segment.artifact_uri.empty()) {
    return fail_manifest("REPLAY_SEGMENT_INVALID", "ReplaySegment id and artifact_uri must be set");
  }
  if (!manifest_run_matches(manifest, segment.run_id)) {
    return fail_manifest("REPLAY_SEGMENT_RUN_MISMATCH",
                         "ReplaySegment.run_id must match ReplayManifest.run_id");
  }
  if (segment.start_time_ns > segment.end_time_ns) {
    return fail_manifest("REPLAY_SEGMENT_TIME_INVALID",
                         "ReplaySegment start_time_ns must be <= end_time_ns");
  }

  manifest.segments.push_back(std::move(segment));
  return qrics::common::Result<ReplayManifest>::success(std::move(manifest));
}

qrics::common::Result<ReplayManifest> append_keyframe(ReplayManifest manifest,
                                                      KeyFrameIndexEntry keyframe) {
  if (manifest.manifest_id.empty() || manifest.run_id.empty()) {
    return fail_manifest("REPLAY_MANIFEST_INVALID", "ReplayManifest id and run_id must be set");
  }
  if (keyframe.keyframe_id.empty()) {
    return fail_manifest("KEYFRAME_ID_EMPTY", "KeyFrameIndexEntry.keyframe_id must not be empty");
  }
  if (!manifest_run_matches(manifest, keyframe.run_id)) {
    return fail_manifest("KEYFRAME_RUN_MISMATCH",
                         "KeyFrameIndexEntry.run_id must match ReplayManifest.run_id");
  }

  manifest.keyframes.push_back(std::move(keyframe));
  return qrics::common::Result<ReplayManifest>::success(std::move(manifest));
}

}  // namespace qrics::replay