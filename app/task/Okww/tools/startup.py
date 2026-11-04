"""等待 OK-WW 启动器完成自更新，再接管工作进程。"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.utils import ProcessInfo, ProcessManager
from app.utils.common.log.sources import LogSource

_START_TIMEOUT = 60.0
_UPDATE_STALL_TIMEOUT = 300.0
_TOTAL_TIMEOUT = 1800.0
_EMITTER = "pyappify_lib::emitter: INFO [ok-ww]: "
# 仅匹配启动器可见输出，不消费 app.json 的内部更新状态。
_PROGRESS = (
    "Fetching updates for existing repository",
    "Fetch complete.",
    "Fetching all tags",
    "Fetching refspec:",
    "Successfully checked out",
    "Checked out commit",
    "Content of 'requirements.txt' changed. Syncing dependencies.",
    "Collecting ",
    "Downloading ",
    "Installing collected packages:",
    "Successfully installed ",
)


async def start_okww(
    manager: ProcessManager,
    program: Path,
    args: list[str],
    *,
    target: ProcessInfo,
    on_log: Callable[[str], Awaitable[None]],
) -> None:
    """仅本次新增的更新进展可续时，重复输出不刷新停滞计时。"""
    sources: dict[Path, LogSource] = {}
    log_dir = program.parent / "logs"
    for path in log_dir.glob("app.*"):
        if not path.is_file():
            continue
        source = LogSource(path)
        source.open()
        sources[path] = source

    started_at = time.time()
    started = time.monotonic()
    deadline = started + _START_TIMEOUT
    updating = False
    # 会话内去重，避免依赖下载重试交替刷同一组消息而不断续时。
    progress: set[str] = set()
    await manager.open_process(program, *args)
    search = asyncio.create_task(
        manager.search_process(
            target, timeout_seconds=_TOTAL_TIMEOUT + 1, min_create_time=started_at
        )
    )
    try:
        while True:
            if search.done():
                await search
                return

            def read_logs() -> list[str]:
                # 启动器按日建文件；跨午夜时继续读旧文件并接入新文件。
                today = log_dir / datetime.now().strftime("app.%Y-%m-%d")
                if today not in sources:
                    source = LogSource(today, start_from_end=False)
                    source.open()
                    sources[today] = source
                return [
                    line for source in sources.values() for line in source.read_new()
                ]

            lines = await asyncio.to_thread(read_logs)
            if search.done():
                await search
                return
            now = time.monotonic()
            for line in lines:
                # ERROR 中可能包含无关的 Defender 检查，不能据此判更新失败。
                if _EMITTER not in line:
                    continue
                message = line.split(_EMITTER, 1)[1].strip()
                marker = next(
                    (item for item in _PROGRESS if message.startswith(item)), None
                )
                if marker is None or message in progress:
                    continue
                progress.add(message)
                deadline = now + _UPDATE_STALL_TIMEOUT
                if not updating:
                    updating = True
                    await on_log(
                        "检测到 OK-WW 启动器正在检查或安装更新，已延长启动等待"
                    )
            if now - started >= _TOTAL_TIMEOUT:
                raise RuntimeError("等待 OK-WW 更新及启动超过 30 分钟，请检查启动器")
            if now >= deadline:
                raise RuntimeError(
                    "OK-WW 更新或启动连续 5 分钟无新进展，请检查启动器"
                    if updating
                    else "OK-WW 在 60 秒内未启动，且未检测到更新进展，请检查启动器"
                )
            await asyncio.sleep(0.5)
    finally:
        search.cancel()
        with suppress(asyncio.CancelledError):
            await search
