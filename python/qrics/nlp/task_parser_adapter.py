"""Adapter between API scene payloads and the NLP parser catalog."""

from __future__ import annotations

from qrics.api.schemas import SceneProfilePayload
from qrics.nlp.rule_based_parser import RuleBasedChineseTaskParser
from qrics.nlp.schema import AvoidZoneAlias, ParsedTaskDraft, TaskParseCatalog, WaypointAlias

_DEFAULT_WAYPOINTS: tuple[WaypointAlias, ...] = (
    WaypointAlias(
        waypoint_id="A",
        name="巡检点 A",
        aliases=("巡检点A", "巡检 A", "巡检A", "A点", "点A", "A"),
        terrain_hint="flat",
    ),
    WaypointAlias(
        waypoint_id="B",
        name="巡检点 B",
        aliases=("巡检点B", "巡检 B", "巡检B", "B点", "点B", "B"),
        terrain_hint="gravel",
    ),
    WaypointAlias(
        waypoint_id="platform",
        name="平台",
        aliases=("平台", "起点", "基地", "回到平台", "返回平台", "回家", "待命区"),
        terrain_hint="flat",
        default_dwell_time_s=3.0,
    ),
)

_DEFAULT_AVOID_ZONES: tuple[AvoidZoneAlias, ...] = (
    AvoidZoneAlias(
        zone_id="low_friction_zone",
        aliases=("低摩擦区", "低摩擦区域", "湿滑区", "禁行提示区"),
    ),
)


def parse_task_source(source_text: str, scene: SceneProfilePayload | None) -> ParsedTaskDraft:
    """Parse natural-language task text using scene-specific waypoints and zones."""

    catalog = build_parse_catalog(scene)
    return RuleBasedChineseTaskParser().parse(source_text, catalog)


def build_parse_catalog(scene: SceneProfilePayload | None) -> TaskParseCatalog:
    if scene is None:
        return TaskParseCatalog(waypoints=_DEFAULT_WAYPOINTS, avoid_zones=_DEFAULT_AVOID_ZONES)

    waypoints_by_id = {waypoint.waypoint_id: waypoint for waypoint in _DEFAULT_WAYPOINTS}
    avoid_zones = list(_DEFAULT_AVOID_ZONES)

    for asset in scene.assets:
        if asset.asset_type == "checkpoint":
            waypoint_id = _checkpoint_waypoint_id(asset.asset_id)
            existing = waypoints_by_id.get(waypoint_id)
            aliases = _checkpoint_aliases(asset.asset_id, waypoint_id)
            if existing is None:
                waypoints_by_id[waypoint_id] = WaypointAlias(
                    waypoint_id=waypoint_id,
                    name=asset.asset_id,
                    aliases=aliases,
                    terrain_hint=_terrain_hint_for_checkpoint(waypoint_id, scene.terrain_pack),
                )
            else:
                waypoints_by_id[waypoint_id] = WaypointAlias(
                    waypoint_id=existing.waypoint_id,
                    name=existing.name,
                    aliases=_dedupe(existing.aliases + aliases),
                    terrain_hint=existing.terrain_hint,
                    default_dwell_time_s=existing.default_dwell_time_s,
                )
        elif asset.asset_type == "no_go_zone":
            avoid_zones.append(
                AvoidZoneAlias(
                    zone_id=asset.asset_id,
                    aliases=_no_go_zone_aliases(asset.asset_id),
                )
            )

    return TaskParseCatalog(
        waypoints=tuple(waypoints_by_id.values()),
        avoid_zones=tuple(_dedupe_zones(avoid_zones)),
    )


def _checkpoint_waypoint_id(asset_id: str) -> str:
    normalized = asset_id.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"a", "point_a", "checkpoint_a", "inspection_a", "巡检点a"}:
        return "A"
    if normalized in {"b", "point_b", "checkpoint_b", "inspection_b", "巡检点b"}:
        return "B"
    if normalized in {"platform", "base_platform", "start_platform", "home", "平台", "起点平台"}:
        return "platform"
    return asset_id


def _checkpoint_aliases(asset_id: str, waypoint_id: str) -> tuple[str, ...]:
    aliases: tuple[str, ...] = (asset_id,)
    if waypoint_id == "A":
        aliases += ("巡检点A", "巡检A", "A点", "A")
    elif waypoint_id == "B":
        aliases += ("巡检点B", "巡检B", "B点", "B")
    elif waypoint_id == "platform":
        aliases += ("平台", "起点", "基地", "回到平台", "返回平台")
    return _dedupe(aliases)


def _no_go_zone_aliases(asset_id: str) -> tuple[str, ...]:
    aliases = [asset_id, "禁行区", "禁行区域"]
    normalized = asset_id.lower().replace("_", "")
    if "low" in normalized or "friction" in normalized or "低摩擦" in asset_id:
        aliases.extend(["低摩擦区", "低摩擦区域", "湿滑区"])
    return _dedupe(tuple(aliases))


def _terrain_hint_for_checkpoint(waypoint_id: str, terrain_pack: str) -> str:
    if waypoint_id == "B" and terrain_pack in {"gravel", "mixed", "mixed_terrain_pack"}:
        return "gravel"
    if terrain_pack in {"slope", "stairs", "low_friction"}:
        return terrain_pack
    return "flat"


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return tuple(result)


def _dedupe_zones(values: list[AvoidZoneAlias]) -> list[AvoidZoneAlias]:
    by_id: dict[str, AvoidZoneAlias] = {}
    for value in values:
        existing = by_id.get(value.zone_id)
        if existing is None:
            by_id[value.zone_id] = value
        else:
            by_id[value.zone_id] = AvoidZoneAlias(
                zone_id=value.zone_id,
                aliases=_dedupe(existing.aliases + value.aliases),
            )
    return list(by_id.values())
