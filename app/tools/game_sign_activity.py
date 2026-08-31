#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""游戏社区活跃度响应解析和状态归一，不负责网络请求或签到。"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.utils.constants import UTC8

from .game_sign_contract import ActivityState, CommunityActivitySnapshot

__all__ = ["ACTIVITY_GAME_DEFINITIONS", "parse_activity_snapshot"]


class ActivityResponseLimitedError(ValueError):
    """上游响应被风控、拦截或返回了不可解析内容。"""


class ActivityResponseUnavailableError(ValueError):
    """上游响应可达但没有当前版本可识别的数据。"""


ActivityRole = Mapping[str, Any] | None
ActivityParser = Callable[
    [Mapping[str, Any], str, str, ActivityRole], CommunityActivitySnapshot
]

_RISK_CODES = frozenset({1034, 5003, 10035, 10041})


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0) if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return max(int(float(text)), 0)
        except ValueError:
            return None
    return None


def _as_code(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _first_int(item: Mapping[str, Any], names: tuple[str, ...]) -> int | None:
    for name in names:
        value = _as_int(item.get(name))
        if value is not None:
            return value
    return None


def _progress_pair(value: object) -> tuple[int, int] | None:
    if isinstance(value, str):
        current_text, separator, target_text = value.partition("/")
        if separator:
            current = _as_int(current_text)
            target = _as_int(target_text)
            if current is not None and target is not None:
                return current, target
        return None

    if not isinstance(value, Mapping):
        return None

    current = _first_int(
        value,
        (
            "current",
            "cur",
            "completed",
            "finished",
            "finish",
            "done",
            "progress",
            "dailyActivation",
            "daily_activation",
            "curStamina",
            "currentStamina",
            "finished_task_num",
            "current_train_score",
            "current_training_score",
            "current_rogue_score",
            "accepted_expedition_num",
            "curLevel",
            "currentValue",
            "current_value",
            "count",
            "num",
            "score",
        ),
    )
    target = _first_int(
        value,
        (
            "total",
            "target",
            "max",
            "maxProgress",
            "maxStamina",
            "max_stamina",
            "totalCount",
            "total_task_num",
            "max_train_score",
            "max_training_score",
            "max_rogue_score",
            "total_expedition_num",
            "maxDailyActivation",
            "max_daily_activation",
            "maxLevel",
            "limit",
            "maxValue",
            "max_value",
        ),
    )
    if current is not None and target is not None:
        return current, target

    for name in ("progress", "data", "detail", "stat", "value", "daily"):
        nested = value.get(name)
        if nested is not value:
            pair = _progress_pair(nested)
            if pair is not None:
                return pair
    return None


def _activity_item(name: str, value: object) -> dict[str, Any] | None:
    pair = _progress_pair(value)
    if pair is None:
        return None
    completed, target = pair
    return {
        "name": name,
        "completed": completed,
        "target": target,
        "status": "已完成" if target > 0 and completed >= target else "进行中",
    }


def _task_items(value: object, *, default_name: str) -> list[dict[str, Any]]:
    item = _activity_item(default_name, value)
    if item is not None:
        return [item]
    if not isinstance(value, Mapping):
        return []

    for key in ("items", "tasks", "list"):
        entries = value.get(key)
        if not isinstance(entries, list):
            continue
        items: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            name = str(
                entry.get("name")
                or entry.get("title")
                or entry.get("desc")
                or f"{default_name}{index + 1}"
            ).strip()
            item = _activity_item(name, entry)
            if item is not None:
                items.append(item)
        if items:
            return items
    return []


def _resource_item(name: str, value: object) -> dict[str, Any] | None:
    pair = _progress_pair(value)
    if pair is None:
        return None
    current, target = pair
    return {
        "name": name,
        "current": current,
        "target": target,
        "status": "已满" if target > 0 and current >= target else "可用",
    }


def _mark_period(
    items: list[dict[str, Any]], period: str
) -> list[dict[str, Any]]:
    return [dict(item, period=period) for item in items]


def _unwrap_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, Mapping) else payload


