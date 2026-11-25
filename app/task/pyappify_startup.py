"""基于 pyappify 启动器可见日志的有界进程等待。"""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Coroutine
from pathlib import Path
from typing import Any

from app.utils.common.log.sources import LogSource

_START_TIMEOUT = 60.0
# 新进展后的静默上限：非 tty 下 pip 输出「Downloading 包名」一行后静默下载，
# 大包慢速下载期可长时间无完整新行，窗口须覆盖（量级对齐启动器交互的
# 下载顺延等待，launcher_start._UPDATE_ACTIVE_GRACE_SECONDS 为 600 秒）。
_UPDATE_STALL_TIMEOUT = 900.0
# 重复进展持续刷屏的上限，静默阶段不计入刷屏时长。
_REPEAT_STALL_TIMEOUT = 300.0
# 重试循环仍在进行时旧进展会在一分钟内再次出现；更久远的单次重复不构成
# 持续刷屏，不得让刷屏判定在静默下载期保持武装。
_REPEAT_ACTIVE_WINDOW = 60.0
_TOTAL_TIMEOUT = 1800.0
# 启动器日志按日滚动命名（上游按 UTC 日期）；只认日期形态的文件，排除
# app.previous 等轮转产物——轮转补偿由 LogSource 按文件身份处理。
_LOG_NAME = re.compile(r"app\.\d{4}-\d{2}-\d{2}")
_UPDATE_FAILURE = re.compile(r"Update to version ([A-Za-z0-9_.+-]+) failed:")
_UPDATE_STATE_FAILURES = {
    "Failed to record update progress:": "启动器无法记录升级进度，请查看启动器日志",
    "Update completed, but its state could not be saved:": "启动器无法保存升级结果，请查看启动器日志",
}
_PIP_READ_TIMEOUT = "pip._vendor.urllib3.exceptions.ReadTimeoutError:"
_EXIT_CODE = re.compile(r"exit code: (-?\d+)$")
# 仅匹配启动器可见输出，不消费 app.json 的内部更新状态。
_UPDATE_CHECK = (
    "Fetching updates for existing repository",
    "Fetch complete.",
    "Fetching all tags",
)
_UPDATE_PROGRESS = (
    "Fetching refspec:",
    "Successfully checked out",
    "Checked out commit",
    "Content of 'requirements.txt' changed. Syncing dependencies.",
    "Collecting ",
    "Downloading ",
    "Installing collected packages:",
    "Successfully installed ",
)


def open_launcher_logs(log_dir: Path) -> dict[Path, LogSource]:
    """启动前记录已有日志的末尾，跳过此前会话的输出。"""
    sources: dict[Path, LogSource] = {}
    for path in log_dir.glob("app.*"):
        if not path.is_file() or not _LOG_NAME.fullmatch(path.name):
            continue
        source = LogSource(path)
        source.open()
        sources[path] = source

    return sources


