// 事件沉淀内存实现

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

#include "qrics/events/event_sink.hpp"

namespace qrics::events {

namespace {

[[nodiscard]] qrics::common::Error make_error(const std::string& code, const std::string& message) {
  return qrics::common::Error{code, message};
}

[[nodiscard]] qrics::common::Result<EventRecord> fail_record(const std::string& code,
                                                             const std::string& message) {
  return qrics::common::Result<EventRecord>::failure({make_error(code, message)});
}

[[nodiscard]] bool matches_query(const EventRecord& record, const EventQuery& query) {
  if (!query.run_id.empty() && record.run_id != query.run_id) {
    return false;
  }
  if (query.has_event_type && record.event_type != query.event_type) {
    return false;
  }
  if (query.has_start_time && record.timestamp_ns < query.start_time_ns) {
    return false;
  }
  if (query.has_end_time && record.timestamp_ns > query.end_time_ns) {
    return false;
  }
  return true;
}

}  // namespace

qrics::common::Result<EventRecord> InMemoryEventSink::append(EventRecord record) {
  if (record.event_id.empty()) {
    return fail_record("EVENT_ID_EMPTY", "EventRecord.event_id must not be empty");
  }
  if (record.run_id.empty()) {
    return fail_record("EVENT_RUN_ID_EMPTY", "EventRecord.run_id must not be empty");
  }
  if (record.timestamp_ns < 0) {
    return fail_record("EVENT_TIMESTAMP_INVALID", "EventRecord.timestamp_ns must not be negative");
  }

  records_.push_back(std::move(record));
  return qrics::common::Result<EventRecord>::success(records_.back());
}

qrics::common::Result<std::vector<EventRecord>> InMemoryEventSink::query(
    const EventQuery& query) const {
  std::vector<EventRecord> result{};
  std::copy_if(records_.begin(), records_.end(), std::back_inserter(result),
               [&query](const EventRecord& record) { return matches_query(record, query); });
  return qrics::common::Result<std::vector<EventRecord>>::success(std::move(result));
}

}  // namespace qrics::events