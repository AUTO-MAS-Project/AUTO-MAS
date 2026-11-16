import asyncio
from datetime import datetime

from app.models.task import LogRecord, ScriptItem, UserItem
from app.task.base import ScriptAutoProxyBase


class Proxy(ScriptAutoProxyBase):
    run_timeout_seconds = 0.1

    def __init__(self):
        super().__init__()
        self.cur_user_item = UserItem("test", "测试账号", "运行")
        self.cur_user_item.log_record[datetime.now()] = LogRecord(status="运行中")
        self.script_info = ScriptItem("script", "测试脚本", "运行")
        self.crashes = []
        self.finalized = False
        self.cancelled = False
        self.ticks = 0

    async def main_task(self):
        try:
            while True:
                self.ticks += 1
                await asyncio.sleep(0.002)
        finally:
            self.cancelled = True

    async def final_task(self):
        await asyncio.sleep(0.01)
        self.saved_status = self.cur_user_item.result
        self.finalized = True

    async def on_crash(self, error):
        self.crashes.append(error)


async def run(proxy):
    async with asyncio.TaskGroup() as group:
        await proxy._execute_task(group)


def test_progress_cannot_extend_hard_timeout_or_skip_finalization():

    async def scenario():
        first = Proxy()
        await run(first)
        assert first.finalized and first.cancelled and first.accomplish.is_set()
        assert first.ticks > 1
        assert first.cur_user_item.status == "异常"
        assert "已终止" in first.saved_status
        assert not first.stopped_manually and (not first.crashes)

    asyncio.run(scenario())
