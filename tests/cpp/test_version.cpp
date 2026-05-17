#include "qrics/core/version.hpp"

int main() {
  const auto v = qrics::core::version();

  if (qrics::core::project_name() != "QRICS") {
    return 1;
  }

  if (v.major != 0 || v.minor != 1 || v.patch != 0) {
    return 2;
  }

  return 0;
}