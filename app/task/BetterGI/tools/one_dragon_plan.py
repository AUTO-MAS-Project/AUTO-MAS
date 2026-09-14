#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 一条龙：MAS 自编排的「执行计划（Plan）」模型与工具。

一条龙的可视化队列 ``OneDragon.Queue`` 只是 ``[{kind, name}]`` 的有序列表，
无法携带 per-任务的执行层参数，也不能表达「同一任务跑两遍、参数不同」。
``Plan`` 取代/并列于它，结构为：

    {
      "version": 1,
      "steps": [
        {"uid", "kind", "name", "enabled", "settings": {...}}
      ]
    }

其中 ``settings`` 携带该步骤的 per-任务执行层参数（路径 B 下战斗 4 项直连执行层用）。

本模块**只做解析 / 校验 / 迁移**，不触碰 BetterGI 运行链路；真正的执行切换由
``AutoProxy`` 在灰度开关 ``OneDragon.UseExecutionLayer`` 打开后接入（桥接期）。
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from app.utils import get_logger

logger = get_logger("BetterGI 一条龙计划")

# 步骤来源类型，与前端队列 kind 保持一致
StepKind = Literal["builtin", "js", "pathing", "scriptgroup", "keymouse", "custom"]
_STEP_KINDS: frozenset[str] = frozenset(
    {"builtin", "js", "pathing", "scriptgroup", "keymouse", "custom"}
)

# 8 个内置一条龙步骤的标准名（与 BGI 一条龙 TaskDefinitions 值一致）
BUILTIN_STEP_NAMES: frozenset[str] = frozenset(
    {
        "领取邮件",
        "合成树脂",
        "自动地脉花",
        "自动秘境",
        "自动首领讨伐",
        "自动幽境危战",
        "领取每日奖励",
        "领取尘歌壶奖励",
    }
)

# 内置战斗 4 项（路径 B 下由执行层直连；日常 4 项无执行层入口，继续走一条龙）
BUILTIN_COMBAT_STEP_NAMES: frozenset[str] = frozenset(
    {
        "自动秘境",
        "自动地脉花",
        "自动幽境危战",
        "自动首领讨伐",
    }
)

# 执行层步骤命名约定：同一战斗类型可配置多个独立实例，名字形如 ``自动秘境``（默认）
# 或 ``自动秘境-副本A``（基名 + "-" 后缀）。解析时一律归一到基名，以复用设置白名单 /
# 右栏翻译 / 每周结构 / 执行层分发的既有逻辑。基名本身不含 "-" 分隔符，故按前缀匹配即可。
_BUILTIN_STEP_NAME_LIST: list[str] = list(BUILTIN_STEP_NAMES)


def _resolve_base_name(name: str) -> str | None:
    """把可能带后缀的执行层步骤名归一到基名；非内置步骤返回 ``None``。

    - ``自动秘境`` -> ``自动秘境``
    - ``自动秘境-副本A`` -> ``自动秘境``
    """
    name = str(name or "").strip()
    if name in BUILTIN_STEP_NAMES:
        return name
    for base in _BUILTIN_STEP_NAME_LIST:
        if name.startswith(base + "-"):
            return base
    return None


# 公开别名，供外部（如 AutoProxy 计算 _exclude）按基名归一
resolve_base_name = _resolve_base_name

