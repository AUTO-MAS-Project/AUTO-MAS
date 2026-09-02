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

from app.utils.constants import UTC8

from .community_contract import ActivityState, CommunityActivitySnapshot

__all__ = ["ACTIVITY_GAME_DEFINITIONS", "parse_activity_snapshot"]


class ActivityResponseLimitedError(ValueError):
    """上游响应被风控、拦截或返回了不可解析内容。"""


class ActivityResponseUnavailableError(ValueError):
    """上游响应可达但没有当前版本可识别的数据。"""


ActivityRole = Mapping[str, object] | None
ActivityParser = Callable[
    [Mapping[str, object], str, str, ActivityRole], CommunityActivitySnapshot
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


def _first_int(item: Mapping[str, object], names: tuple[str, ...]) -> int | None:
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
            "currentValue",
            "current_value",
        ),
    )
    target = _first_int(
        value,
        (
            "total",
            "target",
            "max",
            "maxProgress",
            "totalCount",
            "maxValue",
            "max_value",
        ),
    )
    if current is not None and target is not None:
        return current, target

    for name in ("progress", "value"):
        nested = value.get(name)
        if nested is not value:
            pair = _progress_pair(nested)
            if pair is not None:
                return pair
    return None


def _named_progress(
    value: object,
    *,
    current_names: tuple[str, ...],
    target_names: tuple[str, ...],
) -> tuple[int, int] | None:
    """只从调用方确认的同一字段对象读取进度，不递归扫描通用数字。"""

    if not isinstance(value, Mapping):
        return None
    current = _first_int(value, current_names)
    target = _first_int(value, target_names)
    if current is None or target is None:
        return None
    return current, target


def _activity_item(
    name: str,
    value: object,
    *,
    pair: tuple[int, int] | None = None,
) -> dict[str, object] | None:
    pair = pair or _progress_pair(value)
    if pair is None:
        return None
    completed, target = pair
    return {
        "name": name,
        "completed": completed,
        "target": target,
        "status": "已完成" if target > 0 and completed >= target else "进行中",
    }


def _task_items(value: object, *, default_name: str) -> list[dict[str, object]]:
    item = _activity_item(default_name, value)
    if item is not None:
        return [item]
    if not isinstance(value, Mapping):
        return []

    for key in ("items", "tasks", "list"):
        entries = value.get(key)
        if not isinstance(entries, list):
            continue
        items: list[dict[str, object]] = []
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


def _resource_item(
    name: str,
    value: object,
    *,
    pair: tuple[int, int] | None = None,
    status: str | None = None,
) -> dict[str, object] | None:
    pair = pair or _progress_pair(value)
    if pair is None:
        return None
    current, target = pair
    return {
        "name": name,
        "current": current,
        "target": target,
        "status": status or (
            "已满" if target > 0 and current >= target else "可用"
        ),
    }


def _recovery_status(
    seconds: object,
    *,
    current: int,
    target: int,
) -> str:
    """将上游剩余秒数转换为便笺可直接展示的恢复状态。"""

    if target > 0 and current >= target:
        return "已满"
    duration = _duration_text(seconds)
    if duration is None:
        return "恢复中"
    if _as_int(seconds) == 0:
        return "即将回满"

    return f"预计{duration}后回满"


def _duration_text(seconds: object) -> str | None:
    total_seconds = _as_int(seconds)
    if total_seconds is None:
        return None

    total_minutes = max(1, math.ceil(total_seconds / 60))
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}天")
    if hours:
        parts.append(f"{hours}小时")
    if minutes or not parts:
        parts.append(f"{minutes}分钟")
    return "".join(parts)


def _remaining_seconds(timestamp: object, current_timestamp: object) -> int | None:
    finish = _as_int(timestamp)
    current = _as_int(current_timestamp)
    if finish is None or current is None:
        return None
    return max(0, finish - current)