def _role_value(role: ActivityRole, names: tuple[str, ...]) -> str:
    if not isinstance(role, Mapping):
        return ""
    for name in names:
        value = role.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _build_snapshot(
    *,
    account_uid: str,
    account_name: str,
    platform: str,
    game: str,
    items: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    role: ActivityRole,
    source: str,
) -> CommunityActivitySnapshot:
    daily_items = [item for item in items if item.get("period", "daily") == "daily"]
    if not daily_items:
        raise ActivityResponseUnavailableError(
            f"{platform}{game}未返回可识别的每日任务进度"
        )

    completed = sum(_as_int(item.get("completed")) or 0 for item in daily_items)
    target = sum(_as_int(item.get("target")) or 0 for item in daily_items)
    return CommunityActivitySnapshot(
        account=account_name,
        account_uid=account_uid,
        game=game,
        platform=platform,
        status="success",
        completed=completed,
        target=target,
        tasks=tuple(items),
        resources=tuple(resources),
        updated_at=datetime.now(tz=UTC8).isoformat(),
        role_name=_role_value(role, ("name", "nickname", "nickName")),
        role_uid=_role_value(
            role,
            ("roleId", "role_id", "uid", "gameUid", "game_uid"),
        ),
        server=_role_value(
            role,
            ("serverName", "server", "serverId", "server_id", "channelName"),
        ),
        source=source,
    )


def _failed_snapshot(
    *,
    account_uid: str,
    account_name: str,
    platform: str,
    game: str,
    status: ActivityState,
    reason: str,
    role: ActivityRole,
    source: str = "",
) -> CommunityActivitySnapshot:
    return CommunityActivitySnapshot(
        account=account_name,
        account_uid=account_uid,
        game=game,
        platform=platform,
        status=status,
        reason=reason,
        updated_at=datetime.now(tz=UTC8).isoformat(),
        role_name=_role_value(role, ("name", "nickname", "nickName")),
        role_uid=_role_value(
            role,
            ("roleId", "role_id", "uid", "gameUid", "game_uid"),
        ),
        server=_role_value(
            role,
            ("serverName", "server", "serverId", "server_id", "channelName"),
        ),
        source=source,
    )


def _coerce_payload(
    payload: object, *, platform: str, game: str
) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        root = payload
    else:
        if isinstance(payload, (bytes, bytearray)):
            text = bytes(payload).decode("utf-8", errors="replace").strip()
        elif isinstance(payload, str):
            text = payload.strip()
        else:
            text = ""
        if not text:
            raise ActivityResponseLimitedError(
                f"{platform}{game}接口返回空响应，可能触发风控或维护"
            )
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ActivityResponseLimitedError(
                f"{platform}{game}接口返回非 JSON，可能触发风控"
            ) from exc
        if not isinstance(decoded, Mapping):
            raise ActivityResponseUnavailableError(
                f"{platform}{game}接口返回的数据结构无法识别"
            )
        root = decoded

    for key in ("retcode", "code"):
        code = _as_code(root.get(key))
        if code is None or code == 0:
            continue
        if abs(code) in _RISK_CODES:
            raise ActivityResponseLimitedError(
                f"{platform}{game}接口受到上游风控（业务码 {code}）"
            )
        raise ActivityResponseUnavailableError(
            f"{platform}{game}接口返回业务失败（业务码 {code}）"
        )
    return root


