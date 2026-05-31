#include "qrics/audit/audit_log.hpp"

namespace {

[[nodiscard]] qrics::task::TaskLifecycleEvent make_task_confirmed_event() {
  qrics::task::TaskLifecycleEvent event{};
  event.type = qrics::task::TaskLifecycleEventType::Confirmed;
  event.from_state = qrics::task::TaskLifecycleState::PreviewReady;
  event.to_state = qrics::task::TaskLifecycleState::Confirmed;
  event.task_id = "task_audit";
  event.actor_id = "operator_001";
  event.reason = "operator confirmed preview";
  event.occurred_at_ns = 7000;
  return event;
}

[[nodiscard]] qrics::audit::AuditLog make_policy_release_log() {
  qrics::audit::AuditLog log{};
  log.audit_id = "audit_policy_release";
  log.request_id = "request_policy_release";
  log.actor.actor_id = "approver_001";
  log.actor.actor_role = "algorithm_engineer";
  log.action = qrics::audit::AuditAction::PolicyReleased;
  log.object.object_type = "PolicyArtifact";
  log.object.object_ref = qrics::common::ResourceRef{"policy_candidate", "0.2.0"};
  log.result = qrics::audit::AuditResult::Succeeded;
  log.timestamp_ns = 8000;
  return log;
}

}  // namespace

int main() {
  qrics::audit::InMemoryAuditLogStore store{};

  qrics::audit::TaskLifecycleAuditRequest request{};
  request.lifecycle_event = make_task_confirmed_event();
  request.request_id = "request_task_confirm";
  const auto task_audit = qrics::audit::make_audit_log_from_task_lifecycle_event(request);
  const auto appended_task = store.append(task_audit);
  if (!appended_task.ok) {
    return 1;
  }
  if (appended_task.value.action != qrics::audit::AuditAction::TaskConfirmed) {
    return 2;
  }

  qrics::audit::AuditQuery query{};
  query.actor_id = "operator_001";
  query.has_action = true;
  query.action = qrics::audit::AuditAction::TaskConfirmed;
  const auto queried = store.query(query);
  if (!queried.ok || queried.value.size() != 1U) {
    return 3;
  }

  auto release_log = make_policy_release_log();
  if (!qrics::audit::is_high_risk_action(release_log.action)) {
    return 4;
  }
  if (store.append(release_log).ok) {
    return 5;
  }

  release_log.reason = "gate report passed and approval recorded";
  const auto appended_release = store.append(release_log);
  if (!appended_release.ok) {
    return 6;
  }

  qrics::audit::AuditQuery policy_query{};
  policy_query.object_id = "policy_candidate";
  policy_query.has_start_time = true;
  policy_query.start_time_ns = 7500;
  const auto policy_logs = store.query(policy_query);
  if (!policy_logs.ok || policy_logs.value.size() != 1U) {
    return 7;
  }

  return 0;
}