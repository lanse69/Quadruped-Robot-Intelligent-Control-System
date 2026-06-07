"""Rule-based Chinese task parser used by the local demo API.

This parser is deterministic and dependency-free.  It accepts operator-level
intent such as patrol/checkpoint/avoid/dwell phrases, then emits a TaskScript
draft.  It explicitly rejects prompts that attempt to bypass the safety boundary
or request low-level action output.
"""

from __future__ import annotations

import re
from dataclasses import replace

from qrics.nlp.schema import (
    AvoidZoneAlias,
    DirectActionGuard,
    FallbackAction,
    ParsedTaskDraft,
    ParsedWaypoint,
    TaskParseCatalog,
    WaypointAlias,
)

PARSER_VERSION = "rule-based-zh-api-0.2.0"

_DIRECT_ACTION_GUARDS: tuple[DirectActionGuard, ...] = (
    DirectActionGuard("safeaction", "自然语言任务不得直接生成 SafeAction"),
    DirectActionGuard("actionproposal", "自然语言任务不得直接生成 ActionProposal"),
    DirectActionGuard("simulationadapter", "自然语言任务不得直接调用 SimulationAdapter"),
    DirectActionGuard("jointposition", "自然语言任务不得输出底层关节位置命令"),
    DirectActionGuard("jointvelocity", "自然语言任务不得输出底层关节速度命令"),
    DirectActionGuard("关节角", "自然语言任务不得输出底层关节角命令"),
    DirectActionGuard("关节速度", "自然语言任务不得输出底层关节速度命令"),
    DirectActionGuard("底层关节", "自然语言任务不得输出底层关节命令"),
    DirectActionGuard("绕过安全", "任务请求不得绕过 Safety Shield"),
    DirectActionGuard("跳过安全", "任务请求不得绕过 Safety Shield"),
    DirectActionGuard("直接下发动作", "动作下发必须经过任务图、控制器和 Safety Shield"),
    DirectActionGuard("直接控制电机", "自然语言任务不得直接控制电机"),
)

_AVOID_CUES = ("避开", "绕开", "不要进入", "禁止进入", "禁行", "远离", "不要靠近")
_REPLAN_CUES = ("重新规划", "重规划", "绕行")
_RETURN_HOME_CUES = ("回到平台", "返回平台", "回到起点", "返回起点", "回家", "回基地")
_STOP_CUES = ("停止", "停车", "原地停止")
_DWELL_CUES = ("驻留", "停留", "等待", "待命")

_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


class RuleBasedChineseTaskParser:
    """Scene-aware, deterministic Chinese parser for operator task text."""

    def parse(self, source_text: str, catalog: TaskParseCatalog) -> ParsedTaskDraft:
        normalized = source_text.strip()
        if not normalized:
            return ParsedTaskDraft(
                source_text=source_text,
                goal=source_text,
                parser_version=PARSER_VERSION,
                confidence=0.0,
                explanations=("任务文本为空",),
                safety_rejection_reason="source_text_empty",
            )

        guard_reason = _direct_action_rejection(normalized)
        if guard_reason:
            return ParsedTaskDraft(
                source_text=source_text,
                goal=normalized,
                parser_version=PARSER_VERSION,
                confidence=0.0,
                explanations=(
                    guard_reason,
                    "请改用目标点、巡检顺序、避障约束等任务级表达；系统只接受 TaskScript 草案。",
                ),
                safety_rejection_reason=guard_reason,
            )

        waypoint_matches = _extract_waypoints(normalized, catalog.waypoints)
        avoid_zone_ids, avoid_messages = _extract_avoid_zones(normalized, catalog.avoid_zones)
        fallback = _infer_fallback_action(normalized, catalog.default_fallback_action)
        explanations: list[str] = []
        if waypoint_matches:
            explanations.append(
                "已按文本出现顺序生成路径点："
                + " -> ".join(waypoint.waypoint_id for waypoint in waypoint_matches)
            )
        else:
            explanations.append("未匹配到已知路径点或检查点。")
        explanations.extend(avoid_messages)
        explanations.append(f"回退动作：{fallback}")
        explanations.append("解析结果仅为 TaskScript 草案，执行动作仍由 Safety Shield 门控。")

        confidence = _confidence(waypoint_matches, avoid_zone_ids, normalized)
        needs_confirmation = True
        if confidence >= 0.88 and not avoid_messages:
            needs_confirmation = True  # UI demo仍要求操作者确认，保持安全边界一致。

        return ParsedTaskDraft(
            source_text=source_text,
            goal=normalized,
            parser_version=PARSER_VERSION,
            waypoints=tuple(waypoint_matches),
            avoid_zone_ids=tuple(avoid_zone_ids),
            fallback_action=fallback,
            confidence=confidence,
            needs_confirmation=needs_confirmation,
            explanations=tuple(explanations),
            unmatched_phrases=tuple(message for message in avoid_messages if "未匹配" in message),
        )


def _direct_action_rejection(source_text: str) -> str:
    compact = source_text.replace(" ", "").replace("_", "").lower()
    for guard in _DIRECT_ACTION_GUARDS:
        if guard.token.replace(" ", "").replace("_", "").lower() in compact:
            return guard.reason
    return ""


