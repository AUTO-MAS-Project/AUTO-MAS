#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import aiofiles
from contextlib import suppress
from datetime import datetime, timedelta, date
from copy import copy
from pathlib import Path
from typing import Callable, Optional, List, Awaitable

from .constants import TIME_FIELDS, ANSI_ESCAPE_RE
from .logger import get_logger
from .tools import decode_bytes

logger = get_logger("日志监控器")


def strptime(date_string: str, format: str, default_date: datetime) -> datetime:
    """根据指定格式解析日期字符串"""

    date = datetime.strptime(date_string, format)

    # 构建参数字典
    datetime_kwargs = {}
    for format_code, field_name in TIME_FIELDS.items():
        if format_code in format:
            datetime_kwargs[field_name] = getattr(date, field_name)
        else:
            datetime_kwargs[field_name] = getattr(default_date, field_name)

    return datetime(**datetime_kwargs)


class LogMonitor:
    def __init__(
        self,
        time_stamp_range: tuple[int, int],
        time_format: str,
        callback: Callable[[List[str], datetime], Awaitable[None]],
        except_logs: List[str] = [],
    ):
        self.time_start = time_stamp_range[0]
        self.time_end = time_stamp_range[1]
        self.time_format = time_format
        self.callback = callback
        self.except_logs = except_logs
        self.last_callback_time: datetime = datetime.now()
        self.log_contents: List[str] = []
        self.latest_time = datetime.now()
        self.task: Optional[asyncio.Task] = None

    async def monitor_file(self, log_file_path: Path, log_start_time: datetime):
        """监控日志文件的主循环"""

        logger.info(f"开始监控日志文件: {log_file_path}")

        await self.update_latest_timestamp("", if_init=True)

        if_mtime_checked = False
        if_log_start = False
        offset = 0
        log_contents = []

        while True:

            # 检查文件是否仍然存在
            if not log_file_path.exists():
                logger.warning(f"日志文件不存在: {log_file_path}")
                await self.do_callback()
                await asyncio.sleep(1)
                continue

            if not if_mtime_checked:
                if date.fromtimestamp(log_file_path.stat().st_mtime) == date.today():
                    log_stat = log_file_path.stat()
                    if_mtime_checked = True
                else:
                    logger.warning(
                        f"日志文件今天未被修改: {date.fromtimestamp(log_file_path.stat().st_mtime)}"
                    )
                    await self.do_callback()
                    await asyncio.sleep(1)
                    continue

            # 尝试读取文件
            try:

                if (
                    log_stat.st_ino != log_file_path.stat().st_ino
                    or log_stat.st_size > log_file_path.stat().st_size
                ):
                    offset = 0
                    log_contents = []
                    if_log_start = False

                log_stat = log_file_path.stat()

                if log_stat.st_size <= offset:

                    # 日志无变化超时调用回调
                    if datetime.now() - self.last_callback_time > timedelta(minutes=1):
                        await self.do_callback()

                    await asyncio.sleep(1)
                    continue

                async with aiofiles.open(log_file_path, "rb") as f:
                    await f.seek(offset)
                    async for bline in f:
                        offset = await f.tell()
                        line = decode_bytes(bline)
                        if not if_log_start:
                            with suppress(IndexError, ValueError):
                                entry_time = strptime(
                                    line[self.time_start : self.time_end],
                                    self.time_format,
                                    self.last_callback_time,
                                )
                                if entry_time > log_start_time:
                                    if_log_start = True
                                    log_contents.append(line)
                                    await self.update_latest_timestamp(line)
                        else:
                            log_contents.append(line)
                            await self.update_latest_timestamp(line)

            except (FileNotFoundError, PermissionError) as e:
                logger.warning(f"文件访问错误: {e}")
                await asyncio.sleep(5)
                continue

            # 日志变化调用回调
            if len(log_contents) != len(self.log_contents):
                self.log_contents = copy(log_contents)
                await self.do_callback()

            await asyncio.sleep(1)

    async def monitor_process(self, process: asyncio.subprocess.Process):
        """监控日志文件的主循环"""

        logger.info(f"开始监控进程日志: {process.pid}")

        await self.update_latest_timestamp("", if_init=True)

        if process.stdout is None:
            raise ValueError("进程没有标准输出")

        self.log_contents = []

        while True:

            try:
                bline = await asyncio.wait_for(process.stdout.readline(), timeout=60)
            except asyncio.TimeoutError:
                # 超时后调用回调函数
                await self.do_callback()
                continue

            line = ANSI_ESCAPE_RE.sub("", decode_bytes(bline))
            self.log_contents.append(line)
            await self.update_latest_timestamp(line)

            if datetime.now() - self.last_callback_time > timedelta(seconds=0.1):
                await self.do_callback()

    async def do_callback(self):
        """安全调用回调函数"""
        self.last_callback_time = datetime.now()
        try:
            await self.callback(self.log_contents, self.latest_time)
        except Exception as e:
            logger.error(f"回调函数执行失败: {e}")

    async def update_latest_timestamp(self, log: str, if_init: bool = False) -> None:

        if if_init:
            self.last_log = log
            self.latest_time = datetime.now()
            return

        if any(_ in log for _ in self.except_logs):
            return

        with suppress(IndexError, ValueError):
            log_text = log[: self.time_start] + log[self.time_end :]
            if log_text != self.last_log:
                self.latest_time = strptime(
                    log[self.time_start : self.time_end],
                    self.time_format,
                    self.last_callback_time,
                )
                self.last_log = log_text

    async def start_monitor_file(
        self, log_file_path: Path, start_time: datetime
    ) -> None:
        """
        开始监控日志文件

        Args:
            log_file_path (Path): 日志文件路径
            start_time (datetime): 日志时间戳起始时间
        """

        if log_file_path.is_dir():
            raise ValueError(f"日志文件不能是目录: {log_file_path}")

        if self.task is not None and not self.task.done():
            await self.stop()

        self.task = asyncio.create_task(self.monitor_file(log_file_path, start_time))
        logger.info(f"日志文件监控已启动: {log_file_path}")

    async def start_monitor_process(self, process: asyncio.subprocess.Process) -> None:
        """
        开始监控进程日志

        Args:
            process (asyncio.subprocess.Process): 进程对象
        """

        if self.task is not None and not self.task.done():
            await self.stop()

        self.task = asyncio.create_task(self.monitor_process(process))
        logger.info(f"进程日志监控已启动: {process.pid}")

    async def stop(self):
        """停止监控"""

        logger.info("请求取消日志监控任务")

        if self.task is not None and not self.task.done():
            self.task.cancel()

            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("日志监控任务已中止")

        logger.success("日志监控任务已停止")
        self.task = None
