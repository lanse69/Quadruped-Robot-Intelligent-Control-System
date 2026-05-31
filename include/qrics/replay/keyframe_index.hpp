// 关键帧索引模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/safety/safety_event.hpp"

namespace qrics::replay {

enum class KeyFrameType : std::uint8_t { SafetyEvent, Alert, StateTransition, OperatorMarker };

struct KeyFrameIndexEntry final {
  std::string keyframe_id{};
  std::string run_id{};
  KeyFrameType keyframe_type{KeyFrameType::SafetyEvent};
  qrics::common::TimestampNs timestamp_ns{0};
  qrics::common::ResourceRef event_ref{};
  qrics::common::ResourceRef replay_segment_ref{};
  std::string summary{};
};

struct KeyFrameQuery final {
  std::string run_id{};
  bool has_keyframe_type{false};
  KeyFrameType keyframe_type{KeyFrameType::SafetyEvent};
  bool has_start_time{false};
  qrics::common::TimestampNs start_time_ns{0};
  bool has_end_time{false};
  qrics::common::TimestampNs end_time_ns{0};
};

class KeyFrameIndex {
 public:
  virtual ~KeyFrameIndex() = default;

  [[nodiscard]] virtual qrics::common::Result<KeyFrameIndexEntry> add(KeyFrameIndexEntry entry) = 0;
  [[nodiscard]] virtual qrics::common::Result<std::vector<KeyFrameIndexEntry>> query(
      const KeyFrameQuery& query) const = 0;
};

class InMemoryKeyFrameIndex final : public KeyFrameIndex {
 public:
  [[nodiscard]] qrics::common::Result<KeyFrameIndexEntry> add(KeyFrameIndexEntry entry) override;
  [[nodiscard]] qrics::common::Result<std::vector<KeyFrameIndexEntry>> query(
      const KeyFrameQuery& query) const override;

 private:
  std::vector<KeyFrameIndexEntry> entries_{};
};

[[nodiscard]] KeyFrameIndexEntry make_keyframe_from_safety_event(
    const qrics::safety::SafetyEvent& safety_event,
    const qrics::common::ResourceRef& replay_segment_ref);

}  // namespace qrics::replay