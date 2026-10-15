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

"""新用户的空任务队列写成实打实的默认队列。

``Task.TaskSnapshot`` 的默认值是空的 ``{ }``：用户页显示空队列，运行时却按
``run_plan.resolve_default_snapshot`` 回落到预设（选了的那个，否则第一个）或各任务的
default_check，界面和实际运行对不上。这里用同一个函数把它算出来写回快照，之后用户页上
看到的就是要跑的；规则不变，所有人实际跑的东西也不变。代价是默认队列定格在写回那一刻，
项目以后改了第一个预设不再自动跟。

建用户时脚本可能还没导入项目，所以三处都调：建用户（``Config.add_user``）、读用户
（``Config.get_user``，用户页走它）、运行前检查（``embedded_manager._check``，上锁建副本
之前）。只认真正为空的快照，判据与 ``runner_task`` 建计划的 ``task_snapshot or None`` 相同；
项目还没导入、interface 读不出来、选的预设已经不在时什么都不写，留给下一次。脚本运行中
（配置已锁）不写。写入走 ``Config.update_user``，与用户页保存同一条路（特调整理、全局选项
降级双写、密码加密）。存的形状与用户页保存的一致：只列勾选的任务。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.core import Config
from app.task.MaaFW.tools.core.interface.loader import load_interface_model_cached
from app.task.MaaFW.tools.core.runner.run_plan import (
    MaaFWRunPlanError,
    resolve_default_snapshot,
)
from app.utils import get_logger

from .embedded_project import copy_is_healthy, resolve_maafw_project_root

logger = get_logger("MaaFW 默认任务队列")


def is_empty_task_snapshot(raw: Any) -> bool:
    """解析不出非空对象就是空（``{ }``、空串、坏 JSON），与 ``runner_task`` 建计划的判据一致。"""

    if isinstance(raw, dict):
        return not raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return True
        return not (isinstance(data, dict) and data)
    return True


def _build_default_snapshots(
    script_id: str,
    script_config: Any,
    targets: list[tuple[str, str, str | None]],
) -> dict[str, tuple[str, str]]:
    """``targets`` 是 ``(用户 id, 用户名, 选的预设)``；返回 ``{用户 id: (要写进的快照 JSON,
    给日志的来源说明)}``。"""

    root = Path(resolve_maafw_project_root(script_id, script_config))
    if not copy_is_healthy(root):
        return {}
    try:
        interface = load_interface_model_cached(root)
    except Exception as exc:  # noqa: BLE001 - 读不出 interface 就留到下一次
        logger.debug(f"读取 interface 失败，空任务队列留到下次再补：{exc}")
        return {}

    snapshots: dict[str, tuple[str, str]] = {}
    for user_id, user_name, selected_preset in targets:
        try:
            snapshot = resolve_default_snapshot(
                interface, selected_preset=selected_preset
            )
        except MaaFWRunPlanError as exc:
            # 运行时同样会报这一句，这里不替用户换预设
            logger.warning(f"MFW 用户 {user_name} 的任务队列为空，没有写入：{exc}")
            continue
        queued = [
            task_id
            for task_id in snapshot.taskOrder
            if snapshot.taskChecked.get(task_id, False)
        ]
        text = json.dumps(
            {
                "taskOrder": queued,
                "taskChecked": dict.fromkeys(queued, True),
                "taskOptions": {
                    task_id: snapshot.taskOptions[task_id]
                    for task_id in queued
                    if task_id in snapshot.taskOptions
                },
                "globalOptions": snapshot.globalOptions,
            },
            ensure_ascii=False,
        )
        # 与 resolve_default_snapshot 的取法同一顺序，只用来写日志
        if selected_preset:
            origin = f"所选预设「{selected_preset}」"
        elif interface.preset:
            origin = f"项目第一个预设「{interface.preset[0].name}」"
        else:
            origin = "项目默认勾选的任务"
        snapshots[user_id] = (text, origin)
    return snapshots


def _queued_count(raw: Any) -> int:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return len(data.get("taskOrder") or [])
    except (TypeError, ValueError, AttributeError):
        return 0


async def fill_default_task_snapshots(
    script_id: str,
    script_config: Any,
    user_ids: Iterable[str] | None = None,
) -> None:
    """把脚本下（``user_ids`` 给了就只看这几位）任务队列为空的用户写成默认队列。从不抛出。"""

    try:
        if script_config.is_locked:
            return
        wanted = None if user_ids is None else {str(item) for item in user_ids}
        users = {
            str(uid): user
            for uid, user in script_config.UserData.items()
            if (wanted is None or str(uid) in wanted)
            and is_empty_task_snapshot(user.get("Task", "TaskSnapshot"))
        }
        if not users:
            return
        targets = [
            (
                user_id,
                str(user.get("Info", "Name") or user_id),
                str(user.get("Task", "SelectedPreset") or "").strip() or None,
            )
            for user_id, user in users.items()
        ]
        snapshots = await asyncio.to_thread(
            _build_default_snapshots, script_id, script_config, targets
        )
    except Exception as exc:  # noqa: BLE001 - 补不上不该挡住读写用户与运行
        logger.opt(exception=True).warning(f"生成 MFW 默认任务队列失败：{exc}")
        return

    for user_id, _, selected_preset in targets:
        if user_id not in snapshots:
            continue
        text, origin = snapshots[user_id]
        user = users[user_id]

        def unchanged(
            user: Any = user, selected_preset: str | None = selected_preset
        ) -> bool:
            # 算的这段时间里、以及 update_user 写入前的预处理期间，用户页存过队列、换过预设，
            # 或脚本开始运行了：不覆盖、不硬写
            return (
                not script_config.is_locked
                and is_empty_task_snapshot(user.get("Task", "TaskSnapshot"))
                and (str(user.get("Task", "SelectedPreset") or "").strip() or None)
                == selected_preset
            )

        try:
            if not unchanged():
                continue
            if not await Config.update_user(
                script_id,
                user_id,
                {"Task": {"TaskSnapshot": text}},
                precondition=unchanged,
            ):
                continue
            # 任务数按落盘的算：特调写入前会整理（M9A 的启动 / 关闭游戏不进队列）
            logger.info(
                f"MFW 用户 {user.get('Info', 'Name') or user_id} 的任务队列为空，"
                f"按{origin}写入默认队列"
                f"（{_queued_count(user.get('Task', 'TaskSnapshot'))} 个任务）"
            )
        except Exception as exc:  # noqa: BLE001 - 这一位写不进去不影响其他人
            logger.opt(exception=True).warning(
                f"写入 MFW 用户 {user_id} 的默认任务队列失败：{exc}"
            )
