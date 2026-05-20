// 最小控制闭环

#pragma once

#include <utility>
#include <vector>

#include "qrics/common/types.hpp"
#include "qrics/control/action.hpp"
#include "qrics/safety/safety_shield.hpp"
#include "qrics/simulation/simulation_adapter.hpp"

namespace qrics::control {

struct ControlStepResult final {
  qrics::safety::SafetyEvaluation safety_evaluation{};
  bool adapter_stepped{false};
  qrics::simulation::AdapterStepResult adapter_step_result{};
};

class ControlLoop final {
 public:
  ControlLoop(qrics::simulation::SimulationAdapter& adapter,
              const qrics::safety::SafetyShield& safety_shield)
      : adapter_(adapter), safety_shield_(safety_shield) {}

  [[nodiscard]] qrics::common::Result<ControlStepResult> step_once(
      const ActionProposal& proposal, const qrics::safety::SafetyContext& context) {
    ControlStepResult result{};
    result.safety_evaluation = safety_shield_.evaluate(proposal, context);

    if (result.safety_evaluation.safe_action.decision == SafetyDecision::Rejected) {
      result.adapter_stepped = false;
      return qrics::common::Result<ControlStepResult>::success(std::move(result));
    }

    auto adapter_result = adapter_.step(result.safety_evaluation.safe_action);
    if (!adapter_result.ok) {
      return qrics::common::Result<ControlStepResult>::failure(adapter_result.errors);
    }

    result.adapter_stepped = true;
    result.adapter_step_result = adapter_result.value;
    return qrics::common::Result<ControlStepResult>::success(std::move(result));
  }

 private:
  qrics::simulation::SimulationAdapter& adapter_;
  const qrics::safety::SafetyShield& safety_shield_;
};

}  // namespace qrics::control