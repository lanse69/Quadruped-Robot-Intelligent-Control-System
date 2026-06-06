import json
from pathlib import Path

from qrics.demo.evidence import generate_evidence_bundle
from qrics.sim import SceneObstacle, SceneProfile, Vec3
from qrics.sim.observation_mapping import nearest_obstacle_state
from qrics.sim.scene_loader import load_scene_profile_from_json


def test_observation_mapping_uses_box_surface_clearance() -> None:
    scene = SceneProfile(
        scene_id="geom_scene",
        version="0.1.0",
        obstacle_set=(
            SceneObstacle(
                obstacle_id="box_obstacle",
                position=Vec3(x=0.30, y=0.0, z=0.35),
                geometry_type="box",
                size=Vec3(x=0.20, y=0.20, z=0.30),
                radius_m=0.10,
                height_m=0.30,
            ),
        ),
    )

    obstacle = nearest_obstacle_state(scene, Vec3(x=0.0, y=0.0, z=0.35))

    assert obstacle.obstacle_detected is True
    assert 0.19 <= obstacle.nearest_distance_m <= 0.21
    assert abs(obstacle.nearest_point.x - 0.20) <= 1.0e-9


def test_scene_loader_accepts_typed_box_and_sphere(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(
        json.dumps(
            {
                "scene_id": "typed_loader_scene",
                "version": "0.5.0",
                "terrain_pack": "mixed_terrain_pack",
                "obstacles": [
                    {
                        "id": "box",
                        "geometry_type": "box",
                        "position": [0.2, 0.0, 0.35],
                        "size": [0.2, 0.16, 0.3],
                    },
                    {
                        "id": "sphere",
                        "geometry_type": "sphere",
                        "position": [0.7, 0.1, 0.35],
                        "radius_m": 0.08,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    scene = load_scene_profile_from_json(scene_path)

    assert scene.scene_id == "typed_loader_scene"
    assert len(scene.obstacle_set) == 2
    assert scene.obstacle_set[0].geometry_type == "box"
    assert scene.obstacle_set[0].size.x == 0.2
    assert scene.obstacle_set[1].geometry_type == "sphere"


def test_generate_evidence_bundle_writes_json_and_markdown(tmp_path: Path) -> None:
    result = generate_evidence_bundle(output_dir=tmp_path, backend="minimal")

    evidence = json.loads(result.evidence_json.read_text(encoding="utf-8"))
    markdown = result.evidence_markdown.read_text(encoding="utf-8")

    assert evidence["schema"] == "qrics.demo_evidence.v1"
    assert evidence["handoff"]["control_step_count"] > 0
    assert evidence["handoff"]["obstacle_detected"] is True
    assert evidence["replay"]["keyframe_count"] > 0
    assert "QRICS 本机演示证据包" in markdown
