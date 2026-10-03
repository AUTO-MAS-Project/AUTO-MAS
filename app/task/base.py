"""脚本单账号自动运行的总时限保护。"""

import asyncio
from datetime import datetime

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

    @property
    def run_timeout_seconds(self) -> float:
        return self.script_config.get("Run", "HardTimeLimit") * 60

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
