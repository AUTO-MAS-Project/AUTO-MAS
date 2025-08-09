import asyncio
import aiofiles
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, List, Awaitable

from .logger import get_logger

logger = get_logger("日志监控器")


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
        self.last_callback_time: datetime = datetime.now()
        self.log_contents: List[str] = []
        self.task: Optional[asyncio.Task] = None

    async def monitor_log(self):
        """监控日志文件的主循环"""
        if self.log_file_path is None or not self.log_file_path.exists():
            raise ValueError("Log file path is not set or does not exist.")

        logger.info(f"开始监控日志文件: {self.log_file_path}")

        consecutive_errors = 0

        while True:
            try:
                log_contents = []
                if_log_start = False

                # 检查文件是否仍然存在
                if not self.log_file_path.exists():
                    logger.warning(f"日志文件不存在: {self.log_file_path}")
                    await asyncio.sleep(1)
                    continue

                # 尝试读取文件
                try:
                    async with aiofiles.open(
                        self.log_file_path, "r", encoding=self.encoding
                    ) as f:
                        async for line in f:
                            if not if_log_start:
                                try:
                                    entry_time = datetime.strptime(
                                        line[
                                            self.time_stamp_range[
                                                0
                                            ] : self.time_stamp_range[1]
                                        ],
                                        self.time_format,
                                    )
                                    if entry_time > self.log_start_time:
                                        if_log_start = True
                                        log_contents.append(line)
                                except (ValueError, IndexError):
                                    continue
                            else:
                                log_contents.append(line)

                except (FileNotFoundError, PermissionError) as e:
                    logger.warning(f"文件访问错误: {e}")
                    await asyncio.sleep(5)
                    continue
                except UnicodeDecodeError as e:
                    logger.error(f"文件编码错误: {e}")
                    await asyncio.sleep(10)
                    continue

                # 调用回调
                if (
                    log_contents != self.log_contents
                    or datetime.now() - self.last_callback_time > timedelta(minutes=1)
                ):
                    self.log_contents = log_contents
                    self.last_callback_time = datetime.now()

                    # 安全调用回调函数
                    try:
                        await self.callback(log_contents)
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {e}")

            except asyncio.CancelledError:
                logger.info("日志监控任务被取消")
                break
            except Exception as e:
                logger.error(f"监控日志时发生未知错误：{e}")

                consecutive_errors += 1
                wait_time = min(60, 2**consecutive_errors)
                await asyncio.sleep(wait_time)
                continue

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
        logger.info(f"日志监控已启动: {self.log_file_path}")

    async def stop(self):
        """停止监控"""

        if self.task is not None and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        self.log_contents = []
        self.log_file_path = None
        self.task = None
        logger.info(f"日志监控已停止: {self.log_file_path}")
