// 策略配置加载器

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/config/config_error.hpp"
#include "qrics/training/policy_artifact.hpp"

namespace qrics::config {

class PolicyConfigLoader {
 public:
  virtual ~PolicyConfigLoader() = default;

  [[nodiscard]] virtual qrics::common::Result<qrics::training::PolicyArtifact> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const = 0;
};

class MinimalYamlPolicyConfigLoader final : public PolicyConfigLoader {
 public:
  [[nodiscard]] qrics::common::Result<qrics::training::PolicyArtifact> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const override;
};

}  // namespace qrics::config