# 各内置步骤在执行层（BetterGI 原生任务 Param）的可传参白名单，键名采用
# ``bettergi.d.ts`` 的 Param 字段名（camelCase）。路径 B 下：
#   - 战斗 4 项（秘境/地脉花/幽境危战/首领讨伐）可由 JS 桥接直传执行层；
#   - 日常 4 项（邮件/合成树脂/尘歌壶/每日奖励）执行层无入口，settings 仅持久化、
#     Runtime 忽略，继续走一条龙。
# 白名单用于校验告警（未知键记日志但不阻断），字段语义以目标版本 d.ts 复核为准。
BUILTIN_STEP_SETTING_KEYS: dict[str, frozenset[str]] = {
    "自动秘境": frozenset(
        {
            "partyName",
            "domainName",
            "sundaySelectedValue",
            "weeklyDomainEnabled",
            "autoArtifactSalvage",
            "maxArtifactStar",
            "rewardRecognitionEnabled",
            "specifyResinUse",
            "originalResinUseCount",
            "condensedResinUseCount",
            "transientResinUseCount",
            "fragileResinUseCount",
            "resinPriorityList",
            "combatStrategyPath",
            "domainRoundNum",
            "weeklyDomain",
        }
    ),
    "自动地脉花": frozenset(
        {
            "isResinExhaustionMode",
            "openModeCountMin",
            "count",
            "country",
            "leyLineOutcropType",
            "team",
            "timeout",
            "weeklyLeyLine",
            "useAdventurerHandbook",
            "useFragileResin",
            "useTransientResin",
            "leyLineDailyEnabled",
            "friendshipTeam",
            "combatStrategyPath",
        }
    ),
    "自动幽境危战": frozenset(
        {
            "bossNum",
            "fightTeamName",
            "strategyName",
            "autoArtifactSalvage",
            "specifyResinUse",
            "originalResinUseCount",
            "condensedResinUseCount",
            "transientResinUseCount",
            "fragileResinUseCount",
            "resinPriorityList",
            "combatStrategyPath",
        }
    ),
    "自动首领讨伐": frozenset(
        {
            "bossName",
            "teamName",
            "strategyName",
            "specifyRunCount",
            "runCount",
            "useTransientResin",
            "useFragileResin",
            "rviveRetryCount",
            "returnToStatueAfterEachRound",
            "rewardRecognitionEnabled",
            "timeout",
        }
    ),
}

PLAN_VERSION = 1


def _gen_uid() -> str:
    """生成步骤实例唯一标识（对应前端 dragonRowSeq 概念）。"""
    return uuid.uuid4().hex


def parse_one_dragon_plan(raw: Any) -> list[dict[str, Any]]:
    """解析前端保存的一条龙 Plan JSON（字符串或已是列表），非法时返回空列表。

    每个 step 归一为 ``{"uid", "kind", "name", "enabled", "settings"}``：
    - ``name`` 命中内置 8 组时 ``kind`` 强制为 ``builtin``；
    - 其余 kind 仅在白名单内保留，否则回退 ``builtin``；
    - 空名与非字典项丢弃；**允许同名条目重复**（每个实例是独立 uid）。
    """
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("一条龙 Plan JSON 解析失败，返回空计划")
            return []
    else:
        return []

    # 兼容 ``plan_to_json`` 产出的 ``{"version", "steps": [...]}`` 包装结构，
    # 也兼容裸 list（或字符串化的 list）。否则顶层 dict 会被误判为非法而返回空。
    if isinstance(data, dict) and isinstance(data.get("steps"), list):
        data = data["steps"]
    if not isinstance(data, list):
        return []

    steps: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        kind = str(item.get("kind", "builtin"))
        if kind not in _STEP_KINDS:
            kind = "builtin"
        if name in BUILTIN_STEP_NAMES:
            kind = "builtin"
        uid = str(item.get("uid") or "").strip() or _gen_uid()
        enabled = bool(item.get("enabled", True))
        settings = item.get("settings") or {}
        if not isinstance(settings, dict):
            settings = {}
        steps.append(
            {
                "uid": uid,
                "kind": kind,
                "name": name,
                "enabled": enabled,
                "settings": settings,
            }
        )
    return steps


def validate_step_settings(step: dict[str, Any]) -> dict[str, Any]:
    """按 kind/name 校验 step 的 settings，返回清理后的 settings（未知键仅告警）。

    战斗 4 项按 ``BUILTIN_STEP_SETTING_KEYS`` 白名单过滤；日常 4 项与自定义类步骤
    当前不限制（路径 B 下非直连项由一条龙 / 脚本自行处理）。
    """
    name = str(step.get("name", ""))
    settings = step.get("settings") or {}
    if not isinstance(settings, dict):
        return {}
    base = _resolve_base_name(name)
    allowed = BUILTIN_STEP_SETTING_KEYS.get(base) if base else None
    if allowed is None:
        return dict(settings)
    cleaned: dict[str, Any] = {}
    for key, value in settings.items():
        if key in allowed:
            cleaned[key] = value
        else:
            logger.warning(f"一条龙步骤「{name}」含未知设置键「{key}」，已忽略")
    return cleaned


