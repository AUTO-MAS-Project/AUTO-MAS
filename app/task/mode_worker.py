#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""模式执行层：单用户的 ``AutoProxy`` / ``ManualReview`` / ``ScriptConfig``（设计 §2.4）。

四层任务的最内层。构造只收热态 ``user_entry``，``current.index`` 在 ``__init__``
快照。``plugin.run`` 约定只写该用户。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from app.models.task import HistoryRecordData, TaskMode
from app.task.base import TaskBase
from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.config import ScriptEntry, UserEntry
    from app.models.task import TaskScriptItem

logger = get_logger("模式执行")

__all__ = [
    "MODE_WORKERS",
    "AutoProxyWorker",
    "ManualReviewWorker",
    "ModeWorker",
    "ScriptConfigWorker",
]


class ModeWorker(TaskBase):
    """单用户模式执行基类（AutoProxy / ManualReview / ScriptConfig）。

    ``mode`` 由子类定，不走构造参数 —— 类与模式一一对应，两处都能传就会不一致。
    """

    mode: ClassVar[TaskMode]

    def __init__(
        self,
        *,
        user_entry: UserEntry,
        script_item: TaskScriptItem,
        script_entry: ScriptEntry | None = None,
    ) -> None:
        super().__init__()
        self.user_entry = user_entry
        self.script_item = script_item
        self.script_entry = script_entry
        self.user_uid: UUID = user_entry.uid
        # 构造时快照：运行期 progress 仍写 script_item.current，本层不回头查 expander
        self.current_index: UUID | None = script_item.current.index
        self._check_result = "Pass"

    async def check(self) -> str:
        """返回 ``Pass`` 或用户可读错误串。"""
        return "Pass"

    async def prepare(self) -> None:
        """专项资源准备；插件覆盖。"""

    async def on_crash(self, exc: BaseException) -> None:
        try:
            logger.exception(f"模式执行崩溃（{self.mode}）：{exc}")
        except Exception:
            pass

    async def init_daily_proxy(self) -> None:
        """初始化每日代理状态；插件可覆盖。"""

    async def main_logic(self) -> None:
        """插件主逻辑钩子。"""

    async def main_task(self) -> None:
        await self.init_daily_proxy()
        self._check_result = await self.check()
        if self._check_result != "Pass":
            return
        await self.prepare()
        await self.init_daily_proxy()
        await self.main_logic()

    async def final_task(self) -> None:
        if self._check_result != "Pass":
            if self.user_uid in self.script_item.users:
                u = self.script_item.users[self.user_uid]
                u.info.status = f"check_fail:{self._check_result}"
                await u.commit()
            return
        await self.save_result()

    async def build_history_data(
        self, script_item: TaskScriptItem
    ) -> dict[UUID, HistoryRecordData]:
        """任务中止后按脚本级任务信息树判定各运行日志的最终状态与统计。

        键为 ``log_record`` uid。默认按当前用户是否「完成」兜底判定，
        ``data`` 为空；需要统计的专项覆盖本方法。
        """

        return self._default_history(script_item)

    def _default_history(
        self, script_item: TaskScriptItem
    ) -> dict[UUID, HistoryRecordData]:
        """默认定态：用户「完成」→ success，否则 error；message 取记录状态字。"""

        if self.user_uid not in script_item.users:
            return {}
        user_item = script_item.users[self.user_uid]
        ok = user_item.info.status == "完成"
        return {
            uid: HistoryRecordData(
                status="success" if ok else "error",
                message=rec.info.status or "",
                data={},
            )
            for uid, rec in user_item.log_record.items()
        }

    async def save_result(self) -> None:
        """落历史 + 回写用户上次结果。统计与终态由 ``build_history_data`` 判定。"""
        from app.core.history import history_store

        if self.user_uid not in self.script_item.users:
            return
        user_item = self.script_item.users[self.user_uid]
        username = self.user_entry.info.name or user_item.info.name or str(self.user_uid)
        type_key = (
            type(self.script_entry).__name__
            if self.script_entry is not None
            else "Unknown"
        )

        default = self._default_history(self.script_item)
        try:
            book: dict[UUID, Any] = await self.build_history_data(self.script_item)
        except Exception:
            logger.exception("build_history_data 失败，改用默认定态")
            book = default

        for uid, rec in user_item.log_record.items():
            judged = book.get(uid)
            if not isinstance(judged, HistoryRecordData):
                if judged is not None:
                    logger.warning(f"历史判定缺项或类型错误，改用默认: {uid}")
                judged = default.get(uid) or HistoryRecordData(
                    status="error",
                    message=rec.info.status or "",
                    data={},
                )
            history_store.save(
                time=rec.info.start_time,
                username=username,
                type_key=type_key,
                status=judged.status,
                message=judged.message,
                logs="\n".join(rec.info.content),
                data=judged.data or None,
            )

        self.user_entry.info.last_result = user_item.info.status or "done"
        user_item.info.status = user_item.info.status or "done"
        await user_item.commit()


class AutoProxyWorker(ModeWorker):
    """自动代理：按用户配置跑一轮代理。"""

    mode: ClassVar[TaskMode] = TaskMode.AUTO_PROXY


class ManualReviewWorker(ModeWorker):
    """人工排查：跑一轮供用户确认结果。"""

    mode: ClassVar[TaskMode] = TaskMode.MANUAL_REVIEW


class ScriptConfigWorker(ModeWorker):
    """脚本设置：打开脚本自身的配置界面，不跑代理。"""

    mode: ClassVar[TaskMode] = TaskMode.SCRIPT_CONFIG


MODE_WORKERS: dict[TaskMode, type[ModeWorker]] = {
    TaskMode.AUTO_PROXY: AutoProxyWorker,
    TaskMode.MANUAL_REVIEW: ManualReviewWorker,
    TaskMode.SCRIPT_CONFIG: ScriptConfigWorker,
}
