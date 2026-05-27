#include <fstream>
#include <string>

#include "qrics/config/scene_config_loader.hpp"
#include "qrics/task/constraint_engine.hpp"

namespace {

[[nodiscard]] qrics::task::TaskScript make_task_for_scene(
    const qrics::scenario::SceneProfile& scene) {
  qrics::task::TaskScript task{};
  task.task_id = "task_from_config";
  task.version = "0.1.0";
  task.scene_ref = qrics::common::ResourceRef{scene.scene_id, scene.version};
  task.goal = "巡检 A 并避开低摩擦区";

  qrics::task::Waypoint waypoint{};
  waypoint.waypoint_id = "checkpoint_a";
  waypoint.terrain_hint = "flat";
  task.waypoints.push_back(waypoint);
  task.constraints.avoid_zone_ids.emplace_back("zone_low_friction");
  return task;
}

}  // namespace

int main() {
  qrics::config::MinimalYamlSceneConfigLoader loader{};
  const auto loaded = loader.load("../../configs/scenes/minimal_scene.yaml");
  if (!loaded.ok) {
    return 1;
  }
  if (loaded.value.scene_id != "minimal_scene" || loaded.value.version != "0.1.0") {
    return 2;
  }
  if (loaded.value.checkpoints.size() != 3U) {
    return 3;
  }
  if (loaded.value.forbidden_zones.size() != 1U) {
    return 4;
  }
  if (!loaded.value.randomization_profile.enabled) {
    return 5;
  }

  qrics::task::BasicTaskConstraintEngine constraint_engine{};
  const auto constraint_result =
      constraint_engine.check(make_task_for_scene(loaded.value), loaded.value);
  if (!constraint_result.ok ||
      constraint_result.value.conclusion != qrics::task::ConstraintConclusion::Accepted) {
    return 6;
  }

  const auto missing = loader.load("../../configs/scenes/not_exists.yaml");
  if (missing.ok || missing.errors.empty()) {
    return 7;
  }

  const std::string invalid_path = "invalid_scene.yaml";
  {
    std::ofstream output{invalid_path};
    output << "scene:\n";
    output << "  id: invalid_scene\n";
    output << "  version: 0.1.0\n";
    output << "  terrain_pack: flat\n";
  }

  const auto invalid = loader.load(invalid_path);
  if (invalid.ok || invalid.errors.empty()) {
    return 8;
  }

  return 0;
}