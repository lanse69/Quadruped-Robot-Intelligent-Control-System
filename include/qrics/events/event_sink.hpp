// 事件沉淀接口与内存实现声明

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"

namespace qrics::events {

enum class EventType : std::uint8_t {
  Telemetry,
  Alert,
  Safety,
  TaskLifecycle,
  Audit,
  ReplayKeyFrame
};

enum class EventSeverity : std::uint8_t { Debug, Info, Warning, Error, Critical };

struct EventRecord final {
  std::string event_id{};
  std::string run_id{};
  EventType event_type{EventType::Telemetry};
  EventSeverity severity{EventSeverity::Info};
  std::string source{};
  std::string message{};
  qrics::common::ResourceRef subject_ref{};
  std::vector<std::string> labels{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct EventQuery final {
  std::string run_id{};
  bool has_event_type{false};
  EventType event_type{EventType::Telemetry};
  bool has_start_time{false};
  qrics::common::TimestampNs start_time_ns{0};
  bool has_end_time{false};
  qrics::common::TimestampNs end_time_ns{0};
};

class EventSink {
 public:
  virtual ~EventSink() = default;

  [[nodiscard]] virtual qrics::common::Result<EventRecord> append(EventRecord record) = 0;
  [[nodiscard]] virtual qrics::common::Result<std::vector<EventRecord>> query(
      const EventQuery& query) const = 0;
};

class InMemoryEventSink final : public EventSink {
 public:
  [[nodiscard]] qrics::common::Result<EventRecord> append(EventRecord record) override;
  [[nodiscard]] qrics::common::Result<std::vector<EventRecord>> query(
      const EventQuery& query) const override;

 private:
  std::vector<EventRecord> records_{};
};

}  // namespace qrics::events