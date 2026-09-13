# -*- coding: utf-8 -*-
"""队伍配置表 → 战斗场景选队解析器（BetterGI 一条龙执行层）。

需求定稿要点：

1. **四层选队优先级**
   队伍表场景命中（非通用行） > 右栏 per-任务队伍 > 通用队伍（``OneDragon.PartyName``）
   > 通用队伍留空则不设置（交由 BGI 沿用自身值）。本模块只负责第 1 层，第 2~4 层
   由 ``AutoProxy`` 既有逻辑与执行层 ``main.js`` 的取值链承担。

2. **只认 L1 精确匹配**
   队伍的「战斗场景」条件与步骤「本次实际执行目标」的明细字段全等才算命中，
   不做「类型级」降级匹配。未勾选任何场景的队伍、总开关关闭时的非通用行均不参与。

3. **随机固定在一次运行内**
   命中多个队伍时随机选一个；解析在一条龙启动前一次性完成，结果即固化进本次物化的
   Plan，故同一次运行内不会中途换队。

4. **压过每周配置**
   ``res/templates/BetterGI/MASOneDragon/main.js`` 对秘境/地脉花的取值链是
   「当天行 > 每周默认行 > 步骤级字段」。为让「按任务选队」优先于「按日期配置」，
   本模块写入独立的最高优先级字段 ``masTeamOverride`` / ``masStrategyOverride``。
   **目标（打哪个秘境/地脉）仍由每周表按日期决定，只有队伍改由本表按任务决定。**

匹配键说明：运行期步骤 settings 里只有目标名（秘境 ``domainName``、首领 ``bossName``），
**没有地区字段**，故「地区」仅作界面分组展示、不参与匹配；秘境的「奖励档」同理仅展示
（奖励档决定掉落而非队伍适用性）。地脉花的「地区 + 地脉类型」两个字段运行期均可得，
故两者都参与匹配。
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any

from app.utils import get_logger

from .one_dragon_plan import WEEKDAY_KEYS, resolve_base_name

logger = get_logger("BetterGI 队伍配置")

# 战斗场景标签页 → 步骤基名
SCENE_BY_BASE: dict[str, str] = {
    "自动秘境": "domain",
    "自动地脉花": "leyline",
    "自动首领讨伐": "boss",
}

# Plan 步骤内的选队结果字段（执行层 main.js 以最高优先级读取）
TEAM_OVERRIDE_KEY = "masTeamOverride"
STRATEGY_OVERRIDE_KEY = "masStrategyOverride"


def _clean(value: Any) -> str:
    """字符串化并去首尾空白；``None`` → ``""``。"""
    return str(value or "").strip()


def parse_teams(raw: Any) -> list[dict[str, Any]]:
    """解析 ``OneDragon.Teams``。

    非法 JSON、非数组、结构异常项一律跳过（仅告警，不抛错），保证一条坏数据不会
    阻断整条一条龙。队伍名为空的条目直接剔除（无法用于切队，且会让 BGI 崩）。
    """
    if isinstance(raw, list):
        items: Any = raw
    else:
        text = _clean(raw)
        if not text:
            return []
        try:
            items = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("队伍配置 Teams 不是合法 JSON，已按空表处理")
            return []
    if not isinstance(items, list):
        logger.warning("队伍配置 Teams 不是数组，已按空表处理")
        return []

    out: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(f"队伍配置第 {index} 行不是对象，已忽略")
            continue
        name = _clean(item.get("name"))
        if not name:
            logger.warning(f"队伍配置第 {index} 行队伍名称为空，已忽略")
            continue
        scenes = item.get("scenes")
        out.append(
            {
                "name": name,
                "strategy": _clean(item.get("strategy")),
                "scenes": scenes if isinstance(scenes, dict) else {},
                "note": _clean(item.get("note")),
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return out


def current_weekday_key(now: datetime | None = None) -> str:
    """当前星期对应的 weekly 嵌套键（与 ``one_dragon_plan.WEEKDAY_KEYS`` 对齐）。

    ``datetime.weekday()`` 周一为 0，与 ``WEEKDAY_KEYS[0] == "Monday"`` 一致。
    """
    moment = now or datetime.now()
    return WEEKDAY_KEYS[moment.weekday()]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_domain_name(settings: dict[str, Any], day_key: str) -> str:
    """还原秘境步骤本次实际执行的秘境名（对齐 main.js 取值链）。"""
    weekly = _as_dict(settings.get("weeklyDomain"))
    use_weekly = settings.get("weeklyDomainEnabled") is not False
    today = _as_dict(weekly.get(day_key)) if use_weekly else {}
    default = _as_dict(weekly.get("default"))
    return (
        _clean(today.get("domainName"))
        or _clean(default.get("domainName"))
        or _clean(settings.get("domainName"))
    )


def _resolve_leyline_target(
    settings: dict[str, Any], day_key: str
) -> tuple[str, str] | None:
    """还原地脉花步骤本次实际执行的目标（地区, 地脉类型）；当天不执行时返回 None。

    每日模式直接取步骤级字段；每周模式对齐 main.js：当天行未勾选「执行」即不执行
    （返回 None），字段缺省按「默认」行兜底，再按步骤级兜底。
    """
    if settings.get("leyLineDailyEnabled") is not False:
        country = _clean(settings.get("country"))
        ley_line_type = _clean(settings.get("leyLineOutcropType"))
    else:
        weekly = _as_dict(settings.get("weeklyLeyLine"))
        today = _as_dict(weekly.get(day_key))
        if today.get("run") is not True:
            return None
        default = _as_dict(weekly.get("default"))

        def pick(row_key: str, step_key: str) -> str:
            # 每周行的键与步骤级不同：行内是 country / type，步骤级是 country /
            # leyLineOutcropType（见 one_dragon_plan._leyline_weekly_plan_key 与 main.js）
            for holder in (today, default):
                if holder.get(row_key) is not None:
                    return _clean(holder.get(row_key))
            return _clean(settings.get(step_key))

        country = pick("country", "country")
        ley_line_type = pick("type", "leyLineOutcropType")
    if not country or not ley_line_type:
        return None
    return country, ley_line_type


def resolve_target(
    base: str, settings: dict[str, Any], day_key: str
) -> dict[str, str] | None:
    """还原该步骤「本次实际执行」的目标明细；无法执行（当天跳过/缺字段）返回 None。

    只覆盖纳入场景选队的 3 个战斗组；幽境危战等其余组一律返回 None（不参与）。
    """
    if base == "自动秘境":
        domain = _resolve_domain_name(settings, day_key)
        return {"domain": domain} if domain else None
    if base == "自动地脉花":
        target = _resolve_leyline_target(settings, day_key)
        if target is None:
            return None
        return {"country": target[0], "type": target[1]}
    if base == "自动首领讨伐":
        boss = _clean(settings.get("bossName"))
        return {"boss": boss} if boss else None
    return None


def _condition_hit(scene: str, condition: dict[str, Any], target: dict[str, str]) -> bool:
    """单个场景条件与目标明细的 L1 精确匹配。"""
    if scene == "domain":
        value = _clean(condition.get("domain"))
        return bool(value) and value == target.get("domain")
    if scene == "leyline":
        return _clean(condition.get("country")) == target.get("country") and _clean(
            condition.get("type")
        ) == target.get("type")
    if scene == "boss":
        value = _clean(condition.get("boss"))
        return bool(value) and value == target.get("boss")
    return False


def match_teams(
    teams: list[dict[str, Any]], base: str, target: dict[str, str] | None
) -> list[dict[str, Any]]:
    """返回场景命中该战斗任务的队伍（按表内顺序，保持稳定）。"""
    scene = SCENE_BY_BASE.get(base)
    if not scene or not target:
        return []
    hits: list[dict[str, Any]] = []
    for team in teams:
        if not team.get("enabled", True):
            continue
        conditions = team.get("scenes")
        if not isinstance(conditions, dict):
            continue
        items = conditions.get(scene)
        if not isinstance(items, list):
            continue
        for condition in items:
            if isinstance(condition, dict) and _condition_hit(scene, condition, target):
                hits.append(team)
                break
    return hits


def _describe_target(target: dict[str, str]) -> str:
    if "domain" in target:
        return target["domain"]
    if "type" in target:
        return f"{target.get('country', '')}-{target.get('type', '')}"
    return target.get("boss", "")


def resolve_team_for_step(
    teams: list[dict[str, Any]],
    base: str,
    settings: dict[str, Any],
    day_key: str,
    rng: Any | None = None,
) -> dict[str, str] | None:
    """为单个战斗步骤选出队伍。

    Returns:
        ``{"team": 队伍名, "strategy": 策略名}``；未命中返回 ``None``。
        ``strategy`` 可能为空串，表示该队伍留空策略 → 不写入覆盖字段，
        交由下层（右栏 per-任务 → 通用全局策略）决定。
    """
    base = resolve_base_name(base) or base
    target = resolve_target(base, settings, day_key)
    if target is None:
        return None
    hits = match_teams(teams, base, target)
    if not hits:
        return None
    chooser = rng or random
    chosen = chooser.choice(hits)
    team_name = _clean(chosen.get("name"))
    if not team_name:
        return None
    strategy = _clean(chosen.get("strategy"))
    suffix = f"（策略：{strategy}）" if strategy else "（策略留空，跟随下层）"
    logger.info(
        f"队伍配置：战斗任务「{base}/{_describe_target(target)}」命中 {len(hits)} 个队伍，"
        f"随机选中「{team_name}」{suffix}"
    )
    return {"team": team_name, "strategy": strategy}


def apply_teams_to_steps(
    steps: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    day_key: str | None = None,
    rng: Any | None = None,
) -> int:
    """就地为一组 Plan 战斗步骤写入选队结果，返回命中步骤数。

    只写 ``masTeamOverride`` / ``masStrategyOverride`` 两个新增字段，不改动任何既有
    字段，用户配置零改写（override 随运行时 Plan 副本一起丢弃）。
    """
    if not steps or not teams:
        return 0
    weekday = day_key or current_weekday_key()
    hit_count = 0
    for step in steps:
        if not isinstance(step, dict):
            continue
        base = resolve_base_name(str(step.get("name", "")))
        if base not in SCENE_BY_BASE:
            continue
        settings = step.get("settings")
        if not isinstance(settings, dict):
            settings = {}
            step["settings"] = settings
        resolved = resolve_team_for_step(teams, base, settings, weekday, rng=rng)
        if resolved is None:
            continue
        settings[TEAM_OVERRIDE_KEY] = resolved["team"]
        if resolved["strategy"]:
            settings[STRATEGY_OVERRIDE_KEY] = resolved["strategy"]
        else:
            settings.pop(STRATEGY_OVERRIDE_KEY, None)
        hit_count += 1
    return hit_count
