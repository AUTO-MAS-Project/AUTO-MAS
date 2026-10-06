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

"""脚本展开层：``ScriptExpander``（设计 §5.3 / §5.4）。

四层任务的第二层：``TaskDispatcher`` 建好 ``TaskItem`` 交到这里，本层按 §5.4 真值表
把任务展开成脚本列表、逐脚本加 X（非递归）并订游戏、按 decl 目录取 ``UserExpander``
spawn，最后推完成事件。

组合合法性由派发层 ``TaskDispatcher.start`` 一处判定（§5.4 报错行），本层不再
重复校验 —— 拿到的任务参数已保证能跑。本层只按同一张表**产出**脚本列表（含
队列内断点续跑的切片），展开逻辑内联在 ``main_task`` 里。

脚本锁 / 游戏订阅挂在本实例上；循环内每脚本收尾一次，取消时由 ``TaskBase``
保证的 ``final_task`` 再幂等兜底（与 L3 ``UserExpander`` 同形）。

全流程状态只写 ``TaskItem.info.status``；报错细节进 ``info.result``，不另存 error。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from app.config.core.node import LockTicket
from app.models.task import TaskItem, TaskMode, TaskScriptItem
from app.task.base import TaskBase
from app.task.context import TaskContext
from app.task.params import is_selected, queue_script_ids
from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.config.script import ScriptEntry
    from app.plugin.base.game import DeviceHandle, GameControl

logger = get_logger("脚本展开")

__all__ = ["ScriptExpander"]


class ScriptExpander(TaskBase):
    """建脚本列表 → 逐脚本加锁/订游戏 → spawn UserExpander。"""

    def __init__(self, item: TaskItem) -> None:
        super().__init__()
        self.item = item
        # 当前脚本占用：循环收尾与 final_task 共用，可重复释放
        self._script_entry: ScriptEntry | None = None
        self._script_ticket: LockTicket | None = None
        self._game_ticket: LockTicket | None = None
        self._game: tuple[GameControl, LockTicket, DeviceHandle | None] | None = None

    def expand_scripts(self) -> list[str]:
        """按 §5.4 真值表产出脚本 uid 顺序（含队列内断点续跑切片）。

        组合合法性由 L1 判定，本方法不抛 ``ExpandError``。
        """
        info = self.item.info
        queue_id, script_id = info.queue_id, info.script_id
        has_q, has_s = is_selected(queue_id), is_selected(script_id)
        if info.mode == TaskMode.SCRIPT_CONFIG or not has_q:
            return [str(script_id)]
        if not has_s:
            return queue_script_ids(queue_id)
        ids = queue_script_ids(queue_id)
        return ids[ids.index(str(script_id)) :]

    async def main_task(self) -> None:
        from app.core import Config, GameManager, Plugin
        from app.plugin.base.game import DeviceSubscribeError

        item = self.item
        info = item.info
        info.status = "expanding"
        await item.commit()

        # ── 按 §5.4 真值表产出脚本 uid 顺序（含队列内断点续跑切片）──
        # 组合合法性已由 TaskDispatcher.start 判过，这里不再校验、不抛 ExpandError，
        # 只读 item.info 走产出分支。队列 + 脚本时起点保证在队列内，index 不会失败。
        script_ids = self.expand_scripts()

        for old in list(item.scripts.keys()):
            item.scripts.remove(old)
        for sid in script_ids:
            entry = Config.ScriptConfig.get(UUID(sid))
            item.scripts.add(
                TaskScriptItem,
                uid=UUID(sid),
                payload={
                    "info": {
                        "name": entry.info.name if entry is not None else sid,
                        "status": "pending",
                    }
                },
            )
        # add/remove 暂存在子集合节点上，父 Entry 的 commit 不会下沉排它的队列
        await item.scripts.commit()

        info.status = "running"
        await item.commit()

        for sid in script_ids:
            suid = UUID(sid)
            item.current.index = suid
            await item.commit()

            script_item = item.scripts[suid]
            entry = Config.ScriptConfig.get(suid)
            if entry is None:
                logger.error(f"脚本 {sid} 已不存在，跳过")
                script_item.info.status = "missing"
                await script_item.commit()
                continue

            # 与 GameManager.on_add 同路：类型域的真相源是 decl 目录，不另立索引。
            # 适配器 disable 时目录条目随之摘掉，故查不到即该类型已不可用。
            decl = next(
                (
                    d
                    for d in Plugin.script_types.values()
                    if isinstance(entry, d.entry_type)
                ),
                None,
            )
            if decl is None:
                logger.error(
                    f"脚本类型 {type(entry).__name__} 未注册 UserExpander，跳过脚本 {sid}"
                )
                script_item.info.status = "no_expander"
                await script_item.commit()
                continue

            # ── 脚本 X（非递归）──
            self._script_entry = entry
            script_item.info.status = "waiting_lock"
            await script_item.commit()
            while True:
                ticket = await entry.try_lock_x(cascade=False)
                if ticket is not None:
                    self._script_ticket = ticket
                    break
                await asyncio.sleep(1)

            # ── 游戏 S + 闸门 + 设备订阅（未选游戏 / 插件未挂载则跳过）──
            # game_id / game_device_id 热态为 UUID | str，"-" 即未选
            guid = entry.info.game_id
            if isinstance(guid, UUID):
                game_entry = Config.GameConfig.get(guid)
                control = None
                if game_entry is not None:
                    try:
                        control = game_entry._control
                    except RuntimeError:
                        control = None
                if control is not None:
                    expect = (
                        decl.expect_builder(entry)
                        if decl.expect_builder is not None
                        else None
                    )
                    usage = f"{entry.info.name}/{item.uid}"
                    script_item.info.status = "waiting_game"
                    await script_item.commit()
                    while True:
                        try:
                            control, game_ticket = await GameManager.subscribe(guid)
                            break
                        except asyncio.CancelledError:
                            raise
                        except ValueError:
                            # 游戏正被配置 X 占用，等锁
                            await asyncio.sleep(1)
                        except (KeyError, RuntimeError, TypeError):
                            control = None
                            game_ticket = None
                            break
                    if game_ticket is not None:
                        self._game_ticket = game_ticket
                        handle = None
                        device_uid = entry.info.game_device_id
                        if isinstance(device_uid, UUID):
                            while True:
                                try:
                                    handle = await control.subscribe_device(
                                        game_ticket, device_uid, usage, expect
                                    )
                                    break
                                except asyncio.CancelledError:
                                    raise
                                except DeviceSubscribeError:
                                    await asyncio.sleep(1)
                        self._game = (control, game_ticket, handle)

            script_item.info.status = "running"
            await script_item.commit()

            ctx = TaskContext(
                task_id=item.uid,
                trigger_source=info.trigger_source,
                mode=info.mode,
                queue_id=info.queue_id,
                script_id=info.script_id,
                user_id=info.user_id,
            )
            try:
                await self.spawn(
                    decl.expander_class(
                        task_context=ctx,
                        script_item=script_item,
                        script_entry=entry,
                        game=self._game,
                    )
                )
            finally:
                # 本脚本占用在循环内释放；取消时 final_task 再幂等兜底
                await self._release()

        # 未被 crash/stop 改写时，正常跑完记 success
        if info.status == "running":
            info.status = "success"
            await item.commit()

    async def _release(self) -> None:
        """提交脚本写入 → 解锁 → 退订；可重复调用。"""
        entry = self._script_entry
        if entry is not None:
            try:
                await entry.commit()
            except Exception:
                logger.exception(f"脚本 {entry.uid} 收尾 commit 失败")
        if self._script_ticket is not None and entry is not None:
            try:
                await entry.unlock(self._script_ticket)
            except Exception:
                logger.exception(f"脚本 {entry.uid} 解锁失败")
            self._script_ticket = None
        if self._game_ticket is not None:
            try:
                from app.core import GameManager

                await GameManager.unsubscribe(self._game_ticket)
            except Exception:
                uid = entry.uid if entry is not None else "?"
                logger.exception(f"脚本 {uid} 退订游戏失败")
            self._game_ticket = None
            self._game = None
        self._script_entry = None

    async def final_task(self) -> None:
        from app.core.ws import Publisher, protocol
        from app.core.ws.protocol import WSTaskCompletedData

        # TaskBase 保证本方法总会跑到：取消打断循环时在此释放当前脚本占用
        await self._release()

        self.item.current.index = None
        await self.item.commit()
        info = self.item.info
        # WS 仍带 outcome 字段供前端；取值来自 TaskItem.status，不再另存
        outcome = (
            info.status
            if info.status in ("success", "error", "cancelled")
            else "success"
        )
        await Publisher.send(
            id=str(self.item.uid),
            type=protocol.TASK_COMPLETED,
            data=WSTaskCompletedData(
                result=info.result or "",
                outcome=outcome,
                error=None,
                task=self.item.model_dump(mode="json"),
            ),
        )

    async def on_crash(self, exc: BaseException) -> None:
        info = self.item.info
        if info.status not in ("error", "cancelled"):
            info.status = "error"
            await self.item.commit()
        logger.error(f"任务 {self.item.uid} 执行失败：{type(exc).__name__}: {exc}")

    async def stop(self) -> None:
        info = self.item.info
        if info.status not in ("error", "cancelled"):
            info.status = "cancelled"
            await self.item.commit()
        await super().stop()
