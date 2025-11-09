#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 AUTO-MAS Team

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
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Callable, Optional, List, Awaitable

from app.utils.constants import TIME_FIELDS
from app.utils.logger import get_logger

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
            raise ValueError("日志文件路径未设置或文件不存在")

        logger.info(f"开始监控日志文件: {self.log_file_path}")

        if_mtime_checked = False

        while True:
            logger.debug("正在检查日志文件...")
            log_contents = []
            if_log_start = False

            # 检查文件是否仍然存在
            if not self.log_file_path.exists():
                logger.warning(f"日志文件不存在: {self.log_file_path}")
                await asyncio.sleep(1)
                continue

            if not if_mtime_checked:
                if (
                    date.fromtimestamp(self.log_file_path.stat().st_mtime)
                    == date.today()
                ):
                    if_mtime_checked = True
                else:
                    logger.warning(
                        f"日志文件今天未被修改: {date.fromtimestamp(self.log_file_path.stat().st_mtime)}"
                    )
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
                                entry_time = strptime(
                                    line[
                                        self.time_stamp_range[
                                            0
                                        ] : self.time_stamp_range[1]
                                    ],
                                    self.time_format,
                                    self.last_callback_time,
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

            await asyncio.sleep(1)

    async def start(self, log_file_path: Path, start_time: datetime) -> None:
        """启动监控"""

        if log_file_path.is_dir():
            raise ValueError(f"日志文件不能是目录: {log_file_path}")

        if self.task is not None and not self.task.done():
            await self.stop()

        self.log_contents = []
        self.log_file_path = log_file_path
        self.log_start_time = start_time
        self.task = asyncio.create_task(self.monitor_log())
        logger.info(f"日志监控已启动: {self.log_file_path}")

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
