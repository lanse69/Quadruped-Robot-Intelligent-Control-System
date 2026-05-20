// ControlLoop 集成测试

#include <string>

#include "qrics/control/control_loop.hpp"

namespace {

class FakeAdapter final : public qrics::simulation::SimulationAdapter {
 public:
  [[nodiscard]] std::string name() const override {
    return "fake";
  }

  [[nodiscard]] qrics::simulation::AdapterState state() const override {
    return qrics::simulation::AdapterState::Running;
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> initialize(
      const qrics::simulation::AdapterConfig& /*config*/) override {
    return qrics::common::Result<qrics::simulation::AdapterState>::success(
        qrics::simulation::AdapterState::Initialized);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> load_scene(
      const qrics::scenario::SceneProfile& /*scene_profile*/) override {
    return qrics::common::Result<qrics::simulation::AdapterState>::success(
        qrics::simulation::AdapterState::SceneLoaded);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::ObservationPacket> reset() override {
    return qrics::common::Result<qrics::simulation::ObservationPacket>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterStepResult> step(
      const qrics::control::SafeAction& action) override {
    ++step_count;
    last_action = action;

    qrics::simulation::AdapterStepResult result{};
    result.state = qrics::simulation::AdapterState::Running;
    return qrics::common::Result<qrics::simulation::AdapterStepResult>::success(result);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::ObservationPacket> observe()
      const override {
    return qrics::common::Result<qrics::simulation::ObservationPacket>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::RobotState> robot_state() const override {
    return qrics::common::Result<qrics::simulation::RobotState>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> close() override {
    return qrics::common::Result<qrics::simulation::AdapterState>::success(
        qrics::simulation::AdapterState::Stopped);
  }

  int step_count{0};
  qrics::control::SafeAction last_action{};
};

[[nodiscard]] qrics::control::ActionProposal make_proposal(qrics::control::ActionType action_type) {
  qrics::control::ActionProposal proposal{};
  proposal.proposal_id = "proposal_001";
  proposal.action_type = action_type;
  proposal.desired_body_velocity = qrics::common::Vec3{0.5, 0.0, 0.0};
  proposal.desired_yaw_rate_radps = 0.1;
  proposal.timestamp_ns = 2000;
  return proposal;
}

[[nodiscard]] qrics::safety::SafetyContext make_context() {
  qrics::safety::SafetyContext context{};
  context.run_id = "run_001";
  context.robot_state.stability_state = qrics::simulation::StabilityState::Stable;
  context.robot_state.risk_score = 0.0;
  return context;
}

}  // namespace

int main() {
  FakeAdapter adapter{};
  qrics::safety::BasicSafetyShield shield{qrics::safety::SafetyLimits{}};
  qrics::control::ControlLoop loop{adapter, shield};

  const auto accepted_result =
      loop.step_once(make_proposal(qrics::control::ActionType::BodyVelocity), make_context());

  if (!accepted_result.ok) {
    return 1;
  }
  if (!accepted_result.value.adapter_stepped) {
    return 2;
  }
  if (adapter.step_count != 1) {
    return 3;
  }
  if (adapter.last_action.decision != qrics::control::SafetyDecision::Accepted) {
    return 4;
  }

  auto manual_context = make_context();
  manual_context.manual_override_active = true;
  manual_context.override_command.command_type = qrics::safety::OverrideCommandType::ManualControl;

  const auto manual_result =
      loop.step_once(make_proposal(qrics::control::ActionType::BodyVelocity), manual_context);

  if (!manual_result.ok) {
    return 5;
  }
  if (manual_result.value.adapter_stepped) {
    return 6;
  }
  if (adapter.step_count != 1) {
    return 7;
  }
  if (manual_result.value.safety_evaluation.safe_action.decision !=
      qrics::control::SafetyDecision::Rejected) {
    return 8;
  }
  if (manual_result.value.safety_evaluation.events.empty()) {
    return 9;
  }

  const auto rejected_result =
      loop.step_once(make_proposal(qrics::control::ActionType::JointVelocity), make_context());

  if (!rejected_result.ok) {
    return 10;
  }
  if (rejected_result.value.adapter_stepped) {
    return 11;
  }
  if (adapter.step_count != 1) {
    return 12;
  }
  if (rejected_result.value.safety_evaluation.events.empty()) {
    return 13;
  }

  return 0;
}