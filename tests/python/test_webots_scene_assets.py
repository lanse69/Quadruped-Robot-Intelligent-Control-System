from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "python/qrics/sim/assets/webots/worlds/qrics_demo.wbt"
CONTROLLER = (
    ROOT / "python/qrics/sim/assets/webots/controllers/qrics_controller/qrics_controller.py"
)


def test_webots_supervisor_is_synchronized_for_persistent_presentation() -> None:
    text = WORLD.read_text(encoding="utf-8")
    assert 'controller "qrics_controller"' in text
    assert "supervisor TRUE" in text
    assert "synchronization TRUE" in text


def test_webots_semantic_markers_are_visual_only_not_obstacles() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")
    semantic_section = text.split("def _spawn_semantic_markers", 1)[1].split(
        "def _spawn_obstacles", 1
    )[0]
    assert "Transform" in semantic_section
    assert "boundingObject" not in semantic_section
    assert "physics Physics" not in semantic_section
