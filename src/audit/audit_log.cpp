// 审计日志模型与内存存储实现

#include "qrics/audit/audit_log.hpp"

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

namespace qrics::audit {

namespace {

[[nodiscard]] qrics::common::Result<AuditLog> fail_log(const std::string& code,
                                                       const std::string& message) {
  return qrics::common::Result<AuditLog>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] AuditAction map_task_lifecycle_action(qrics::task::TaskLifecycleEventType type) {
  switch (type) {
    case qrics::task::TaskLifecycleEventType::Submitted:
    case qrics::task::TaskLifecycleEventType::UnderstandingStarted:
    case qrics::task::TaskLifecycleEventType::PreviewGenerated:
      return AuditAction::TaskSubmitted;
    case qrics::task::TaskLifecycleEventType::Confirmed:
      return AuditAction::TaskConfirmed;
    case qrics::task::TaskLifecycleEventType::HandedOff:
      return AuditAction::TaskHandedOff;
    case qrics::task::TaskLifecycleEventType::Cancelled:
      return AuditAction::TaskCancelled;
    case qrics::task::TaskLifecycleEventType::Rejected:
    case qrics::task::TaskLifecycleEventType::Failed:
      return AuditAction::TaskRejected;
  }
  return AuditAction::TaskSubmitted;
}

[[nodiscard]] AuditResult map_task_lifecycle_result(qrics::task::TaskLifecycleEventType type) {
  switch (type) {
    case qrics::task::TaskLifecycleEventType::Rejected:
    case qrics::task::TaskLifecycleEventType::Failed:
      return AuditResult::Blocked;
    case qrics::task::TaskLifecycleEventType::Submitted:
    case qrics::task::TaskLifecycleEventType::UnderstandingStarted:
    case qrics::task::TaskLifecycleEventType::PreviewGenerated:
    case qrics::task::TaskLifecycleEventType::Confirmed:
    case qrics::task::TaskLifecycleEventType::HandedOff:
    case qrics::task::TaskLifecycleEventType::Cancelled:
      return AuditResult::Succeeded;
  }
  return AuditResult::Failed;
}

[[nodiscard]] bool matches_query(const AuditLog& log, const AuditQuery& query) {
  if (!query.actor_id.empty() && log.actor.actor_id != query.actor_id) {
    return false;
  }
  if (!query.object_id.empty() && log.object.object_ref.id != query.object_id) {
    return false;
  }
  if (query.has_action && log.action != query.action) {
    return false;
  }
  if (query.has_start_time && log.timestamp_ns < query.start_time_ns) {
    return false;
  }
  if (query.has_end_time && log.timestamp_ns > query.end_time_ns) {
    return false;
  }
  return true;
}

}  // namespace

bool is_high_risk_action(AuditAction action) noexcept {
  return action == AuditAction::EmergencyStop || action == AuditAction::ManualOverride ||
         action == AuditAction::PolicyReleased || action == AuditAction::PolicyRolledBack ||
         action == AuditAction::PolicyArchived || action == AuditAction::SceneBaselined ||
         action == AuditAction::PermissionChanged;
}

AuditLog make_audit_log_from_task_lifecycle_event(const TaskLifecycleAuditRequest& request) {
  AuditLog log{};
  log.audit_id = "audit_" + request.lifecycle_event.task_id + "_" +
                 std::to_string(request.lifecycle_event.occurred_at_ns);
  log.request_id = request.request_id;
  log.actor.actor_id = request.lifecycle_event.actor_id;
  log.actor.actor_role = "operator";
  log.action = map_task_lifecycle_action(request.lifecycle_event.type);
  log.object.object_type = "TaskSession";
  log.object.object_ref =
      qrics::common::ResourceRef{request.lifecycle_event.task_id, request.object_version};
  log.result = map_task_lifecycle_result(request.lifecycle_event.type);
  log.reason = request.lifecycle_event.reason;
  log.timestamp_ns = request.lifecycle_event.occurred_at_ns;
  return log;
}

qrics::common::Result<AuditLog> InMemoryAuditLogStore::append(AuditLog log) {
  if (log.audit_id.empty()) {
    return fail_log("AUDIT_ID_EMPTY", "AuditLog.audit_id must not be empty");
  }
  if (log.request_id.empty()) {
    return fail_log("AUDIT_REQUEST_ID_EMPTY", "AuditLog.request_id must not be empty");
  }
  if (log.actor.actor_id.empty()) {
    return fail_log("AUDIT_ACTOR_EMPTY", "AuditLog.actor.actor_id must not be empty");
  }
  if (log.object.object_ref.id.empty()) {
    return fail_log("AUDIT_OBJECT_EMPTY", "AuditLog.object.object_ref.id must not be empty");
  }
  if (is_high_risk_action(log.action) && log.reason.empty()) {
    return fail_log("AUDIT_REASON_REQUIRED", "High-risk audit action must include reason");
  }
  if (log.timestamp_ns < 0) {
    return fail_log("AUDIT_TIMESTAMP_INVALID", "AuditLog.timestamp_ns must not be negative");
  }

  logs_.push_back(std::move(log));
  return qrics::common::Result<AuditLog>::success(logs_.back());
}

qrics::common::Result<std::vector<AuditLog>> InMemoryAuditLogStore::query(
    const AuditQuery& query) const {
  std::vector<AuditLog> result{};
  std::copy_if(logs_.begin(), logs_.end(), std::back_inserter(result),
               [&query](const AuditLog& log) { return matches_query(log, query); });
  return qrics::common::Result<std::vector<AuditLog>>::success(std::move(result));
}

}  // namespace qrics::audit