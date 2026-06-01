// 策略注册中心接口与内存实现声明

#pragma once

#include <string>
#include <vector>

#include "qrics/audit/audit_log.hpp"
#include "qrics/common/types.hpp"
#include "qrics/training/approval_record.hpp"
#include "qrics/training/gate_report.hpp"
#include "qrics/training/policy_artifact.hpp"

namespace qrics::training {

struct PolicyRegistryEntry final {
  PolicyArtifact artifact{};
  bool has_gate_report{false};
  GateReport gate_report{};
  bool is_current_baseline{false};
  std::vector<ApprovalRecord> approvals{};
  qrics::common::TimestampNs updated_at_ns{0};
};

struct PolicyRegistryRegisterRequest final {
  PolicyArtifact artifact{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyGateReportAttachRequest final {
  qrics::common::ResourceRef policy_ref{};
  GateReport gate_report{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyReleaseRequest final {
  qrics::common::ResourceRef policy_ref{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyBaselinePromotionRequest final {
  qrics::common::ResourceRef policy_ref{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyRollbackRequest final {
  qrics::common::ResourceRef target_policy_ref{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

struct PolicyArchiveRequest final {
  qrics::common::ResourceRef policy_ref{};
  std::string actor_id{"algorithm_engineer"};
  std::string request_id{};
  std::string reason{};
  qrics::common::TimestampNs timestamp_ns{0};
};

class PolicyRegistry {
 public:
  virtual ~PolicyRegistry() = default;

  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> register_candidate(
      const PolicyRegistryRegisterRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> attach_gate_report(
      const PolicyGateReportAttachRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> release(
      const PolicyReleaseRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> promote_baseline(
      const PolicyBaselinePromotionRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> rollback_baseline(
      const PolicyRollbackRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> archive(
      const PolicyArchiveRequest& request) = 0;
  [[nodiscard]] virtual qrics::common::Result<PolicyRegistryEntry> find(
      const qrics::common::ResourceRef& policy_ref) const = 0;
  [[nodiscard]] virtual qrics::common::Result<std::vector<PolicyRegistryEntry>> list_by_stage(
      PolicyStage stage) const = 0;
};

class InMemoryPolicyRegistry final : public PolicyRegistry {
 public:
  explicit InMemoryPolicyRegistry(qrics::audit::AuditLogStore* audit_store = nullptr);

  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> register_candidate(
      const PolicyRegistryRegisterRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> attach_gate_report(
      const PolicyGateReportAttachRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> release(
      const PolicyReleaseRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> promote_baseline(
      const PolicyBaselinePromotionRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> rollback_baseline(
      const PolicyRollbackRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> archive(
      const PolicyArchiveRequest& request) override;
  [[nodiscard]] qrics::common::Result<PolicyRegistryEntry> find(
      const qrics::common::ResourceRef& policy_ref) const override;
  [[nodiscard]] qrics::common::Result<std::vector<PolicyRegistryEntry>> list_by_stage(
      PolicyStage stage) const override;

 private:
  qrics::audit::AuditLogStore* audit_store_{};
  std::vector<PolicyRegistryEntry> entries_{};
};

}  // namespace qrics::training