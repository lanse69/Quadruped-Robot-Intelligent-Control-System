// 训练配置加载器实现

#include "qrics/config/training_config_loader.hpp"

#include <cstdint>
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

[[nodiscard]] int get_int_or(const FlatYamlDocument& document, const std::string& key,
                             int fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return std::stoi(value);
}

[[nodiscard]] std::uint64_t get_uint64_or(const FlatYamlDocument& document, const std::string& key,
                                          std::uint64_t fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return static_cast<std::uint64_t>(std::stoull(value));
}

[[nodiscard]] bool get_bool_or(const FlatYamlDocument& document, const std::string& key,
                               bool fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return value == "true" || value == "yes" || value == "1";
}

[[nodiscard]] qrics::common::ResourceRef parse_resource_ref(const std::string& value) {
  const auto separator = value.find(':');
  if (separator == std::string::npos) {
    return qrics::common::ResourceRef{value, {}};
  }
  return qrics::common::ResourceRef{value.substr(0U, separator), value.substr(separator + 1U)};
}

[[nodiscard]] std::vector<qrics::common::Error> validate_training(const TrainingConfig& config) {
  std::vector<qrics::common::Error> errors{};
  if (config.training_id.empty()) {
    errors.push_back(make_config_error("TRAINING_ID_EMPTY", "training.id must not be empty"));
  }
  if (config.algorithm.empty()) {
    errors.push_back(
        make_config_error("TRAINING_ALGORITHM_EMPTY", "training.algorithm must not be empty"));
  }
  if (config.max_iterations <= 0) {
    errors.push_back(make_config_error("TRAINING_ITERATIONS_INVALID",
                                       "training.max_iterations must be positive"));
  }
  if (config.scene_ref.id.empty() || config.scene_ref.version.empty()) {
    errors.push_back(make_config_error("TRAINING_SCENE_REF_INVALID",
                                       "environment.scene_ref must use id:version format"));
  }
  if (config.num_envs <= 0) {
    errors.push_back(
        make_config_error("TRAINING_NUM_ENVS_INVALID", "environment.num_envs must be positive"));
  }
  if (config.output_dir.empty()) {
    errors.push_back(
        make_config_error("TRAINING_OUTPUT_DIR_EMPTY", "artifacts.output_dir must not be empty"));
  }
  return errors;
}

}  // namespace

qrics::common::Result<TrainingConfig> MinimalYamlTrainingConfigLoader::load(
    const std::string& path, const ConfigLoadOptions& /*options*/) const {
  auto loaded = load_flat_yaml_file(path);
  if (!loaded.ok) {
    return qrics::common::Result<TrainingConfig>::failure(std::move(loaded.errors));
  }

  TrainingConfig config{};
  config.training_id = get_value(loaded.value, "training.id");
  config.algorithm = get_value(loaded.value, "training.algorithm");
  config.max_iterations = get_int_or(loaded.value, "training.max_iterations", 0);
  config.seed = get_uint64_or(loaded.value, "training.seed", 0U);
  config.scene_ref = parse_resource_ref(get_value(loaded.value, "environment.scene_ref"));
  config.num_envs = get_int_or(loaded.value, "environment.num_envs", 0);
  config.randomization_enabled =
      get_bool_or(loaded.value, "environment.randomization_enabled", false);
  config.output_dir = get_value(loaded.value, "artifacts.output_dir");

  auto errors = validate_training(config);
  if (!errors.empty()) {
    return qrics::common::Result<TrainingConfig>::failure(std::move(errors));
  }

  return qrics::common::Result<TrainingConfig>::success(std::move(config));
}

}  // namespace qrics::config