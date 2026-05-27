#include <fstream>
#include <string>

#include "qrics/config/policy_config_loader.hpp"
#include "qrics/config/training_config_loader.hpp"

int main() {
  qrics::config::MinimalYamlPolicyConfigLoader policy_loader{};
  const auto policy = policy_loader.load("../../configs/policies/placeholder_policy.yaml");
  if (!policy.ok) {
    return 1;
  }
  if (policy.value.policy_id != "placeholder_policy" || policy.value.version != "0.1.0") {
    return 2;
  }
  if (policy.value.stage != qrics::training::PolicyStage::Released) {
    return 3;
  }
  if (policy.value.metrics_digest.success_rate < 0.89) {
    return 4;
  }

  qrics::config::MinimalYamlTrainingConfigLoader training_loader{};
  const auto training = training_loader.load("../../configs/training/minimal_training.yaml");
  if (!training.ok) {
    return 5;
  }
  if (training.value.training_id != "minimal_training" || training.value.max_iterations != 10) {
    return 6;
  }
  if (training.value.scene_ref.id != "minimal_scene" ||
      training.value.scene_ref.version != "0.1.0") {
    return 7;
  }
  if (!training.value.randomization_enabled) {
    return 8;
  }

  const std::string invalid_path = "invalid_policy.yaml";
  {
    std::ofstream output{invalid_path};
    output << "policy:\n";
    output << "  id: invalid_policy\n";
    output << "  version: 0.1.0\n";
    output << "  stage: draft\n";
  }

  const auto invalid = policy_loader.load(invalid_path);
  if (invalid.ok || invalid.errors.empty()) {
    return 9;
  }

  return 0;
}