def _parse_skland_arknights(
    payload: Mapping[str, Any],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    routine = root.get("routine")
    routine = routine if isinstance(routine, Mapping) else {}
    daily_value = routine.get("daily") or root.get("daily")
    weekly_value = routine.get("weekly") or root.get("weekly")
    items = _task_items(daily_value, default_name="日常活跃度")
    items.extend(_mark_period(
        _task_items(weekly_value, default_name="每周活跃度"), "weekly"
    ))

    status = root.get("status")
    status = status if isinstance(status, Mapping) else {}
    ap_value = status.get("ap") or root.get("ap")
    if isinstance(ap_value, Mapping):
        current = _first_int(ap_value, ("current", "cur"))
        maximum = _first_int(ap_value, ("max", "total"))
        current_ts = _as_int(root.get("currentTs"))
        last_add_ts = _as_int(ap_value.get("lastApAddTime"))
        if (
            current is not None
            and maximum is not None
            and current_ts is not None
            and last_add_ts is not None
        ):
            # Widget 返回的是上次恢复时的基础值，按每 6 分钟恢复 1 点补齐当前值。
            current = min(maximum, current + max(0, (current_ts - last_add_ts) // 360))
            ap_value = {"current": current, "total": maximum}
    resource_values = (
        ("理智", ap_value),
        ("公开招募", status.get("recruit") or root.get("recruit")),
        ("无人机", status.get("drone") or root.get("drone")),
        ("经验", status.get("exp") or root.get("exp")),
        ("干员疲劳", status.get("fatigue") or root.get("fatigue")),
    )
    resources = []
    for name, value in resource_values:
        item = _resource_item(name, value)
        if item is not None:
            resources.append(item)
    return _build_snapshot(
        account_uid=account_uid,
        account_name=account_name,
        platform="森空岛",
        game="明日方舟",
        items=items,
        resources=resources,
        role=role,
        source="/api/v1/game/player/info",
    )


def _parse_skland_endfield(
    payload: Mapping[str, Any],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    data_root = _unwrap_data(payload)
    sources: list[Mapping[str, Any]] = [data_root]
    pending = [data_root]
    seen = {id(data_root)}
    while pending:
        current = pending.pop()
        for key in ("detail", "card", "data", "activity", "daily"):
            nested = current.get(key)
            if isinstance(nested, Mapping) and id(nested) not in seen:
                seen.add(id(nested))
                sources.append(nested)
                pending.append(nested)

    def first_value(*names: str) -> object:
        for source in sources:
            for name in names:
                if source.get(name) is not None:
                    return source[name]
        return None

    daily_value = first_value(
        "dailyMission",
        "daily_mission",
        "dailyTask",
        "dailyActivity",
    )
    weekly_value = first_value(
        "weeklyMission",
        "weekly_mission",
        "weeklyTask",
        "weeklyActivity",
    )
    items = _task_items(daily_value, default_name="日常活跃度")
    items.extend(
        _mark_period(
            _task_items(weekly_value, default_name="每周任务"), "weekly"
        )
    )
    for value, name in (
        (first_value("bpSystem", "bp_system", "battlePass"), "通行证"),
        (
            first_value("seekSuspicion", "seek_suspicion", "roguelike"),
            "蚀像寻遗",
        ),
    ):
        item = _activity_item(name, value)
        if item is not None:
            items.append(dict(item, period="weekly"))

    resource_values = (
        ("体力", first_value("stamina", "ap", "sanity", "dungeon")),
    )
    resources = []
    for name, value in resource_values:
        item = _resource_item(name, value)
        if item is not None:
            resources.append(item)
    return _build_snapshot(
        account_uid=account_uid,
        account_name=account_name,
        platform="森空岛",
        game="终末地",
        items=items,
        resources=resources,
        role=role,
        source="/api/v1/game/endfield/card/detail",
    )


def _parse_miyoushe_genshin(
    payload: Mapping[str, Any],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    daily_value = root.get("daily") or root.get("daily_task")
    daily = _activity_item("每日委托", daily_value)
    if daily is None:
        daily = _activity_item("每日委托", root)
    items = [daily] if daily is not None else []
    resources = []
    resource_values = (
        ("原粹树脂", {"current": root.get("current_resin"), "total": root.get("max_resin")}),
        ("洞天宝钱", {"current": root.get("current_home_coin"), "total": root.get("max_home_coin")}),
        ("探索派遣", {"current": root.get("current_expedition_num"), "total": root.get("total_expedition_num")}),
    )
    for name, value in resource_values:
        item = _resource_item(name, value)
        if item is not None:
            resources.append(item)
    return _build_snapshot(
        account_uid=account_uid,
        account_name=account_name,
        platform="米游社",
        game="原神",
        items=items,
        resources=resources,
        role=role,
        source="/game_record/app/genshin/api/dailyNote",
    )


def _parse_miyoushe_hsr(
    payload: Mapping[str, Any],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    daily_value = root.get("daily") or root.get("daily_task")
    daily = _activity_item("每日实训", daily_value)
    if daily is None:
        daily = _activity_item(
            "每日实训",
            {
                "current": root.get("current_training_score"),
                "total": root.get("max_training_score"),
            },
        )
    items = [daily] if daily is not None else []
    resources = []
    resource_values = (
        ("开拓力", {"current": root.get("current_stamina"), "total": root.get("max_stamina")}),
        ("储备开拓力", {"current": root.get("current_reserve_stamina"), "total": root.get("max_reserve_stamina")}),
        ("探索派遣", {"current": root.get("current_expedition_num"), "total": root.get("total_expedition_num")}),
    )
    for name, value in resource_values:
        item = _resource_item(name, value)
        if item is not None:
            resources.append(item)
    return _build_snapshot(
        account_uid=account_uid,
        account_name=account_name,
        platform="米游社",
        game="星穹铁道",
        items=items,
        resources=resources,
        role=role,
        source="/game_record/app/hkrpg/api/note",
    )


@dataclass(frozen=True)
class ActivityGameDefinition:
    platform: str
    game: str
    parser: ActivityParser | None
    source: str = ""
    limited_reason: str = ""


ACTIVITY_GAME_DEFINITIONS = (
    ActivityGameDefinition(
        platform="森空岛",
        game="明日方舟",
        parser=_parse_skland_arknights,
        source="/api/v1/game/player/info",
    ),
    ActivityGameDefinition(
        platform="森空岛",
        game="终末地",
        parser=_parse_skland_endfield,
        source="/api/v1/game/endfield/card/detail",
    ),
    ActivityGameDefinition(
        platform="米游社",
        game="原神",
        parser=_parse_miyoushe_genshin,
        source="/game_record/app/genshin/api/dailyNote",
    ),
    ActivityGameDefinition(
        platform="米游社",
        game="星穹铁道",
        parser=_parse_miyoushe_hsr,
        source="/game_record/app/hkrpg/api/note",
    ),
    ActivityGameDefinition(
        platform="米游社",
        game="绝区零",
        parser=None,
        source="",
        limited_reason=(
            "参考项目未确认绝区零稳定实时便笺接口，当前仅展示受限状态，不请求未经确认的字段"
        ),
    ),
)


def _definition_for(platform: str, game: str) -> ActivityGameDefinition | None:
    return next(
        (
            definition
            for definition in ACTIVITY_GAME_DEFINITIONS
            if definition.platform == platform and definition.game == game
        ),
        None,
    )


def parse_activity_snapshot(
    payload: object,
    *,
    account_uid: str,
    account_name: str,
    platform: str,
    game: str,
    role: ActivityRole = None,
) -> CommunityActivitySnapshot:
    """将单个游戏的脱敏响应转换为稳定的活跃度快照。

    Args:
        payload: 已由调用方读取的 JSON 对象、JSON 字符串或响应正文。
        account_uid: 游戏社区账号组 UUID。
        account_name: 游戏社区账号组名称。
        platform: 社区平台名称。
        game: 游戏名称。
        role: 当前查询角色的脱敏字段。

    Returns:
        单个游戏的活跃度快照；不支持或受限状态也以快照返回。
    """
    definition = _definition_for(platform, game)
    if definition is None:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="unavailable",
            reason=f"{platform}{game}尚未登记活跃度解析器",
            role=role,
        )
    if definition.parser is None:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="limited",
            reason=definition.limited_reason,
            role=role,
            source=definition.source,
        )

    try:
        root = _coerce_payload(payload, platform=platform, game=game)
        return definition.parser(root, account_uid, account_name, role)
    except ActivityResponseLimitedError as exc:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="limited",
            reason=str(exc),
            role=role,
            source=definition.source,
        )
    except ActivityResponseUnavailableError as exc:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="unavailable",
            reason=str(exc),
            role=role,
            source=definition.source,
        )
    except ValueError:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="failed",
            reason=f"{platform}{game}活跃度响应解析失败",
            role=role,
            source=definition.source,
        )
    except Exception:
        return _failed_snapshot(
            account_uid=account_uid,
            account_name=account_name,
            platform=platform,
            game=game,
            status="failed",
            reason=f"{platform}{game}活跃度处理失败",
            role=role,
            source=definition.source,
        )
