// 命令行入口

#include <iostream>

#include "qrics/core/version.hpp"

int main() {
  const auto v = qrics::core::version();

  std::cout << qrics::core::project_name() << " " << v.major << "." << v.minor << "." << v.patch
            << '\n';

  return 0;
}