async def wait_for_launcher_process(
    log_dir: Path,
    sources: dict[Path, LogSource],
    *,
    app_id: str,
    started: float,
    search_process: Callable[[float], Coroutine[Any, Any, None]],
    on_log: Callable[[str], Awaitable[None]],
    check_lines: Callable[[list[str]], None] | None = None,
    include_update_check: bool = True,
) -> None:
    """等待本体出现，仅用新增且未见过的更新进展延长等待。"""
    label = app_id.upper()
    emitter = f"pyappify_lib::emitter: INFO [{app_id}]: "
    error_emitter = f"pyappify_lib::emitter: ERROR [{app_id}]: "
    update_start = f"pyappify_lib::app_service: Updating {app_id} to version "
    progress_prefixes = (
        _UPDATE_CHECK + _UPDATE_PROGRESS if include_update_check else _UPDATE_PROGRESS
    )
    deadline = started + _START_TIMEOUT
    updating = False
    pip_read_timed_out = False
    update_version = ""
    last_repeat: float | None = None
    repeat_started: float | None = None
    # 会话内去重，避免依赖下载重试交替刷同一组消息而不断续时。
    progress: set[str] = set()

    def read_logs() -> list[str]:
        # 启动器日志按日滚动且上游按 UTC 日期命名（本地凌晨时 UTC
        # 当日即本地昨天），不按本地日期猜文件名；每轮扫描目录接入
        # 新出现的日志文件。启动前已存在的文件已按当前末尾接入。
        for path in log_dir.glob("app.*"):
            if path in sources or not path.is_file():
                continue
            if not _LOG_NAME.fullmatch(path.name):
                continue
            source = LogSource(path, start_from_end=False)
            source.open()
            sources[path] = source
        return [line for source in sources.values() for line in source.read_new()]

    # 让外层先到达总上限，给出更新及启动超时原因。
    search = asyncio.create_task(search_process(_TOTAL_TIMEOUT + 1))
    try:
        while True:
            if search.done():
                await search
                return

            lines = await asyncio.to_thread(read_logs)
            if check_lines is not None:
                check_lines(lines)
            for line in lines:
                _, start_marker, version = line.partition(update_start)
                if start_marker:
                    update_version = version.strip()
                    pip_read_timed_out = False
                _, separator, message = line.partition(error_emitter)
                if not separator:
                    continue
                message = message.strip()
                if message.startswith(_PIP_READ_TIMEOUT):
                    pip_read_timed_out = True
                failure = _UPDATE_FAILURE.match(message)
                # 只在启动器报告升级终态后终止，留出依赖重试与版本回滚的时间。
                if failure is None:
                    prefix, _, _ = message.partition(":")
                    reason = _UPDATE_STATE_FAILURES.get(prefix + ":")
                    if reason is not None:
                        target = f"至 {update_version} " if update_version else ""
                        raise RuntimeError(f"{label} 启动器更新{target}失败：{reason}")
                    continue
                reason = "详情请查看启动器日志"
                if " -m pip install " in message:
                    exit_code = _EXIT_CODE.search(message)
                    if pip_read_timed_out:
                        reason = "下载依赖时读取超时"
                    elif exit_code is not None:
                        reason = (
                            f"安装依赖失败（退出码 {exit_code[1]}），请查看启动器日志"
                        )
                raise RuntimeError(f"{label} 启动器更新至 {failure[1]} 失败：{reason}")
            if search.done():
                await search
                return
            now = time.monotonic()
            for line in lines:
                if emitter in line:
                    message = line.split(emitter, 1)[1].strip()
                    if not message.startswith(progress_prefixes):
                        continue
                elif not include_update_check and update_start in line:
                    message = update_start + line.split(update_start, 1)[1].strip()
                else:
                    continue
                if message in progress:
                    # 重复进展行：疑似下载失败重试刷屏，只记时刻、不刷新静默窗口。
                    if last_repeat is None or now - last_repeat > _REPEAT_ACTIVE_WINDOW:
                        repeat_started = now
                    last_repeat = now
                    continue
                progress.add(message)
                last_repeat = None
                repeat_started = None
                deadline = now + _UPDATE_STALL_TIMEOUT
                if not updating:
                    updating = True
                    await on_log(
                        f"检测到 {label} 启动器正在检查或安装更新，已延长启动等待"
                    )
            if now - started >= _TOTAL_TIMEOUT:
                raise RuntimeError(
                    f"等待 {label} 更新及启动超过 {_TOTAL_TIMEOUT / 60:g} 分钟，"
                    "请检查启动器"
                )
            if (
                last_repeat is not None
                and repeat_started is not None
                and now - last_repeat <= _REPEAT_ACTIVE_WINDOW
                and now - repeat_started >= _REPEAT_STALL_TIMEOUT
            ):
                raise RuntimeError(
                    f"{label} 更新连续 {_REPEAT_STALL_TIMEOUT / 60:g} 分钟"
                    "反复输出旧进展，疑似下载重试卡死，请检查启动器"
                )
            if now >= deadline:
                raise RuntimeError(
                    f"{label} 更新或启动连续 {_UPDATE_STALL_TIMEOUT / 60:g} 分钟"
                    "无新进展，请检查启动器"
                    if updating
                    else f"{label} 在 {_START_TIMEOUT:g} 秒内未启动，"
                    "且未检测到更新进展，请检查启动器"
                )
            await asyncio.sleep(0.5)
    finally:
        search.cancel()
        await asyncio.gather(search, return_exceptions=True)
