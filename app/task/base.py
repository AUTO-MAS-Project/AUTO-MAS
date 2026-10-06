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

"""任务执行契约：所有嵌套层级共用的可取消生命周期。

任务分四层，每层一个文件：本模块是最底层的**执行契约**，只描述"怎么跑、
怎么收尾、怎么取消"，不碰任何业务状态 —— 状态的唯一事实源是
``app.models.task`` 里的配置树。

上层依次为 ``script_expander``（展开脚本列表）、``user_expander``（锁配置、
展开用户列表）、``mode_worker``（单用户三模式，真正干活的那层）。
"""

from __future__ import annotations

import asyncio
import inspect
from abc import ABC, abstractmethod

from blinker import Signal

from app.utils import get_logger

logger = get_logger("任务基类")


class TaskBase(ABC):
    """可取消的异步任务执行契约（两层 Expander 与 Worker 共用）。

    子类实现 ``main_task``；``final_task`` 在成功、失败与取消路径都会执行。
    嵌套子任务一律 ``await self.spawn(child)``，取消时沿 await 链传播。

    ``ended`` 只在 ``start()`` 启动的顶层任务收尾后发出（自然结束、失败、取消
    同一条路）。派发层把 ``_running`` 清理挂在这条信号上，而不是写在 ``stop`` 里。
    """

    ended: Signal = Signal()

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self.accomplish = asyncio.Event()

    @abstractmethod
    async def main_task(self) -> None:
        """任务主流程。"""

    async def final_task(self) -> None:
        """任务收尾：释放锁、回写结果、触发后续动作。"""

    async def on_crash(self, exc: BaseException) -> None:
        """未捕获异常兜底；默认只记录，自身不得再抛。"""
        try:
            logger.exception(f"任务执行异常：{type(exc).__name__}: {exc}")
        except Exception:
            pass

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """作为顶层任务派发到事件循环；重复启动视为错误。"""
        if self.running:
            raise RuntimeError("任务已在运行")
        self.accomplish.clear()
        self._task = asyncio.create_task(self.run())

    async def spawn(self, child: TaskBase) -> None:
        """启动子任务并等待其完整生命周期（含 final_task）结束。

        必须 ``await child.run()`` 同上下文执行：X 持票者写入靠 ContextVar
        继承 token。改成 ``create_task`` 后子层拿不到父层 token，写回会被拒。
        """
        await child.run()

    async def run(self) -> None:
        """就地执行一轮完整生命周期，取消时仍保证收尾。"""
        try:
            await self.main_task()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.on_crash(exc)
        finally:
            # 取消传播时 final_task 仍需跑完，用 shield 挡住二次取消
            try:
                await asyncio.shield(self.final_task())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.on_crash(exc)
            # 先发 ended 再置 accomplish：订阅方（派发层 drop）清完挂点后，
            # stop() 的 wait 才返回，避免「已结束但仍在 _running」的窗口。
            # 只有 start() 的顶层持 _task；spawn 的子任务不发，免得误清。
            if self._task is not None:
                for _receiver, result in self.ended.send(self):
                    if inspect.isawaitable(result):
                        await result
            self.accomplish.set()

    async def stop(self) -> None:
        """取消顶层任务并等待收尾结束。

        只有 ``start()`` 启动的层级持有 Task 句柄。被 spawn 的子任务就地跑在
        父任务的 Task 里（``spawn`` 直接 ``await child.run()``），取消沿 await
        链自然传到它，没有也不需要独立句柄 —— 故此处无事可做。
        """
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await self.accomplish.wait()
