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
import shutil
import threading
import time
from collections.abc import Sequence
from pathlib import Path

import psutil

from app.services import System
from app.utils.update_files import (
    file_md5,
    file_size,
    resolve_within,
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


def _resolve_within(root: Path, name: str) -> Path:
    """解析已规范化的清单路径，保留终末地不经过链接的落地约束。"""
    try:
        return resolve_within(root, name, resolve_links=False, reject_links=True)
    except ValueError as error:
        raise EndfieldUpdateError(str(error)) from error


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
    moves: Sequence[MoveJob] | None,
    install_dir: Path,
    progress: ProgressFn | None,
    abort: threading.Event,
) -> tuple[set[str], list[str]]:
    """核一遍每个条目还要不要做，返回 `(已落地的路径, 与基线不符的路径)`。

    判据顺序是**先看新文件、再看旧基线**：上一轮中途停下时，已经改名就位的那些条目在盘上
    已经是新值，若只认旧基线就会把它们一律判成「与官方不符」，于是用户永远停在
    「请手动更新」——这正是续传要解决的事。新值对得上就是已完成，本轮不必重打一遍。

    体积先比、MD5 后算：体积就不对的文件没必要读内容（`file_md5` 一次要读完整份文件，
    而整文件成员可以到 GB 级）。这一步跑完之前一个字都不写进游戏目录——差量打在错基线上
    产出的是「长度对得上、内容坏了」的文件，只有落盘前那次 MD5 能发现，而那时游戏目录
    已经被写了一半。

    `moves` 为 `None` 表示包内清单没预取到：那些整文件只能按「要不要做」留在待办里，
    它们没有基线，不参与「不符」判定。
    """

    done: set[str] = set()
    bad: list[str] = []
    entries: list[tuple[str, str, int, str | None, str, int]] = [
        (spec.path, spec.md5, spec.size, spec.base_path, spec.base_md5, spec.base_size)
        for spec in specs
    ]
    # 整文件没有基线：本地不是新值就重写一份，没有「不符」可言
    entries += [
        (entry.path, entry.md5, entry.size, None, "", 0) for entry in (moves or ())
    ]
    total = len(entries)
    for index, (path, md5, size, base_path, base_md5, base_size) in enumerate(
        entries, start=1
    ):
        if abort.is_set():
            break
        target = _resolve_within(install_dir, path)
        if md5 and file_size(target) == size:
            try:
                if await asyncio.to_thread(file_md5, target) == md5:
                    done.add(path)
                    if progress is not None and (
                        index % _APPLY_STEP == 0 or index == total
                    ):
                        await progress(f"正在核对本地基线文件 {index}/{total}")
                    continue
            except OSError:
                pass
        if base_path is not None:
            base = _resolve_within(install_dir, base_path)
            if file_size(base) != base_size:
                bad.append(base_path)
            else:
                try:
                    digest = await asyncio.to_thread(file_md5, base)
                except OSError:
                    digest = ""
                if digest != base_md5:
                    bad.append(base_path)
        if progress is not None and (index % _APPLY_STEP == 0 or index == total):
            await progress(f"正在核对本地基线文件 {index}/{total}")
    return done, bad
