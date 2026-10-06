#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

"""任务派发层：任务入口的持有者。

四层嵌套任务里的第一层，也是唯一**有身份**的一层 —— 它持有在跑任务的表，
对外提供建、停与启动队列。

一条在跑任务在本层的引用是一组 ``RunningTask``（任务信息实例 + L2 实例），
以任务 uid 为键。建好 ``TaskItem`` 后即把它交给
``app.task.script_expander.ScriptExpander`` 的构造，往下的逐层展开都不在这里
（见 :mod:`app.task`）。

任务信息不再进 ``Config`` —— 在跑任务表就是唯一事实源。运行态查询走
``/api/dispatch/get``（读本层的 ``running_items``），载荷即 ``TaskItem`` 本身。
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.models.task import TaskItem, TaskMode, TaskTriggerSource
from app.task import ExpandError, ScriptExpander, is_selected, queue_script_ids
from app.utils import get_logger

logger = get_logger("任务派发")


@dataclass(slots=True)
class RunningTask:
    """一条在跑任务在派发层的全部引用：状态实例 + 执行实例。

    两者一同取一同弃 —— 停任务要 L2 的句柄，查任务要 ``TaskItem`` 的载荷，
    分放两张表就会出现一张有、另一张没有的中间态。
    """

    info: TaskItem
    task: ScriptExpander


class _TaskDispatcher:
    """任务入口的持有者：创建、启停与启动队列。"""

    def __init__(self) -> None:
        self._running: dict[UUID, RunningTask] = {}
        self._startup_queue_started = False
        # 自然结束与 stop 取消都靠这条信号摘表；stop 只负责取消并等待收尾
        ScriptExpander.ended.connect(self.drop)

    async def start(
        self,
        *,
        mode: TaskMode,
        queue_id: str | None,
        script_id: str | None,
        user_id: str | None,
        trigger_source: TaskTriggerSource = TaskTriggerSource.MANUAL_TASK,
    ) -> UUID:
        """创建并启动一条任务，返回任务 uid。

        Raises:
            ExpandError: 调度参数组合非法（此时不建 ``TaskItem``、不入表）。
        """
        from app.core.ws import Publisher, protocol
        from app.core.ws.protocol import WSTaskCreatedData

        # ── ① 参数合法性：照 §5.4 真值表的报错行逐条判 ──
        # 只判"能不能跑"，不在这里展开 —— 展开是脚本展开层自己的活（见
        # ScriptExpander.expand_scripts）。先判后建，避免留下永远跑不起来的 TaskItem。
        has_q, has_s, has_u = (
            is_selected(queue_id),
            is_selected(script_id),
            is_selected(user_id),
        )
        if mode == TaskMode.SCRIPT_CONFIG:
            if not has_s:
                raise ExpandError("配置脚本任务必须指定脚本")
        elif not has_q and not has_s:
            raise ExpandError("自动代理/人工排查须指定队列或脚本")
        elif has_q and not has_s and has_u:
            raise ExpandError("有队列无脚本时不可指定用户")
        elif has_q and has_s and str(script_id) not in queue_script_ids(queue_id):
            # 队列内断点续跑的起点必须真在队列里，否则展开时才炸就已经建了任务
            raise ExpandError(f"队列中找不到脚本 {script_id}")

        # ── ② 建任务信息实例（独立 root，不挂 Config 集合）──
        # 任务是纯运行态，唯一持有者就是下面的 _running；作为自身的持久化根
        # activate，其嵌套 scripts/users 后续能正常 commit，类级 WS 订阅沿 parent
        # 上溯到它本身照常推送。
        uid = uuid4()
        item = TaskItem.build(
            uid=uid,
            payload={
                "info": {
                    "mode": mode,
                    "queue_id": queue_id,
                    "script_id": script_id,
                    "user_id": user_id,
                    "trigger_source": trigger_source,
                }
            },
        )
        await item.activate()

        # ── ③ 建 L2 实例（传入任务信息实例）→ 成组登记 → 启动 ──
        task = ScriptExpander(item)
        self._running[uid] = RunningTask(info=item, task=task)
        task.start()

        # ── ④ 推创建事件 ──
        # 只报创建参数本身（请求的 queue/script/user），不在这里展开脚本列表 ——
        # 本次跑哪些脚本是展开层的活，随后经 task.info.updated 的 TaskItem 载荷送达。
        await Publisher.send(
            id=protocol.ID_TASK_MANAGER,
            type=protocol.TASK_CREATED,
            data=WSTaskCreatedData(
                taskId=str(uid),
                mode=mode,
                queueId=queue_id,
                scriptId=script_id,
                userId=user_id,
            ),
        )
        return uid

    async def drop(self, sender: object) -> None:
        """顶层任务 ended 时从 ``_running`` 摘掉，并在队列收尾时接电源。"""
        if not isinstance(sender, ScriptExpander):
            return
        item = sender.item
        self._running.pop(item.uid, None)
        if item.info.status == "cancelled":
            return
        if item.info.mode != TaskMode.AUTO_PROXY:
            return
        queue_id = item.info.queue_id
        if not is_selected(queue_id):
            return
        for running in self._running.values():
            if str(running.info.info.queue_id) == str(queue_id):
                return
        from app.core import Config
        from app.services import System

        if Config.power_sign != "NoAction":
            return
        try:
            queue = Config.queues.get(UUID(str(queue_id)))
        except (ValueError, TypeError):
            return
        if queue is None:
            return
        action = queue.info.after_accomplish
        if action == "NoAction":
            return
        try:
            Config.power_sign = action
            await System.start_power_task()
        except Exception:
            logger.exception(f"队列 {queue_id} after_accomplish 执行失败")

    async def stop(self, task_id: UUID | str) -> None:
        """停止指定任务；``"ALL"`` 表示停止全部在跑任务。

        只取消并等待收尾；从表里摘掉走 ``ended`` → ``drop``，自然结束同一条路。
        """
        if task_id == "ALL":
            for running in list(self._running.values()):
                await running.task.stop()
            return
        uid = task_id if isinstance(task_id, UUID) else UUID(task_id)
        running = self._running.get(uid)
        if running is not None:
            await running.task.stop()

    # ── 运行态查询：派发层是任务信息的唯一事实源，API 只读这里 ──

    def get_task(self, uid: UUID) -> TaskItem | None:
        """取单条在跑任务的 ``TaskItem``；不存在返回 ``None``。"""
        running = self._running.get(uid)
        return running.info if running is not None else None

    def running_items(self) -> Iterator[tuple[UUID, TaskItem]]:
        """遍历全部在跑任务的 ``(uid, TaskItem)``（登记顺序）。"""
        for uid, running in self._running.items():
            yield uid, running.info

    async def start_startup_queue(self) -> None:
        """主连接就绪后拉起所有勾选了"启动时运行"的队列（整个进程仅一次）。"""
        from app.core import Config
        from app.core.ws import MainConnection

        if self._startup_queue_started:
            logger.info("启动队列已执行过，跳过本次触发")
            return

        # 循环等待主连接就绪：连接可能建立又断开，等到真正在线再往下
        while not MainConnection.is_connected:
            await asyncio.sleep(1)

        self._startup_queue_started = True

        # 给前端留出订阅时间，避免任务事件发在页面就绪之前
        await asyncio.sleep(10)

        logger.info("开始执行启动队列")
        for uid, queue in Config.queues.items():
            if not queue.info.start_up_enabled:
                continue
            logger.info(f"启动时运行队列：{uid}")
            try:
                await self.start(
                    mode=TaskMode.AUTO_PROXY,
                    queue_id=str(uid),
                    script_id=None,
                    user_id=None,
                    trigger_source=TaskTriggerSource.STARTUP_TASK,
                )
            except Exception as error:
                logger.error(f"队列 {uid} 无法创建任务：{error}")

        logger.success("启动队列执行完成")


TaskDispatcher = _TaskDispatcher()

__all__ = ["RunningTask", "TaskDispatcher"]
