from qrics.api.app import create_demo_app
from qrics.api.routes_scenes import create_scene
from qrics.api.routes_tasks import submit_task
from qrics.api.schemas import (
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCreatePayload,
    TaskSubmissionPayload,
)
from qrics.nlp import RuleBasedChineseTaskParser, TaskParseCatalog, WaypointAlias
from qrics.nlp.schema import AvoidZoneAlias


def test_rule_based_parser_generates_task_script_draft() -> None:
    parser = RuleBasedChineseTaskParser()
    catalog = TaskParseCatalog(
        waypoints=(
            WaypointAlias("A", "巡检点 A", ("巡检A", "A"), "flat"),
            WaypointAlias("B", "巡检点 B", ("巡检B", "B"), "gravel"),
            WaypointAlias("platform", "平台", ("平台", "返回平台"), "flat", 3.0),
        ),
        avoid_zones=(AvoidZoneAlias("low_friction_zone", ("低摩擦区",)),),
    )

    parsed = parser.parse("避开低摩擦区，先巡检A，再巡检B并驻留五秒，最后返回平台", catalog)

    assert parsed.accepted
    assert parsed.parser_version == "rule-based-zh-api-0.2.0"
    assert [waypoint.waypoint_id for waypoint in parsed.waypoints] == ["A", "B", "platform"]
    assert parsed.waypoints[1].dwell_time_s == 5.0
    assert parsed.avoid_zone_ids == ("low_friction_zone",)
    assert parsed.fallback_action == "return_home"
    assert parsed.to_task_script_json()["constraints"] == {
        "avoid_zone_ids": ["low_friction_zone"],
        "ai_output_boundary": "task_script_only",
    }
    graph = parsed.to_task_graph_json()
    assert graph["entry_node_id"]
    assert graph["terminal_node_id"] == "stop_terminal"


def test_api_task_preview_exposes_parser_evidence_and_scene_zone() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-nlp", actor_id="tester", role="test_engineer")
    scene_ref = ResourceRef("nlp_scene", "0.1.0")
    created = create_scene(
        app,
        SceneCreatePayload(
            scene_id=scene_ref.id,
            version=scene_ref.version,
            terrain_pack="mixed_terrain_pack",
            assets=(
                SceneAssetPayload(
                    asset_id="low_friction_zone",
                    asset_type="no_go_zone",
                    geometry_type="box",
                    position=(0.2, 0.0, 0.01),
                    size=(0.6, 0.35, 0.02),
                ),
                SceneAssetPayload(asset_id="巡检点A", asset_type="checkpoint"),
                SceneAssetPayload(asset_id="巡检点B", asset_type="checkpoint"),
                SceneAssetPayload(asset_id="平台", asset_type="checkpoint"),
            ),
        ),
        context,
    )
    assert created.ok

    response = submit_task(
        app,
        TaskSubmissionPayload(
            source_text="避开低摩擦区，先巡检A，再巡检B并驻留3秒，最后回到平台待命",
            scene_ref=scene_ref,
        ),
        context,
    )

    assert response.ok
    assert response.data["state"] == "preview_ready"
    assert response.data["parser_version"] == "rule-based-zh-api-0.2.0"
    assert response.data["waypoints"] == ["A", "B", "platform"]
    assert response.data["constraints"] == ["low_friction_zone"]
    assert response.data["fallback_action"] == "return_home"
    assert isinstance(response.data["task_script"], dict)
    assert isinstance(response.data["task_graph"], dict)
    parse_confidence = response.data["parse_confidence"]
    assert isinstance(parse_confidence, (int, float))
    assert parse_confidence >= 0.8
