// 模型门禁引擎基础实现

#include "qrics/training/gate_engine.hpp"

#include <string>
#include <utility>

namespace qrics::training {

namespace {

[[nodiscard]] qrics::common::Result<GateReport> fail_report(const std::string& code,
                                                            const std::string& message) {
  return qrics::common::Result<GateReport>::failure({qrics::common::Error{code, message}});
}

void add_failed_rule(GateReport& report, std::string rule) {
  report.failed_rules.push_back(std::move(rule));
}

}  // namespace

qrics::common::Result<GateReport> BasicGateEngine::evaluate(
    const GateEvaluationRequest& request) const {
  const auto& metric_report = request.metric_report;
  if (metric_report.metric_report_id.empty()) {
    return fail_report("METRIC_REPORT_ID_EMPTY", "MetricReport.metric_report_id must not be empty");
  }
  if (metric_report.policy_ref.id.empty() || metric_report.policy_ref.version.empty()) {
    return fail_report("POLICY_REF_INVALID", "MetricReport.policy_ref must include id and version");
  }
  if (metric_report.scene_ref.id.empty()) {
    return fail_report("SCENE_REF_EMPTY", "MetricReport.scene_ref.id must not be empty");
  }
  if (metric_report.evaluation_run_ref.id.empty()) {
    return fail_report("EVALUATION_RUN_REF_EMPTY",
                       "MetricReport.evaluation_run_ref.id must not be empty");
  }
  if (metric_report.evaluation_suite_id.empty()) {
    return fail_report("EVALUATION_SUITE_EMPTY",
                       "MetricReport.evaluation_suite_id must not be empty");
  }
  if (metric_report.status != MetricReportStatus::Completed) {
    return fail_report("METRIC_REPORT_NOT_COMPLETED",
                       "Only completed MetricReport can be evaluated by GateEngine");
  }
  if (request.evaluated_at_ns < 0) {
    return fail_report("GATE_TIMESTAMP_INVALID", "Gate evaluation timestamp must not be negative");
  }

  GateReport report{};
  report.gate_report_id = "gate_" + metric_report.policy_ref.id + "_" +
                          metric_report.policy_ref.version + "_" +
                          std::to_string(request.evaluated_at_ns);
  report.policy_ref = metric_report.policy_ref;
  report.scene_ref = metric_report.scene_ref;
  report.evaluation_run_ref = metric_report.evaluation_run_ref;
  report.evaluation_suite_id = metric_report.evaluation_suite_id;
  report.metrics_digest = metric_report.metrics_digest;
  report.thresholds = request.thresholds;
  report.generated_at_ns = request.evaluated_at_ns;

  if (metric_report.metrics_digest.success_rate < request.thresholds.min_success_rate) {
    add_failed_rule(report, "success_rate below minimum");
  }
  if (metric_report.metrics_digest.collision_rate > request.thresholds.max_collision_rate) {
    add_failed_rule(report, "collision_rate above maximum");
  }
  if (metric_report.metrics_digest.tracking_error_m > request.thresholds.max_tracking_error_m) {
    add_failed_rule(report, "tracking_error_m above maximum");
  }
  if (metric_report.metrics_digest.recovery_rate < request.thresholds.min_recovery_rate) {
    add_failed_rule(report, "recovery_rate below minimum");
  }
  if (metric_report.metrics_digest.energy_proxy > request.thresholds.max_energy_proxy) {
    add_failed_rule(report, "energy_proxy above maximum");
  }
  if (metric_report.metrics_digest.hard_constraint_violation_count >
      request.thresholds.max_hard_constraint_violation_count) {
    add_failed_rule(report, "hard_constraint_violation_count above maximum");
  }

  if (report.failed_rules.empty()) {
    report.decision = GateDecision::Passed;
    report.reason = "Policy metrics passed all gate thresholds";
  } else {
    report.decision = GateDecision::Failed;
    report.reason = "Policy metrics failed one or more gate thresholds";
  }

  return qrics::common::Result<GateReport>::success(std::move(report));
}

}  // namespace qrics::training