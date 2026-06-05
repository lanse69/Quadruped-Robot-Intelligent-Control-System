// 恢复控制器实现

#include "qrics/control/recovery_controller.hpp"

#include <string>

namespace qrics::control {

namespace {

[[nodiscard]] ActionProposal make_recovery_proposal(const RecoveryRequest& request,
                                                    ActionType action_type, double confidence) {
  ActionProposal proposal{};
  proposal.proposal_id = "recovery_" + request.task_node.node_id;
  proposal.policy_ref = request.policy_ref;
  proposal.task_node_id = request.task_node.node_id;
  proposal.action_type = action_type;
  proposal.confidence = confidence;
  proposal.timestamp_ns = request.timestamp_ns;
  return proposal;
}

}  // namespace

StabilityRecoveryController::StabilityRecoveryController(RecoveryControllerConfig config)
    : config_(config) {}

RecoveryDecision StabilityRecoveryController::evaluate(const RecoveryRequest& request) const {
  RecoveryDecision decision{};

  switch (request.robot_state.stability_state) {
    case qrics::simulation::StabilityState::Fallen:
      decision.recovery_required = true;
      decision.terminal_recovery = true;
      decision.proposal = make_recovery_proposal(request, ActionType::SafeStand, 1.0);
      decision.reason = "Robot is fallen; request SafeStand recovery";
      return decision;
    case qrics::simulation::StabilityState::Unstable:
      decision.recovery_required = true;
      decision.terminal_recovery = false;
      decision.proposal = make_recovery_proposal(request, ActionType::SafeStand, 0.95);
      decision.reason = "Robot is unstable; request SafeStand before continuing";
      return decision;
    case qrics::simulation::StabilityState::Recovering:
      decision.recovery_required = true;
      decision.terminal_recovery = false;
      decision.proposal = make_recovery_proposal(request, ActionType::Stop, 0.85);
      decision.reason = "Robot is already recovering; hold position";
      return decision;
    case qrics::simulation::StabilityState::Stable:
    case qrics::simulation::StabilityState::Unknown:
      break;
  }

  if (request.robot_state.risk_score >= config_.recovery_risk_threshold) {
    decision.recovery_required = true;
    decision.terminal_recovery = false;
    decision.proposal = make_recovery_proposal(request, ActionType::SafeStand, 0.90);
    decision.reason = "Risk score exceeds recovery threshold; request SafeStand";
    return decision;
  }

  if (request.robot_state.risk_score >= config_.stand_still_risk_threshold) {
    decision.recovery_required = true;
    decision.terminal_recovery = false;
    decision.proposal = make_recovery_proposal(request, ActionType::Stop, 0.75);
    decision.reason = "Risk score is elevated; hold position";
    return decision;
  }

  decision.recovery_required = false;
  decision.reason = "Recovery is not required";
  return decision;
}

}  // namespace qrics::control