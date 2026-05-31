// 回放清单模型

#pragma once

#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/replay/keyframe_index.hpp"

namespace qrics::replay {

struct ReplaySegment final {
  std::string segment_id{};
  std::string run_id{};
  std::string artifact_uri{};
  qrics::common::TimestampNs start_time_ns{0};
  qrics::common::TimestampNs end_time_ns{0};
  qrics::common::Checksum checksum{};
};

struct ReplayManifest final {
  std::string manifest_id{};
  std::string run_id{};
  qrics::common::ResourceRef scene_ref{};
  qrics::common::ResourceRef policy_ref{};
  std::vector<ReplaySegment> segments{};
  std::vector<KeyFrameIndexEntry> keyframes{};
  qrics::common::TimestampNs created_at_ns{0};
};

[[nodiscard]] qrics::common::Result<ReplayManifest> append_replay_segment(ReplayManifest manifest,
                                                                          ReplaySegment segment);

[[nodiscard]] qrics::common::Result<ReplayManifest> append_keyframe(ReplayManifest manifest,
                                                                    KeyFrameIndexEntry keyframe);

}  // namespace qrics::replay