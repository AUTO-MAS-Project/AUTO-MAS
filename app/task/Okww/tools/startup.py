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
# 新进展后的静默上限：非 tty 下 pip 输出「Downloading 包名」一行后静默下载，
# 大包慢速下载期可长时间无完整新行，窗口须覆盖（量级对齐启动器交互的
# 下载顺延等待，launcher_start._UPDATE_ACTIVE_GRACE_SECONDS 为 600 秒）。
_UPDATE_STALL_TIMEOUT = 900.0
# 重复进展刷屏上限：依赖下载失败后重试会交替刷同一组消息，5 分钟内没有
# 任何新消息即可判卡死，避免无限续时（总上限之外的第二道兜底）。
_REPEAT_STALL_TIMEOUT = 300.0
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
    """拉起 OK-WW 并等待其工作进程出现，自更新期间按启动器日志进展延长等待。

    启动器启动时可能先执行自更新（git 拉取 + 依赖同步），期间工作进程迟迟
    不出现：通过启动器日志的可见输出判定更新进展并延长等待；静默（大包慢速
    下载期可长时间无新行）与重复刷屏（下载重试交替刷同一组消息）各有上限，
    防止更新卡死后无限等待。

    Args:
        manager: OK-WW 进程管理器，负责拉起程序与检索工作进程。
        program: OK-WW 启动器 exe 路径。
        args: 传给启动器的命令行参数。
        target: 要检索的工作进程特征。
        on_log: 流程进度回调（供 MAS 推送调度台日志）。

    Raises:
        RuntimeError: 等待超时（未启动 / 更新停滞 / 重复刷屏 / 超总上限）。
    """
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
    last_new = started
    last_repeat: float | None = None
    # 会话内去重，避免依赖下载重试交替刷同一组消息而不断续时。
    progress: set[str] = set()
    await manager.open_process(program, *args)
    search = asyncio.create_task(
        manager.search_process(
            # 检索超时比总上限多留 1 秒，让主循环的总上限先触发并给出具体原因。
            target,
            timeout_seconds=_TOTAL_TIMEOUT + 1,
            min_create_time=started_at,
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
                if marker is None:
                    continue
                if message in progress:
                    # 重复进展行：疑似下载失败重试刷屏，只记时刻、不刷新静默窗口。
                    last_repeat = now
                    continue
                progress.add(message)
                last_new = now
                deadline = now + _UPDATE_STALL_TIMEOUT
                if not updating:
                    updating = True
                    await on_log(
                        "检测到 OK-WW 启动器正在检查或安装更新，已延长启动等待"
                    )
            if now - started >= _TOTAL_TIMEOUT:
                raise RuntimeError(
                    f"等待 OK-WW 更新及启动超过 {_TOTAL_TIMEOUT / 60:g} 分钟，"
                    "请检查启动器"
                )
            if (
                last_repeat is not None
                and last_repeat > last_new
                and now - last_new >= _REPEAT_STALL_TIMEOUT
            ):
                raise RuntimeError(
                    f"OK-WW 更新连续 {_REPEAT_STALL_TIMEOUT / 60:g} 分钟"
                    "反复输出旧进展，疑似下载重试卡死，请检查启动器"
                )
            if now >= deadline:
                raise RuntimeError(
                    f"OK-WW 更新或启动连续 {_UPDATE_STALL_TIMEOUT / 60:g} 分钟"
                    "无新进展，请检查启动器"
                    if updating
                    else f"OK-WW 在 {_START_TIMEOUT:g} 秒内未启动，"
                    "且未检测到更新进展，请检查启动器"
                )
            await asyncio.sleep(0.5)
    finally:
        search.cancel()
        with suppress(asyncio.CancelledError):
            await search
