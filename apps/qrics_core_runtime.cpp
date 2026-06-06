#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "qrics/runtime/local_task_run_engine.hpp"
#include "qrics/simulation/local_simulation_adapter.hpp"

namespace {

[[nodiscard]] bool starts_with(const std::string& value, const std::string& prefix) {
  return value.starts_with(prefix);
}

[[nodiscard]] std::vector<std::string> split(const std::string& value, char delimiter) {
  std::vector<std::string> parts;
  std::string current;
  std::istringstream stream(value);
  while (std::getline(stream, current, delimiter)) {
    parts.push_back(current);
  }
  return parts;
}

[[nodiscard]] double parse_double(const std::string& value, double fallback) {
  try {
    return std::stod(value);
  } catch (...) {
    return fallback;
  }
}

[[nodiscard]] int parse_int(const std::string& value, int fallback) {
  try {
    return std::stoi(value);
  } catch (...) {
    return fallback;
  }
}

[[nodiscard]] std::vector<qrics::runtime::LocalTaskTarget> parse_task_path(
    const std::string& value) {
  std::vector<qrics::runtime::LocalTaskTarget> targets;
  if (value.empty()) {
    return targets;
  }
  for (const auto& item : split(value, ',')) {
    const auto parts = split(item, ':');
    if (parts.size() < 3U) {
      continue;
    }
    qrics::runtime::LocalTaskTarget target{};
    target.target_id = parts[0];
    target.position.x = parse_double(parts[1], 0.0);
    target.position.y = parse_double(parts[2], 0.0);
    target.position.z = parts.size() > 3U ? parse_double(parts[3], 0.35) : 0.35;
    target.dwell_time_s = parts.size() > 4U ? parse_double(parts[4], 0.0) : 0.0;
    targets.push_back(target);
  }
  return targets;
}

[[nodiscard]] std::vector<qrics::runtime::LocalTaskTarget> default_task_path() {
  return {qrics::runtime::LocalTaskTarget{"A", qrics::common::Vec3{0.85, 0.25, 0.35}, 0.3},
          qrics::runtime::LocalTaskTarget{"B", qrics::common::Vec3{1.65, -0.25, 0.35}, 0.3},
          qrics::runtime::LocalTaskTarget{"platform", qrics::common::Vec3{0.0, 0.0, 0.35}, 0.0}};
}

void print_usage() {
  std::cerr << "Usage: qrics_core_runtime [--run-id ID] [--backend minimal|mujoco|webots] "
               "[--profile headless_fast] [--terrain flat|mixed_terrain_pack] [--steps N] "
               "[--task-path id:x:y[:z[:dwell]],...]\n";
}

}  // namespace

int main(int argc, char** argv) {
  std::string run_id{"cpp_cli_run"};
  std::string backend{"minimal"};
  std::string profile{"headless_fast"};
  std::string terrain{"mixed_terrain_pack"};
  std::string scene_id{"cpp_cli_scene"};
  std::string scene_version{"0.1.0"};
  std::string task_path_arg{};
  int max_steps{160};

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto next_value = [&]() -> std::string {
      if (i + 1 >= argc) {
        return {};
      }
      ++i;
      return argv[i];
    };

    if (arg == "--help" || arg == "-h") {
      print_usage();
      return 0;
    }
    if (arg == "--run-id") {
      run_id = next_value();
    } else if (arg == "--backend") {
      backend = next_value();
    } else if (arg == "--profile") {
      profile = next_value();
    } else if (arg == "--terrain") {
      terrain = next_value();
    } else if (arg == "--scene-id") {
      scene_id = next_value();
    } else if (arg == "--scene-version") {
      scene_version = next_value();
    } else if (arg == "--steps") {
      max_steps = parse_int(next_value(), max_steps);
    } else if (arg == "--task-path") {
      task_path_arg = next_value();
    } else if (starts_with(arg, "--")) {
      std::cerr << "Unknown argument: " << arg << '\n';
      print_usage();
      return 2;
    }
  }

  const auto parsed_backend = qrics::simulation::parse_local_backend_kind(backend);
  if (!parsed_backend.ok) {
    std::cerr << parsed_backend.errors.front().message << '\n';
    return 3;
  }

  qrics::runtime::LocalTaskRunRequest request{};
  request.run_id = run_id;
  request.backend = parsed_backend.value;
  request.runtime_profile = profile;
  request.max_steps = max_steps;
  request.scene = qrics::runtime::make_default_local_demo_scene(scene_id, scene_version, terrain);
  request.task_path = task_path_arg.empty() ? default_task_path() : parse_task_path(task_path_arg);

  const auto summary = qrics::runtime::run_local_task(request);
  if (!summary.ok) {
    std::cerr << "qrics_core_runtime failed";
    if (!summary.errors.empty()) {
      std::cerr << ": " << summary.errors.front().code << " - " << summary.errors.front().message;
    }
    std::cerr << '\n';
    return 4;
  }

  std::cout << qrics::runtime::to_json(summary.value) << '\n';
  return summary.value.state == "failed" ? 5 : 0;
}