def _future_status(
    seconds: object,
    *,
    action: str,
    fallback: str,
) -> str:
    duration = _duration_text(seconds)
    if duration is None:
        return fallback
    if _as_int(seconds) == 0:
        return f"即将{action}"
    return f"预计{duration}后{action}"


def _status_item(name: str, status: str, *, period: str = "daily") -> dict[str, object]:
    return {
        "name": name,
        "completed": 0,
        "target": 0,
        "status": status,
        "period": period,
    }


def _status_resource(name: str, status: str) -> dict[str, object]:
    return {
        "name": name,
        "current": 0,
        "target": 0,
        "status": status,
    }


def _number_text(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return str(max(value, 0))
    if isinstance(value, float):
        return f"{max(value, 0):g}" if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return f"{max(number, 0):g}" if math.isfinite(number) else None
    return None


def _mark_period(
    items: list[dict[str, object]], period: str
) -> list[dict[str, object]]:
    return [dict(item, period=period) for item in items]


def _unwrap_data(payload: Mapping[str, object]) -> Mapping[str, object]:
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
    items: list[dict[str, object]],
    resources: list[dict[str, object]],
    role: ActivityRole,
    source: str,
    progress: tuple[int, int] | None = None,
) -> CommunityActivitySnapshot:
    daily_items = [item for item in items if item.get("period", "daily") == "daily"]
    if not daily_items:
        raise ActivityResponseUnavailableError(
            f"{platform}{game}未返回可识别的每日任务进度"
        )

    if progress is None:
        completed = sum(
            _as_int(item.get("completed")) or 0 for item in daily_items
        )
        target = sum(_as_int(item.get("target")) or 0 for item in daily_items)
    else:
        completed, target = progress
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
) -> Mapping[str, object]:
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
    payload: Mapping[str, object],
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
    items.extend(
        _mark_period(
            _task_items(weekly_value, default_name="每周活跃度"), "weekly"
        )
    )

    campaign = root.get("campaign")
    campaign_reward = (
        campaign.get("reward") if isinstance(campaign, Mapping) else None
    )
    campaign_item = _activity_item("每周报酬合成玉", campaign_reward)
    if campaign_item is not None:
        items.append(dict(campaign_item, period="weekly"))

    tower = root.get("tower")
    tower_reward = tower.get("reward") if isinstance(tower, Mapping) else None
    if isinstance(tower_reward, Mapping):
        for name, field in (
            ("数据增补条", "lowerItem"),
            ("数据增补仪", "higherItem"),
        ):
            tower_item = _activity_item(name, tower_reward.get(field))
            if tower_item is not None:
                items.append(dict(tower_item, period="weekly"))

    status = root.get("status")
    status = status if isinstance(status, Mapping) else {}
    ap_value = status.get("ap") or root.get("ap")
    ap_status: str | None = None
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
            elapsed = max(0, current_ts - last_add_ts)
            current = min(maximum, current + elapsed // 360)
            complete_recovery_ts = _as_int(
                ap_value.get("completeRecoveryTime")
            )
            recovery_seconds = (
                max(0, complete_recovery_ts - current_ts)
                if complete_recovery_ts is not None
                else max(0, (maximum - current) * 360 - (elapsed % 360))
            )
            ap_status = _recovery_status(
                recovery_seconds,
                current=current,
                target=maximum,
            )
            ap_value = {"current": current, "total": maximum}

    resources: list[dict[str, object]] = []
    ap_item = _resource_item("理智", ap_value, status=ap_status)
    if ap_item is not None:
        resources.append(ap_item)

    current_ts = _as_int(root.get("currentTs"))
    recruit_value = root.get("recruit")
    recruit_entries = (
        [entry for entry in recruit_value if isinstance(entry, Mapping)]
        if isinstance(recruit_value, list)
        else []
    )
    if recruit_entries:
        completed_recruits = sum(
            (_as_code(entry.get("state")) or 0) != 2
            for entry in recruit_entries
        )
        finish_timestamps = [
            timestamp
            for entry in recruit_entries
            if (timestamp := _as_code(entry.get("finishTs"))) is not None
            and timestamp >= 0
        ]
        recruit_status = (
            "招募已全部完成"
            if completed_recruits >= len(recruit_entries)
            else _future_status(
                _remaining_seconds(
                    max(finish_timestamps) if finish_timestamps else None,
                    current_ts,
                ),
                action="全部完成",
                fallback="招募进行中",
            )
        )
        recruit_item = _resource_item(
            "公开招募",
            {},
            pair=(completed_recruits, len(recruit_entries)),
            status=recruit_status,
        )
        if recruit_item is not None:
            resources.append(recruit_item)

    building = root.get("building")
    building = building if isinstance(building, Mapping) else {}

    hire = building.get("hire")
    if isinstance(hire, Mapping):
        refresh_count = _as_int(hire.get("refreshCount"))
        if refresh_count is not None:
            hire_status = (
                f"可刷新{refresh_count}次"
                if refresh_count > 0
                else _future_status(
                    _remaining_seconds(
                        hire.get("completeWorkTime"),
                        current_ts,
                    ),
                    action="获得刷新次数",
                    fallback="联络中",
                )
            )
            resources.append(_status_resource("公招刷新", hire_status))

    training = building.get("training")
    if isinstance(training, Mapping):
        trainee = training.get("trainee")
        if isinstance(trainee, Mapping):
            char_info_map = root.get("charInfoMap")
            char_info = (
                char_info_map.get(str(trainee.get("charId")))
                if isinstance(char_info_map, Mapping)
                else None
            )
            trainee_name = (
                str(char_info.get("name") or "").strip()
                if isinstance(char_info, Mapping)
                else ""
            )
            training_state = _future_status(
                training.get("remainSecs"),
                action="完成训练",
                fallback="训练中",
            )
            resources.append(
                _status_resource(
                    "训练室",
                    f"{trainee_name}，{training_state}"
                    if trainee_name
                    else training_state,
                )
            )
        else:
            resources.append(_status_resource("训练室", "空闲中"))

    labor = building.get("labor")
    labor_pair = _named_progress(
        labor,
        current_names=("value",),
        target_names=("maxValue",),
    )
    if labor_pair is not None:
        current, target = labor_pair
        labor_item = _resource_item(
            "无人机",
            labor,
            pair=labor_pair,
            status=_recovery_status(
                labor.get("remainSecs") if isinstance(labor, Mapping) else None,
                current=current,
                target=target,
            ),
        )
        if labor_item is not None:
            resources.append(labor_item)

    manufactures = building.get("manufactures")
    formula_map = root.get("manufactureFormulaInfoMap")
    manufacture_current = 0
    manufacture_target = 0
    if isinstance(manufactures, list) and isinstance(formula_map, Mapping):
        for manufacture in manufactures:
            if not isinstance(manufacture, Mapping):
                continue
            manufacture_current += _as_int(manufacture.get("complete")) or 0
            formula_id = str(manufacture.get("formulaId") or "")
            formula = formula_map.get(formula_id)
            capacity = _as_int(manufacture.get("capacity"))
            weight = (
                _as_int(formula.get("weight"))
                if isinstance(formula, Mapping)
                else None
            )
            if capacity is not None and weight:
                manufacture_target += capacity // weight
    if manufacture_target > 0:
        manufacture_item = _resource_item(
            "制造进度",
            {},
            pair=(manufacture_current, manufacture_target),
        )
        if manufacture_item is not None:
            resources.append(manufacture_item)

    tradings = building.get("tradings")
    trading_current = 0
    trading_target = 0
    if isinstance(tradings, list):
        for trading in tradings:
            if not isinstance(trading, Mapping):
                continue
            stock = trading.get("stock")
            stock_count = len(stock) if isinstance(stock, list) else _as_int(stock)
            stock_limit = _as_int(trading.get("stockLimit"))
            if stock_count is not None and stock_limit is not None:
                trading_current += stock_count
                trading_target += stock_limit
    if trading_target > 0:
        trading_item = _resource_item(
            "订单进度",
            {},
            pair=(trading_current, trading_target),
        )
        if trading_item is not None:
            resources.append(trading_item)

    tired_chars = building.get("tiredChars")
    if isinstance(tired_chars, list):
        resources.append(
            _status_resource("干员疲劳", f"{len(tired_chars)}名干员疲劳")
        )

    experience = _resource_item("经验", status.get("exp") or root.get("exp"))
    if experience is not None:
        resources.append(experience)
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
    payload: Mapping[str, object],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    detail = root.get("detail")
    if not isinstance(detail, Mapping):
        raise ActivityResponseUnavailableError(
            "森空岛终末地未返回可识别的角色详情"
        )

    daily_value = detail.get("dailyMission")
    daily_pair = _named_progress(
        daily_value,
        current_names=("dailyActivation",),
        target_names=("maxDailyActivation",),
    )
    items = []
    if daily_pair is not None:
        daily = _activity_item("日常活跃度", daily_value, pair=daily_pair)
        if daily is not None:
            items.append(daily)

    weekly_value = detail.get("weeklyMission")
    weekly_pair = _named_progress(
        weekly_value,
        current_names=("score",),
        target_names=("total",),
    )
    if weekly_pair is not None:
        weekly_item = _activity_item(
            "每周事务",
            weekly_value,
            pair=weekly_pair,
        )
        if weekly_item is not None:
            items.append(dict(weekly_item, period="weekly"))

    bp_system = detail.get("bpSystem")
    bp_pair = _named_progress(
        bp_system,
        current_names=("curLevel",),
        target_names=("maxLevel",),
    )
    if bp_pair is not None:
        item = _activity_item("通行证等级", bp_system, pair=bp_pair)
        if item is not None:
            items.append(dict(item, period="weekly"))

    seek_suspicion = detail.get("seekSuspicion")
    seek_pair = _named_progress(
        seek_suspicion,
        current_names=("count",),
        target_names=("total",),
    )
    if seek_pair is not None:
        seek_item = _activity_item(
            "蚀像寻遗",
            seek_suspicion,
            pair=seek_pair,
        )
        if seek_item is not None:
            items.append(dict(seek_item, period="weekly"))

    resources = []
    dungeon = detail.get("dungeon")
    dungeon_pair = _named_progress(
        dungeon,
        current_names=("curStamina",),
        target_names=("maxStamina",),
    )
    if dungeon_pair is not None:
        current, target = dungeon_pair
        current_ts = detail.get("currentTs") or root.get("currentTs")
        recovery_seconds = (
            _remaining_seconds(dungeon.get("maxTs"), current_ts)
            if isinstance(dungeon, Mapping)
            else None
        )
        item = _resource_item(
            "理智",
            dungeon,
            pair=dungeon_pair,
            status=_recovery_status(
                recovery_seconds
                if recovery_seconds is not None
                else max(0, target - current) * 432,
                current=current,
                target=target,
            ),
        )
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
        source="/web/v1/game/endfield/card/detail",
    )


