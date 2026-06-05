// C++ 回放清单写入器

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/replay/replay_manifest.hpp"
#include "qrics/safety/safety_event.hpp"

namespace qrics::replay {

struct ReplayManifestWriterConfig final {
  std::string manifest_id{};
  std::string run_id{};
  qrics::common::ResourceRef scene_ref{};
  qrics::common::ResourceRef policy_ref{};
  std::string segment_id{"segment_0001"};
  std::string artifact_uri{};
  qrics::common::TimestampNs created_at_ns{0};
  qrics::common::TimestampNs segment_start_time_ns{0};
};

class ReplayManifestWriter final {
 public:
  [[nodiscard]] static qrics::common::Result<ReplayManifestWriter> create(
      ReplayManifestWriterConfig config);

  [[nodiscard]] qrics::common::Result<KeyFrameIndexEntry> record_safety_event(
      const qrics::safety::SafetyEvent& safety_event);

  [[nodiscard]] qrics::common::Result<ReplayManifest> finalize(
      qrics::common::TimestampNs segment_end_time_ns) const;

  [[nodiscard]] const ReplayManifest& manifest() const {
    return manifest_;
  }
  [[nodiscard]] const ReplaySegment& segment() const {
    return segment_;
  }

 private:
  ReplayManifest manifest_{};
  ReplaySegment segment_{};
};

[[nodiscard]] std::string serialize_replay_manifest_json(const ReplayManifest& manifest);

}  // namespace qrics::replay