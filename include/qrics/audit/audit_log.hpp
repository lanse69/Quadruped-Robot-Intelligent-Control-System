// 审计日志模型与内存存储声明

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/task/task_lifecycle.hpp"

namespace qrics::audit {

enum class AuditAction : std::uint8_t {
  TaskSubmitted,
  TaskConfirmed,
  TaskHandedOff,
  TaskCancelled,
  TaskRejected,
  EmergencyStop,
  ManualOverride,
  PolicyReleased,
  PolicyRolledBack,
  PolicyArchived,
  SceneBaselined,
  PermissionChanged
};

enum class AuditResult : std::uint8_t { Succeeded, Failed, Blocked };

struct AuditActor final {
  std::string actor_id{};
  std::string actor_role{"operator"};
};

struct AuditObject final {
  std::string object_type{};
  qrics::common::ResourceRef object_ref{};
};

struct AuditLog final {
  std::string audit_id{};
  std::string request_id{};
  AuditActor actor{};
  AuditAction action{AuditAction::TaskSubmitted};
  AuditObject object{};
  AuditResult result{AuditResult::Succeeded};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct AuditQuery final {
  std::string actor_id{};
  std::string object_id{};
  bool has_action{false};
  AuditAction action{AuditAction::TaskSubmitted};
  bool has_start_time{false};
  qrics::common::TimestampNs start_time_ns{0};
  bool has_end_time{false};
  qrics::common::TimestampNs end_time_ns{0};
};

struct TaskLifecycleAuditRequest final {
  qrics::task::TaskLifecycleEvent lifecycle_event{};
  std::string request_id{};
  std::string object_version{"0.1.0"};
};

class AuditLogStore {
 public:
  virtual ~AuditLogStore() = default;

  [[nodiscard]] virtual qrics::common::Result<AuditLog> append(AuditLog log) = 0;
  [[nodiscard]] virtual qrics::common::Result<std::vector<AuditLog>> query(
      const AuditQuery& query) const = 0;
};

class InMemoryAuditLogStore final : public AuditLogStore {
 public:
  [[nodiscard]] qrics::common::Result<AuditLog> append(AuditLog log) override;
  [[nodiscard]] qrics::common::Result<std::vector<AuditLog>> query(
      const AuditQuery& query) const override;

 private:
  std::vector<AuditLog> logs_{};
};

[[nodiscard]] bool is_high_risk_action(AuditAction action) noexcept;

[[nodiscard]] AuditLog make_audit_log_from_task_lifecycle_event(
    const TaskLifecycleAuditRequest& request);

}  // namespace qrics::audit