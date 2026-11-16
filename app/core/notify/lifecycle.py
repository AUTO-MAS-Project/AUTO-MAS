"""托管级通知批次；持锁阶段只固定请求，完整收尾后交给宿主发送。"""

import asyncio

from app.config import LockTicket
from app.core import Config
from app.models.config import ScriptConfigType
from app.models.task import ScriptItem, TaskExecuteBase, TaskItem


class NotificationTaskBase(TaskExecuteBase):
    """[兼容旧专项] 旧 manager 的持锁基类；新四级执行链由派发层持有下层配置锁。"""

    task_info: TaskItem
    script_info: ScriptItem

    # L2 负责覆盖 manager 完整生命周期的通知批次。

    async def lock_script_config(self, config: ScriptConfigType) -> LockTicket:
        """[兼容旧专项] 仅旧 manager 取递归锁；新 L2 取托管非级联 X 锁，L3 取用户级联 X 锁。"""
        # 旧 manager 在实际使用配置的层级等锁；不再由 L2 预约托管或目录。
        last_wait_message = None
        while True:
            if Config.ScriptConfig.get(config.uid) is not config or config.deleted:
                raise ValueError("托管配置已删除或替换")
            ticket = await config.try_lock_x()
            if ticket is not None:
                break
            from app.core.task_manager import TaskManager

            await self.script_info.set_state(status="等待")
            holders = TaskManager.describe_lock_holders(config, cascade=True)
            message = (
                f"等待托管配置「{config.Info.Name}」的 X 锁，当前占用：{holders}。"
            )
            if message != last_wait_message:
                self.script_info.current.log = (
                    self.script_info.current.log + message + "\n"
                )
                await self.script_info.commit()
                last_wait_message = message
            await asyncio.sleep(1)
        return ticket
