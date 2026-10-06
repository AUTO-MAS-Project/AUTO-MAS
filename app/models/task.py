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

"""任务运行态：配置树与查询字段定义。

配置树（``TaskItem`` / ``TaskScriptItem`` / ``TaskUserItem`` / ``LogRecordEntry``）
是任务状态的**唯一事实源**；字段变更经本模块类级 ``connect`` 推前端。

怎么跑归 ``app.task``（四层嵌套任务与执行契约），本模块只管状态长什么样 ——
两边分开，故任务类换实现不动持久化结构。

本模块**不得在模块级 import ``app.core``**：``app.core.task_dispatcher`` 在模块级
import 它（``TaskItem`` 是在跑任务的载荷），反向再引就成环。故推送回调内再懒加载
``Publisher``。
运行态与 HTTP/WS 返回值共用 ``TaskItem`` 自身（``model_dump``），不再另造快照 DTO。

``info.result`` 对齐非插件版分层摘要：用户看 ``log_record``，脚本汇总用户，
任务再汇总脚本。``current.log`` 不是落盘字段 —— 经 ``current`` 指针逐级落到
当前用户最新一条 ``log_record`` 的正文；任务侧只写用户日志，不往各级抄一份。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.config import ConfigCollection, ConfigEntry, ConfigGroup, Virtual
from app.config.shortcuts import collection, virtual_field
from app.config.signals import FieldChangeEvent
from app.utils.constants import UTC8


class TaskMode(str, Enum):
    """任务执行模式（配置树 / API / WS 共用同一枚举值）。"""

    AUTO_PROXY = "AutoProxy"
    MANUAL_REVIEW = "ManualReview"
    SCRIPT_CONFIG = "ScriptConfig"


class TaskTriggerSource(str, Enum):
    """任务触发来源（入口点写入，不进 HTTP 契约）。"""

    MANUAL_TASK = "manual_task"
    SCHEDULED_TASK = "scheduled_task"
    STARTUP_TASK = "startup_task"


class HistoryRecordData(BaseModel):
    """单条运行日志的历史落盘数据（由模式执行器在任务中止后判定）。"""

    status: Literal["success", "error"] = Field(description="最终状态")
    message: str = Field(default="", description="结果说明，异常时为报错原因")
    data: dict[str, Any] = Field(default_factory=dict, description="统计数据")


class LogRecordEntry(ConfigEntry):
    """单条日志监看记录（真实日志正文只落在这里）。"""

    class Info(ConfigGroup):
        start_time: datetime = Field(
            default_factory=lambda: datetime(2000, 1, 1, 0, 0, tzinfo=UTC8),
            description="任务起始时间",
        )
        content: list[str] = Field(default_factory=list, description="日志内容")
        status: str = Field(default="未开始监看日志", description="最终状态")

    info: Info = Field(default_factory=Info, description="日志记录")


class TaskUserItem(ConfigEntry):
    """任务内用户项。"""

    class Info(ConfigGroup):
        name: str = Field(default="", description="用户名")
        status: str = Field(default="", description="执行状态")
        result: Virtual[str] = None

    info: Info = Field(default_factory=Info, description="用户任务信息")
    log_record: ConfigCollection[LogRecordEntry] = collection(LogRecordEntry)

    @virtual_field("info.result")
    def compute_result(self) -> str:
        # 对齐非插件版 UserItem.result：按监看记录起止时间拼简要结果
        if not self.log_record:
            return "未开始运行"
        return " | ".join(
            f"{rec.info.start_time.strftime('%H:%M')} - {rec.info.status}"
            for rec in sorted(
                self.log_record.values(), key=lambda item: item.info.start_time
            )
        )


class TaskScriptItem(ConfigEntry):
    """任务内脚本项。"""

    class Info(ConfigGroup):
        name: str = Field(default="", description="脚本名")
        status: str = Field(default="", description="执行状态")
        result: Virtual[str] = None

    class Current(ConfigGroup):
        index: UUID | None = Field(default=None, description="当前用户；None=未开始")
        log: Virtual[str] = None

    info: Info = Field(default_factory=Info, description="脚本任务信息")
    current: Current = Field(default_factory=Current, description="当前进度")
    users: ConfigCollection[TaskUserItem] = collection(TaskUserItem)

    @virtual_field("info.result")
    def compute_result(self) -> str:
        if not self.users:
            return "用户未加载"
        return "\n".join(
            f"{user.info.name or uid}: {user.info.result}"
            for uid, user in self.users.items()
        )

    @virtual_field("current.log")
    def compute_log(self) -> str:
        uid = self.current.index
        if uid is None or uid not in self.users:
            return ""
        records = self.users[uid].log_record
        if not records:
            return ""
        latest = max(records.values(), key=lambda item: item.info.start_time)
        return "".join(latest.info.content)


class TaskItem(ConfigEntry):
    """一条调度任务（uid = 任务 uid）。

    同时是运行态事实源与 HTTP/WS 任务信息载荷（``/get``、``task.info.updated``、
    ``task.completed.task``）。
    """

    class Info(ConfigGroup):
        mode: TaskMode = Field(default=TaskMode.AUTO_PROXY, description="任务模式")
        queue_id: str | None = Field(default=None, description="请求队列 uid")
        script_id: str | None = Field(default=None, description="请求脚本 uid")
        user_id: str | None = Field(default=None, description="请求用户 uid")
        trigger_source: TaskTriggerSource = Field(
            default=TaskTriggerSource.MANUAL_TASK, description="触发来源"
        )
        # 全流程状态唯一真相源（进行中 / 终态都写这里）；报错细节进 result
        status: str = Field(default="pending", description="任务状态")
        result: Virtual[str] = None

    class Current(ConfigGroup):
        index: UUID | None = Field(default=None, description="当前脚本；None=未开始")
        log: Virtual[str] = None

    info: Info = Field(default_factory=Info, description="任务参数")
    current: Current = Field(default_factory=Current, description="当前进度")
    scripts: ConfigCollection[TaskScriptItem] = collection(TaskScriptItem)

    @virtual_field("info.result")
    def compute_result(self) -> str:
        if not self.scripts:
            return "任务未加载"
        blocks: list[str] = []
        for uid, script in self.scripts.items():
            users = list(script.users.values())
            done = sum(1 for user in users if user.info.status == "完成")
            pending = sum(1 for user in users if user.info.status != "完成")
            name = script.info.name or str(uid)
            body = (script.info.result or "").replace("\n", "\n    ")
            blocks.append(
                f"{name}：\n\n"
                f"    已完成用户数：{done}；未完成用户数：{pending}\n\n"
                f"    {body}"
            )
        return "\n\n\n".join(blocks)

    @virtual_field("current.log")
    def compute_log(self) -> str:
        # 当前脚本的 current.log（其本身再落到用户 log_record）
        if self.current.index is None or self.current.index not in self.scripts:
            return ""
        return self.scripts[self.current.index].current.log or ""


# ── 类级订阅：模块 import 即生效，无需启动后手动 bind（设计 §5.2）──


@TaskItem.connect(phase="runtime")
@TaskScriptItem.connect(phase="runtime")
@TaskUserItem.connect(phase="runtime")
@LogRecordEntry.connect(phase="runtime")
async def _publish_task_ws(sender: object, event: FieldChangeEvent) -> None:
    """运行态树任一节点字段变更 → 推 TaskItem 载荷与当前日志。"""
    from app.core.ws import Publisher, protocol
    from app.core.ws.protocol import WSTaskLogUpdatedData

    # 沿 parent 上溯到 TaskItem
    node: object | None = sender
    task: TaskItem | None = None
    while node is not None:
        if isinstance(node, TaskItem):
            task = node
            break
        node = getattr(node, "parent", None)
    if task is None:
        return

    # task.info.updated 的 data 段即 TaskItem API dump（与 /get 同形）
    payload = task.model_dump(mode="json")
    # current.log 已是 Virtual：经脚本 → 用户 log_record 转接
    log = task.current.log or ""
    if len(log) > 200_000:
        log = log[-200_000:]
        # dump 里同步截断，避免单条 WS 爆内存；完整正文仍在用户 log_record
        current = payload.get("current")
        if isinstance(current, dict):
            current["log"] = log
        sid = task.current.index
        scripts = payload.get("scripts")
        if sid is not None and isinstance(scripts, dict) and str(sid) in scripts:
            script_current = scripts[str(sid)].get("current")
            if isinstance(script_current, dict):
                script_current["log"] = log

    await Publisher.send(
        id=str(task.uid),
        type=protocol.TASK_INFO_UPDATED,
        data=payload,
    )
    if log:
        await Publisher.send(
            id=str(task.uid),
            type=protocol.TASK_LOG_UPDATED,
            data=WSTaskLogUpdatedData(log=log),
        )
