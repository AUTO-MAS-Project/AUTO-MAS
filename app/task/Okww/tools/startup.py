"""等待 OK-WW 启动器完成自更新，再接管工作进程。"""

import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.task.pyappify_startup import open_launcher_logs, wait_for_launcher_process
from app.utils import ProcessInfo, ProcessManager

from .batch_logs import (
    NATIVE_SWITCH_UNSUPPORTED_MESSAGE,
    NativeSwitchUnsupportedError,
    native_switch_unsupported,
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
    log_dir = program.parent / "logs"
    sources = open_launcher_logs(log_dir)
    started_at = time.time()
    started = time.monotonic()
    await manager.open_process(program, *args)

    def check_lines(lines: list[str]) -> None:
        if "MultiAccountConfigTask" in args and any(
            native_switch_unsupported(line) for line in lines
        ):
            raise NativeSwitchUnsupportedError(NATIVE_SWITCH_UNSUPPORTED_MESSAGE)

    await wait_for_launcher_process(
        log_dir,
        sources,
        app_id="ok-ww",
        started=started,
        search_process=lambda timeout: manager.search_process(
            target, timeout_seconds=timeout, min_create_time=started_at
        ),
        on_log=on_log,
        check_lines=check_lines,
    )
