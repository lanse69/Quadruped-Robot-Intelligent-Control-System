#include <cassert>

#include "qrics/audit/audit_log.hpp"
#include "qrics/training/gate_engine.hpp"
#include "qrics/training/policy_registry.hpp"

namespace {

[[nodiscard]] qrics::training::PolicyArtifact make_policy(const std::string& version) {
  qrics::training::PolicyArtifact artifact{};
  artifact.policy_id = "flat_policy";
  artifact.version = version;
  artifact.algorithm_type = "ppo";
  artifact.artifact_uri = "artifacts/policies/flat_policy_" + version + ".onnx";
  artifact.checksum.value = "checksum_" + version;
  artifact.stage = qrics::training::PolicyStage::Draft;
  return artifact;
}

[[nodiscard]] qrics::training::GateReport make_passed_gate_report(
    const qrics::common::ResourceRef& policy_ref, qrics::common::TimestampNs generated_at_ns) {
  qrics::training::MetricReport metric{};
  metric.metric_report_id = "metric_" + policy_ref.id + "_" + policy_ref.version;
  metric.evaluation_run_ref = qrics::common::ResourceRef{"eval_" + policy_ref.version, "0.1.0"};
  metric.policy_ref = policy_ref;
  metric.scene_ref = qrics::common::ResourceRef{"minimal_scene", "0.1.0"};
  metric.evaluation_suite_id = "standard_locomotion_suite";
  metric.metrics_digest.success_rate = 0.95;
  metric.metrics_digest.collision_rate = 0.0;
  metric.metrics_digest.tracking_error_m = 0.10;
  metric.metrics_digest.recovery_rate = 0.80;
  metric.metrics_digest.energy_proxy = 10.0;
  metric.metrics_digest.hard_constraint_violation_count = 0;
  metric.status = qrics::training::MetricReportStatus::Completed;
  metric.generated_at_ns = generated_at_ns;

  qrics::training::BasicGateEngine engine{};
  qrics::training::GateEvaluationRequest request{};
  request.metric_report = metric;
  request.evaluated_at_ns = generated_at_ns + 1;
  const auto result = engine.evaluate(request);
  assert(result.ok);
  return result.value;
}

}  // namespace

int main() {
  qrics::audit::InMemoryAuditLogStore audit_store{};
  qrics::training::InMemoryPolicyRegistry registry{&audit_store};

  qrics::training::PolicyRegistryRegisterRequest register_v1{};
  register_v1.artifact = make_policy("1.0.0");
  register_v1.actor_id = "algo";
  register_v1.request_id = "req_register_v1";
  register_v1.timestamp_ns = 100;

  const auto candidate = registry.register_candidate(register_v1);
  assert(candidate.ok);
  assert(candidate.value.artifact.stage == qrics::training::PolicyStage::Candidate);

  qrics::training::PolicyReleaseRequest premature_release{};
  premature_release.policy_ref = qrics::common::ResourceRef{"flat_policy", "1.0.0"};
  premature_release.actor_id = "algo";
  premature_release.request_id = "req_release_blocked";
  premature_release.reason = "try release before gate";
  premature_release.timestamp_ns = 110;
  const auto blocked = registry.release(premature_release);
  assert(!blocked.ok);
  assert(blocked.errors.front().code == "POLICY_GATE_NOT_PASSED");

  qrics::training::PolicyGateReportAttachRequest attach_v1{};
  attach_v1.policy_ref = qrics::common::ResourceRef{"flat_policy", "1.0.0"};
  attach_v1.gate_report = make_passed_gate_report(attach_v1.policy_ref, 200);
  attach_v1.actor_id = "algo";
  attach_v1.request_id = "req_gate_v1";
  attach_v1.timestamp_ns = 210;
  const auto gate_attached = registry.attach_gate_report(attach_v1);
  assert(gate_attached.ok);
  assert(gate_attached.value.artifact.stage == qrics::training::PolicyStage::GatePassed);

  qrics::training::PolicyReleaseRequest release_v1{};
  release_v1.policy_ref = attach_v1.policy_ref;
  release_v1.actor_id = "algo";
  release_v1.request_id = "req_release_v1";
  release_v1.reason = "passed standard gate";
  release_v1.timestamp_ns = 300;
  const auto released = registry.release(release_v1);
  assert(released.ok);
  assert(released.value.artifact.stage == qrics::training::PolicyStage::Released);

  qrics::training::PolicyBaselinePromotionRequest baseline_v1{};
  baseline_v1.policy_ref = attach_v1.policy_ref;
  baseline_v1.actor_id = "lead";
  baseline_v1.request_id = "req_baseline_v1";
  baseline_v1.reason = "promote first stable policy";
  baseline_v1.timestamp_ns = 400;
  const auto baseline = registry.promote_baseline(baseline_v1);
  assert(baseline.ok);
  assert(baseline.value.artifact.stage == qrics::training::PolicyStage::Baseline);
  assert(baseline.value.is_current_baseline);

  qrics::training::PolicyRegistryRegisterRequest register_v2{};
  register_v2.artifact = make_policy("2.0.0");
  register_v2.actor_id = "algo";
  register_v2.request_id = "req_register_v2";
  register_v2.timestamp_ns = 500;
  assert(registry.register_candidate(register_v2).ok);

  qrics::training::PolicyGateReportAttachRequest attach_v2{};
  attach_v2.policy_ref = qrics::common::ResourceRef{"flat_policy", "2.0.0"};
  attach_v2.gate_report = make_passed_gate_report(attach_v2.policy_ref, 600);
  attach_v2.actor_id = "algo";
  attach_v2.request_id = "req_gate_v2";
  attach_v2.timestamp_ns = 610;
  assert(registry.attach_gate_report(attach_v2).ok);

  qrics::training::PolicyReleaseRequest release_v2{};
  release_v2.policy_ref = attach_v2.policy_ref;
  release_v2.actor_id = "algo";
  release_v2.request_id = "req_release_v2";
  release_v2.reason = "passed second gate";
  release_v2.timestamp_ns = 700;
  assert(registry.release(release_v2).ok);

  qrics::training::PolicyRollbackRequest rollback{};
  rollback.target_policy_ref = attach_v1.policy_ref;
  rollback.actor_id = "lead";
  rollback.request_id = "req_rollback_v1";
  rollback.reason = "rollback to stable baseline for demo";
  rollback.timestamp_ns = 800;
  const auto rolled_back = registry.rollback_baseline(rollback);
  assert(rolled_back.ok);
  assert(rolled_back.value.is_current_baseline);
  assert(rolled_back.value.artifact.version == "1.0.0");

  qrics::training::PolicyArchiveRequest archive_baseline{};
  archive_baseline.policy_ref = attach_v1.policy_ref;
  archive_baseline.actor_id = "lead";
  archive_baseline.request_id = "req_archive_baseline";
  archive_baseline.reason = "should be blocked";
  archive_baseline.timestamp_ns = 900;
  const auto archive_blocked = registry.archive(archive_baseline);
  assert(!archive_blocked.ok);
  assert(archive_blocked.errors.front().code == "POLICY_BASELINE_ARCHIVE_BLOCKED");

  qrics::audit::AuditQuery audit_query{};
  audit_query.object_id = "flat_policy";
  const auto audits = audit_store.query(audit_query);
  assert(audits.ok);
  assert(audits.value.size() >= 3U);

  return 0;
}