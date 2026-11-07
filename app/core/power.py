"""应用电源编排：管理待执行信号，订阅调度结束并持有唯一倒计时。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core import Publisher
from app.core.ws import protocol
from app.models.schema import (
    PowerCountdownSnapshot,
    WSPowerCountdownData,
    WSPowerSignData,
)
from app.utils import get_logger, power
from app.utils.contracts.power import PowerSignal

if TYPE_CHECKING:
    from app.core.task_manager import _TaskManager
    from app.models.task import TaskItem

logger = get_logger("电源管理")


class _PowerManager:
    def __init__(self) -> None:
        from app.core.task_manager import _TaskManager

        self.signal: PowerSignal = PowerSignal.NO_ACTION
        self.delay = 60
        # 唯一占用标识：创建倒计时即登记，执行完成或取消后清除。
        self.power_task: asyncio.Task[None] | None = None
        self.current_power_operation: PowerSignal | None = None
        self.current_power_remaining = 0
        _TaskManager.task_ended.connect(self._on_task_ended)

    async def set_signal(
        self, signal: PowerSignal, *, overwrite: bool, delay: int = 60
    ) -> bool:
        """设置待执行意图及倒计时秒数；已有电源任务不覆盖，非强制仅填补空意图。"""
        if self.power_task is not None or (
            not overwrite and self.signal != PowerSignal.NO_ACTION
        ):
            return False
        if not overwrite and signal == PowerSignal.NO_ACTION:
            return False
        self.signal, self.delay = signal, delay
        await Publisher.send(
            id=protocol.ID_MAIN,
            type=protocol.POWER_SIGN_UPDATED,
            data=WSPowerSignData(signal=signal),
        )
        return True

    async def _on_task_ended(self, sender: _TaskManager, *, task: TaskItem) -> None:
        """只在调度已注销任务后判定；不在信号接收链等待倒计时或后台工作。"""
        if not sender.idle or task.info.status == "cancelled":
            return
        await self.start_power_task()

    async def start_power_task(self) -> bool:
        """消费待执行意图并启动唯一倒计时；重复触发直接跳过。"""
        if self.power_task is not None or self.signal == PowerSignal.NO_ACTION:
            return False
        signal, delay = self.signal, self.delay
        self.signal, self.delay = PowerSignal.NO_ACTION, 60
        self.power_task = asyncio.create_task(self._power_task(signal, delay))

        def finished(done: asyncio.Task) -> None:
            if self.power_task is done:
                self.power_task = None
            if not done.cancelled() and (error := done.exception()) is not None:
                logger.opt(exception=error).error(f"电源操作 {signal} 失败")

        self.power_task.add_done_callback(finished)
        return True

    async def _power_task(self, signal: PowerSignal, delay: int) -> None:
        self.current_power_operation = signal
        try:
            for self.current_power_remaining in range(delay, 0, -1):
                await Publisher.send(
                    id=protocol.ID_MAIN,
                    type=protocol.POWER_COUNTDOWN_UPDATED,
                    data=WSPowerCountdownData(
                        operation=signal, remaining=self.current_power_remaining
                    ),
                )
                await asyncio.sleep(1)
            await self.set_power(signal)
        except Exception:
            await Publisher.send(
                id=protocol.ID_MAIN, type=protocol.POWER_COUNTDOWN_CANCELLED
            )
            raise
        finally:
            self.current_power_operation = None
            self.current_power_remaining = 0

    async def set_power(self, mode: PowerSignal) -> None:
        """执行电源动作；睡眠和休眠保留宿主，其余结束动作交给退出协调器。"""
        from app.core import ShutdownCoordinator

        if mode == PowerSignal.NO_ACTION:
            return
        if mode not in {PowerSignal.KILL_SELF, PowerSignal.RESTART_SELF}:
            from app.core import EmulatorManager

            if mode not in power.supported_actions:
                raise RuntimeError(f"当前平台不支持电源操作: {mode}")
            if mode in {
                PowerSignal.SHUTDOWN,
                PowerSignal.SHUTDOWN_FORCE,
                PowerSignal.REBOOT,
                PowerSignal.LOGOFF,
            }:
                try:
                    await asyncio.wait_for(
                        EmulatorManager.close_running_avd_instances(), 30
                    )
                except Exception as error:
                    logger.warning(f"关闭魔改 AVD 实例失败，继续电源操作: {error}")
            if mode in {PowerSignal.SHUTDOWN, PowerSignal.REBOOT, PowerSignal.LOGOFF}:
                await EmulatorManager.kill_emulator_processes()
        if mode not in {PowerSignal.KILL_SELF, PowerSignal.RESTART_SELF}:
            # TODO(退出时序优化)：本轮保留先发系统动作再请求应用退出的顺序。
            # /t 0、/f 可能先终止本进程，不能保证后台收尾及时完成。
            await power.execute(mode)
        # 睡眠／休眠恢复后继续运行，不触发 teardown 停止调度和后台任务。
        if mode not in {PowerSignal.SLEEP, PowerSignal.HIBERNATE}:
            ShutdownCoordinator.request_exit(restart=mode == PowerSignal.RESTART_SELF)

    def get_power_countdown_snapshot(self) -> PowerCountdownSnapshot:
        active = bool(
            self.power_task
            and not self.power_task.done()
            and self.current_power_remaining > 0
        )
        return PowerCountdownSnapshot(
            active=active,
            operation=self.current_power_operation if active else None,
            remaining=self.current_power_remaining if active else 0,
        )

    async def cancel_power_task(self) -> None:
        """清除意图并等待电源任务退出；取消不能撤回已经发出的系统动作。"""
        self.signal, self.delay = PowerSignal.NO_ACTION, 60
        task = self.power_task
        if task is None or task.done():
            return
        requested = not task.cancelling() and task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        if requested:
            await Publisher.send(
                id=protocol.ID_MAIN, type=protocol.POWER_COUNTDOWN_CANCELLED
            )


Power = _PowerManager()

__all__ = ["Power"]
