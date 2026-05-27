// 配置加载通用类型

#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>

#include "qrics/common/types.hpp"

namespace qrics::config {

enum class ConfigFormat : std::uint8_t { MinimalYaml };

struct ConfigLoadOptions final {
  ConfigFormat format{ConfigFormat::MinimalYaml};
  bool allow_unknown_keys{true};
};

struct FlatYamlDocument final {
  std::map<std::string, std::string> values{};
};

[[nodiscard]] qrics::common::Result<FlatYamlDocument> load_flat_yaml_file(const std::string& path);

[[nodiscard]] qrics::common::Error make_config_error(const std::string& code,
                                                     const std::string& message);

}  // namespace qrics::config