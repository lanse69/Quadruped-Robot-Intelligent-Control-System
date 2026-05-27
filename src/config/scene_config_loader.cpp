// 场景配置加载器实现

#include "qrics/config/scene_config_loader.hpp"

#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

namespace qrics::config {

namespace {

[[nodiscard]] std::string get_value(const FlatYamlDocument& document, const std::string& key) {
  const auto found = document.values.find(key);
  if (found == document.values.end()) {
    return {};
  }
  return found->second;
}

[[nodiscard]] double get_double_or(const FlatYamlDocument& document, const std::string& key,
                                   double fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return std::stod(value);
}

[[nodiscard]] bool get_bool_or(const FlatYamlDocument& document, const std::string& key,
                               bool fallback) {
  const auto value = get_value(document, key);
  if (value.empty()) {
    return fallback;
  }
  return value == "true" || value == "yes" || value == "1";
}

[[nodiscard]] qrics::scenario::SceneStatus parse_status(const std::string& value) {
  if (value == "validated") {
    return qrics::scenario::SceneStatus::Validated;
  }
  if (value == "baseline") {
    return qrics::scenario::SceneStatus::Baseline;
  }
  if (value == "locked") {
    return qrics::scenario::SceneStatus::Locked;
  }
  if (value == "archived") {
    return qrics::scenario::SceneStatus::Archived;
  }
  return qrics::scenario::SceneStatus::Draft;
}

void add_checkpoints(const FlatYamlDocument& document, qrics::scenario::SceneProfile& scene) {
  for (int index = 0; index < 128; ++index) {
    const auto prefix = "checkpoints[" + std::to_string(index) + "].";
    const auto id = get_value(document, prefix + "id");
    if (id.empty()) {
      break;
    }

    qrics::scenario::Checkpoint checkpoint{};
    checkpoint.checkpoint_id = id;
    checkpoint.pose.position.x = get_double_or(document, prefix + "x", 0.0);
    checkpoint.pose.position.y = get_double_or(document, prefix + "y", 0.0);
    checkpoint.pose.position.z = get_double_or(document, prefix + "z", 0.0);
    checkpoint.pose.orientation.w = get_double_or(document, prefix + "qw", 1.0);
    checkpoint.pose.orientation.x = get_double_or(document, prefix + "qx", 0.0);
    checkpoint.pose.orientation.y = get_double_or(document, prefix + "qy", 0.0);
    checkpoint.pose.orientation.z = get_double_or(document, prefix + "qz", 0.0);
    checkpoint.dwell_time_s = get_double_or(document, prefix + "dwell_time_s", 0.0);
    scene.checkpoints.push_back(std::move(checkpoint));
  }
}

void add_forbidden_zones(const FlatYamlDocument& document, qrics::scenario::SceneProfile& scene) {
  for (int index = 0; index < 128; ++index) {
    const auto prefix = "forbidden_zones[" + std::to_string(index) + "].";
    const auto id = get_value(document, prefix + "id");
    if (id.empty()) {
      break;
    }

    qrics::scenario::ForbiddenZone zone{};
    zone.zone_id = id;
    zone.polygon.push_back(qrics::common::Vec3{get_double_or(document, prefix + "x", 0.0),
                                               get_double_or(document, prefix + "y", 0.0),
                                               get_double_or(document, prefix + "z", 0.0)});
    scene.forbidden_zones.push_back(std::move(zone));
  }
}

[[nodiscard]] std::vector<qrics::common::Error> validate_scene(
    const qrics::scenario::SceneProfile& scene) {
  std::vector<qrics::common::Error> errors{};
  if (scene.scene_id.empty()) {
    errors.push_back(make_config_error("SCENE_ID_EMPTY", "scene.id must not be empty"));
  }
  if (scene.version.empty()) {
    errors.push_back(make_config_error("SCENE_VERSION_EMPTY", "scene.version must not be empty"));
  }
  if (scene.terrain_pack.empty()) {
    errors.push_back(
        make_config_error("SCENE_TERRAIN_EMPTY", "scene.terrain_pack must not be empty"));
  }
  if (scene.checkpoints.empty()) {
    errors.push_back(
        make_config_error("SCENE_CHECKPOINTS_EMPTY", "checkpoints must contain at least one item"));
  }
  if (scene.sensor_profile.sample_rate_hz <= 0.0) {
    errors.push_back(
        make_config_error("SCENE_SENSOR_RATE_INVALID", "sensors.sample_rate_hz must be positive"));
  }
  if (scene.randomization_profile.friction_min > scene.randomization_profile.friction_max) {
    errors.push_back(make_config_error("SCENE_RANDOMIZATION_INVALID",
                                       "randomization.friction_min must be <= friction_max"));
  }
  return errors;
}

}  // namespace

qrics::common::Result<qrics::scenario::SceneProfile> MinimalYamlSceneConfigLoader::load(
    const std::string& path, const ConfigLoadOptions& /*options*/) const {
  auto loaded = load_flat_yaml_file(path);
  if (!loaded.ok) {
    return qrics::common::Result<qrics::scenario::SceneProfile>::failure(std::move(loaded.errors));
  }

  qrics::scenario::SceneProfile scene{};
  scene.scene_id = get_value(loaded.value, "scene.id");
  scene.version = get_value(loaded.value, "scene.version");
  scene.name = get_value(loaded.value, "scene.name");
  scene.terrain_pack = get_value(loaded.value, "scene.terrain_pack");
  scene.status = parse_status(get_value(loaded.value, "scene.status"));
  scene.sensor_profile.imu_enabled = get_bool_or(loaded.value, "sensors.imu_enabled", true);
  scene.sensor_profile.contact_sensor_enabled =
      get_bool_or(loaded.value, "sensors.contact_sensor_enabled", true);
  scene.sensor_profile.camera_enabled = get_bool_or(loaded.value, "sensors.camera_enabled", false);
  scene.sensor_profile.depth_camera_enabled =
      get_bool_or(loaded.value, "sensors.depth_camera_enabled", false);
  scene.sensor_profile.lidar_enabled = get_bool_or(loaded.value, "sensors.lidar_enabled", false);
  scene.sensor_profile.sample_rate_hz =
      get_double_or(loaded.value, "sensors.sample_rate_hz", 100.0);
  scene.randomization_profile.enabled = get_bool_or(loaded.value, "randomization.enabled", false);
  scene.randomization_profile.friction_min =
      get_double_or(loaded.value, "randomization.friction_min", 0.5);
  scene.randomization_profile.friction_max =
      get_double_or(loaded.value, "randomization.friction_max", 1.2);
  scene.randomization_profile.mass_scale_min =
      get_double_or(loaded.value, "randomization.mass_scale_min", 0.9);
  scene.randomization_profile.mass_scale_max =
      get_double_or(loaded.value, "randomization.mass_scale_max", 1.1);
  scene.randomization_profile.sensor_noise_std =
      get_double_or(loaded.value, "randomization.sensor_noise_std", 0.0);
  scene.checksum.algorithm = get_value(loaded.value, "checksum.algorithm");
  scene.checksum.value = get_value(loaded.value, "checksum.value");

  add_checkpoints(loaded.value, scene);
  add_forbidden_zones(loaded.value, scene);

  auto errors = validate_scene(scene);
  if (!errors.empty()) {
    return qrics::common::Result<qrics::scenario::SceneProfile>::failure(std::move(errors));
  }

  return qrics::common::Result<qrics::scenario::SceneProfile>::success(std::move(scene));
}

}  // namespace qrics::config