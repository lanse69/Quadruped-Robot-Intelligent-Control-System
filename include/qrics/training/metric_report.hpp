// 训练评测指标报告模型

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/training/policy_artifact.hpp"

namespace qrics::training {

enum class MetricReportStatus : std::uint8_t { Draft, Completed, Invalidated };

struct MetricReport final {
  std::string metric_report_id{};
  qrics::common::ResourceRef evaluation_run_ref{};
  qrics::common::ResourceRef policy_ref{};
  qrics::common::ResourceRef scene_ref{};
  std::string evaluation_suite_id{};
  MetricsDigest metrics_digest{};
  MetricReportStatus status{MetricReportStatus::Draft};
  std::vector<std::string> notes{};
  qrics::common::TimestampNs generated_at_ns{0};
};

}  // namespace qrics::training