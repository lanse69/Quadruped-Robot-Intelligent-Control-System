#pragma once

#include <string_view>

namespace qrics::core {

struct Version final {
  int major;
  int minor;
  int patch;
};

[[nodiscard]] constexpr Version version() noexcept {
  return Version{0, 1, 0};
}

[[nodiscard]] std::string_view project_name() noexcept;

}  // namespace qrics::core