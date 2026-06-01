// 模型审批记录模型

#pragma once

#include <cstdint>
#include <string>

#include "qrics/common/types.hpp"

namespace qrics::training {

enum class ApprovalAction : std::uint8_t { Release, PromoteBaseline, RollbackBaseline, Archive };

enum class ApprovalDecision : std::uint8_t { Approved, Rejected };

struct ApprovalRecord final {
  std::string approval_id{};
  qrics::common::ResourceRef policy_ref{};
  ApprovalAction action{ApprovalAction::Release};
  ApprovalDecision decision{ApprovalDecision::Approved};
  std::string approver_id{};
  std::string reason{};
  qrics::common::TimestampNs approved_at_ns{0};
};

}  // namespace qrics::training