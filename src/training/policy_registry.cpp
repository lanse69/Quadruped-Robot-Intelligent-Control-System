// 策略注册中心内存实现

#include "qrics/training/policy_registry.hpp"

#include <algorithm>
#include <string>
#include <utility>
#include <vector>

namespace qrics::training {

namespace {

[[nodiscard]] qrics::common::Result<PolicyRegistryEntry> fail_entry(const std::string& code,
                                                                    const std::string& message) {
  return qrics::common::Result<PolicyRegistryEntry>::failure({qrics::common::Error{code, message}});
}

[[nodiscard]] bool same_ref(const qrics::common::ResourceRef& lhs,
                            const qrics::common::ResourceRef& rhs) noexcept {
  return lhs.id == rhs.id && lhs.version == rhs.version;
}

[[nodiscard]] bool policy_identity_is_valid(const PolicyArtifact& artifact) noexcept {
  return !artifact.policy_id.empty() && !artifact.version.empty() &&
         !artifact.artifact_uri.empty() && !artifact.algorithm_type.empty() &&
         !artifact.checksum.value.empty();
}

[[nodiscard]] qrics::common::ResourceRef ref_from_artifact(const PolicyArtifact& artifact) {
  return qrics::common::ResourceRef{artifact.policy_id, artifact.version};
}

[[nodiscard]] ApprovalRecord make_approval(const qrics::common::ResourceRef& policy_ref,
                                           ApprovalAction action, const std::string& actor_id,
                                           const std::string& reason,
                                           qrics::common::TimestampNs timestamp_ns) {
  ApprovalRecord approval{};
  approval.approval_id = "approval_" + policy_ref.id + "_" + std::to_string(timestamp_ns);
  approval.policy_ref = policy_ref;
  approval.action = action;
  approval.decision = ApprovalDecision::Approved;
  approval.approver_id = actor_id;
  approval.reason = reason;
  approval.approved_at_ns = timestamp_ns;
  return approval;
}

[[nodiscard]] qrics::audit::AuditLog make_policy_audit(const qrics::common::ResourceRef& policy_ref,
                                                       qrics::audit::AuditAction action,
                                                       const std::string& actor_id,
                                                       const std::string& request_id,
                                                       const std::string& reason,
                                                       qrics::common::TimestampNs timestamp_ns) {
  qrics::audit::AuditLog log{};
  log.audit_id = "audit_policy_" + policy_ref.id + "_" + policy_ref.version + "_" +
                 std::to_string(timestamp_ns);
  log.request_id = request_id;
  log.actor.actor_id = actor_id;
  log.actor.actor_role = "algorithm_engineer";
  log.action = action;
  log.object.object_type = "PolicyArtifact";
  log.object.object_ref = policy_ref;
  log.result = qrics::audit::AuditResult::Succeeded;
  log.reason = reason;
  log.timestamp_ns = timestamp_ns;
  return log;
}

[[nodiscard]] bool request_context_is_valid(const std::string& actor_id,
                                            const std::string& request_id,
                                            qrics::common::TimestampNs timestamp_ns) noexcept {
  return !actor_id.empty() && !request_id.empty() && timestamp_ns >= 0;
}

}  // namespace

InMemoryPolicyRegistry::InMemoryPolicyRegistry(qrics::audit::AuditLogStore* audit_store)
    : audit_store_(audit_store) {}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::register_candidate(
    const PolicyRegistryRegisterRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (!policy_identity_is_valid(request.artifact)) {
    return fail_entry("POLICY_ARTIFACT_INVALID",
                      "PolicyArtifact must include policy_id, version, algorithm_type, "
                      "artifact_uri and checksum");
  }
  const auto policy_ref = ref_from_artifact(request.artifact);
  const auto existing =
      std::find_if(entries_.begin(), entries_.end(), [&policy_ref](const auto& item) {
        return same_ref(ref_from_artifact(item.artifact), policy_ref);
      });
  if (existing != entries_.end()) {
    return fail_entry("POLICY_ALREADY_EXISTS", "PolicyArtifact already exists in registry");
  }

  PolicyRegistryEntry entry{};
  entry.artifact = request.artifact;
  entry.artifact.stage = PolicyStage::Candidate;
  entry.updated_at_ns = request.timestamp_ns;
  entries_.push_back(std::move(entry));
  return qrics::common::Result<PolicyRegistryEntry>::success(entries_.back());
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::attach_gate_report(
    const PolicyGateReportAttachRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (!same_ref(request.policy_ref, request.gate_report.policy_ref)) {
    return fail_entry("GATE_POLICY_REF_MISMATCH",
                      "GateReport.policy_ref must match request policy_ref");
  }

  auto existing = std::find_if(entries_.begin(), entries_.end(), [&request](const auto& item) {
    return same_ref(ref_from_artifact(item.artifact), request.policy_ref);
  });
  if (existing == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND", "PolicyArtifact does not exist in registry");
  }
  if (existing->artifact.stage == PolicyStage::Archived) {
    return fail_entry("POLICY_ARCHIVED", "Archived PolicyArtifact cannot receive a new GateReport");
  }

  existing->gate_report = request.gate_report;
  existing->has_gate_report = true;
  existing->artifact.metrics_digest = request.gate_report.metrics_digest;
  existing->artifact.stage = request.gate_report.decision == GateDecision::Passed
                                 ? PolicyStage::GatePassed
                                 : PolicyStage::GateFailed;
  existing->updated_at_ns = request.timestamp_ns;
  return qrics::common::Result<PolicyRegistryEntry>::success(*existing);
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::release(
    const PolicyReleaseRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (request.reason.empty()) {
    return fail_entry("POLICY_RELEASE_REASON_REQUIRED",
                      "Policy release must include approval reason");
  }

  auto existing = std::find_if(entries_.begin(), entries_.end(), [&request](const auto& item) {
    return same_ref(ref_from_artifact(item.artifact), request.policy_ref);
  });
  if (existing == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND", "PolicyArtifact does not exist in registry");
  }
  if (!existing->has_gate_report || existing->gate_report.decision != GateDecision::Passed ||
      existing->artifact.stage != PolicyStage::GatePassed) {
    return fail_entry("POLICY_GATE_NOT_PASSED", "Only GatePassed PolicyArtifact can be released");
  }

  existing->artifact.stage = PolicyStage::Released;
  existing->updated_at_ns = request.timestamp_ns;
  existing->approvals.push_back(make_approval(request.policy_ref, ApprovalAction::Release,
                                              request.actor_id, request.reason,
                                              request.timestamp_ns));

  if (audit_store_ != nullptr) {
    const auto audit_result = audit_store_->append(make_policy_audit(
        request.policy_ref, qrics::audit::AuditAction::PolicyReleased, request.actor_id,
        request.request_id, request.reason, request.timestamp_ns));
    if (!audit_result.ok) {
      return fail_entry("POLICY_AUDIT_WRITE_FAILED", audit_result.errors.front().message);
    }
  }

  return qrics::common::Result<PolicyRegistryEntry>::success(*existing);
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::promote_baseline(
    const PolicyBaselinePromotionRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (request.reason.empty()) {
    return fail_entry("POLICY_BASELINE_REASON_REQUIRED", "Baseline promotion must include reason");
  }

  auto existing = std::find_if(entries_.begin(), entries_.end(), [&request](const auto& item) {
    return same_ref(ref_from_artifact(item.artifact), request.policy_ref);
  });
  if (existing == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND", "PolicyArtifact does not exist in registry");
  }
  if (existing->artifact.stage != PolicyStage::Released &&
      existing->artifact.stage != PolicyStage::Baseline) {
    return fail_entry("POLICY_NOT_RELEASED", "Only Released PolicyArtifact can become Baseline");
  }

  for (auto& entry : entries_) {
    if (entry.is_current_baseline &&
        !same_ref(ref_from_artifact(entry.artifact), request.policy_ref)) {
      entry.is_current_baseline = false;
      entry.artifact.stage = PolicyStage::Released;
      entry.updated_at_ns = request.timestamp_ns;
    }
  }

  existing->artifact.stage = PolicyStage::Baseline;
  existing->is_current_baseline = true;
  existing->updated_at_ns = request.timestamp_ns;
  existing->approvals.push_back(make_approval(request.policy_ref, ApprovalAction::PromoteBaseline,
                                              request.actor_id, request.reason,
                                              request.timestamp_ns));

  if (audit_store_ != nullptr) {
    const auto audit_result = audit_store_->append(make_policy_audit(
        request.policy_ref, qrics::audit::AuditAction::PolicyReleased, request.actor_id,
        request.request_id, request.reason, request.timestamp_ns));
    if (!audit_result.ok) {
      return fail_entry("POLICY_AUDIT_WRITE_FAILED", audit_result.errors.front().message);
    }
  }

  return qrics::common::Result<PolicyRegistryEntry>::success(*existing);
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::rollback_baseline(
    const PolicyRollbackRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (request.reason.empty()) {
    return fail_entry("POLICY_ROLLBACK_REASON_REQUIRED", "Baseline rollback must include reason");
  }

  auto target = std::find_if(entries_.begin(), entries_.end(), [&request](const auto& item) {
    return same_ref(ref_from_artifact(item.artifact), request.target_policy_ref);
  });
  if (target == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND",
                      "Rollback target PolicyArtifact does not exist in registry");
  }
  if (target->artifact.stage != PolicyStage::Released &&
      target->artifact.stage != PolicyStage::Baseline) {
    return fail_entry("POLICY_ROLLBACK_TARGET_INVALID",
                      "Rollback target must be Released or Baseline PolicyArtifact");
  }

  for (auto& entry : entries_) {
    if (entry.is_current_baseline) {
      entry.is_current_baseline = false;
      entry.artifact.stage = PolicyStage::Released;
      entry.updated_at_ns = request.timestamp_ns;
    }
  }

  target->artifact.stage = PolicyStage::Baseline;
  target->is_current_baseline = true;
  target->updated_at_ns = request.timestamp_ns;
  target->approvals.push_back(make_approval(request.target_policy_ref,
                                            ApprovalAction::RollbackBaseline, request.actor_id,
                                            request.reason, request.timestamp_ns));

  if (audit_store_ != nullptr) {
    const auto audit_result = audit_store_->append(make_policy_audit(
        request.target_policy_ref, qrics::audit::AuditAction::PolicyRolledBack, request.actor_id,
        request.request_id, request.reason, request.timestamp_ns));
    if (!audit_result.ok) {
      return fail_entry("POLICY_AUDIT_WRITE_FAILED", audit_result.errors.front().message);
    }
  }

  return qrics::common::Result<PolicyRegistryEntry>::success(*target);
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::archive(
    const PolicyArchiveRequest& request) {
  if (!request_context_is_valid(request.actor_id, request.request_id, request.timestamp_ns)) {
    return fail_entry(
        "POLICY_REQUEST_CONTEXT_INVALID",
        "Policy registry request must include actor_id, request_id and non-negative timestamp");
  }
  if (request.reason.empty()) {
    return fail_entry("POLICY_ARCHIVE_REASON_REQUIRED", "Policy archive must include reason");
  }

  auto existing = std::find_if(entries_.begin(), entries_.end(), [&request](const auto& item) {
    return same_ref(ref_from_artifact(item.artifact), request.policy_ref);
  });
  if (existing == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND", "PolicyArtifact does not exist in registry");
  }
  if (existing->is_current_baseline) {
    return fail_entry("POLICY_BASELINE_ARCHIVE_BLOCKED",
                      "Current Baseline PolicyArtifact cannot be archived");
  }

  existing->artifact.stage = PolicyStage::Archived;
  existing->updated_at_ns = request.timestamp_ns;
  existing->approvals.push_back(make_approval(request.policy_ref, ApprovalAction::Archive,
                                              request.actor_id, request.reason,
                                              request.timestamp_ns));

  if (audit_store_ != nullptr) {
    const auto audit_result = audit_store_->append(make_policy_audit(
        request.policy_ref, qrics::audit::AuditAction::PolicyArchived, request.actor_id,
        request.request_id, request.reason, request.timestamp_ns));
    if (!audit_result.ok) {
      return fail_entry("POLICY_AUDIT_WRITE_FAILED", audit_result.errors.front().message);
    }
  }

  return qrics::common::Result<PolicyRegistryEntry>::success(*existing);
}

qrics::common::Result<PolicyRegistryEntry> InMemoryPolicyRegistry::find(
    const qrics::common::ResourceRef& policy_ref) const {
  const auto existing =
      std::find_if(entries_.begin(), entries_.end(), [&policy_ref](const auto& item) {
        return same_ref(ref_from_artifact(item.artifact), policy_ref);
      });
  if (existing == entries_.end()) {
    return fail_entry("POLICY_NOT_FOUND", "PolicyArtifact does not exist in registry");
  }
  return qrics::common::Result<PolicyRegistryEntry>::success(*existing);
}

qrics::common::Result<std::vector<PolicyRegistryEntry>> InMemoryPolicyRegistry::list_by_stage(
    PolicyStage stage) const {
  std::vector<PolicyRegistryEntry> result{};
  std::copy_if(entries_.begin(), entries_.end(), std::back_inserter(result),
               [stage](const auto& item) { return item.artifact.stage == stage; });
  return qrics::common::Result<std::vector<PolicyRegistryEntry>>::success(std::move(result));
}

}  // namespace qrics::training