def _parse_miyoushe_genshin(
    payload: Mapping[str, object],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    daily_value = root.get("daily") or root.get("daily_task")
    daily = _activity_item("每日委托", daily_value)
    if daily is None:
        daily = _activity_item(
            "每日委托",
            daily_value,
            pair=_named_progress(
                daily_value,
                current_names=("finished_num", "finished_task_num"),
                target_names=("total_num", "total_task_num"),
            ),
        )
    if daily is None:
        daily = _activity_item(
            "每日委托",
            root,
            pair=_named_progress(
                root,
                current_names=("finished_task_num",),
                target_names=("total_task_num",),
            ),
        )
    items = [daily] if daily is not None else []
    nested_reward_received = (
        daily_value.get("is_extra_task_reward_received")
        if isinstance(daily_value, Mapping)
        else None
    )
    reward_received = (
        nested_reward_received
        if isinstance(nested_reward_received, bool)
        else root.get("is_extra_task_reward_received")
    )
    if daily is not None and isinstance(reward_received, bool):
        if daily["completed"] == daily["target"]:
            items[0] = dict(
                daily,
                status="奖励已领取" if reward_received else "奖励待领取",
            )

    remaining_discounts = _as_int(root.get("remain_resin_discount_num"))
    discount_limit = _as_int(root.get("resin_discount_num_limit"))
    if remaining_discounts is not None and discount_limit is not None:
        items.append(
            {
                "name": "周本减半次数",
                "completed": max(0, discount_limit - remaining_discounts),
                "target": discount_limit,
                "status": f"剩余{remaining_discounts}次",
                "period": "weekly",
            }
        )

    transformer = root.get("transformer")
    if isinstance(transformer, Mapping):
        if transformer.get("obtained") is False:
            transformer_status = "未获得"
        else:
            recovery_time = transformer.get("recovery_time")
            recovery_time = (
                recovery_time if isinstance(recovery_time, Mapping) else {}
            )
            if recovery_time.get("reached") is True:
                transformer_status = "可使用"
            else:
                transformer_seconds = sum(
                    (_as_int(recovery_time.get(field)) or 0) * multiplier
                    for field, multiplier in (
                        ("Day", 24 * 60 * 60),
                        ("Hour", 60 * 60),
                        ("Minute", 60),
                        ("Second", 1),
                    )
                )
                transformer_status = _future_status(
                    transformer_seconds,
                    action="可使用",
                    fallback="冷却中",
                )
        items.append(
            _status_item(
                "参量质变仪",
                transformer_status,
                period="weekly",
            )
        )

    resources = []
    recoverable_resources = (
        (
            "原粹树脂",
            root.get("current_resin"),
            root.get("max_resin"),
            root.get("resin_recovery_time"),
        ),
        (
            "洞天宝钱",
            root.get("current_home_coin"),
            root.get("max_home_coin"),
            root.get("home_coin_recovery_time"),
        ),
    )
    for name, current_value, target_value, recovery_time in recoverable_resources:
        pair = _progress_pair(
            {"current": current_value, "total": target_value}
        )
        if pair is None:
            continue
        current, target = pair
        item = _resource_item(
            name,
            {},
            pair=pair,
            status=_recovery_status(
                recovery_time,
                current=current,
                target=target,
            ),
        )
        if item is not None:
            resources.append(item)

    daily_detail = root.get("daily_task")
    stored_attendance = (
        _number_text(daily_detail.get("stored_attendance"))
        if isinstance(daily_detail, Mapping)
        and daily_detail.get("attendance_visible") is not False
        else None
    )
    if stored_attendance is not None:
        resources.append(
            _status_resource("长效历练点", f"现有{stored_attendance}点")
        )

    expeditions = root.get("expeditions")
    expedition_entries = (
        [entry for entry in expeditions if isinstance(entry, Mapping)]
        if isinstance(expeditions, list)
        else []
    )
    expedition_current = _as_int(root.get("current_expedition_num"))
    if expedition_current is None and isinstance(expeditions, list):
        expedition_current = len(expedition_entries)
    expedition_target = _first_int(
        root,
        ("max_expedition_num", "total_expedition_num"),
    )
    finished_expeditions = sum(
        str(entry.get("status") or "") == "Finished"
        for entry in expedition_entries
    )
    expedition = _resource_item(
        "探索派遣",
        {
            "current": expedition_current,
            "total": expedition_target,
        },
        status=(
            "奖励待领取"
            if expedition_entries
            and finished_expeditions == len(expedition_entries)
            else "进行中"
        ),
    )
    if expedition is not None:
        resources.append(expedition)
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
    payload: Mapping[str, object],
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
                "current": (
                    root.get("current_train_score")
                    if root.get("current_train_score") is not None
                    else root.get("current_training_score")
                ),
                "total": (
                    root.get("max_train_score")
                    if root.get("max_train_score") is not None
                    else root.get("max_training_score")
                ),
            },
        )
    items = [daily] if daily is not None else []
    rogue_pair = _named_progress(
        root,
        current_names=("current_rogue_score",),
        target_names=("max_rogue_score",),
    )
    if rogue_pair is not None:
        rogue = _activity_item("模拟宇宙积分", root, pair=rogue_pair)
        if rogue is not None:
            items.append(dict(rogue, period="weekly"))

    if root.get("rogue_tourn_weekly_unlocked") is True:
        synchronicity_pair = _named_progress(
            root,
            current_names=("rogue_tourn_weekly_cur",),
            target_names=("rogue_tourn_weekly_max",),
        )
        # Widget 偶尔返回当前值大于目标值的反向语义，无法确认时不展示错误进度。
        if (
            synchronicity_pair is not None
            and synchronicity_pair[0] <= synchronicity_pair[1]
        ):
            synchronicity = _activity_item(
                "差分宇宙同步积分",
                root,
                pair=synchronicity_pair,
            )
            if synchronicity is not None:
                items.append(dict(synchronicity, period="weekly"))

    remaining_discounts = _as_int(root.get("weekly_cocoon_cnt"))
    discount_limit = _as_int(root.get("weekly_cocoon_limit"))
    if remaining_discounts is not None and discount_limit is not None:
        items.append(
            {
                "name": "历战余响次数",
                "completed": max(0, discount_limit - remaining_discounts),
                "target": discount_limit,
                "status": f"剩余{remaining_discounts}次",
                "period": "weekly",
            }
        )

    resources = []
    stamina_pair = _progress_pair(
        {
            "current": root.get("current_stamina"),
            "total": root.get("max_stamina"),
        }
    )
    if stamina_pair is not None:
        current, target = stamina_pair
        stamina = _resource_item(
            "开拓力",
            {},
            pair=stamina_pair,
            status=_recovery_status(
                root.get("stamina_recover_time"),
                current=current,
                target=target,
            ),
        )
        if stamina is not None:
            resources.append(stamina)

    reserve_stamina = _as_int(root.get("current_reserve_stamina"))
    reserve_target = _as_int(root.get("max_reserve_stamina"))
    if reserve_stamina is not None:
        reserve_item = _resource_item(
            "储备开拓力",
            {},
            pair=(reserve_stamina, reserve_target or 2400),
        )
        if reserve_item is not None:
            resources.append(reserve_item)

    expeditions = root.get("expeditions")
    expedition_entries = (
        [entry for entry in expeditions if isinstance(entry, Mapping)]
        if isinstance(expeditions, list)
        else []
    )
    expedition_current = _first_int(
        root,
        (
            "accepted_epedition_num",
            "accepted_expedition_num",
            "current_expedition_num",
        ),
    )
    if expedition_current is None and isinstance(expeditions, list):
        expedition_current = len(expedition_entries)
    expedition_target = _as_int(root.get("total_expedition_num"))
    if expedition_current is not None and expedition_target is not None:
        expedition = _resource_item(
            "探索派遣",
            {},
            pair=(expedition_current, expedition_target),
            status=(
                "奖励待领取"
                if expedition_entries
                and all(
                    str(entry.get("status") or "") == "Finished"
                    for entry in expedition_entries
                )
                else "进行中"
            ),
        )
        if expedition is not None:
            resources.append(expedition)
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