def plan_to_json(steps: list[dict[str, Any]]) -> str:
    """把 steps 序列化为持久化的 Plan JSON 字符串。"""
    payload = {
        "version": PLAN_VERSION,
        "steps": [
            {
                "uid": s.get("uid") or _gen_uid(),
                "kind": s.get("kind", "builtin"),
                "name": s.get("name", ""),
                "enabled": s.get("enabled", True),
                "settings": s.get("settings") or {},
            }
            for s in steps
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


# ── 右栏 → 执行层 Plan 键翻译（仅战斗 4 项、仅可对齐字段）────────────────────
# 右栏字段按 source 分三条存储（dragon / globalDomain / globalStygian），但键名唯一；
# 这里按「战斗组内名」统一映射。global* 端点不带组名，由调用方按段固定映射：
#   globalStygian → 自动幽境危战；globalDomain → 自动秘境。
# 键名全部来自 BUILTIN_STEP_SETTING_KEYS 白名单（已逐项核对），未列出的右栏字段
# （如秘境每周秘境表、地脉花每工作日 country/type、maxArtifactStar）
# 属结构化/全局共享，无法对齐到单值 Plan，留在原生存储。
# 注：地脉花「跳过准备流程」(LeyLineOneDragonMode) 因 BGI 未向 JS 暴露注入点，
# 在 MAS 接管路径下无效，已从右栏移除（不进 Plan、不进原生白名单）。
RIGHTBAR_TO_PLAN: dict[str, dict[str, str]] = {
    "自动幽境危战": {
        "bossNum": "bossNum",
        "fightTeamName": "fightTeamName",
        "strategyName": "strategyName",
        "autoArtifactSalvage": "autoArtifactSalvage",
        "specifyResinUse": "specifyResinUse",
        "originalResinUseCount": "originalResinUseCount",
        "condensedResinUseCount": "condensedResinUseCount",
        "transientResinUseCount": "transientResinUseCount",
        "fragileResinUseCount": "fragileResinUseCount",
    },
    "自动秘境": {
        "autoArtifactSalvage": "autoArtifactSalvage",
        "maxArtifactStar": "maxArtifactStar",
        "rewardRecognitionEnabled": "rewardRecognitionEnabled",
        "specifyResinUse": "specifyResinUse",
        "originalResinUseCount": "originalResinUseCount",
        "condensedResinUseCount": "condensedResinUseCount",
        "transientResinUseCount": "transientResinUseCount",
        "fragileResinUseCount": "fragileResinUseCount",
        "PartyName": "partyName",
        "DomainName": "domainName",
        "SundayEverySelectedValue": "sundaySelectedValue",
        "WeeklyDomainEnabled": "weeklyDomainEnabled",
    },
    "自动首领讨伐": {
        "AutoBossName": "bossName",
        "AutoBossTeamName": "teamName",
        "AutoBossStrategyName": "strategyName",
        "AutoBossSpecifyRunCount": "specifyRunCount",
        "AutoBossRunCount": "runCount",
        "AutoBossUseTransientResin": "useTransientResin",
        "AutoBossUseFragileResin": "useFragileResin",
        "AutoBossReviveRetryCount": "rviveRetryCount",
        "AutoBossReturnToStatueAfterEachRound": "returnToStatueAfterEachRound",
        "AutoBossRewardRecognitionEnabled": "rewardRecognitionEnabled",
        "AutoBossTimeout": "timeout",
    },
    "自动地脉花": {
        "LeyLineResinExhaustionMode": "isResinExhaustionMode",
        "LeyLineOpenModeCountMin": "openModeCountMin",
        "LeyLineRunCount": "count",
        "LeyLineTimeout": "timeout",
        "useAdventurerHandbook": "useAdventurerHandbook",
        "useFragileResin": "useFragileResin",
        "useTransientResin": "useTransientResin",
        "country": "country",
        "leyLineOutcropType": "leyLineOutcropType",
        "team": "team",
        "leyLineDailyEnabled": "leyLineDailyEnabled",
        "friendshipTeam": "friendshipTeam",
        "combatStrategyPath": "combatStrategyPath",
    },
}


# ── 每周配置：右栏平铺键 ↔ Plan 嵌套结构 ───────────────────────────────
# 前端 weekly 表格仍用 BGI 原生平铺键（MondayPartyName / LeyLineMondayCountry …），
# 后端落盘时重组为 Plan settings 内的嵌套对象，执行层 main.js 按「今天星期」取值。
# 嵌套键：秘境 weeklyDomain / 地脉花 weeklyLeyLine，值形如
#   { "default": {partyName, domainName, reward}, "Monday": {...}, ... }
#   { "Monday": {country, type, run}, ... }
WEEKDAY_KEYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _secret_weekly_plan_key(field_key: str):
    """秘境 weekly 平铺键 → (天键, 嵌套字段)；非 weekly 返 None。

    ``PartyName`` / ``DomainName`` / ``StrategyName`` 既是每日行的单值，也是每周表的
    「默认」行，两者同键同值（见前端每周秘境表 default 行），统一归到 ``default``。
    ``default.reward`` 只认 ``SundayWeeklySelectedValue``（每周表默认行的奖励）；
    每日行的 ``SundayEverySelectedValue`` 归扁平 ``sundaySelectedValue``，二者语义
    不同（BGI 原生：开每周走前者、走每日走后者），不能混用。
    ``StrategyName`` 是 MAS 扩展键（BGI 原生一条龙没有 per-任务战斗策略键），由执行层
    ``setCombatStrategyPath`` 直传，不走全局 ``autoFightConfig``。
    """
    if field_key == "PartyName":
        return "default", "partyName"
    if field_key == "DomainName":
        return "default", "domainName"
    if field_key == "StrategyName":
        return "default", "strategy"
    if field_key == "SundayWeeklySelectedValue":
        return "default", "reward"
    for day in WEEKDAY_KEYS:
        if field_key == f"{day}PartyName":
            return day, "partyName"
        if field_key == f"{day}StrategyName":
            return day, "strategy"
        if field_key == f"{day}DomainName":
            return day, "domainName"
        if field_key == f"{day}SelectedValue":
            return day, "reward"
        if field_key == f"DomainRun{day}":
            return day, "run"
    return None


def _leyline_weekly_plan_key(field_key: str):
    """地脉花 weekly 平铺键 → (天键, 嵌套字段)；非 weekly 返 None。

    default 行是兜底：当天某字段为空时按默认行填写（default 行无执行开关）。
    team/strategy 为 MAS 扩展列（BGI 原生一条龙无 per-天队伍/策略键）。"""
    # 默认行（兜底）
    if field_key == "LeyLineDefaultTeam":
        return "default", "team"
    if field_key == "LeyLineDefaultStrategy":
        return "default", "strategy"
    if field_key == "LeyLineDefaultCountry":
        return "default", "country"
    if field_key == "LeyLineDefaultType":
        return "default", "type"
    for day in WEEKDAY_KEYS:
        if field_key == f"LeyLine{day}Team":
            return day, "team"
        if field_key == f"LeyLine{day}Strategy":
            return day, "strategy"
        if field_key == f"LeyLine{day}Country":
            return day, "country"
        if field_key == f"LeyLine{day}Type":
            return day, "type"
        if field_key == f"LeyLineRun{day}":
            return day, "run"
    return None


def extract_weekly_struct(group: str, settings: dict[str, Any]) -> dict[str, Any]:
    """从右栏 settings 提取 weekly 嵌套结构；无则返空 dict。"""
    result: dict[str, Any] = {}
    base = _resolve_base_name(group)
    if base == "自动秘境":
        struct: dict[str, Any] = {}
        for k, v in settings.items():
            parsed = _secret_weekly_plan_key(k)
            if parsed:
                day, field = parsed
                struct.setdefault(day, {})[field] = v
        if struct:
            result["weeklyDomain"] = struct
    elif base == "自动地脉花":
        struct = {}
        for k, v in settings.items():
            parsed = _leyline_weekly_plan_key(k)
            if parsed:
                day, field = parsed
                struct.setdefault(day, {})[field] = v
        if struct:
            result["weeklyLeyLine"] = struct
    return result


def flatten_weekly_struct(group: str, settings: dict[str, Any]) -> dict[str, Any]:
    """把 Plan settings 里的 weeklyDomain/weeklyLeyLine 还原为平铺右栏键（回显）。"""
    out: dict[str, Any] = {}
    base = _resolve_base_name(group)
    if base == "自动秘境" and isinstance(settings.get("weeklyDomain"), dict):
        for day, vals in settings["weeklyDomain"].items():
            if not isinstance(vals, dict):
                continue
            if day == "default":
                if "reward" in vals:
                    out["SundayWeeklySelectedValue"] = vals["reward"]
                if "partyName" in vals:
                    out["PartyName"] = vals["partyName"]
                if "strategy" in vals:
                    out["StrategyName"] = vals["strategy"]
                if "domainName" in vals:
                    out["DomainName"] = vals["domainName"]
            else:
                if "partyName" in vals:
                    out[f"{day}PartyName"] = vals["partyName"]
                if "strategy" in vals:
                    out[f"{day}StrategyName"] = vals["strategy"]
                if "domainName" in vals:
                    out[f"{day}DomainName"] = vals["domainName"]
                if "reward" in vals:
                    out[f"{day}SelectedValue"] = vals["reward"]
                if "run" in vals:
                    out[f"DomainRun{day}"] = vals["run"]
    if base == "自动地脉花" and isinstance(settings.get("weeklyLeyLine"), dict):
        for day, vals in settings["weeklyLeyLine"].items():
            if not isinstance(vals, dict):
                continue
            if day == "default":
                if "team" in vals:
                    out["LeyLineDefaultTeam"] = vals["team"]
                if "strategy" in vals:
                    out["LeyLineDefaultStrategy"] = vals["strategy"]
                if "country" in vals:
                    out["LeyLineDefaultCountry"] = vals["country"]
                if "type" in vals:
                    out["LeyLineDefaultType"] = vals["type"]
            else:
                if "team" in vals:
                    out[f"LeyLine{day}Team"] = vals["team"]
                if "strategy" in vals:
                    out[f"LeyLine{day}Strategy"] = vals["strategy"]
                if "country" in vals:
                    out[f"LeyLine{day}Country"] = vals["country"]
                if "type" in vals:
                    out[f"LeyLine{day}Type"] = vals["type"]
                if "run" in vals:
                    out[f"LeyLineRun{day}"] = vals["run"]
    return out


def build_combat_steps(
    plan_steps: list[dict[str, Any]],
    queue: list[dict[str, Any]] | None = None,
    enabled_groups: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按 Plan 顺序挑出「由执行层接管」的战斗步骤，支持同类型多实例。

    命名约定：同一战斗类型可配置多个独立实例，名字形如 ``自动秘境``（默认）或
    ``自动秘境-副本A``（基名 + 后缀），各实例持有独立 uid 与 settings。

    接管需同时满足：
    1. 步骤基名属于战斗 4 项（``BUILTIN_COMBAT_STEP_NAMES``）；
    2. 该基名在 ``enabled_groups``（``OneDragon.Groups``）中启用——组开关是启停权威源；
    3. 该步骤自身 ``enabled`` 为真。

    不再按 name 去重：每个带后缀/同名的战斗步骤都是独立实例，各自带参。顺序以 Plan
    步骤为准；``queue`` 仅在非空时作为排序/启用过滤器（精确名匹配优先，同基名 FIFO 兜底），
    以兼容桥接期旧队列。
    """
    enabled = {str(name) for name in (enabled_groups or [])}

    # 1) 收集 Plan 中全部战斗步骤（按 uid 去重防重复），保留原顺序
    plan_combat: list[dict[str, Any]] = []
    seen_uid: set[str] = set()
    for step in plan_steps:
        name = str(step.get("name", ""))
        base = _resolve_base_name(name)
        if base not in BUILTIN_COMBAT_STEP_NAMES:
            continue
        if enabled and base not in enabled:
            # 组开关缺失但 Plan 中已配置：本次按启用接管并告警，避免「界面/队列
            # 显示已开、运行时静默跳过」（Groups 与界面偶发不同步时的兜底）。
            # 请在界面重新开关一次该组以同步数据。
            logger.warning(
                f"内置战斗组「{base}」不在 OneDragon.Groups 中，但 Plan 已配置，"
                "本次按启用处理（请在界面重新开关一次该组以同步数据）"
            )
        if not step.get("enabled", True):
            continue
        uid = step.get("uid")
        if uid in seen_uid:
            continue
        seen_uid.add(uid)
        plan_combat.append(dict(step))
    if not plan_combat:
        return []

    if not queue:
        return plan_combat

    # 2) queue 作为排序/启用过滤器：精确名优先，同基名 FIFO 兜底（兼容旧队列同名项）
    by_base: dict[str, list[int]] = {}
    for i, s in enumerate(plan_combat):
        by_base.setdefault(_resolve_base_name(s["name"]), []).append(i)
    out: list[dict[str, Any]] = []
    consumed: set[int] = set()
    # 推导队列条目对应的 Plan 步骤名（与前端 stepNameIn 规则一致）：
    # 同名条目中 uid 最小者沿用基名，其余为「基名-uid」
    min_uid_by_name: dict[str, int] = {}
    for item in queue:
        if not isinstance(item, dict) or not bool(item.get("enabled", True)):
            continue
        qn = str(item.get("name", ""))
        uid = item.get("uid")
        if qn and isinstance(uid, int):
            min_uid_by_name[qn] = min(min_uid_by_name.get(qn, uid), uid)
    for item in queue:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        qname = str(item.get("name", ""))
        # ① 条目 planUid 与 Plan 步骤 uid 一致 → 精确定向（同名多实例的唯一区分手段）
        quid = str(item.get("planUid", "") or "")
        if quid:
            exact = next(
                (
                    i
                    for i in range(len(plan_combat))
                    if i not in consumed and str(plan_combat[i].get("uid", "")) == quid
                ),
                None,
            )
            if exact is not None:
                consumed.add(exact)
                out.append(plan_combat[exact])
                continue
        # ② 由 (name, uid) 推导的 Plan 步骤名精确匹配（同名多实例定向排序）
        q_uid = item.get("uid")
        step_name = qname
        if isinstance(q_uid, int) and min_uid_by_name.get(qname) != q_uid:
            step_name = f"{qname}-{q_uid}"
        exact = next(
            (
                i
                for i in range(len(plan_combat))
                if i not in consumed and plan_combat[i].get("name") == step_name
            ),
            None,
        )
        # 推导名未命中时回退基名（兼容 uid 与步骤名不对应的存量队列）
        if exact is None and step_name != qname:
            exact = next(
                (
                    i
                    for i in range(len(plan_combat))
                    if i not in consumed and plan_combat[i].get("name") == qname
                ),
                None,
            )
        if exact is not None:
            consumed.add(exact)
            out.append(plan_combat[exact])
            continue
        base = _resolve_base_name(qname)
        bucket = by_base.get(base)
        if bucket:
            while bucket:
                idx = bucket.pop(0)
                if idx not in consumed:
                    break
            else:
                idx = None
            if idx is not None:
                consumed.add(idx)
                out.append(plan_combat[idx])
    # 3) 未被 queue 消费的 Plan 步骤（孤儿实例，如曾创建后从队列移除/未入队）
    #    不执行：左栏队列是用户所见即所得，追加执行会让用户跑出「界面上没有的
    #    任务」（2026-09-09 实机排障：队列 7 个战斗组被跑出 11 步）。
    orphans = [str(plan_combat[i].get("name", "")) for i in range(len(plan_combat)) if i not in consumed]
    if orphans:
        logger.warning(f"以下执行层实例不在队列中，本次跳过: {', '.join(orphans)}")
    return out


def prune_plan_to_queue(
    plan_json: str | dict,
    queue_raw: Any,
    enabled_groups: list[str] | None = None,
) -> str:
    """队列是战斗实例的唯一真相源：删除 Plan 中「不再被队列引用」的战斗实例。

    前端删除一条龙队列行时只改 ``OneDragon.Queue``，Plan 中的对应实例会残留成孤儿
    （界面没有、运行时却可能被追加执行）。本函数在队列落盘时调用：以「队列当前实际
    引用到的战斗步骤名」为准，保留被引用实例，删除战斗 4 项中其余孤儿实例；非战斗
    实例（邮件/尘歌壶等本就不在 Plan 中）不受影响。仅剔除「已从队列移除」的行——
    被关闭（enabled=false）但仍在队列里的行仍保留其实例。

    返回处理后的 Plan JSON 字符串；无实例被删时原样返回，避免无谓改写。
    """
    plan_steps = parse_one_dragon_plan(plan_json)
    if isinstance(queue_raw, str):
        try:
            queue = json.loads(queue_raw)
        except json.JSONDecodeError:
            queue = []
    else:
        queue = queue_raw
    if not isinstance(queue, list):
        queue = []

    if not plan_steps:
        return plan_json if isinstance(plan_json, str) else json.dumps(plan_json, ensure_ascii=False)

    # 计算队列当前引用的战斗实例步骤名（含被关闭行；仅剔除已从队列移除的行）
    referenced: set[str] = set()
    min_uid: dict[str, int] = {}
    for it in queue:
        if isinstance(it, dict):
            n = str(it.get("name", ""))
            u = it.get("uid")
            if isinstance(u, int) and n:
                min_uid[n] = min(min_uid.get(n, u), u)
    for it in queue:
        if not isinstance(it, dict):
            continue
        qn = str(it.get("name", ""))
        if not qn:
            continue
        base = _resolve_base_name(qn)
        if base not in BUILTIN_COMBAT_STEP_NAMES:
            continue
        quid = str(it.get("planUid", "") or "")
        if quid:
            hit = next((s for s in plan_steps if str(s.get("uid", "")) == quid), None)
            if hit:
                referenced.add(hit.get("name"))  # type: ignore[arg-type]
                continue
        step_name = qn
        u = it.get("uid")
        if isinstance(u, int) and min_uid.get(qn, u) != u:
            step_name = f"{qn}-{u}"
        referenced.add(step_name)

    new_steps = [
        s
        for s in plan_steps
        if _resolve_base_name(s.get("name", "")) not in BUILTIN_COMBAT_STEP_NAMES
        or s.get("name") in referenced
    ]
    if len(new_steps) == len(plan_steps):
        # 无变化：原样返回（保留原字符串，避免每次队列保存都重写 Plan）
        return plan_json if isinstance(plan_json, str) else json.dumps(plan_json, ensure_ascii=False)

    # 重建 JSON，保留 version 等外层字段
    if isinstance(plan_json, str):
        try:
            wrapper = json.loads(plan_json)
        except json.JSONDecodeError:
            wrapper = None
    else:
        wrapper = plan_json
    if isinstance(wrapper, dict) and isinstance(wrapper.get("steps"), list):
        wrapper = dict(wrapper)
        wrapper["steps"] = new_steps
    else:
        wrapper = new_steps
    removed = [s.get("name") for s in plan_steps if s not in new_steps]
    logger.info(f"队列变更：清理 Plan 孤儿战斗实例 {len(removed)} 个 -> {removed}")
    return json.dumps(wrapper, ensure_ascii=False, indent=2)


def merge_rightbar_into_plan(
    plan_json: str,
    group: str,
    settings: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> str:
    """把右栏设置（frontend 键）翻译后合并进 Plan 中名为 ``group`` 的步骤 settings。

    找不到该步骤则新建（kind=builtin, enabled=True）。合并后仅保留白名单键。
    非战斗组或无可映射键时原样返回 ``plan_json``。
    """
    base = _resolve_base_name(group)
    mapping = RIGHTBAR_TO_PLAN.get(base)
    if not mapping or not settings:
        return plan_json
    transl: dict[str, Any] = {
        pk: settings[k] for k, pk in mapping.items() if k in settings
    }
    if not transl and not extra:
        return plan_json
    steps = parse_one_dragon_plan(plan_json) if plan_json else []
    target = next((s for s in steps if s.get("name") == group), None)
    if target is None:
        target = {
            "uid": _gen_uid(),
            "kind": "builtin",
            "name": group,
            "enabled": True,
            "settings": {},
        }
        steps.append(target)
    merged = {**(target.get("settings") or {}), **transl}
    if extra:
        merged.update(extra)
    target["settings"] = validate_step_settings({"name": group, "settings": merged})
    return plan_to_json(steps)


def extract_rightbar_from_plan(plan_json: str, group: str) -> dict[str, Any]:
    """从 Plan 中名为 ``group`` 的步骤 settings 反查回右栏 frontend 键。"""
    base = _resolve_base_name(group)
    mapping = RIGHTBAR_TO_PLAN.get(base)
    if not mapping:
        return {}
    steps = parse_one_dragon_plan(plan_json) if plan_json else []
    target = next((s for s in steps if s.get("name") == group), None)
    if not target:
        return {}
    settings = target.get("settings") or {}
    return {fk: settings[pk] for fk, pk in mapping.items() if pk in settings}
