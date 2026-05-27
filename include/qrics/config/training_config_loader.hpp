// 训练配置加载器

#pragma once

#include <cstdint>
#include <string>

#include "qrics/common/types.hpp"
#include "qrics/config/config_error.hpp"

namespace qrics::config {

struct TrainingConfig final {
  std::string training_id{};
  std::string algorithm{};
  int max_iterations{0};
  std::uint64_t seed{0U};
  qrics::common::ResourceRef scene_ref{};
  int num_envs{0};
  bool randomization_enabled{false};
  std::string output_dir{};
};

class TrainingConfigLoader {
 public:
  virtual ~TrainingConfigLoader() = default;

  [[nodiscard]] virtual qrics::common::Result<TrainingConfig> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const = 0;
};

class MinimalYamlTrainingConfigLoader final : public TrainingConfigLoader {
 public:
  [[nodiscard]] qrics::common::Result<TrainingConfig> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const override;
};

}  // namespace qrics::config