def _extract_waypoints(
    source_text: str,
    waypoints: tuple[WaypointAlias, ...],
) -> list[ParsedWaypoint]:
    """Extract waypoint mentions in textual order while preserving repeats.

    Earlier demo code kept only the first occurrence of each waypoint.  That
    made a common defence sentence such as “从平台出发，巡检 A，最后回到平台”
    lose the final return-home segment.  This implementation records every
    non-overlapping alias occurrence and prefers longer aliases when phrases
    overlap, so “回到平台” wins over the shorter embedded “平台”, while a
    separate starting “平台” remains in the route.
    """

    candidates: list[tuple[int, int, int, WaypointAlias]] = []
    for waypoint in waypoints:
        for alias in waypoint.aliases:
            alias = alias.strip()
            if not alias:
                continue
            search_from = 0
            while True:
                position = source_text.find(alias, search_from)
                if position < 0:
                    break
                end = position + len(alias)
                candidates.append((position, end, len(alias), waypoint))
                search_from = max(position + 1, end)

    candidates.sort(key=lambda item: (item[0], -item[2], item[3].waypoint_id))
    matches: list[tuple[int, int, WaypointAlias]] = []
    occupied = [False] * len(source_text)
    for start, end, _length, waypoint in candidates:
        if any(occupied[index] for index in range(start, end)):
            continue
        for index in range(start, end):
            occupied[index] = True
        matches.append((start, end, waypoint))

    matches.sort(key=lambda item: item[0])
    result: list[ParsedWaypoint] = []
    for index, (position, _end, waypoint) in enumerate(matches):
        segment_end = matches[index + 1][0] if index + 1 < len(matches) else len(source_text)
        segment = source_text[position:segment_end]
        dwell_time_s = _extract_dwell_time_s(segment)
        if dwell_time_s <= 0.0:
            dwell_time_s = waypoint.default_dwell_time_s
        result.append(
            ParsedWaypoint(
                waypoint_id=waypoint.waypoint_id,
                name=waypoint.name,
                terrain_hint=waypoint.terrain_hint,
                dwell_time_s=dwell_time_s,
            )
        )
    return result


def _extract_avoid_zones(
    source_text: str,
    avoid_zones: tuple[AvoidZoneAlias, ...],
) -> tuple[list[str], list[str]]:
    if not _contains_any(source_text, _AVOID_CUES):
        return [], []
    zone_ids: list[str] = []
    messages: list[str] = []
    for zone in avoid_zones:
        if any(alias and alias in source_text for alias in zone.aliases):
            zone_ids.append(zone.zone_id)
    if zone_ids:
        messages.append("已识别禁行/避让区域：" + ", ".join(zone_ids))
    else:
        messages.append("任务包含避让语义，但未匹配到当前场景中的禁行区别名。")
    return zone_ids, messages


def _infer_fallback_action(source_text: str, default: FallbackAction) -> FallbackAction:
    if _contains_any(source_text, _REPLAN_CUES):
        return "replan"
    if _contains_any(source_text, _RETURN_HOME_CUES):
        return "return_home"
    if _contains_any(source_text, _STOP_CUES):
        return "stop"
    return default


def _extract_dwell_time_s(text_segment: str) -> float:
    digit_match = re.search(
        r"(?:驻留|停留|等待|待命)[^0-9一二两三四五六七八九十]{0,8}([0-9]+(?:\.[0-9]+)?)\s*秒",
        text_segment,
    )
    if digit_match:
        return float(digit_match.group(1))
    chinese_match = re.search(
        r"(?:驻留|停留|等待|待命)[^0-9一二两三四五六七八九十]{0,8}([一二两三四五六七八九十]{1,3})\s*秒",
        text_segment,
    )
    if chinese_match:
        return float(_parse_chinese_number(chinese_match.group(1)))
    if _contains_any(text_segment, ("待命",)):
        return 3.0
    return 0.0


def _parse_chinese_number(value: str) -> int:
    if value in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value]
    if "十" in value:
        before, _, after = value.partition("十")
        tens = 1 if before == "" else _CHINESE_DIGITS.get(before, 0)
        ones = 0 if after == "" else _CHINESE_DIGITS.get(after, 0)
        number = tens * 10 + ones
        return number if number > 0 else 10
    return 0


def _confidence(
    waypoints: list[ParsedWaypoint],
    avoid_zone_ids: list[str],
    source_text: str,
) -> float:
    if not waypoints:
        return 0.20
    score = 0.64 + min(len(waypoints), 3) * 0.08
    if _contains_any(source_text, _DWELL_CUES):
        score += 0.04
    if avoid_zone_ids:
        score += 0.04
    if _contains_any(source_text, _RETURN_HOME_CUES + _REPLAN_CUES + _STOP_CUES):
        score += 0.04
    return min(0.98, round(score, 2))


def _contains_any(source_text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in source_text for token in tokens)


def with_extra_waypoint_alias(
    catalog: TaskParseCatalog,
    waypoint_id: str,
    alias: str,
) -> TaskParseCatalog:
    """Return a copy of catalog with an additional alias for a waypoint."""

    updated: list[WaypointAlias] = []
    for waypoint in catalog.waypoints:
        if waypoint.waypoint_id == waypoint_id:
            updated.append(replace(waypoint, aliases=waypoint.aliases + (alias,)))
        else:
            updated.append(waypoint)
    return replace(catalog, waypoints=tuple(updated))
