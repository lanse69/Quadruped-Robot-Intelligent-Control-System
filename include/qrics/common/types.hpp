// 通用基础类型

#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace qrics::common {

// 纳秒时间戳
using TimestampNs = std::int64_t;

struct Vec3 final {
  double x{0.0};
  double y{0.0};
  double z{0.0};
};

struct Quaternion final {
  double w{1.0};
  double x{0.0};
  double y{0.0};
  double z{0.0};
};

struct Pose final {
  Vec3 position{};
  Quaternion orientation{};
};

struct Version final {
  int major{0};
  int minor{0};
  int patch{0};
};

// 用于引用场景、策略、实验、回放等版本化对象
struct ResourceRef final {
  std::string id{};
  std::string version{};
};

struct Checksum final {
  std::string algorithm{"sha256"};
  std::string value{};
};

struct Error final {
  std::string code{};
  std::string message{};
};

// 先用于接口返回
template <typename T>
struct Result final {
  bool ok{false};
  T value{};
  std::vector<Error> errors{};

  static Result<T> success(T result_value) {
    return Result<T>{true, std::move(result_value), {}};
  }

  static Result<T> failure(std::vector<Error> result_errors) {
    return Result<T>{false, T{}, std::move(result_errors)};
  }
};

}  // namespace qrics::common