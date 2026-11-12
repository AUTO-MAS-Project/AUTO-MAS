"""按路径查询及终止进程；调用方提供目标，不读取应用配置。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger, process_platform

logger = get_logger("进程操作")


@dataclass(frozen=True, slots=True)
class _ProcessPathScan:
    pids: list[int]
    uncertain_pids: list[int]
    complete: bool


async def is_process_running(path: Path | str) -> bool:
    """按镜像路径判断该进程是否还在跑。

    Args:
        path (Path | str): 目标进程路径。

    Returns:
        bool: 有该路径的进程在跑时返回 True。读不出镜像路径的同名候选不算——
            那些进程无法归到这个路径上，与 `kill_process` 用同一套判据。
    """

    return bool((await _scan_processes_by_path(path)).pids)


async def is_process_stopped(path: Path | str) -> bool:
    """确认目标路径没有存活进程；扫描不完整或同名进程路径不可读时返回 False。"""

    scan = await _scan_processes_by_path(path)
    return scan.complete and not scan.pids and not scan.uncertain_pids


async def kill_process(path: Path | str, *, kill_tree: bool = True) -> bool:
    """根据路径中止进程。

    Args:
        path (Path | str): 目标进程路径。
        kill_tree (bool): 是否同时中止子进程树。

    Returns:
        bool: 所有匹配进程均成功中止时返回 True。
    """

    path = Path(path)
    logger.info(f"开始中止进程: {path}")

    scan = await _scan_processes_by_path(path)
    success = scan.complete
    first_error: Exception | None = None
    if scan.uncertain_pids:
        logger.warning(
            f"存在无法确认路径的同名进程: {path.name}, PID: {scan.uncertain_pids}"
        )

    for pid in scan.pids:
        try:
            pid_success = await kill_process_by_pid(pid, kill_tree=kill_tree)
        except Exception as e:
            pid_success = False
            if first_error is None:
                first_error = e
            logger.opt(exception=True).warning(f"进程中止异常 PID: {pid}, 原因: {e}")
        if not pid_success:
            success = False

    if first_error is not None:
        raise first_error
    if success:
        logger.success(f"进程已中止: {path}")
    return success


async def kill_process_by_pid(pid: int, *, kill_tree: bool = True) -> bool:
    """根据 PID 中止进程。

    Args:
        pid (int): 目标进程 PID。
        kill_tree (bool): 是否同时中止子进程树。

    Returns:
        bool: 进程成功终止时返回 True。
    """

    logger.info(f"开始中止进程 PID: {pid}")
    succeeded, reason = await process_platform.platform_process.kill_process(
        pid, kill_tree
    )
    if not succeeded:
        if not psutil.pid_exists(pid):
            logger.info(f"进程已自行退出 PID: {pid}")
            return True

        logger.warning(f"进程中止失败 PID: {pid}, {reason}")
        return False

    logger.success(f"进程已中止 PID: {pid}")
    return True


async def _scan_processes_by_path(path: Path | str) -> _ProcessPathScan:
    """扫描精确路径进程，并记录无法确认路径的同名候选。"""

    path = Path(path)
    pids: list[int] = []
    uncertain_pids: list[int] = []
    target_path = str(path).casefold()
    target_name = path.name.casefold()

    def _scan() -> bool:
        try:
            processes = psutil.process_iter(["pid", "name", "exe"])
            for proc in processes:
                try:
                    info = proc.info
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue

                process_path = info.get("exe")
                if process_path:
                    if str(process_path).casefold() == target_path:
                        pids.append(info["pid"])
                    continue

                process_name = info.get("name")
                if process_name and str(process_name).casefold() == target_name:
                    uncertain_pids.append(info["pid"])
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"扫描进程路径失败: {e}")
            return False
        return True

    complete = await asyncio.to_thread(_scan)

    return _ProcessPathScan(
        pids=pids,
        uncertain_pids=uncertain_pids,
        complete=complete,
    )
