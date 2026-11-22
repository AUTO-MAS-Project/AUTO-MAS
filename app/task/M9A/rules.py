#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 的规则常量与「这是不是 M9A 项目」的判据：全包只有这一份。

建计划与预览用的四张规则表（``M9A_PLAN_RULES``）、重试不补跑的 entry（``M9A_SKIP_ON_RETRY``）、
托管类型键、旧版名字的反查表都在这里。账号流程、托管属主（预览规则表与拒收）、``migration.py`` 都从这里取，
之后 M9A 自己的流程也从这里取。

启动早期配置迁移就会导入本模块，所以只依赖 ``managed.py`` 与解析一侧的 interface 模型、规则表。
"""

from __future__ import annotations

import re
from typing import Any

from app.task.M9A.managed import CLOSE_ENTRY, STARTUP_ENTRY, SWITCH_ACCOUNT_ENTRY
from app.task.MaaFW.blocks.maafw_interface.interface.models import MaaFWInterface
from app.task.MaaFW.blocks.maafw_interface.interface.plan_rules import MaaFWPlanRules

TYPE_KEY = "M9A"

# 旧版 M9A 专项按名字记任务；名字随版本变过（「每日心相」→「每日心相（意志解析）」），
# 迁移时按 entry 反查。这张表只服务迁移与无 interface 降级，运行期不用。
LEGACY_ENTRY_ALIASES: dict[str, str] = {
    "每日心相（意志解析）": "Psychube",
    "每日心相": "Psychube",
    "自动深眠": "Limbo",
    "自动醒梦": "Lucidscape",
    "启动游戏": STARTUP_ENTRY,
    "关闭游戏": CLOSE_ENTRY,
    "切换账号": SWITCH_ACCOUNT_ENTRY,
}
# 没有 interface 可查时（迁移的降级路径）按 v4.9 的名字兜底。
FALLBACK_TASK_NAMES: dict[str, str] = {
    "Psychube": "每日心相（意志解析）",
    "Limbo": "自动深眠",
    "Lucidscape": "自动醒梦",
    STARTUP_ENTRY: "启动游戏",
    CLOSE_ENTRY: "关闭游戏",
    SWITCH_ACCOUNT_ENTRY: "切换账号",
}

# 切换账号失败或超时就结束本轮、照常重试：切号没成功，后面的任务会跑在错的账号上。
# 不列 StartUp：它失败不代表游戏用不了（上游一直只声明切号），本轮照旧按普通失败继续。
M9A_ABORT_ROUND_ENTRIES: dict[str, str] = {SWITCH_ACCOUNT_ENTRY: "切换账号失败"}
# 关闭游戏失败、超时只记一行，不算本轮失败：收尾时 MAS 会关闭模拟器，重跑一整轮没有意义
M9A_NONFATAL_ENTRIES: dict[str, str] = {
    CLOSE_ENTRY: "MAS 收尾时会关闭游戏/模拟器，不影响本轮结果"
}
# 本次运行里完成过的任务重试时不再补跑（v4.11.3 全部非受管任务）：重跑已领完、已刷完的
# 只是白等几分钟。逐个写出而不是「除受管三项外全部」，M9A 以后新增的任务默认照旧补跑，
# 确认重跑无意义再加进来。受管三项每次尝试都要重做，不列。
M9A_SKIP_ON_RETRY: frozenset[str] = frozenset(
    {
        "Wilderness",
        "Awards",
        "Bank",
        "redeem_code",
        "Character",
        "Psychube",
        "switch_menu",
        "WarehouseInventory",
        "Limbo",
        "Lucidscape",
        "TheAlarm",
        "Colosseum",
        "UTTU",
        "SeriesOfDusks",
        "TheSyndromeOfSilence",
        "8bit",
        "CritterCrash",
        "MusesBoxStartParty",
        "PreStormProtocolStart",
        "CompleteInduction",
        "BalancedFarming",
        "Combat",
        "CombatActivity",
        "AutoPromotion",
        "SSReopen",
        "CharUpgrade",
    }
)
# 五个小游戏：M9A 资源里没有导航，要用户先手动停在对应页面才能跑，MAS 无人值守放进队列只会
# 出错。账号页不让选，运行时剔掉（优先于上面的声明，M9A_SKIP_ON_RETRY 里留着无妨）。
M9A_UNSELECTABLE_ENTRIES: dict[str, str] = dict.fromkeys(
    (
        "8bit",
        "CritterCrash",
        "MusesBoxStartParty",
        "PreStormProtocolStart",
        "CompleteInduction",
    ),
    "需手动进入对应页面（M9A 没有自动导航）",
)
# 自定义兑换码没填时不回落 default：它的 default 是字面量「占位」，旧版迁移专门把预填的它清成
# 空串（migration._clean_input_values）；交给 agent 的话，交不过去的码会中断整个兑换，后面
# 真正的兑换码也不交。其余 input 的 default 是能跑的真值，照常回落
M9A_NO_DEFAULT_FALLBACK_INPUTS: frozenset[tuple[str, str]] = frozenset(
    {("自定义兑换码", "兑换码")}
)

#: 建计划与预览共用的规则表（不可选、切号失败结束本轮、关闭游戏失败放过、兑换码不回落）。
M9A_PLAN_RULES = MaaFWPlanRules(
    unselectable=M9A_UNSELECTABLE_ENTRIES,
    abort_round=M9A_ABORT_ROUND_ENTRIES,
    nonfatal=M9A_NONFATAL_ENTRIES,
    no_default_fallback_inputs=M9A_NO_DEFAULT_FALLBACK_INPUTS,
)

_GITHUB_M9A_RE = re.compile(r"(^|[/:])MAA1999/M9A(\.git)?/?$", re.IGNORECASE)


def is_m9a_project(interface_model: MaaFWInterface | dict[str, Any]) -> bool:
    """三条判据任一命中：``mirrorchyan_rid == M9A``、``github`` 指向 MAA1999/M9A、``name == m9a``。"""

    if isinstance(interface_model, dict):
        rid = interface_model.get("mirrorchyan_rid")
        github = interface_model.get("github")
        name = interface_model.get("name")
    else:
        rid = getattr(interface_model, "mirrorchyan_rid", None)
        github = getattr(interface_model, "github", None)
        name = getattr(interface_model, "name", None)
    if str(rid or "").strip().casefold() == "m9a":
        return True
    if _GITHUB_M9A_RE.search(str(github or "").strip()):
        return True
    return str(name or "").strip().casefold() == "m9a"


__all__ = [
    "FALLBACK_TASK_NAMES",
    "LEGACY_ENTRY_ALIASES",
    "M9A_ABORT_ROUND_ENTRIES",
    "M9A_NONFATAL_ENTRIES",
    "M9A_NO_DEFAULT_FALLBACK_INPUTS",
    "M9A_PLAN_RULES",
    "M9A_SKIP_ON_RETRY",
    "M9A_UNSELECTABLE_ENTRIES",
    "TYPE_KEY",
    "is_m9a_project",
]
