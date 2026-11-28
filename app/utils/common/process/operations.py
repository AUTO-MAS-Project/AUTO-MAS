"""按路径查询及终止进程；调用方提供目标，不读取应用配置。"""

import asyncio
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psutil

from app.utils import IS_WINDOWS, get_logger, process_platform

from .session import matches_session, process_in_scope, restricted_session

logger = get_logger("进程操作")


def iter_processes(
    attributes: list[str], *, current_session_only: bool = False
) -> Iterator[psutil.Process]:
    """为插件兼容入口枚举当前范围内的进程，提供 ``Process.info``。"""
    return processes_in_scope(
        psutil.process_iter(attributes), current_session_only=current_session_only
    )


def iter_process_info(
    attributes: list[str], *, processes: Iterable[psutil.Process] | None = None
) -> Iterator[tuple[psutil.Process, dict[str, Any]]]:
    """枚举进程并读取本轮所需的字段。

    带属性参数的 ``psutil.process_iter`` 会改写缓存对象的 ``info``，
    这里单独读取字段，使两次扫描可以使用不同的字段。
    """
    candidates = psutil.process_iter() if processes is None else processes
    for process in candidates:
        try:
            info = process.as_dict(attrs=attributes)
        except psutil.NoSuchProcess:
            continue
        yield process, info


def iter_scoped_process_info(
    attributes: list[str], *, current_session_only: bool = False
) -> Iterator[tuple[psutil.Process, dict[str, Any]]]:
    """读取当前进程管理范围内的进程字段。"""
    processes = processes_in_scope(
        psutil.process_iter(), current_session_only=current_session_only
    )
    return iter_process_info(attributes, processes=processes)


def processes_in_scope(
    processes: Iterable[psutil.Process], *, current_session_only: bool = False
) -> Iterator[psutil.Process]:
    """在同一轮枚举内使用一致的会话范围。"""
    session_id = restricted_session()
    if session_id is None and current_session_only and IS_WINDOWS:
        from app.utils.windows.desktop_session.native import process_session

        session_id = process_session(os.getpid())
    return (
        process for process in processes if matches_session(process.pid, session_id)
    )


def managed_process(
    pid: int, *, expected_create_time: float | None = None
) -> psutil.Process | None:
    """打开当前管理范围内的进程。

    原进程已退出或 PID 已复用时返回 ``None``。存活进程无法确认属于当前范围时
    抛 ``ProcessLookupError``。
    """

    try:
        process = psutil.Process(pid)
        create_time = process.create_time()
    except psutil.NoSuchProcess:
        return None
    if expected_create_time is not None and abs(create_time - expected_create_time) > 1:
        return None
    if process_in_scope(pid):
        return process
    if not process.is_running():
        return None
    raise ProcessLookupError(f"无法确认进程属于当前范围: {pid}")


def terminate_process(process: psutil.Process, *, force: bool = False) -> bool:
    """核验范围后发送终止请求，返回是否真的发出了终止请求。

    越界（不属于当前桌面分身会话）意味着「这个进程不归我们管」，与「已经结束」是两件
    不同的事。调用方必须把 ``False`` 当成「没能结束」，不要据此当作清理完成。
    """

    if not process_in_scope(process.pid):
        logger.warning(f"跳过不属于当前范围的进程: pid={process.pid}")
        return False
    if force:
        process.kill()
    else:
        process.terminate()
    return True


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


async def is_process_stopped(path: Path | str, *, all_sessions: bool = False) -> bool:
    """确认目标路径无存活进程，共享文件的占用检查可查所有会话。

    扫描不完整或同名进程路径不可读时返回 False。
    """

    scan = await _scan_processes_by_path(path, all_sessions=all_sessions)
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


async def _scan_processes_by_path(
    path: Path | str, *, all_sessions: bool = False
) -> _ProcessPathScan:
    """扫描精确路径进程，并记录无法确认路径的同名候选。"""

    path = Path(path)
    pids: list[int] = []
    uncertain_pids: list[int] = []
    target_name = path.name.casefold()

    def _scan() -> bool:
        try:
            target_path = str(path.resolve() if all_sessions else path).casefold()
            session_id = None if all_sessions else restricted_session()
            for proc, info in iter_process_info(["name", "exe"]):
                process_path = info.get("exe")
                if process_path:
                    candidate = Path(process_path)
                    if all_sessions and candidate.name.casefold() == target_name:
                        try:
                            candidate = candidate.resolve()
                        except OSError:
                            uncertain_pids.append(proc.pid)
                            continue
                    if str(candidate).casefold() == target_path and matches_session(
                        proc.pid, session_id
                    ):
                        pids.append(proc.pid)
                    continue

                process_name = info.get("name")
                if (
                    process_name
                    and str(process_name).casefold() == target_name
                    and matches_session(proc.pid, session_id)
                ):
                    uncertain_pids.append(proc.pid)
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
