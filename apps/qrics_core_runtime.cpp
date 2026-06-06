#include <cstdlib>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "qrics/runtime/local_task_run_engine.hpp"
#include "qrics/scenario/scene_profile.hpp"
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

[[nodiscard]] qrics::scenario::SceneGeometryType parse_geometry_type(const std::string& value) {
  if (value == "box") {
    return qrics::scenario::SceneGeometryType::Box;
  }
  if (value == "sphere") {
    return qrics::scenario::SceneGeometryType::Sphere;
  }
  return qrics::scenario::SceneGeometryType::Cylinder;
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

[[nodiscard]] qrics::scenario::SceneObstacle parse_scene_obstacle(const std::string& value) {
  // id:geometry:x:y:z:size_x:size_y:size_z:radius:height
  const auto parts = split(value, ':');
  qrics::scenario::SceneObstacle obstacle{};
  obstacle.obstacle_id = parts.empty() ? "custom_obstacle" : parts[0];
  obstacle.geometry_type = parts.size() > 1U ? parse_geometry_type(parts[1])
                                             : qrics::scenario::SceneGeometryType::Cylinder;
  obstacle.pose.position.x = parts.size() > 2U ? parse_double(parts[2], 0.0) : 0.0;
  obstacle.pose.position.y = parts.size() > 3U ? parse_double(parts[3], 0.0) : 0.0;
  obstacle.pose.position.z = parts.size() > 4U ? parse_double(parts[4], 0.20) : 0.20;
  obstacle.size_m.x = parts.size() > 5U ? parse_double(parts[5], 0.0) : 0.0;
  obstacle.size_m.y = parts.size() > 6U ? parse_double(parts[6], 0.0) : 0.0;
  obstacle.size_m.z = parts.size() > 7U ? parse_double(parts[7], 0.0) : 0.0;
  obstacle.radius_m = parts.size() > 8U ? parse_double(parts[8], 0.12) : 0.12;
  obstacle.height_m = parts.size() > 9U ? parse_double(parts[9], 0.35) : 0.35;
  return obstacle;
}

[[nodiscard]] qrics::scenario::Checkpoint parse_checkpoint(const std::string& value) {
  // id:x:y:z:dwell
  const auto parts = split(value, ':');
  qrics::scenario::Checkpoint checkpoint{};
  checkpoint.checkpoint_id = parts.empty() ? "checkpoint" : parts[0];
  checkpoint.pose.position.x = parts.size() > 1U ? parse_double(parts[1], 0.0) : 0.0;
  checkpoint.pose.position.y = parts.size() > 2U ? parse_double(parts[2], 0.0) : 0.0;
  checkpoint.pose.position.z = parts.size() > 3U ? parse_double(parts[3], 0.35) : 0.35;
  checkpoint.dwell_time_s = parts.size() > 4U ? parse_double(parts[4], 0.0) : 0.0;
  return checkpoint;
}

[[nodiscard]] qrics::scenario::ForbiddenZone parse_forbidden_zone(const std::string& value) {
  // id:x1:y1:z1;x2:y2:z2;x3:y3:z3
  const auto header = split(value, ':');
  qrics::scenario::ForbiddenZone zone{};
  if (header.empty()) {
    zone.zone_id = "forbidden_zone";
    return zone;
  }
  zone.zone_id = header[0];
  const auto id_prefix = zone.zone_id + ":";
  const std::string point_blob =
      starts_with(value, id_prefix) ? value.substr(id_prefix.size()) : "";
  for (const auto& item : split(point_blob, ';')) {
    const auto coords = split(item, ':');
    if (coords.size() < 2U) {
      continue;
    }
    zone.polygon.push_back(
        qrics::common::Vec3{parse_double(coords[0], 0.0), parse_double(coords[1], 0.0),
                            coords.size() > 2U ? parse_double(coords[2], 0.0) : 0.0});
  }
  return zone;
}

[[nodiscard]] std::vector<qrics::runtime::LocalTaskTarget> default_task_path() {
  return {qrics::runtime::LocalTaskTarget{"A", qrics::common::Vec3{0.85, 0.25, 0.35}, 0.3},
          qrics::runtime::LocalTaskTarget{"B", qrics::common::Vec3{1.65, -0.25, 0.35}, 0.3},
          qrics::runtime::LocalTaskTarget{"platform", qrics::common::Vec3{0.0, 0.0, 0.35}, 0.0}};
}

void print_usage() {
  std::cerr << "Usage: qrics_core_runtime [--run-id ID] [--backend minimal|mujoco|webots] "
               "[--profile headless_fast] [--terrain flat|mixed_terrain_pack] [--steps N] "
               "[--task-path id:x:y[:z[:dwell]],...] [--clear-default-assets] "
               "[--obstacle id:type:x:y:z:sx:sy:sz:radius:height] "
               "[--checkpoint id:x:y:z:dwell] [--forbidden-zone id:x:y:z;x:y:z;... ]\n";
}

struct CliOptions {
  std::string run_id{"cpp_cli_run"};
  std::string backend{"minimal"};
  std::string profile{"headless_fast"};
  std::string terrain{"mixed_terrain_pack"};
  std::string scene_id{"cpp_cli_scene"};
  std::string scene_version{"0.1.0"};
  std::string task_path_arg{};
  int max_steps{160};
  bool clear_default_assets{false};
  bool show_help{false};
  std::vector<qrics::scenario::SceneObstacle> custom_obstacles;
  std::vector<qrics::scenario::Checkpoint> custom_checkpoints;
  std::vector<qrics::scenario::ForbiddenZone> custom_forbidden_zones;
};

struct CliParseResult {
  CliOptions options{};
  std::string error{};
};

[[nodiscard]] std::string consume_next_value(int argc, char** argv, int& index) {
  if (index + 1 >= argc) {
    return {};
  }
  ++index;
  return argv[index];
}

[[nodiscard]] bool apply_cli_argument(const std::string& arg, int argc, char** argv, int& index,
                                      CliOptions& options, std::string& error) {
  if (arg == "--help" || arg == "-h") {
    options.show_help = true;
  } else if (arg == "--run-id") {
    options.run_id = consume_next_value(argc, argv, index);
  } else if (arg == "--backend") {
    options.backend = consume_next_value(argc, argv, index);
  } else if (arg == "--profile") {
    options.profile = consume_next_value(argc, argv, index);
  } else if (arg == "--terrain") {
    options.terrain = consume_next_value(argc, argv, index);
  } else if (arg == "--scene-id") {
    options.scene_id = consume_next_value(argc, argv, index);
  } else if (arg == "--scene-version") {
    options.scene_version = consume_next_value(argc, argv, index);
  } else if (arg == "--steps") {
    options.max_steps = parse_int(consume_next_value(argc, argv, index), options.max_steps);
  } else if (arg == "--task-path") {
    options.task_path_arg = consume_next_value(argc, argv, index);
  } else if (arg == "--clear-default-assets") {
    options.clear_default_assets = true;
  } else if (arg == "--obstacle") {
    options.custom_obstacles.push_back(parse_scene_obstacle(consume_next_value(argc, argv, index)));
  } else if (arg == "--checkpoint") {
    options.custom_checkpoints.push_back(parse_checkpoint(consume_next_value(argc, argv, index)));
  } else if (arg == "--forbidden-zone") {
    options.custom_forbidden_zones.push_back(
        parse_forbidden_zone(consume_next_value(argc, argv, index)));
  } else if (starts_with(arg, "--")) {
    error = "Unknown argument: " + arg;
    return false;
  }
  return true;
}

[[nodiscard]] CliParseResult parse_cli_options(int argc, char** argv) {
  CliParseResult result{};
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (!apply_cli_argument(arg, argc, argv, i, result.options, result.error)) {
      return result;
    }
  }
  return result;
}

