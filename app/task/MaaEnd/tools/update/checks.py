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

"""终末地更新前的路径防护、基线核对、磁盘与进程占用检查。"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import psutil

from app.services import System
from app.utils.update_files import (
    file_md5,
    file_size,
    native_path,
)

from .common import (
    _APPLY_STEP,
    EndfieldUpdateError,
    MoveJob,
    PatchJob,
    ProgressFn,
    logger,
)

_KILL_WAIT_SECONDS = 30.0


def _is_link(stat_result: os.stat_result) -> bool:
    """认符号链接与 NTFS 联接点：联接点在 Windows 上只有重解析点属性认得出来。"""

    return bool(
        stat.S_ISLNK(stat_result.st_mode)
        or getattr(stat_result, "st_reparse_tag", 0)
        or (
            getattr(stat_result, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        )
    )


def _resolve_within(root: Path, name: str) -> Path:
    """把包内路径解析到安装目录之内。

    成员名来自下载的包，属于不可信输入：目录穿越会把文件写到安装目录外面去。
    """

    parts = tuple(part for part in re.split(r"[\\/]+", name) if part not in ("", "."))
    if not parts:
        # 空路径会归一成安装目录本身，放过就等于把整棵目录树冲掉
        raise EndfieldUpdateError(f"包内路径为空: {name!r}")
    if any(":" in part for part in parts):
        # 盘符与交替数据流都靠冒号表达，NTFS 也不允许文件名带它
        raise EndfieldUpdateError(f"包内路径含非法冒号: {name!r}")
    target = root.joinpath(*parts)
    anchor = os.path.normcase(os.path.abspath(root))
    absolute = os.path.normcase(os.path.abspath(target))
    if absolute != anchor and not absolute.startswith(anchor + os.sep):
        raise EndfieldUpdateError(f"包内路径越出安装目录: {name!r}")
    # 词法检查只管得住 `..`：目录里躺着一条指向别处的链接时，拼出来的路径仍在安装目录
    # 之内，顺着它写就写到外面去了。逐段看一眼是不是重解析点，段不存在就不必再看更深
    for depth in range(1, len(parts) + 1):
        try:
            info = os.stat(
                native_path(root.joinpath(*parts[:depth])), follow_symlinks=False
            )
        except OSError:
            break
        if _is_link(info):
            raise EndfieldUpdateError(
                f"包内路径 {name!r} 经过一个指向别处的链接，MAS 不顺着它写"
            )
    # 返回规范化后的绝对路径：`\\\\?\\` 前缀是把字符串直接交给 Win32，内核不做
    # `..` 折叠，留着 `..` 段会让写入莫名失败
    return Path(os.path.normpath(os.path.abspath(target)))


def _processes_under(root: Path) -> list[str]:
    """列出镜像路径落在安装目录里的进程。

    按镜像路径而不是进程名判断：终末地是 UE 客户端，会带一串同名子进程，同时别家
    同名的 `Endfield.exe` 不该被误伤。
    """

    try:
        anchor = root.resolve()
    except OSError:
        return []
    found: list[str] = []
    for process in psutil.process_iter(["pid", "name", "exe"]):
        try:
            executable = process.info.get("exe")
            if not executable:
                continue
            image = Path(executable)
            if anchor != image.parent and anchor not in image.parents:
                continue
            found.append(
                f"{process.info.get('name') or image.name}（PID {process.info.get('pid')}）"
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return found


async def _release_install_dir(game_exe: Path) -> str | None:
    """让安装目录脱离进程占用；仍被占用时返回给用户看的说明。"""

    install_dir = game_exe.parent
    busy = await _busy_processes(install_dir)
    if not busy:
        return None
    logger.info(f"终末地客户端正在运行，先请求退出: {', '.join(busy)}")
    await System.kill_process(game_exe)
    deadline = time.monotonic() + _KILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not await _busy_processes(install_dir):
            return None
        await asyncio.sleep(2.0)
    busy = await _busy_processes(install_dir)
    # 占用者按镜像路径认，未必只有游戏本身：游戏目录里放着的别的工具同样会挡路
    return f"{', '.join(busy)} 仍在使用游戏目录，请退出上面列出的程序后重试"


async def _busy_processes(root: Path) -> list[str]:
    """在工作线程里问一遍进程占用：Windows 上取每个进程的镜像路径是百毫秒级的活。"""

    return await asyncio.to_thread(_processes_under, root)


def _landing_need(
    patches: Sequence[PatchJob],
    moves: Sequence[MoveJob],
    install_dir: Path,
    expanded: int = 0,
) -> int:
    """按写入顺序计算额外空闲峰值，下载前后共用此算法。

    新文件先占临时空间，改名后才释放目标原有体积；不提前计入删除表的释放量。
    expanded 另计暂存中最大差量的展开体积，未知时由固定余量兜底。
    """

    peak = 0
    net_growth = 0
    for job in (*patches, *moves):
        old = max(file_size(_resolve_within(install_dir, job.path)), 0)
        peak = max(peak, net_growth + job.size)
        net_growth += job.size - old
    return peak + expanded


def _disk_shortfall(directory: Path, need: int, label: str) -> str | None:
    """核对磁盘余量，失败返回说明，放行时记录需要量与可用量。

    暂存卷收尾会删除，日志保留核对时占用，便于与用户事后查看的余量对账。"""

    probe = directory
    while not probe.exists() and probe.parent != probe:
        # 目录还没建出来时向上找到挂载点，否则 disk_usage 直接抛错
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as error:
        return f"无法确认{label}所在磁盘的余量：{error}"
    if free >= need:
        logger.info(
            f"{label}所在磁盘余量核对：需要约 {need / 1024**3:.1f} GB，"
            f"当前可用 {free / 1024**3:.1f} GB，足够"
        )
        return None
    return (
        f"{label}所在磁盘余量不足：需要约 {need / 1024**3:.1f} GB，"
        f"当前可用 {free / 1024**3:.1f} GB"
    )


def _write_probe(directory: Path) -> str | None:
    """用临时文件探测目录可写，不猜路径权限或触发无人值守的 UAC 弹窗。"""

    probe = directory / f".mas_write_probe.{os.getpid()}"
    try:
        probe.write_bytes(b"")
    except OSError as error:
        return f"游戏目录不可写入（{error}），请给当前用户授予该目录写权限后重试"
    finally:
        try:
            probe.unlink()
        except OSError:
            pass
    return None


async def _check_baselines(
    specs: Sequence[PatchJob],
    install_dir: Path,
    progress: ProgressFn | None,
    abort: threading.Event,
) -> list[str]:
    """核对本地基线，先比体积再算 MD5，返回不符的路径。

    必须在覆盖游戏文件之前完成，避免落地校验才发现基线错误而留下部分更新。"""

    bad: list[str] = []
    total = len(specs)
    for index, spec in enumerate(specs, start=1):
        if abort.is_set():
            break
        base = _resolve_within(install_dir, spec.base_path)
        if file_size(base) != spec.base_size:
            bad.append(spec.base_path)
            continue
        try:
            digest = await asyncio.to_thread(file_md5, base)
        except OSError:
            digest = ""
        if digest != spec.base_md5:
            bad.append(spec.base_path)
        if progress is not None and (index % _APPLY_STEP == 0 or index == total):
            await progress(f"正在核对本地基线文件 {index}/{total}")
    return bad
