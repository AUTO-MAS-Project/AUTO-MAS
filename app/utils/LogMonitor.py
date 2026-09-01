#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import asyncio
import time

import aiofiles
from contextlib import suppress
from datetime import datetime, timedelta, date
from copy import copy
from pathlib import Path
from typing import Callable, Literal, Awaitable

from .constants import TIME_FIELDS, ANSI_ESCAPE_RE
from .logger import get_logger
from .tools import decode_bytes

logger = get_logger("日志监控器")

# 排空旧日志失败时的最大重试轮次，超过后放弃旧文件剩余内容继续切换
_DRAIN_RETRY_LIMIT = 5


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
        callback: Callable[[list[str], datetime], Awaitable[None]],
        except_logs: list[str] | None = None,
        parse_log: Callable[[list[str]], list[str]] | None = None,
        line_hook: Callable[[str], str | None] | None = None,
    ):
        self.time_start = time_stamp_range[0]
        self.time_end = time_stamp_range[1]
        self.time_format = time_format
        self.callback = callback
        self.except_logs = except_logs or []
        self.parse_log = parse_log
        # 日志处理钩子：日志行进入日志内容前逐行预处理（改写）或丢弃
        self.line_hook = line_hook
        self.last_callback_time: datetime = datetime.now()
        # 节流判定用的单调时钟读数。last_callback_time 还要充当 strptime 的
        # 基准日期，必须保持墙钟；而墙钟回拨会让节流差值变成负数，接下来
        # 「跳变幅度」那么久都不再触发回调——文件监控没有兜底超时，停滞
        # 判定与界面状态会一起冻结。
        self.last_callback_at = time.monotonic()
        self.log_contents: list[str] = []
        self.latest_time = datetime.now()
        # 最近一次日志推进的单调时钟读数。停滞判定必须用单调时钟：
        # latest_time 与 datetime.now() 都是墙钟，系统时钟跳变（夏令时切换、
        # NTP 校时）会让两者的差值凭空增加一小时，把正常任务误判为超时。
        self.latest_progress_at = time.monotonic()
        self.task: asyncio.Task | None = None

    async def monitor_file(
        self,
        log_file_path_resolver: Callable[[], Path],
        log_start_time: datetime,
        bak_log_path: Path | None = None,
    ):
        """监控日志文件

        ``log_file_path_resolver`` 每轮循环重新解析路径。用于监控按日期滚动
        的日志（如 M9A 的 ``logs/log-YYYYMMDD.log``）：任务跨过本地午夜时，
        被监控脚本会写入新文件，固定路径会导致再也读不到新行。
        """

        current_path = log_file_path_resolver()
        logger.info(f"开始监控日志文件: {current_path}")

        await self.update_latest_timestamp("", if_init=True)

        if_mtime_checked = False
        warned_mtime_date: date | None = None
        if_log_start = False
        offset = 0
        log_contents = []
        # 按路径记忆读取偏移：时钟回拨可能让解析出的路径倒退回昨天，
        # 若一律从 0 重读会把整份旧日志重复摄入。
        read_offsets: dict[Path, int] = {current_path: 0}
        drain_failures = 0

        while True:
            # 日志按日期滚动（如 M9A 的 log-YYYYMMDD.log）时切换到新文件。
            try:
                resolved = log_file_path_resolver()
            except Exception as e:
                # 解析器异常不应让监控任务静默死亡，否则调用方会永久挂起
                logger.warning(f"日志路径解析失败，沿用当前路径: {e}")
                resolved = current_path

            if resolved != current_path:
                # 必须先读完旧文件的剩余内容：轮询间隔内被监控进程可能刚往
                # 旧文件写了完成或失败标志，直接切换会永久丢掉这些行。
                drain_error = None
                if current_path.is_file():
                    offset, if_log_start, drain_error = await self._consume_new_lines(
                        current_path,
                        offset,
                        log_contents,
                        if_log_start,
                        log_start_time,
                    )
                if drain_error is not None and drain_failures < _DRAIN_RETRY_LIMIT:
                    drain_failures += 1
                    logger.warning(
                        f"排空旧日志失败（第 {drain_failures} 次），本轮不切换: {drain_error}"
                    )
                    await asyncio.sleep(1)
                    continue
                if drain_error is not None:
                    logger.warning(f"排空旧日志连续失败，放弃其剩余内容: {drain_error}")
                drain_failures = 0

                # 排空所得必须立刻同步并回调：新文件可能尚未创建，下方
                # 「文件不存在」分支会 continue，绕过循环底部的同步，让刚
                # 读到的完成或失败标志永远到不了回调。
                await self._sync_and_callback(log_contents)

                logger.info(
                    f"日志文件已滚动，切换监控目标: {current_path} -> {resolved}"
                )
                # log_contents 与 if_log_start 保留：滚动前后属于同一次运行，
                # 清空会丢掉午夜前累积的全部日志，历史记录也只剩后半截。
                read_offsets[current_path] = offset
                current_path = resolved
                if_mtime_checked = False
                warned_mtime_date = None
                offset = read_offsets.get(current_path, 0)

            # 检查文件是否仍然存在
            if not current_path.exists():
                logger.warning(f"日志文件不存在: {current_path}")
                await self.do_callback()
                await asyncio.sleep(1)
                continue

            if not if_mtime_checked:
                file_mtime_date = date.fromtimestamp(current_path.stat().st_mtime)
                if file_mtime_date == date.today():
                    log_stat = current_path.stat()
                    if_mtime_checked = True
                else:
                    if warned_mtime_date != file_mtime_date:
                        logger.warning(f"日志文件今天未被修改: {file_mtime_date}")
                        warned_mtime_date = file_mtime_date
                    await self.do_callback()
                    await asyncio.sleep(1)
                    continue

            # 尝试读取文件
            try:
                # 发生日志轮转或文件被替换，重置监控状态并加载被轮换的旧日志
                if (
                    log_stat.st_ino != current_path.stat().st_ino
                    or log_stat.st_size > current_path.stat().st_size
                ):
                    offset = 0
                    log_contents = []
                    if_log_start = False
                    if bak_log_path is not None and bak_log_path.exists():
                        async with aiofiles.open(bak_log_path, "rb") as f:
                            async for bline in f:
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
                                            self.append_line(log_contents, line)
                                else:
                                    self.append_line(log_contents, line)

                log_stat = current_path.stat()

                if log_stat.st_size < offset:
                    # 文件比记录的偏移还短，说明它被替换或截断过。按日期滚动
                    # 切回旧路径时最容易撞上：offset 是离开前记住的，而文件在
                    # 离开期间被换掉了，既有的缩水检测只比较在场期间的两次
                    # stat，对此天然失明。不归零就会永远落进下面的「无变化」
                    # 分支空转，新内容再也读不到。
                    logger.info(
                        f"日志文件已被替换或截断（{log_stat.st_size} < {offset}），从头重读"
                    )
                    offset = 0
                    continue

                if log_stat.st_size <= offset:
                    # 日志无变化超时调用回调
                    if time.monotonic() - self.last_callback_at > 60:
                        await self.do_callback()

                    await asyncio.sleep(1)
                    continue

                offset, if_log_start, read_error = await self._consume_new_lines(
                    current_path, offset, log_contents, if_log_start, log_start_time
                )
                if read_error is not None:
                    # 已读到的行必须先同步，否则重试期间回调看不到它们
                    await self._sync_and_callback(log_contents)
                    logger.warning(f"文件访问错误: {read_error}")
                    await asyncio.sleep(5)
                    continue

            except (FileNotFoundError, PermissionError) as e:
                logger.warning(f"文件访问错误: {e}")
                await asyncio.sleep(5)
                continue

            # 日志变化调用回调
            await self._sync_and_callback(log_contents)

            await asyncio.sleep(1)

    async def monitor_process(
        self, process: asyncio.subprocess.Process, stream: Literal["stdout", "stderr"]
    ):
        """监控进程日志"""

        logger.info(f"开始监控进程日志: {process.pid}")

        await self.update_latest_timestamp("", if_init=True)

        if hasattr(process, stream):
            process_stream = getattr(process, stream)
            if not isinstance(process_stream, asyncio.StreamReader):
                raise ValueError(f"进程没有可用的{stream}流")
        else:
            raise ValueError(f"无效的流类型: {stream}")

        self.log_contents = []

        while True:
            try:
                bline = await asyncio.wait_for(process_stream.readline(), timeout=60)
            except asyncio.TimeoutError:
                # 超时后调用回调函数
                await self.do_callback()
                continue

            line = ANSI_ESCAPE_RE.sub("", decode_bytes(bline))

            self.append_line(self.log_contents, line)
            await self.update_latest_timestamp(line)

            if process_stream.at_eof():
                logger.info("监控的流已结束")
                await self.do_callback()
                break

            if time.monotonic() - self.last_callback_at > 1:
                await self.do_callback()

    async def do_callback(self):
        """安全调用回调函数"""
        self.last_callback_time = datetime.now()
        self.last_callback_at = time.monotonic()
        try:
            if self.parse_log is None:
                await self.callback(self.log_contents, self.latest_time)
            else:
                await self.callback(
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.parse_log, self.log_contents
                    ),
                    self.latest_time,
                )
        except Exception as e:
            logger.error(f"回调函数执行失败: {e}")

    def append_line(self, log_contents: list[str], line: str) -> None:
        """经日志处理钩子后把日志行写入日志内容

        执行顺序：日志起始判定与时间戳活跃度跟踪读取原始行 → 钩子（丢弃/改写）
        → 日志内容。因此被钩子丢弃的行不会进入任务日志、推送日志采集与成功/
        失败标志判定，但不影响 latest_time，过滤噪声行不会造成误判超时。
        未挂钩子时行为与直接 append 完全一致。
        """
        if self.line_hook is None:
            log_contents.append(line)
            return
        try:
            hooked = self.line_hook(line)
        except Exception as e:
            logger.warning(f"日志处理钩子执行失败: {e}")
            log_contents.append(line)
            return
        if hooked is not None:
            log_contents.append(hooked)

    async def update_latest_timestamp(self, log: str, if_init: bool = False) -> None:

        if if_init:
            self.last_log = log
            self.latest_time = datetime.now()
            self.latest_progress_at = time.monotonic()
            return

        if log == "" or any(_ in log for _ in self.except_logs):
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
                self.latest_progress_at = time.monotonic()

    def seconds_since_progress(self) -> float:
        """距最近一次日志推进的秒数，按单调时钟计量。"""

        return time.monotonic() - self.latest_progress_at

    async def _consume_new_lines(
        self,
        path: Path,
        offset: int,
        log_contents: list[str],
        if_log_start: bool,
        log_start_time: datetime,
    ) -> tuple[int, bool, Exception | None]:
        """读取文件自 offset 起的新增行并追加到 log_contents。

        Args:
            path (Path): 日志文件路径。
            offset (int): 上次读到的字节偏移。
            log_contents (list[str]): 日志内容列表，原地追加。
            if_log_start (bool): 是否已越过本次运行的起始时刻。
            log_start_time (datetime): 本次运行的起始时刻。

        Returns:
            tuple[int, bool, Exception | None]: 新的字节偏移、if_log_start，以及
                读取过程中捕获的文件访问异常。异常必须在函数内捕获并连同已推进
                的进度一起回传：若让它逸出，调用方拿不到返回值，offset 会退回
                调用前，而 log_contents 已就地追加，重试时会重复摄入这些行。
        """

        try:
            async with aiofiles.open(path, "rb") as f:
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
                                self.append_line(log_contents, line)
                                await self.update_latest_timestamp(line)
                    else:
                        self.append_line(log_contents, line)
                        await self.update_latest_timestamp(line)
        except (FileNotFoundError, PermissionError) as e:
            return offset, if_log_start, e
        return offset, if_log_start, None

    async def _sync_and_callback(self, log_contents: list[str]) -> None:
        """日志内容有变化时同步到实例缓冲区并触发回调。

        Args:
            log_contents (list[str]): 当前轮询累积的日志内容。
        """

        if len(log_contents) != len(self.log_contents):
            self.log_contents = copy(log_contents)
            await self.do_callback()

    async def start_monitor_file(
        self,
        log_file_path_resolver: Callable[[], Path],
        start_time: datetime,
        bak_log_path: Path | None = None,
    ) -> None:
        """
        开始监控日志文件

        Args:
            log_file_path_resolver (Callable[[], Path]): 返回日志文件路径的方法；
                每轮循环重新解析，用于按日期滚动的日志
            start_time (datetime): 日志时间戳起始时间
        """

        probe_path = log_file_path_resolver()
        if probe_path.is_dir():
            raise ValueError(f"日志文件不能是目录: {probe_path}")

        if self.task is not None and not self.task.done():
            await self.stop()

        self.task = asyncio.create_task(
            self.monitor_file(log_file_path_resolver, start_time, bak_log_path)
        )
        logger.info(f"日志文件监控已启动: {probe_path}")

    async def start_monitor_process(
        self,
        process: asyncio.subprocess.Process,
        stream: Literal["stdout", "stderr"] = "stdout",
    ) -> None:
        """
        开始监控进程日志

        Args:
            process (asyncio.subprocess.Process): 进程对象
            stream (Literal["stdout", "stderr"]): 流对象
        """

        if self.task is not None and not self.task.done():
            await self.stop()

        self.task = asyncio.create_task(self.monitor_process(process, stream))
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
