// 场景配置加载器

#pragma once

#include <string>

#include "qrics/common/types.hpp"
#include "qrics/config/config_error.hpp"
#include "qrics/scenario/scene_profile.hpp"

namespace qrics::config {

class SceneConfigLoader {
 public:
  virtual ~SceneConfigLoader() = default;

  [[nodiscard]] virtual qrics::common::Result<qrics::scenario::SceneProfile> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const = 0;
};

class MinimalYamlSceneConfigLoader final : public SceneConfigLoader {
 public:
  [[nodiscard]] qrics::common::Result<qrics::scenario::SceneProfile> load(
      const std::string& path, const ConfigLoadOptions& options = {}) const override;
};

}  // namespace qrics::config