void append_custom_scene_assets(qrics::scenario::SceneProfile& scene, const CliOptions& options) {
  if (options.clear_default_assets) {
    scene.obstacle_set.clear();
    scene.obstacles.clear();
    scene.checkpoints.clear();
    scene.forbidden_zones.clear();
  }
  for (const auto& obstacle : options.custom_obstacles) {
    scene.obstacles.push_back(obstacle);
    scene.obstacle_set.push_back(obstacle.obstacle_id);
  }
  for (const auto& checkpoint : options.custom_checkpoints) {
    scene.checkpoints.push_back(checkpoint);
  }
  for (const auto& zone : options.custom_forbidden_zones) {
    scene.forbidden_zones.push_back(zone);
  }
}

[[nodiscard]] qrics::scenario::SceneProfile make_scene_from_options(const CliOptions& options) {
  qrics::scenario::SceneProfile scene = qrics::runtime::make_default_local_demo_scene(
      options.scene_id, options.scene_version, options.terrain);
  append_custom_scene_assets(scene, options);
  return scene;
}

[[nodiscard]] std::vector<qrics::runtime::LocalTaskTarget> make_task_path_from_options(
    const CliOptions& options) {
  if (options.task_path_arg.empty()) {
    return default_task_path();
  }
  return parse_task_path(options.task_path_arg);
}

[[nodiscard]] qrics::runtime::LocalTaskRunRequest make_run_request(
    const CliOptions& options, qrics::simulation::LocalBackendKind backend) {
  qrics::runtime::LocalTaskRunRequest request{};
  request.run_id = options.run_id;
  request.backend = backend;
  request.runtime_profile = options.profile;
  request.max_steps = options.max_steps;
  request.scene = make_scene_from_options(options);
  request.task_path = make_task_path_from_options(options);
  return request;
}

[[nodiscard]] int print_run_summary(
    const qrics::common::Result<qrics::runtime::LocalTaskRunSummary>& summary) {
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

}  // namespace

int main(int argc, char** argv) {
  const auto cli = parse_cli_options(argc, argv);
  if (!cli.error.empty()) {
    std::cerr << cli.error << '\n';
    print_usage();
    return 2;
  }
  if (cli.options.show_help) {
    print_usage();
    return 0;
  }

  const auto parsed_backend = qrics::simulation::parse_local_backend_kind(cli.options.backend);
  if (!parsed_backend.ok) {
    std::cerr << parsed_backend.errors.front().message << '\n';
    return 3;
  }

  const auto request = make_run_request(cli.options, parsed_backend.value);
  return print_run_summary(qrics::runtime::run_local_task(request));
}