#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""常规专项的账号选择、运行检查、跳过处理与报告汇总。"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.ConfigBase import ConfigBase
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, TaskItem, UserItem
from app.task.maintenance import (
    get_maintenance_message,
    get_user_maintenance,
)
from app.task.notify_core import push_maintenance_notice
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH
from app.utils.game_apk import GameUpdateResult

logger = get_logger("脚本调度")


@dataclass(frozen=True)
class UserRunSummary:
    """MAS 已有用户状态的分组；不替专项判断脚本任务成败。"""

    completed: tuple[UserItem, ...]
    failed: tuple[UserItem, ...]
    waiting: tuple[UserItem, ...]
    skipped: tuple[UserItem, ...]
    other: tuple[UserItem, ...]

    @property
    def uncompleted_count(self) -> int:
        return len(self.failed) + len(self.waiting)


class ScriptManagerBase(TaskExecuteBase):
    # 分组只消费专项已经给出的状态；成功口径可由专项声明。
    completed_user_statuses = frozenset({"完成"})

    script_info: ScriptItem
    task_info: TaskItem

    def __init__(self) -> None:
        super().__init__()
        self.maintenance_only = False
        self.begin_time = ""
        self._executed_user_ids: set[str] = set()

    def is_user_selected(self, user_id: uuid.UUID | str, user: ConfigBase) -> bool:
        return (
            bool(user.get("Info", "Status"))
            and user.get("Info", "RemainedDay") != 0
            and self.task_info.is_target_user(str(user_id))
        )

    def selected_user_configs(
        self, items: Iterable[tuple[uuid.UUID, ConfigBase]] | None = None
    ) -> list[tuple[uuid.UUID, ConfigBase]]:
        if items is None:
            script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
            items = script_config.UserData.items()
        return [(uid, user) for uid, user in items if self.is_user_selected(uid, user)]

    def build_proxy_user_list(
        self, items: Iterable[tuple[uuid.UUID, ConfigBase]] | None = None
    ) -> list[UserItem]:
        """只生成运行列表；用于写回的配置副本始终保留全部账号。"""
        return [
            UserItem(str(uid), user.get("Info", "Name"), "等待")
            for uid, user in self.selected_user_configs(items)
        ]

    def collect_user_results(self) -> UserRunSummary:
        groups: dict[str, list[UserItem]] = {
            status: [] for status in ("完成", "异常", "等待", "跳过")
        }
        other: list[UserItem] = []
        for user in self.script_info.user_list:
            status = (
                "完成" if user.status in self.completed_user_statuses else user.status
            )
            groups.get(status, other).append(user)
        return UserRunSummary(
            completed=tuple(groups["完成"]),
            failed=tuple(groups["异常"]),
            waiting=tuple(groups["等待"]),
            skipped=tuple(groups["跳过"]),
            other=tuple(other),
        )

    @property
    def all_users_maintenance_skipped(self) -> bool:
        users = self.script_info.user_list
        return bool(users) and all(user.maintenance_skipped for user in users)

    @property
    def has_proxy_run(self) -> bool:
        return bool(self._executed_user_ids)

    def record_user_run_start(self, user: UserItem) -> None:
        self._executed_user_ids.add(user.user_id)

    async def run_user_task(self, user: UserItem, task: TaskExecuteBase) -> None:
        if self.task_info.mode == "AutoProxy":
            self.record_user_run_start(user)
        await self.spawn(task)

    def build_proxy_report(
        self,
        *,
        result_text: str | None = None,
    ) -> dict:
        """按专项的用户状态口径组织已有报告字段。"""
        summary = self.collect_user_results()
        mode = TASK_MODE_ZH.get(self.task_info.mode, self.task_info.mode)
        return {
            "title": f"{mode}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(summary.completed),
            "uncompleted_count": summary.uncompleted_count,
            "result": self.script_info.result if result_text is None else result_text,
        }

    async def _record_user_result(
        self, user: UserItem, *, status: Literal["跳过", "异常"], reason: str
    ) -> None:
        user.status = status
        user.log_record[datetime.now()] = LogRecord(status=reason, content=[reason])
        line = f"{self.script_info.name} - {user.name}: {reason}"
        self.script_info.log = (
            f"{self.script_info.log}\n{line}" if self.script_info.log else line
        )
        logger.info(line)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error" if status == "异常" else "info", message=line
            ),
        )

    async def skip_user(
        self, user: UserItem, reason: str, *, maintenance: bool = False
    ) -> None:
        user.maintenance_skipped = maintenance
        await self._record_user_result(user, status="跳过", reason=reason)

    async def notify_user_check_failure(self, user: UserItem, reason: str) -> None:
        # 专项的 check() 已经标记为跳过时保留该状态，不能改成代理失败。
        if user.status == "等待":
            user.status = "异常"
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=reason),
        )

    async def update_game_before_run(self) -> None:
        """专项按现有配置更新游戏；脚本本体更新继续由各专项自己的流程处理。"""

    async def skip_maintenance_user(
        self, user: UserItem, user_config: ConfigBase
    ) -> bool:
        window = await get_user_maintenance(user_config, proxy=Config.proxy)
        if window is None:
            return False
        await self.skip_user(user, window.reason, maintenance=True)
        return True

    async def check_user_before_run(
        self,
        user: UserItem,
        user_config: ConfigBase,
        *,
        game_update_result: GameUpdateResult | None = None,
    ) -> bool:
        if self.task_info.mode != "AutoProxy":
            return True
        if await self.skip_maintenance_user(user, user_config):
            return False
        if (
            game_update_result is not None
            and game_update_result.status == "NeedManualUpdate"
        ):
            await self._record_user_result(
                user, status="异常", reason=game_update_result.message
            )
            return False
        return True

    async def notify_maintenance(self) -> None:
        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        try:
            await push_maintenance_notice(
                message=get_maintenance_message(script_config), task_info=self.task_info
            )
        except Exception as exc:
            logger.opt(exception=True).warning(f"推送维护通知失败: {exc}")

    async def _run_main_task(self) -> None:
        if self.task_info.mode == "AutoProxy":
            await self.update_game_before_run()
            selected = self.selected_user_configs()
            windows = [
                await get_user_maintenance(user, proxy=Config.proxy)
                for _, user in selected
            ]
            if selected and all(window is not None for window in windows):
                self.script_info.user_list = self.build_proxy_user_list(selected)
                for user, window in zip(self.script_info.user_list, windows):
                    if window is not None:
                        await self.skip_user(user, window.reason, maintenance=True)
                self.maintenance_only = True
                self.script_info.status = "跳过"
                await self.notify_maintenance()
                return
        await super()._run_main_task()
