"""MAA 模式运行上下文；配置提交和日志消费留在持锁的执行协程。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import datetime

from auto_mas_core import ModeWorker
from auto_mas_core.host.models_task import LogRecord
from auto_mas_core.host.services import execute_script_task
from auto_mas_core.host.services_common_update_prefetch import prefetch_paths

from maa_adapter.config.user import MaaUserConfig


@contextmanager
def prefetched_scope(paths):
    """在当前异步上下文内绑定 URL 到预下载文件的映射，退出时恢复外层任务的映射。"""
    token = prefetch_paths.set(paths)
    try:
        yield
    finally:
        prefetch_paths.reset(token)


class MaaWorkerContext(ModeWorker):
    wait_event: asyncio.Event

    def __init__(self, expander, user, config):
        """绑定 L4 基础上下文，初始化账号前后脚本执行标记、日志停滞状态和待处理日志队列。"""
        super().__init__(expander, user, config)
        self._user_scripts_started = False
        self._log_progress = {}
        self._log_updates = asyncio.Queue(maxsize=1)

    @property
    def config_user_id(self):
        """将任务默认用户标识转换为来源 MAA 使用的 Default 名称，其余用户标识原样返回。"""
        return (
            "Default"
            if self.user_info.info.user_id == "default"
            else self.user_info.info.user_id
        )

    @property
    def stopped_manually(self):
        """判断当前 L4 或任务根是否已取消，供来源业务区分手动停止与异常。"""
        return self.cancelled or self.task_info.info.status == "cancelled"

    def iter_logs(self):
        """将当前账号的日志集合转换为本地时间与记录配对，供来源日志分析逻辑遍历。"""
        return [
            (record.info.start_time.astimezone(), record)
            for record in self.user_info.logs.values()
        ]

    def current_log_at(self, moment):
        """按开始时间查找当前账号已有日志记录，无匹配记录时返回空值。"""
        return next((record for at, record in self.iter_logs() if at == moment), None)

    async def add_log(self, moment, record):
        """为当前账号建立并提交一条带指定开始时间的日志记录，返回已登记的实际配置节点。"""
        payload = record.model_dump(context={"audience": "persist"})
        payload["info"]["start_time"] = moment
        uid = self.user_info.logs.add(LogRecord, payload=payload)
        await self.user_info.logs.commit()
        return self.user_info.logs[uid]

    async def queue_log(self, content, latest):
        """提交最新一批日志更新，队列已满时丢弃旧批次以避免处理进度落后。"""
        if self._log_updates.full():
            self._log_updates.get_nowait()
        self._log_updates.put_nowait((content, latest))

    async def wait_logs(
        self, check_log: Callable[[list[str], datetime], Awaitable[None]]
    ):
        """持续消费日志更新并交给具体业务检查回调，等待事件结束时停止观察。"""
        while not self.wait_event.is_set():
            content, latest = await self._log_updates.get()
            await check_log(content, latest)

    def is_log_stalled(self, latest, minutes, key="default"):
        """按观察键记录最后一次日志变化时间，判断是否超过调用方设定的停滞分钟数。"""
        now = time.monotonic()
        previous, since = self._log_progress.get(key, (None, now))
        if previous != latest:
            since = now
        self._log_progress[key] = latest, since
        return now - since > minutes * 60

    async def run_user_scripts_before(self, config: MaaUserConfig):
        """标记账号脚本阶段已进入，并在配置启用时执行账号任务前脚本。"""
        self._user_scripts_started = True
        if config.Info.IfScriptBeforeTask:
            await execute_script_task(
                config.Info.ScriptBeforeTask, "MAA 账号任务前脚本"
            )

    async def run_user_scripts_after(self, config: MaaUserConfig):
        """仅为已进入脚本阶段的账号执行一次任务后脚本，并清除执行标记。"""
        if not self._user_scripts_started:
            return
        self._user_scripts_started = False
        if config.Info.IfScriptAfterTask:
            await execute_script_task(config.Info.ScriptAfterTask, "MAA 账号任务后脚本")
