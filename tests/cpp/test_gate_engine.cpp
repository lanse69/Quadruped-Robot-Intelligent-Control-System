#include <cassert>
#include <string>

#include "qrics/training/gate_engine.hpp"

namespace {

[[nodiscard]] qrics::training::MetricReport make_metric_report(
    qrics::training::MetricsDigest metrics) {
  qrics::training::MetricReport report{};
  report.metric_report_id = "metric_policy_v1";
  report.evaluation_run_ref = qrics::common::ResourceRef{"eval_run_001", "0.1.0"};
  report.policy_ref = qrics::common::ResourceRef{"policy_flat", "1.0.0"};
  report.scene_ref = qrics::common::ResourceRef{"minimal_scene", "0.1.0"};
  report.evaluation_suite_id = "standard_locomotion_suite";
  report.metrics_digest = metrics;
  report.status = qrics::training::MetricReportStatus::Completed;
  report.generated_at_ns = 100;
  return report;
}

}  // namespace

int main() {
  qrics::training::BasicGateEngine engine{};

  qrics::training::MetricsDigest passing_metrics{};
  passing_metrics.success_rate = 0.95;
  passing_metrics.collision_rate = 0.0;
  passing_metrics.tracking_error_m = 0.10;
  passing_metrics.recovery_rate = 0.80;
  passing_metrics.energy_proxy = 10.0;
  passing_metrics.hard_constraint_violation_count = 0;

  qrics::training::GateEvaluationRequest passing_request{};
  passing_request.metric_report = make_metric_report(passing_metrics);
  passing_request.evaluated_at_ns = 200;

  const auto passed = engine.evaluate(passing_request);
  assert(passed.ok);
  assert(passed.value.decision == qrics::training::GateDecision::Passed);
  assert(passed.value.failed_rules.empty());

  qrics::training::MetricsDigest failing_metrics{};
  failing_metrics.success_rate = 0.50;
  failing_metrics.collision_rate = 0.20;
  failing_metrics.tracking_error_m = 0.60;
  failing_metrics.recovery_rate = 0.10;
  failing_metrics.energy_proxy = 200.0;
  failing_metrics.hard_constraint_violation_count = 1;

  qrics::training::GateEvaluationRequest failing_request{};
  failing_request.metric_report = make_metric_report(failing_metrics);
  failing_request.evaluated_at_ns = 300;

  const auto failed = engine.evaluate(failing_request);
  assert(failed.ok);
  assert(failed.value.decision == qrics::training::GateDecision::Failed);
  assert(failed.value.failed_rules.size() == 6U);

  qrics::training::GateEvaluationRequest invalid_request{};
  invalid_request.metric_report = make_metric_report(passing_metrics);
  invalid_request.metric_report.status = qrics::training::MetricReportStatus::Draft;
  invalid_request.evaluated_at_ns = 400;

  const auto invalid = engine.evaluate(invalid_request);
  assert(!invalid.ok);
  assert(invalid.errors.front().code == "METRIC_REPORT_NOT_COMPLETED");

  return 0;
}