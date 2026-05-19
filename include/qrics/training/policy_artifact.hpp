// 策略工件模型

#pragma once

#include <cstdint>
#include <string>

#include "qrics/common/types.hpp"

namespace qrics::training {

enum class PolicyStage : std::uint8_t {
  Draft,
  Candidate,
  GatePassed,
  GateFailed,
  Released,
  Baseline,
  Archived
};

struct MetricsDigest final {
  double success_rate{0.0};
  double collision_rate{0.0};
  double tracking_error_m{0.0};
  double recovery_rate{0.0};
  double energy_proxy{0.0};
};

struct PolicyArtifact final {
  std::string policy_id{};
  std::string version{};
  std::string algorithm_type{};
  std::string artifact_uri{};
  qrics::common::Checksum checksum{};
  PolicyStage stage{PolicyStage::Draft};
  MetricsDigest metrics_digest{};
};

}  // namespace qrics::training