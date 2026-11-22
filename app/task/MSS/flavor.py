#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MSS（MaaStellaSora / 星塔旅人）特调：队列装饰与重试任务声明。

以下差异均通过 MaaFW 的既有钩子声明，执行与重试流程仍由通用引擎负责：

1. 活动：队列里有「活动快速战斗」（entry ``活动快速战斗_入口``）时查一次活动排期
   （``app/tools/common/game_calendar/stella.py``，只认会开活动关的「版本活动」）。有进行中的活动
   就把它挪到悬赏试炼前面先打；确实没有活动就把它摘掉；取不到数据时按队列原样跑——
   真在活动期却摘掉，整轮就漏打了活动。
2. 日常：用户选了 MSS 计划表（``Info.PlanMode`` 不是 ``Fixed``）时，按当天槽位改写
   「悬赏试炼快速战斗」（entry ``战斗_入口``）的关卡、是否跳过难度选择与难度、是否消耗
   所有干劲与作战次数；队列里没有这个任务就补上。``Fixed`` 时一个选项都不动。
3. 周常：「新版爬塔」（entry ``星塔_入口_agent``）挪到队尾——爬塔不消耗干劲，上游爬塔
   偶发卡住，放最后不拖累前面的任务。每周只跑一次用 MaaFW 通用的「每周仅一次」。
4. 已确认的日常与挑战任务在本次运行中成功过后，重试不再补跑；登录仍每次执行。
   仅使用引擎收集的 ``completedTasks``，不额外解析上游日志或判断游戏状态。

按 entry 找任务、按 interface 里真实的选项名与 case 名写值（取自 MaaStellaSora v1.4.4 的
``resource/tasks/{activity,fight,climb_tower}.json``）；找不到就写一行账号日志跳过那一项。

这里只是 MFW 风味路径上的一层外壳：规则常量与项目判据在 ``rules.py``，排队列在 ``arrange.py``
（活动探测前后两段）；本模块从配置里取出计划表与活动优先后转调它们，活动探测仍在建计划的工作线程里做。
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from app.task.MaaFW.tools.core.interface.models import (
    MaaFWInterface,
    task_name_for_entry,
)
from app.task.MaaFW.tools.embedded.flavor_support import (
    MaaFWSelectionContext,
    config_value,
)
from app.task.MSS.arrange import mss_arrange_head, mss_arrange_tail
from app.task.MSS.rules import (
    ACTIVITY_ENTRY,
    CLIMB_ENTRY,
    MSS_SKIP_ON_RETRY,
    PLAN_MODE_FIXED,
    TRIBULATION_ENTRY,
    TYPE_KEY,
    github_repo_name,
    is_mss_project,
)


def activity_running() -> bool | None:
    """当前有没有进行中的版本活动：有 True、确实没有 False、取不到数据 None。

    钩子在建运行计划的工作线程里被调，那里没有事件循环，自己起一个跑完就收；
    万一在事件循环线程里被调，拿不到结果，按「说不准」处理。
    """

    from app.tools.common.game_calendar import stella as _tool_stella_official

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_tool_stella_official.has_running_official_activity())
    return None


class MSSFlavor:
    """满足 ``MaaFWFlavor`` 协议的 MSS 特调对象。

    重试不补跑的声明就是 ``rules.MSS_SKIP_ON_RETRY``（说明写在那里）；队列装饰 = ``arrange`` 的前半段
    → 按需查一次活动排期 → 后半段。
    """

    type_key = TYPE_KEY
    skip_on_retry_entries = MSS_SKIP_ON_RETRY

    def __init__(
        self,
        *,
        activity_probe: Callable[[], bool | None] = activity_running,
    ) -> None:
        self._activity_probe = activity_probe

    def matches_project(self, interface_model: MaaFWInterface) -> bool:
        return is_mss_project(interface_model)

    def decorate_selection(
        self,
        interface_model: MaaFWInterface,
        task_ids: list[str],
        task_options: dict[str, Any],
        *,
        context: MaaFWSelectionContext,
    ) -> tuple[list[str], dict[str, Any]]:
        # MSS 的装饰只看账号配置与活动排期
        log = context.log
        user_config = context.user_config
        plan_key = _current_plan_key(user_config, log)
        state = mss_arrange_head(
            interface_model,
            task_ids,
            task_options,
            excluded_ids=context.excluded_task_ids,
            plan_key=plan_key,
            if_activity_first=config_value(user_config, "Info", "IfActivityFirst"),
            log=log,
        )
        # 活动排期只在前半段说要查时查，最多一次
        running = self._activity_probe() if state.probe_needed else None
        return mss_arrange_tail(
            state, running, interface_model=interface_model, log=log
        )


def _current_plan_key(
    user_config: Any, log: Callable[[str], None]
) -> dict[str, Any] | None:
    """用户引用的 MSS 计划表今天那一格；``Fixed`` 或取不到时返回 None（不改悬赏试炼）。"""

    mode = str(config_value(user_config, "Info", "PlanMode") or PLAN_MODE_FIXED)
    if mode == PLAN_MODE_FIXED:
        return None
    try:
        plan = type(user_config).related_config["PlanConfig"][uuid.UUID(mode)]
        key = plan.get_current_key()
    except Exception as exc:  # noqa: BLE001 - 计划表被删或类型不对：按固定处理
        log(f"[MSS] 引用的计划表不可用，本轮不改悬赏试炼：{exc}")
        return None
    if not isinstance(key, dict) or not str(key.get("TribulationStage") or ""):
        return None
    return key


FLAVOR = MSSFlavor()

__all__ = [
    "ACTIVITY_ENTRY",
    "CLIMB_ENTRY",
    "FLAVOR",
    "MSSFlavor",
    "TRIBULATION_ENTRY",
    "TYPE_KEY",
    "activity_running",
    "github_repo_name",
    "is_mss_project",
    "task_name_for_entry",
]
