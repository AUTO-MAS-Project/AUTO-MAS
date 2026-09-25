#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""IRunEventFeed 默认实现：tail 上游 loguru 日志并逐行转结构化事件。

上游日志面（whimbox/common/logger.py，v3.0.5 源码实证）：
- sink = ``logs/whimbox-{time:YYYY-MM-DD}.log``，按天新文件，启动清理 7 天前
  旧文件；``enqueue=True`` 异步写队列（毫秒级落盘，atexit flush 兜底）；
- 生产构建无 stdout sink（仅 DEBUG_MODE），无头模式下文件是唯一日志通道；
- 行格式为 loguru 默认 format，时间列 (0, 23)、格式 ``%Y-%m-%d %H:%M:%S.%f``；
- 结果块等消息内换行的续行没有时间列——越过运行起始时刻后监控器会原样
  采集（LogMonitor._consume_new_lines 的 if_log_start 语义）。

事件模型是结构化的（text/timestamp）——这是 RPC 结果面预留的
硬约束：Round 2 的 RpcEventFeed（订阅 ``event.run.log``）与文件行浅解析
两侧语义对齐，高层零改动。
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.task.Whimbox.contracts import WhimboxRunEvent
from app.utils import get_logger
from app.utils.LogMonitor import LogMonitor, strptime

logger = get_logger("奇想盒 日志流")

# loguru 默认 format 的时间列与格式（对照 BetterGI Serilog 的 (1,13)）
WHIMBOX_LOG_TIME_RANGE = (0, 23)
WHIMBOX_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

LOG_FILE_PREFIX = "whimbox-"
"""日志文件名前缀（logs/whimbox-YYYY-MM-DD.log）"""


def build_log_path_resolver(root_path: Path) -> Callable[[], Path]:
    """构造当日日志路径解析器（跨零点由监控器自动切换新文件）。"""

    def resolve() -> Path:
        return root_path / "logs" / f"{LOG_FILE_PREFIX}{datetime.now():%Y-%m-%d}.log"

    return resolve


class LoguruFileFeed:
    """IRunEventFeed 默认实现：tail whimbox-YYYY-MM-DD.log → 结构化事件。

    Args:
        on_event: 逐行事件回调（同步或异步均可）。
        path_resolver: 当日日志路径解析器。
    """

    def __init__(
        self,
        on_event: Callable[[WhimboxRunEvent], Awaitable[None] | None],
        path_resolver: Callable[[], Path],
    ) -> None:
        self._on_event = on_event
        self._path_resolver = path_resolver
        self._lines: list[str] = []
        # 已归一的元素个数：不能拿 len(self._lines) 当游标（它就是监控器那个 list 本身）
        self._normalized = 0
        self._emitted = 0
        self.latest_time_value: datetime = datetime.now()
        self._monitor = LogMonitor(
            WHIMBOX_LOG_TIME_RANGE,
            WHIMBOX_LOG_TIME_FORMAT,
            self._on_log,
        )

    @property
    def latest_time(self) -> datetime:
        """最近一条带时间戳行的时间（停滞判定输入）。"""

        return self.latest_time_value

    @property
    def log_text(self) -> str:
        """累计日志文本（marker 判定输入）。"""

        return "".join(self._lines)

    async def start(self, log_start_time: datetime) -> None:
        """开始监控（从 log_start_time 之后的行起）。"""

        await self._monitor.start_monitor_file(self._path_resolver, log_start_time)

    async def stop(self) -> None:
        """停止监控。"""

        await self._monitor.stop()

    async def _emit(self, event: WhimboxRunEvent) -> None:
        result = self._on_event(event)
        if inspect.isawaitable(result):
            await result

    async def _on_log(self, log_content: list[str], latest_time: datetime) -> None:
        """监控回调：把新增行转为事件（含无时间列的续行）。

        上游日志是 CRLF，这里**就地**把新增行归一为 LF：下游（历史日志按平台换行
        写盘、通知正文）会再走一次换行翻译，CRLF 会变成 ``\\r\\r\\n``，读起来每行
        之间多一个空行。就地改写而不是新建列表——监控器持有同一个 list 并持续
        追加，换引用会让后续新行读不到。
        """

        for i in range(self._normalized, len(log_content)):
            log_content[i] = log_content[i].replace("\r\n", "\n").replace("\r", "\n")
        self._normalized = len(log_content)
        self._lines = log_content
        self.latest_time_value = latest_time
        for line in log_content[self._emitted :]:
            timestamp = None
            with suppress(ValueError):
                timestamp = strptime(
                    line[WHIMBOX_LOG_TIME_RANGE[0] : WHIMBOX_LOG_TIME_RANGE[1]],
                    WHIMBOX_LOG_TIME_FORMAT,
                    latest_time,
                )
            await self._emit(WhimboxRunEvent(text=line, timestamp=timestamp))
        self._emitted = len(log_content)
