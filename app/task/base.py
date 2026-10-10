"""脚本单账号自动运行的总时限保护。"""

import asyncio
from datetime import datetime
from pathlib import Path

from app.models.ConfigBase import ConfigBase
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.utils.logger import get_logger

logger = get_logger("脚本运行")


class ScriptAutoProxyBase(TaskExecuteBase):
    # 总时限涵盖等待和全部重试，不随日志推进重置；收尾必须完成后再切换账号。
    wait_for_finalizer_on_cancel = True

    script_info: ScriptItem
    script_config: ConfigBase
    cur_user_item: UserItem
    cur_user_config: ConfigBase
    # 用户级前/后脚本成对标记：前置跑过才收尾后置，且每用户只收尾一次。
    _user_scripts_started: bool = False

    @property
    def run_timeout_seconds(self) -> float:
        return self.script_config.get("Run", "HardTimeLimit") * 60

    async def run_user_scripts_before(self) -> None:
        """执行用户级任务前脚本；每用户一次，先于全部重试。"""

        # 就地导入：专项包会反向导入本模块，模块级导入会成环。
        from app.task.general.tools import execute_script_task

        self._user_scripts_started = True
        if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                "脚本前任务",
            )

    async def run_user_scripts_after(self) -> None:
        """执行用户级任务后脚本；前置未执行过时跳过，保证成对且只一次。"""

        from app.task.general.tools import execute_script_task

        if not self._user_scripts_started:
            return
        self._user_scripts_started = False
        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    async def _finalize_task(self) -> None:
        """收尾时成对执行后置脚本；收尾被取消或异常中断也仍会尝试执行。"""

        try:
            await super()._finalize_task()
        finally:
            await self.run_user_scripts_after()

    async def _run_main_task(self) -> None:
        timeout = asyncio.timeout(self.run_timeout_seconds)
        try:
            async with timeout:
                await self.main_task()
        except TimeoutError:
            # 脚本内部的 TimeoutError 仍交给原异常流程处理。
            if not timeout.expired():
                raise

            message = f"运行超过 {self.run_timeout_seconds / 60:g} 分钟，已终止"
            user = self.cur_user_item
            user.status = "异常"
            if user.log_record:
                record = user.log_record[max(user.log_record)]
            else:
                record = LogRecord()
                user.log_record[datetime.now()] = record
            record.status = message
            record.content.append(message)
            self.script_info.log = f"{message}\n正在中止相关程序"
            logger.warning(f"{self.script_info.name} - {user.name}: {message}")
