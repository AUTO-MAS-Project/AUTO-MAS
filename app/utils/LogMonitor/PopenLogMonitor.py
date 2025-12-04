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
from datetime import datetime, timedelta
from subprocess import Popen
from typing import Callable, Optional, List, Awaitable, Literal

from app.utils.constants import TIME_FIELDS
from app.utils import get_logger

logger = get_logger("进程日志监控器")


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


class PopenLogMonitor:
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
        self.process: Optional[Popen] = None
        self.stream_type: Literal["stdout", "stderr"] = "stdout"
        self.log_start_time: datetime = datetime.now()
        self.last_callback_time: datetime = datetime.now()
        self.log_contents: List[str] = []
        self.task: Optional[asyncio.Task] = None

    async def monitor_log(self):
        """监控进程输出流的主循环"""
        if self.process is None:
            raise ValueError("进程实例未设置")

        # 获取对应的输出流
        stream = getattr(self.process, self.stream_type)
        if stream is None:
            raise ValueError(
                f"进程的 {self.stream_type} 流未被捕获（需要在创建 Popen 时设置为 PIPE）"
            )

        logger.info(f"开始监控进程 {self.stream_type} 输出")

        log_contents = []
        if_log_start = False

        try:
            # 读取输出流
            while True:
                # 检查进程是否还在运行
                if self.process.poll() is not None:
                    logger.info(f"进程已结束，退出码: {self.process.returncode}")
                    # 读取剩余的输出
                    remaining = stream.read()
                    if remaining:
                        for line in remaining.decode(
                            self.encoding, errors="replace"
                        ).splitlines(keepends=True):
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
                                    log_contents.append(line)  # 没有时间戳的行也追加
                            else:
                                log_contents.append(line)

                    # 最后一次回调
                    if log_contents != self.log_contents:
                        self.log_contents = log_contents
                        self.last_callback_time = datetime.now()
                        try:
                            await self.callback(log_contents)
                        except Exception as e:
                            logger.error(f"回调函数执行失败: {e}")
                    break

                # 非阻塞地读取一行
                # 使用 asyncio 的方式异步读取
                loop = asyncio.get_event_loop()
                line_bytes = await loop.run_in_executor(None, stream.readline)

                if not line_bytes:
                    # 如果没有读到数据，短暂等待
                    await asyncio.sleep(0.1)
                    continue

                try:
                    line = line_bytes.decode(self.encoding, errors="replace")
                except UnicodeDecodeError as e:
                    logger.error(f"解码错误: {e}")
                    continue

                # 处理日志行
                if not if_log_start:
                    try:
                        entry_time = strptime(
                            line[self.time_stamp_range[0] : self.time_stamp_range[1]],
                            self.time_format,
                            self.last_callback_time,
                        )
                        if entry_time > self.log_start_time:
                            if_log_start = True
                            log_contents.append(line)
                    except (ValueError, IndexError):
                        # 没有时间戳或解析失败，忽略此行
                        continue
                else:
                    log_contents.append(line)

                # 定期调用回调
                if (
                    log_contents != self.log_contents
                    or datetime.now() - self.last_callback_time > timedelta(minutes=1)
                ):
                    self.log_contents = log_contents.copy()
                    self.last_callback_time = datetime.now()

                    # 安全调用回调函数
                    try:
                        await self.callback(log_contents)
                    except Exception as e:
                        logger.error(f"回调函数执行失败: {e}")

        except Exception as e:
            logger.error(f"监控过程中发生错误: {e}")
        finally:
            logger.info("进程日志监控已结束")

    async def start(
        self,
        process: Popen,
        start_time: datetime,
        stream_type: Literal["stdout", "stderr"] = "stdout",
    ) -> None:
        """启动监控

        Args:
            process: subprocess.Popen 实例
            start_time: 开始时间，只记录此时间之后的日志
            stream_type: 要监控的流类型，"stdout" 或 "stderr"，默认为 "stdout"
        """
        if self.task is not None and not self.task.done():
            await self.stop()

        self.log_contents = []
        self.process = process
        self.stream_type = stream_type
        self.log_start_time = start_time
        self.task = asyncio.create_task(self.monitor_log())
        logger.info(f"进程日志监控已启动，监控 {stream_type}")

    async def stop(self):
        """停止监控"""
        logger.info("请求取消进程日志监控任务")

        if self.task is not None and not self.task.done():
            self.task.cancel()

            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("进程日志监控任务已中止")

        logger.success("进程日志监控任务已停止")
        self.task = None
