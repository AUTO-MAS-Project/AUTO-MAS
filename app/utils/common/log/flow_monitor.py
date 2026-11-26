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
import os
import time
from contextlib import suppress
from datetime import date, datetime
from pathlib import Path
from typing import Awaitable, Callable, Literal

import aiofiles

from app.utils.common.constants import ANSI_ESCAPE_RE
from app.utils.common.tools import decode_bytes

from .flow_file import LOG_READ_OPENER, file_identity
from .monitor import _DRAIN_RETRY_LIMIT, LogMonitor, _ProcessOutput, logger, strptime

_STOP_DRAIN_SECONDS = 1.0


class _LogIdentityChanged(OSError):
    """路径在检查与打开之间指向了另一个文件。"""


class LogFlowMonitor(LogMonitor):
    """供主动接入 LogFlow 的执行方使用，复用原生日志的回调和时间解析。"""

    def __init__(
        self,
        time_stamp_range: tuple[int, int],
        time_format: str,
        callback: Callable[[list[str], datetime], Awaitable[None]],
        except_logs: list[str] | None = None,
        parse_log: Callable[[list[str]], list[str]] | None = None,
        line_hook: Callable[[str], str | None] | None = None,
        *,
        on_raw_line: Callable[[str], None] | None = None,
    ):
        super().__init__(
            time_stamp_range,
            time_format,
            callback,
            except_logs=except_logs,
            parse_log=parse_log,
            line_hook=line_hook,
        )
        self.on_raw_line = on_raw_line
        self.on_raw_incomplete: Callable[[str], None] | None = None
        self._file_stop: asyncio.Event | None = None

    async def monitor_file(
        self,
        log_file_path_resolver: Callable[[], Path],
        log_start_time: datetime,
        initial_offset: int | None = None,
        *,
        stop_event: asyncio.Event | None = None,
    ) -> bool:
        """监控日志文件

        ``log_file_path_resolver`` 每轮循环重新解析路径。用于监控按日期滚动
        的日志（如 M9A 的 ``logs/log-YYYYMMDD.log``）：任务跨过本地午夜时，
        被监控脚本会写入新文件，固定路径会导致再也读不到新行。

        ``initial_offset`` 是首个监控文件的起始字节偏移，供追加写且跨运行
        保留的日志使用：被监控进程由调用方启动时，把启动前的文件长度传进来，
        本次运行之前的历史内容就不会被摄入（起始判定只看时间戳，无法分辨
        历史内容里时间戳更晚的旧行）。
        """

        current_path = log_file_path_resolver()
        logger.info(f"开始监控日志文件: {current_path}")

        await self.update_latest_timestamp("", if_init=True)

        if_mtime_checked = False
        warned_mtime_date: date | None = None
        if_log_start = False
        offset = initial_offset if initial_offset is not None else 0
        initial_path = current_path if initial_offset is not None else None
        log_stat: os.stat_result | None = None
        log_contents = []
        # 日期路径可能因时钟回拨而重访。偏移必须与当时的文件状态一起恢复。
        read_positions: dict[Path, tuple[int, os.stat_result | None]] = {}
        drain_failures = 0
        stop_requested = stop_event if stop_event is not None else asyncio.Event()

        async def pause(seconds: float) -> None:
            with suppress(TimeoutError):
                async with asyncio.timeout(seconds):
                    await stop_requested.wait()

        final_poll = False
        incomplete = False
        while not final_poll:
            final_poll = stop_requested.is_set()
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
                expected_id = file_identity(log_stat) if log_stat is not None else None
                if expected_id is not None or current_path.is_file():
                    (
                        offset,
                        if_log_start,
                        drain_error,
                    ) = await self._consume_stream_lines(
                        current_path,
                        offset,
                        log_contents,
                        if_log_start,
                        log_start_time,
                        expected_id=expected_id,
                        allow_partial=final_poll,
                    )
                if expected_id is not None and isinstance(
                    drain_error, (FileNotFoundError, _LogIdentityChanged)
                ):
                    offset, if_log_start, drain_error = await self._read_rotated_tail(
                        current_path,
                        expected_id,
                        offset,
                        log_contents,
                        if_log_start,
                        log_start_time,
                        missing_is_error=True,
                    )
                if (
                    drain_error is not None
                    and not final_poll
                    and drain_failures < _DRAIN_RETRY_LIMIT
                ):
                    drain_failures += 1
                    logger.warning(
                        f"排空旧日志失败（第 {drain_failures} 次），本轮不切换: {drain_error}"
                    )
                    await pause(1)
                    continue
                if drain_error is not None:
                    incomplete = True
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
                read_positions[current_path] = offset, log_stat
                current_path = resolved
                # 刷新 strptime 的基准日期：BetterGI 这类无日期的时间格式靠
                # last_callback_time 补日期，若切换轮次里旧文件没有新行、没有
                # 触发回调，它仍停留在前一天，新文件首行会被归到 24 小时前，
                # check_log 随即误判超时。必须在排空旧文件之后再刷新。
                self.last_callback_time = datetime.now()
                if_mtime_checked = False
                warned_mtime_date = None
                offset, log_stat = read_positions.get(current_path, (0, None))

            # 尝试读取文件
            try:
                current_stat = current_path.stat()
                if current_path == initial_path:
                    if_log_start = offset <= current_stat.st_size
                    initial_path = None
                if not if_mtime_checked:
                    file_mtime_date = date.fromtimestamp(current_stat.st_mtime)
                    if file_mtime_date == date.today():
                        if_mtime_checked = True
                    else:
                        if final_poll:
                            return False
                        if warned_mtime_date != file_mtime_date:
                            logger.warning(f"日志文件今天未被修改: {file_mtime_date}")
                            warned_mtime_date = file_mtime_date
                        await self.do_callback()
                        await pause(1)
                        continue

                # 轮转或文件被替换（同一路径上换了文件身份）：滚动前后属于
                # 同一次运行，log_contents 与 if_log_start 保留不清空，否则
                # 落库历史只剩轮转后内容（跨零点实测）；被重命名的旧文件按
                # 文件身份在同目录找回，把未读尾部接回来。身份规则与主动文件源共用。
                current_id = file_identity(current_stat)
                previous_id = (
                    file_identity(log_stat) if log_stat is not None else current_id
                )
                if log_stat is not None and (
                    previous_id != current_id or log_stat.st_size > current_stat.st_size
                ):
                    _, if_log_start, recovery_error = await self._read_rotated_tail(
                        current_path,
                        previous_id,
                        offset,
                        log_contents,
                        if_log_start,
                        log_start_time,
                        missing_is_error=previous_id != current_id,
                    )
                    if recovery_error is not None:
                        logger.warning(f"轮转旧日志读取失败: {recovery_error}")
                        incomplete = True
                    # 新文件可能没有新行，先交付刚补读的旧文件尾部。
                    await self._sync_and_callback(log_contents)
                    offset = 0
                    # 与上面路径切换分支同理：排空可能一行未得（旧文件在轮转
                    # 前一轮已读空），无行触发回调时 last_callback_time 仍停在
                    # 轮转前；无日期时间格式的跨零点首行会被补到 24 小时前，
                    # check_log 随即误判运行超时（ZZZ-OD 实测）。必须在找回
                    # 之后刷新
                    self.last_callback_time = datetime.now()

                log_stat = current_stat

                if log_stat.st_size < offset:
                    # 启动前记下的初始偏移可能已因截断而失效。
                    logger.info(
                        f"日志文件已被替换或截断（{log_stat.st_size} < {offset}），从头重读"
                    )
                    offset = 0
                    if not final_poll:
                        continue

                if log_stat.st_size <= offset:
                    # 日志无变化超时调用回调
                    if time.monotonic() - self.last_callback_at > 60:
                        await self.do_callback()

                    await pause(1)
                    continue

                offset, if_log_start, read_error = await self._consume_stream_lines(
                    current_path,
                    offset,
                    log_contents,
                    if_log_start,
                    log_start_time,
                    expected_id=current_id,
                    allow_partial=final_poll,
                )
                if read_error is not None:
                    # 已读到的行必须先同步，否则重试期间回调看不到它们
                    await self._sync_and_callback(log_contents)
                    logger.warning(f"文件访问错误: {read_error}")
                    if final_poll:
                        return False
                    await pause(1 if isinstance(read_error, _LogIdentityChanged) else 5)
                    continue

            except (FileNotFoundError, PermissionError) as e:
                logger.warning(f"文件访问错误: {e}")
                if final_poll:
                    if not isinstance(e, FileNotFoundError):
                        return False
                    if log_stat is None:
                        return not incomplete
                    _, _, error = await self._read_rotated_tail(
                        current_path,
                        file_identity(log_stat),
                        offset,
                        log_contents,
                        if_log_start,
                        log_start_time,
                        missing_is_error=True,
                    )
                    await self._sync_and_callback(log_contents)
                    return error is None and not incomplete
                # 日志尚未创建或被短暂锁定时也要推进回调；否则调用方的
                # 停滞超时永远没有机会判定，任务会无限等待。
                await self.do_callback()
                await pause(5)
                continue

            # 日志变化调用回调
            await self._sync_and_callback(log_contents)
            # 读到未闭合行时偏移可能不动，仍需给执行侧机会检查停滞。
            if not final_poll and time.monotonic() - self.last_callback_at > 60:
                await self.do_callback()

            await pause(1)
        return not incomplete

    async def monitor_process(
        self,
        process: _ProcessOutput,
        stream: Literal["stdout", "stderr"],
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
        discarding_line = False

        while True:
            # 订阅需要确认被舍弃行的分隔符，避免下一次读取发布该行的残段。
            read_line = (
                process_stream.readuntil
                if self.on_raw_line is not None or discarding_line
                else process_stream.readline
            )
            try:
                bline = await asyncio.wait_for(read_line(), timeout=60)
            except asyncio.TimeoutError:
                # 超时后调用回调函数
                await self.do_callback()
                continue
            except asyncio.IncompleteReadError as exc:
                bline = exc.partial
            except asyncio.LimitOverrunError as exc:
                await process_stream.readexactly(exc.consumed)
                if not discarding_line:
                    detail = "进程输出中有一行超过读取上限，已丢弃整行"
                    logger.warning(detail)
                    if self.on_raw_incomplete is not None:
                        self.on_raw_incomplete(detail)
                discarding_line = True
                continue
            except ValueError:
                # 单行超过 StreamReader 的读取上限（默认 64 KiB）时 readline 抛
                # ValueError；已读入的超限部分在抛出前被丢弃，下一次 readline 可以接着读，
                # 该行尚未到达的剩余部分会作为一条新行继续处理。
                logger.warning("进程输出中有一行超过读取上限，已丢弃超限部分")
                continue

            if discarding_line:
                discarding_line = False
                if not process_stream.at_eof():
                    continue
                bline = b""

            line = ANSI_ESCAPE_RE.sub("", decode_bytes(bline))

            if bline:
                self._publish_raw_line(line)
            self.append_line(self.log_contents, line)
            await self.update_latest_timestamp(line)

            if process_stream.at_eof():
                logger.info("监控的流已结束")
                await self.do_callback()
                break

            if time.monotonic() - self.last_callback_at > 1:
                await self.do_callback()

    def _publish_raw_line(self, line: str) -> None:
        if self.on_raw_line is not None:
            try:
                self.on_raw_line(line)
            except Exception as exc:
                # 可选观察方失败不能中断执行侧原有日志和状态判定。
                self.on_raw_line = None
                logger.error(f"日志分发失败，停止本轮分发: {exc}")

    async def _consume_stream_lines(
        self,
        path: Path,
        offset: int,
        log_contents: list[str],
        if_log_start: bool,
        log_start_time: datetime,
        *,
        expected_id: tuple[int, int] | None = None,
        allow_partial: bool = False,
    ) -> tuple[int, bool, Exception | None]:
        """读取文件自 offset 起的新增行并追加到 log_contents。

        Args:
            path (Path): 日志文件路径。
            offset (int): 上次读到的字节偏移。
            log_contents (list[str]): 日志内容列表，原地追加。
            if_log_start (bool): 是否已越过本次运行的起始时刻。
            log_start_time (datetime): 本次运行的起始时刻。
            expected_id: 此偏移所属的文件身份。打开后复核，避免轮转时从新文件的旧偏移读取。

        Returns:
            tuple[int, bool, Exception | None]: 新的字节偏移、if_log_start，以及
                读取过程中捕获的文件访问异常。异常必须在函数内捕获并连同已推进
                的进度一起回传：若让它逸出，调用方拿不到返回值，offset 会退回
                调用前，而 log_contents 已就地追加，重试时会重复摄入这些行。
        """

        try:
            async with aiofiles.open(path, "rb", opener=LOG_READ_OPENER) as f:
                if expected_id is not None:
                    opened_stat = await asyncio.to_thread(os.fstat, f.fileno())
                    if file_identity(opened_stat) != expected_id:
                        raise _LogIdentityChanged("打开日志时文件已轮转")
                await f.seek(offset)
                async for bline in f:
                    if (
                        self.on_raw_line is not None
                        and not allow_partial
                        and not bline.endswith(b"\n")
                    ):
                        # 流式订阅只接收完整行。保留偏移，下轮从该行开头续读。
                        break
                    offset = await f.tell()
                    line = decode_bytes(bline)
                    if not if_log_start:
                        with suppress(IndexError, ValueError):
                            entry_time = strptime(
                                line[self.time_start : self.time_end],
                                self.time_format,
                                self.last_callback_time,
                            )
                            # 上游日志沿用本机时钟；任务开始时刻改为带偏移后，在监控边界显式比较本地钟点。
                            comparison_start = (
                                log_start_time.astimezone().replace(tzinfo=None)
                                if log_start_time.utcoffset() is not None
                                else log_start_time
                            )
                            if entry_time > comparison_start:
                                if_log_start = True
                    if if_log_start:
                        self._publish_raw_line(line)
                        self.append_line(log_contents, line)
                        await self.update_latest_timestamp(line)
        except (FileNotFoundError, PermissionError, _LogIdentityChanged) as e:
            return offset, if_log_start, e
        return offset, if_log_start, None

    def _find_stream_rotation(
        self, current_path: Path, old_file_id: tuple[int, int]
    ) -> Path | None:
        """按文件身份在同目录里找回被重命名的旧日志文件。

        固定路径监控下，脚本把正在写的日志重命名滚动（如跨零点
        ``log.txt`` → ``log.txt.YYYY-MM-DD``）后，同目录里持有旧身份的
        那个文件就是它：重命名前后是同一文件，离开时记录的 offset 逐字节
        对应，不依赖任何命名猜测，也不会误读同名旧残留。旧文件已被删除或
        文件系统不提供 inode（st_ino 为 0）时返回 None。
        """

        if not old_file_id[0]:
            return None
        try:
            for candidate in current_path.parent.iterdir():
                if candidate == current_path or not candidate.is_file():
                    continue
                try:
                    if file_identity(candidate.stat()) == old_file_id:
                        return candidate
                except OSError:
                    continue
        except OSError:
            return None
        return None

    async def _read_rotated_tail(
        self,
        current_path: Path,
        old_file_id: tuple[int, int],
        offset: int,
        log_contents: list[str],
        if_log_start: bool,
        log_start_time: datetime,
        *,
        missing_is_error: bool = False,
    ) -> tuple[int, bool, Exception | None]:
        """按身份找到旧文件，续读未读尾部并返回该文件的读取进度。

        Args:
            current_path: 监控目标路径（轮转后指向新文件）
            old_file_id: 轮转前记录的旧文件身份
            offset: 离开旧文件时的读取偏移
            log_contents: 累积中的日志内容（就地追加找回的行）
            if_log_start: 是否已越过本次运行的起始时刻
            log_start_time: 本次运行的起始时刻
            missing_is_error: 末次读取时，找不到旧文件则返回异常。

        Returns:
            旧文件的字节偏移、是否越过运行起点，以及读取错误。
        """

        rotated = self._find_stream_rotation(current_path, old_file_id)
        if rotated is None:
            error = (
                FileNotFoundError("无法定位已轮转的日志文件")
                if missing_is_error
                else None
            )
            return offset, if_log_start, error
        return await self._consume_stream_lines(
            rotated,
            offset,
            log_contents,
            if_log_start,
            log_start_time,
            expected_id=old_file_id,
            allow_partial=True,
        )

    async def start_monitor_file(
        self,
        log_file_path_resolver: Callable[[], Path],
        start_time: datetime,
        initial_offset: int | None = None,
    ) -> None:
        """
        开始监控日志文件

        Args:
            log_file_path_resolver (Callable[[], Path]): 返回日志文件路径的方法；
                每轮循环重新解析，用于按日期滚动的日志
            start_time (datetime): 日志时间戳起始时间
            initial_offset (int | None): 首个监控文件的起始字节偏移，用于追加写
                且跨运行保留的日志：传入被监控进程启动前的文件长度，只有本次
                运行新写的行会被读取；为 None 时从文件头开始读
        """

        probe_path = log_file_path_resolver()
        if probe_path.is_dir():
            raise ValueError(f"日志文件不能是目录: {probe_path}")

        if self.task is not None and not self.task.done():
            await self.stop()
            if self.task is not None and not self.task.done():
                raise RuntimeError("旧日志监控仍在收尾，无法启动新监控")

        self._file_stop = asyncio.Event()
        self.task = asyncio.create_task(
            self.monitor_file(
                log_file_path_resolver,
                start_time,
                initial_offset,
                stop_event=self._file_stop,
            )
        )
        logger.info(f"日志文件监控已启动: {probe_path}")

    async def start_monitor_process(
        self,
        process: _ProcessOutput,
        stream: Literal["stdout", "stderr"] = "stdout",
    ) -> None:
        """
        开始监控进程日志

        Args:
            process: 本机进程或桌面分身进程代理
            stream (Literal["stdout", "stderr"]): 流对象
        """

        if self.task is not None and not self.task.done():
            await self.stop()
            if self.task is not None and not self.task.done():
                raise RuntimeError("旧日志监控仍在收尾，无法启动新监控")

        self._file_stop = None
        self.task = asyncio.create_task(self.monitor_process(process, stream))
        logger.info(f"进程日志监控已启动: {process.pid}")

    @staticmethod
    def _report_cancelled_monitor_failure(task: asyncio.Task) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.warning(f"日志监控取消失败: {error}")

    async def _cancel_after_failed_drain(self, task: asyncio.Task) -> None:
        if task.done():
            self._report_cancelled_monitor_failure(task)
            return
        task.cancel()
        try:
            await asyncio.wait((task,), timeout=_STOP_DRAIN_SECONDS)
        finally:
            if task.done():
                self._report_cancelled_monitor_failure(task)
            else:
                # 保留引用和错误处理，拒绝在旧读取结束前换上新的监控任务。
                task.add_done_callback(self._report_cancelled_monitor_failure)

    async def stop(self):
        """停止监控；有原始行订阅时，在同一期限内排空文件或进程管道。"""

        logger.info("请求取消日志监控任务")

        task = self.task
        file_stop = self._file_stop
        try:
            if task is not None and self.on_raw_line is not None:
                on_incomplete = self.on_raw_incomplete
                if file_stop is not None:
                    file_stop.set()
                drained = False
                try:
                    done, _ = await asyncio.wait((task,), timeout=_STOP_DRAIN_SECONDS)
                    if done and not task.cancelled():
                        result = task.result()
                        drained = file_stop is None or result
                except Exception as exc:
                    logger.warning(f"日志监控末次读取失败: {exc}")
                finally:
                    if not drained:
                        try:
                            if on_incomplete is not None:
                                source = "文件" if file_stop is not None else "进程"
                                on_incomplete(f"原生{source}日志未能完成末次读取")
                            logger.warning("日志监控未能完成末次读取")
                        finally:
                            await self._cancel_after_failed_drain(task)
            elif task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("日志监控任务已中止")
        finally:
            if self.task is task and (task is None or task.done()):
                self.task = None
                self._file_stop = None
        if task is not None and not task.done():
            logger.warning("日志监控仍在收尾，已保留任务等待退出")
        else:
            logger.success("日志监控任务已停止")
