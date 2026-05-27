// 策略配置加载器实现

#include "qrics/config/policy_config_loader.hpp"

#include <string>
#include <utility>
#include <vector>

namespace qrics::config {

namespace {

[[nodiscard]] std::string get_value(const FlatYamlDocument& document, const std::string& key) {
  const auto found = document.values.find(key);
  if (found == document.values.end()) {
    return {};
  }
  return found->second;
}

[[nodiscard]] double get_double_or(const FlatYamlDocument& document, const std::string& key,
                                   double fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return std::stod(value);
}

[[nodiscard]] qrics::training::PolicyStage parse_stage(const std::string& value) {
  if (value == "candidate") {
    return qrics::training::PolicyStage::Candidate;
  }
  if (value == "gate_passed") {
    return qrics::training::PolicyStage::GatePassed;
  }
  if (value == "gate_failed") {
    return qrics::training::PolicyStage::GateFailed;
  }
  if (value == "released") {
    return qrics::training::PolicyStage::Released;
  }
  if (value == "baseline") {
    return qrics::training::PolicyStage::Baseline;
  }
  if (value == "archived") {
    return qrics::training::PolicyStage::Archived;
  }
  return qrics::training::PolicyStage::Draft;
}

[[nodiscard]] std::vector<qrics::common::Error> validate_policy(
    const qrics::training::PolicyArtifact& policy) {
  std::vector<qrics::common::Error> errors{};
  if (policy.policy_id.empty()) {
    errors.push_back(make_config_error("POLICY_ID_EMPTY", "policy.id must not be empty"));
  }
  if (policy.version.empty()) {
    errors.push_back(make_config_error("POLICY_VERSION_EMPTY", "policy.version must not be empty"));
  }
  if (policy.algorithm_type.empty()) {
    errors.push_back(make_config_error("POLICY_TYPE_EMPTY", "policy.type must not be empty"));
  }
  if (policy.artifact_uri.empty()) {
    errors.push_back(
        make_config_error("POLICY_ARTIFACT_URI_EMPTY", "policy.artifact_uri must not be empty"));
  }
  return errors;
}

}  // namespace

qrics::common::Result<qrics::training::PolicyArtifact> MinimalYamlPolicyConfigLoader::load(
    const std::string& path, const ConfigLoadOptions& /*options*/) const {
  auto loaded = load_flat_yaml_file(path);
  if (!loaded.ok) {
    return qrics::common::Result<qrics::training::PolicyArtifact>::failure(
        std::move(loaded.errors));
  }

  qrics::training::PolicyArtifact policy{};
  policy.policy_id = get_value(loaded.value, "policy.id");
  policy.version = get_value(loaded.value, "policy.version");
  policy.algorithm_type = get_value(loaded.value, "policy.type");
  policy.artifact_uri = get_value(loaded.value, "policy.artifact_uri");
  policy.stage = parse_stage(get_value(loaded.value, "policy.stage"));
  policy.checksum.algorithm = get_value(loaded.value, "checksum.algorithm");
  policy.checksum.value = get_value(loaded.value, "checksum.value");
  policy.metrics_digest.success_rate = get_double_or(loaded.value, "metrics.success_rate", 0.0);
  policy.metrics_digest.collision_rate = get_double_or(loaded.value, "metrics.collision_rate", 0.0);
  policy.metrics_digest.tracking_error_m =
      get_double_or(loaded.value, "metrics.tracking_error_m", 0.0);
  policy.metrics_digest.recovery_rate = get_double_or(loaded.value, "metrics.recovery_rate", 0.0);
  policy.metrics_digest.energy_proxy = get_double_or(loaded.value, "metrics.energy_proxy", 0.0);

  auto errors = validate_policy(policy);
  if (!errors.empty()) {
    return qrics::common::Result<qrics::training::PolicyArtifact>::failure(std::move(errors));
  }

  return qrics::common::Result<qrics::training::PolicyArtifact>::success(std::move(policy));
}

}  // namespace qrics::config