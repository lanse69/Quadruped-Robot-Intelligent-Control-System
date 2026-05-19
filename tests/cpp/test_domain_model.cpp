// 领域模型测试

#include <string>

#include "qrics/domain/domain.hpp"

namespace {

class FakeAdapter final : public qrics::simulation::SimulationAdapter {
 public:
  [[nodiscard]] std::string name() const override {
    return "fake";
  }

  [[nodiscard]] qrics::simulation::AdapterState state() const override {
    return state_;
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> initialize(
      const qrics::simulation::AdapterConfig& /*config*/) override {
    state_ = qrics::simulation::AdapterState::Initialized;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterState> load_scene(
      const qrics::scenario::SceneProfile& /*scene_profile*/) override {
    state_ = qrics::simulation::AdapterState::SceneLoaded;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::ObservationPacket> reset() override {
    return qrics::common::Result<qrics::simulation::ObservationPacket>::success({});
  }

  [[nodiscard]] qrics::common::Result<qrics::simulation::AdapterStepResult> step(
      const qrics::control::SafeAction& action) override {
    if (action.decision == qrics::control::SafetyDecision::Rejected) {
      return qrics::common::Result<qrics::simulation::AdapterStepResult>::failure(
          {qrics::common::Error{"ACTION_REJECTED", "Rejected action cannot be stepped"}});
    }

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
    state_ = qrics::simulation::AdapterState::Stopped;
    return qrics::common::Result<qrics::simulation::AdapterState>::success(state_);
  }

 private:
  qrics::simulation::AdapterState state_{qrics::simulation::AdapterState::Created};
};

}  // namespace

int main() {
  qrics::scenario::SceneProfile scene{};
  scene.scene_id = "minimal_scene";
  scene.version = "0.1.0";
  scene.status = qrics::scenario::SceneStatus::Baseline;

  qrics::task::TaskScript task{};
  task.task_id = "task_001";
  task.scene_ref = qrics::common::ResourceRef{scene.scene_id, scene.version};
  task.goal = "move_to_checkpoint";
  task.status = qrics::task::TaskStatus::Planned;

  qrics::training::PolicyArtifact policy{};
  policy.policy_id = "placeholder_policy";
  policy.version = "0.1.0";
  policy.stage = qrics::training::PolicyStage::Released;

  qrics::control::ActionProposal proposal{};
  proposal.proposal_id = "proposal_001";
  proposal.policy_ref = qrics::common::ResourceRef{policy.policy_id, policy.version};
  proposal.task_node_id = "node_001";
  proposal.action_type = qrics::control::ActionType::BodyVelocity;

  qrics::control::SafeAction safe_action{};
  safe_action.action_id = "action_001";
  safe_action.source_proposal_id = proposal.proposal_id;
  safe_action.action_type = qrics::control::ActionType::BodyVelocity;
  safe_action.decision = qrics::control::SafetyDecision::Accepted;

  FakeAdapter adapter{};

  if (adapter.name() != "fake") {
    return 1;
  }

  if (!adapter.initialize({}).ok) {
    return 2;
  }

  if (!adapter.load_scene(scene).ok) {
    return 3;
  }

  const auto step_result = adapter.step(safe_action);
  if (!step_result.ok) {
    return 4;
  }

  qrics::safety::SafetyEvent event{};
  event.event_id = "event_001";
  event.run_id = "run_001";
  event.severity = qrics::safety::Severity::Info;
  event.trigger_type = qrics::safety::TriggerType::None;

  qrics::experiment::ExperimentRun run{};
  run.run_id = "run_001";
  run.scene_ref = qrics::common::ResourceRef{scene.scene_id, scene.version};
  run.policy_ref = qrics::common::ResourceRef{policy.policy_id, policy.version};
  run.status = qrics::experiment::ExperimentStatus::Running;

  if (run.scene_ref.id != "minimal_scene") {
    return 5;
  }

  if (!adapter.close().ok) {
    return 6;
  }

  return 0;
}