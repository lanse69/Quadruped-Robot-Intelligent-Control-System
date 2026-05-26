// 任务编排应用服务

#include "qrics/task/task_orchestrator_service.hpp"

#include <string>
#include <utility>

namespace qrics::task {

namespace {

struct LifecycleEventData final {
  TaskLifecycleEventType type{TaskLifecycleEventType::Submitted};
  TaskLifecycleState from_state{TaskLifecycleState::Received};
  TaskLifecycleState to_state{TaskLifecycleState::Received};
  std::string actor_id{};
  std::string reason{};
  qrics::common::TimestampNs occurred_at_ns{0};
};

[[nodiscard]] qrics::common::Result<TaskSession> fail(qrics::common::Error error) {
  return qrics::common::Result<TaskSession>::failure({std::move(error)});
}

void append_event(TaskSession& session, LifecycleEventData data) {
  TaskLifecycleEvent event{};
  event.type = data.type;
  event.from_state = data.from_state;
  event.to_state = data.to_state;
  event.task_id = session.task_id;
  event.actor_id = std::move(data.actor_id);
  event.reason = std::move(data.reason);
  event.occurred_at_ns = data.occurred_at_ns;
  session.events.push_back(std::move(event));
}

[[nodiscard]] bool is_terminal(TaskLifecycleState state) {
  return state == TaskLifecycleState::Rejected || state == TaskLifecycleState::HandedOff ||
         state == TaskLifecycleState::Cancelled || state == TaskLifecycleState::Failed;
}

}  // namespace

TaskOrchestratorService::TaskOrchestratorService(const TaskUnderstandingPipeline& pipeline,
                                                 TaskSessionStore& store)
    : pipeline_(pipeline), store_(store) {}

qrics::common::Result<TaskSession> TaskOrchestratorService::submit(
    const TaskSubmissionRequest& request) const {
  if (request.parse_context.task_id.empty()) {
    return fail(qrics::common::Error{"TASK_ID_EMPTY",
                                     "TaskParseContext.task_id must be set before submission"});
  }
  if (request.source_text.empty()) {
    return fail(qrics::common::Error{"TASK_SOURCE_EMPTY",
                                     "Task source text must be set before submission"});
  }

  TaskSession session{};
  session.task_id = request.parse_context.task_id;
  session.source_text = request.source_text;
  session.state = TaskLifecycleState::Received;
  append_event(session,
               LifecycleEventData{TaskLifecycleEventType::Submitted, TaskLifecycleState::Received,
                                  TaskLifecycleState::Received, request.operator_id,
                                  "task submitted", request.submitted_at_ns});

  const auto understanding_from = session.state;
  session.state = TaskLifecycleState::Understanding;
  append_event(session, LifecycleEventData{TaskLifecycleEventType::UnderstandingStarted,
                                           understanding_from, session.state, request.operator_id,
                                           "task understanding started", request.submitted_at_ns});

  auto understood = pipeline_.understand(request.source_text, request.parse_context,
                                         request.scene_profile, request.policy_candidates);
  if (!understood.ok) {
    const auto rejected_from = session.state;
    session.state = TaskLifecycleState::Rejected;
    session.rejection_errors = understood.errors;
    append_event(session,
                 LifecycleEventData{TaskLifecycleEventType::Rejected, rejected_from, session.state,
                                    request.operator_id,
                                    "task understanding or validation rejected the request",
                                    request.submitted_at_ns});
    return store_.upsert(std::move(session));
  }

  const auto preview_from = session.state;
  session.state = TaskLifecycleState::PreviewReady;
  session.understanding_result = understood.value;
  session.has_understanding_result = true;
  session.operator_confirmation_required =
      understood.value.execution_preview.operator_action_required;
  append_event(session, LifecycleEventData{TaskLifecycleEventType::PreviewGenerated, preview_from,
                                           session.state, request.operator_id,
                                           "execution preview generated", request.submitted_at_ns});

  return store_.upsert(std::move(session));
}

qrics::common::Result<TaskSession> TaskOrchestratorService::confirm(
    const TaskConfirmationRequest& request) const {
  auto session = store_.find(request.task_id);
  if (!session.ok) {
    return session;
  }
  if (session.value.state != TaskLifecycleState::PreviewReady) {
    return fail(qrics::common::Error{"TASK_CONFIRM_NOT_ALLOWED",
                                     "Task can only be confirmed from PreviewReady state"});
  }
  if (!session.value.has_understanding_result) {
    return fail(qrics::common::Error{"TASK_PREVIEW_MISSING",
                                     "Task confirmation requires an execution preview"});
  }

  const auto from_state = session.value.state;
  session.value.state = TaskLifecycleState::Confirmed;
  session.value.understanding_result.task_script.status = TaskStatus::Confirmed;
  append_event(session.value,
               LifecycleEventData{TaskLifecycleEventType::Confirmed, from_state,
                                  session.value.state, request.operator_id,
                                  "operator confirmed execution preview", request.confirmed_at_ns});
  return store_.upsert(std::move(session.value));
}

qrics::common::Result<TaskSession> TaskOrchestratorService::handoff(
    const TaskHandoffRequest& request) const {
  auto session = store_.find(request.task_id);
  if (!session.ok) {
    return session;
  }
  if (session.value.state != TaskLifecycleState::Confirmed) {
    return fail(qrics::common::Error{"TASK_HANDOFF_NOT_ALLOWED",
                                     "Task can only be handed off from Confirmed state"});
  }
  if (!session.value.has_understanding_result) {
    return fail(qrics::common::Error{"TASK_UNDERSTANDING_RESULT_MISSING",
                                     "Task handoff requires TaskGraph"});
  }

  const auto from_state = session.value.state;
  session.value.state = TaskLifecycleState::HandedOff;
  session.value.understanding_result.task_script.status = TaskStatus::HandedOff;
  append_event(session.value, LifecycleEventData{TaskLifecycleEventType::HandedOff, from_state,
                                                 session.value.state, request.operator_id,
                                                 "task graph handed off to execution layer",
                                                 request.handed_off_at_ns});
  return store_.upsert(std::move(session.value));
}

qrics::common::Result<TaskSession> TaskOrchestratorService::cancel(
    const TaskCancellationRequest& request) const {
  auto session = store_.find(request.task_id);
  if (!session.ok) {
    return session;
  }
  if (is_terminal(session.value.state)) {
    return fail(qrics::common::Error{"TASK_CANCEL_NOT_ALLOWED",
                                     "Terminal task session cannot be cancelled"});
  }

  const auto from_state = session.value.state;
  session.value.state = TaskLifecycleState::Cancelled;
  append_event(session.value, LifecycleEventData{TaskLifecycleEventType::Cancelled, from_state,
                                                 session.value.state, request.operator_id,
                                                 request.reason, request.cancelled_at_ns});
  return store_.upsert(std::move(session.value));
}

}  // namespace qrics::task