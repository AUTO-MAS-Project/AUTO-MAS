import asyncio
import aiofiles
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Awaitable

from loguru import logger


class LogMonitor:
    def __init__(
        self,
        time_stamp_range: tuple[int, int],
        time_format: str,
        callback: Callable[[List[str]], Awaitable[None]],
        encoding: str = "utf-8",
    ):
        self.time_stamp_range = time_stamp_range
        self.time_format = time_format
        self.callback = callback
        self.encoding = encoding
        self.log_file_path: Optional[Path] = None
        self.log_start_time: datetime = datetime.now()
        self.log_contents: List[str] = []
        self.task: Optional[asyncio.Task] = None

    async def monitor_log(self):

        if self.log_file_path is None or not self.log_file_path.exists():
            raise ValueError("Log file path is not set or does not exist.")

        while True:

            log_contents = []
            if_log_start = False

            async with aiofiles.open(
                self.log_file_path, "r", encoding=self.encoding
            ) as f:

                async for line in f:
                    if not if_log_start:
                        try:
                            entry_time = datetime.strptime(
                                line[
                                    self.time_stamp_range[0] : self.time_stamp_range[1]
                                ],
                                self.time_format,
                            )
                            if entry_time > self.log_start_time:
                                if_log_start = True
                                log_contents.append(line)
                        except ValueError:
                            pass
                    else:
                        log_contents.append(line)

            # 调用回调
            if log_contents != self.log_contents:
                self.log_contents = log_contents
                await self.callback(log_contents)

            await asyncio.sleep(1)

    async def start(self, log_file_path: Path, start_time: datetime) -> None:
        """启动监控"""

        if log_file_path.is_dir():
            raise ValueError(f"Log file cannot be a directory: {log_file_path}")

        if self.task is not None and not self.task.done():
            await self.stop()

        self.log_file_path = log_file_path
        self.log_start_time = start_time
        self.task = asyncio.create_task(self.monitor_log())

        logger.info(f"开始监控文件: {self.log_file_path}")

    async def stop(self):
        """停止监控"""

        if self.task is not None and not self.task.done():
            self.task.cancel()

        self.log_contents = []
        logger.info(f"停止监控文件: {self.log_file_path}")
        self.log_file_path = None