def _state_task(
    name: str,
    value: object,
    *,
    complete: str,
    complete_status: str = "已完成",
    incomplete_status: str = "未完成",
) -> dict[str, object]:
    state = str(value or "")
    completed = int(complete in state)
    return _status_item(
        name,
        complete_status if completed else incomplete_status,
    )


def _parse_miyoushe_zzz(
    payload: Mapping[str, object],
    account_uid: str,
    account_name: str,
    role: ActivityRole,
) -> CommunityActivitySnapshot:
    root = _unwrap_data(payload)
    vitality = _progress_pair(root.get("vitality"))
    if vitality is None:
        raise ActivityResponseUnavailableError(
            "米游社绝区零未返回可识别的今日活跃度"
        )
    video_sale = root.get("vhs_sale")
    video_state = (
        str(video_sale.get("sale_state") or "")
        if isinstance(video_sale, Mapping)
        else ""
    )
    video_status = {
        "SaleStateDone": "待结算",
        "SaleStateDoing": "营业中",
        "SaleStateNo": "尚未营业",
    }.get(video_state, "状态未知")
    items = [
        _activity_item("今日活跃度", root.get("vitality")),
        _status_item("录像店经营", video_status),
        _state_task("刮刮卡", root.get("card_sign"), complete="Done"),
    ]

    hollow_zero = root.get("hollow_zero")
    hollow_zero = hollow_zero if isinstance(hollow_zero, Mapping) else {}
    bounty = root.get("bounty_commission") or hollow_zero.get(
        "bounty_commission"
    )
    bounty_pair = _named_progress(
        bounty,
        current_names=("num",),
        target_names=("total",),
    )
    if isinstance(bounty, Mapping) and bounty.get("unlock") is False:
        items.append(_status_item("悬赏委托", "未解锁", period="weekly"))
    elif bounty_pair is not None:
        bounty_item = _activity_item("悬赏委托", bounty, pair=bounty_pair)
        if bounty_item is not None:
            items.append(dict(bounty_item, period="weekly"))

    survey_points = root.get("survey_points") or hollow_zero.get(
        "survey_points"
    )
    survey_pair = _named_progress(
        survey_points,
        current_names=("num",),
        target_names=("total",),
    )
    if survey_pair is not None:
        survey_item = _activity_item(
            "零号空洞调查积分",
            survey_points,
            pair=survey_pair,
        )
        if survey_item is not None:
            items.append(dict(survey_item, period="weekly"))

    weekly_task = root.get("weekly_task")
    weekly_pair = _named_progress(
        weekly_task,
        current_names=("cur_point",),
        target_names=("max_point",),
    )
    if weekly_pair is not None:
        weekly_item = _activity_item(
            "丽都周纪积分",
            weekly_task,
            pair=weekly_pair,
        )
        if weekly_item is not None:
            items.append(dict(weekly_item, period="weekly"))

    resources = []
    energy = root.get("energy")
    if isinstance(energy, Mapping):
        energy_pair = _progress_pair(energy.get("progress"))
        energy_item = None
        if energy_pair is not None:
            current, target = energy_pair
            energy_item = _resource_item(
                "电量",
                energy.get("progress"),
                pair=energy_pair,
                status=_recovery_status(
                    energy.get("restore"),
                    current=current,
                    target=target,
                ),
            )
        if energy_item is not None:
            resources.append(energy_item)

    temple = root.get("temple_running")
    temple_pair = _named_progress(
        temple,
        current_names=("current_currency",),
        target_names=("weekly_currency_max",),
    )
    if temple_pair is not None:
        temple_item = _resource_item(
            "随便观周收益",
            temple,
            pair=temple_pair,
        )
        if temple_item is not None:
            resources.append(temple_item)
    return _build_snapshot(
        account_uid=account_uid,
        account_name=account_name,
        platform="米游社",
        game="绝区零",
        items=[item for item in items if item is not None],
        resources=resources,
        role=role,
        source="/event/game_record_zzz/api/zzz/note",
        progress=vitality,
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
        source="/web/v1/game/endfield/card/detail",
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
        parser=_parse_miyoushe_zzz,
        source="/event/game_record_zzz/api/zzz/note",
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
