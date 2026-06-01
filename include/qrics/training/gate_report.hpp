// 模型门禁报告模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/training/metric_report.hpp"
#include "qrics/training/policy_artifact.hpp"

namespace qrics::training {

enum class GateDecision : std::uint8_t { Passed, Failed };

struct GateThresholds final {
  double min_success_rate{0.80};
  double max_collision_rate{0.05};
  double max_tracking_error_m{0.30};
  double min_recovery_rate{0.50};
  double max_energy_proxy{100.0};
  int max_hard_constraint_violation_count{0};
};

struct GateReport final {
  std::string gate_report_id{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::ResourceRef scene_ref{};
  qrics::common::ResourceRef evaluation_run_ref{};
  std::string evaluation_suite_id{};
  MetricsDigest metrics_digest{};
  GateThresholds thresholds{};
  GateDecision decision{GateDecision::Failed};
  std::vector<std::string> failed_rules{};
  std::string reason{};
  qrics::common::TimestampNs generated_at_ns{0};
};

struct GateEvaluationRequest final {
  MetricReport metric_report{};
  GateThresholds thresholds{};
  qrics::common::TimestampNs evaluated_at_ns{0};
};

}  // namespace qrics::training