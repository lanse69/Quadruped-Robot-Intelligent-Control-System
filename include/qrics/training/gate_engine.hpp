// 模型门禁引擎接口与基础实现声明

#pragma once

#include "qrics/common/types.hpp"
#include "qrics/training/gate_report.hpp"

namespace qrics::training {

class GateEngine {
 public:
  virtual ~GateEngine() = default;

  [[nodiscard]] virtual qrics::common::Result<GateReport> evaluate(
      const GateEvaluationRequest& request) const = 0;
};

class BasicGateEngine final : public GateEngine {
 public:
  [[nodiscard]] qrics::common::Result<GateReport> evaluate(
      const GateEvaluationRequest& request) const override;
};

}  // namespace qrics::training