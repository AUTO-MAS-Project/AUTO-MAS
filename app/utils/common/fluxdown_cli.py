#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com

"""FluxDown CLI 便携包调用封装：进程内嵌引擎、零配置、独立数据目录、不污染用户本体。

用法：
    from app.utils.common.fluxdown_cli import fluxdown_download, fluxdown_find_cli

    path = fluxdown_find_cli(configured_path="")   # 返回 exe 路径或 None
    size, record = await fluxdown_download(
        url="https://.../package.zip",
        destination=Path("package.zip"),
        checksum="sha256=abc123...",               # 可选，FluxDown 下载完自动校验
        segments=8,
        proxy="http://127.0.0.1:7890",             # 可选
        progress=my_progress_callback,              # (downloaded, total, speed) -> Awaitable[None]
    )
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Awaitable, Callable

import psutil

try:
    import aiofiles
except ImportError:
    aiofiles = None

from app.utils import (
    file_lock,
    get_logger,
    process_platform,
    update_native,
)

logger = get_logger("FluxDown")
_LOCAL_CLI_LOCK = threading.Lock()

DownloadProgress = Callable[[int, int, float], Awaitable[None]]


# 下载共享使用权，安装独占使用权；不串行化并行下载。
_usage_lock = threading.Lock()
_active_downloads = 0
_installing = False


def _using_fluxdown(function):
    @wraps(function)
    async def guarded(*args, **kwargs):
        global _active_downloads
        with _usage_lock:
            if _installing:
                raise RuntimeError("FluxDown 正在安装，请稍后重试下载")
            _active_downloads += 1
        try:
            return await function(*args, **kwargs)
        finally:
            with _usage_lock:
                _active_downloads -= 1

    return guarded


@contextmanager
def fluxdown_install_guard():
    """拒绝打断下载或结束不属于本进程的 Agent。"""
    global _installing
    with _usage_lock:
        if _active_downloads or _installing:
            raise RuntimeError("FluxDown 正在下载或安装，请完成后重试")
        _installing = True
    try:
        with _server.lock:
            if _server.handle is not None and not _server.spawned_by_us:
                raise RuntimeError("FluxDown Agent 由其他进程管理，请先手动停止后重试")
        fluxdown_server_shutdown()
        yield
    finally:
        with _usage_lock:
            _installing = False


@dataclass
class FluxdownDownloadRecord:
    """一次 FluxDown 下载的记录，用于 Update.LastUpdateHistory。"""

    url: str = ""
    destination: str = ""
    size: int = 0
    duration_ms: int = 0
    segments: int = 0
    proxy: str | None = None
    checksum: str | None = None
    status: str = (
        ""  # success | failed | checksum_fail | interrupted | fluxdown_fallback
    )
    error: str | None = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        # 下载历史和导出记录不应保留账号密码，包括旧版本的认证代理。
        from urllib.parse import urlsplit, urlunsplit

        proxy = self.proxy
        if proxy:
            parts = urlsplit(proxy)
            proxy = urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[-1]))
        return {
            "url": self.url,
            "destination": self.destination,
            "size": self.size,
            "duration_ms": self.duration_ms,
            "segments": self.segments,
            "proxy": proxy,
            "checksum": self.checksum,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------


def fluxdown_find_cli(
    configured_path: str | None = None, *, search_dirs: tuple[Path, ...] = ()
) -> Path | None:
    """定位 FluxDown CLI 二进制，返回路径或 None。

    查找顺序：
        1. 用户显式配置的 Update.FluxdownPath（尊重用户选择，可为全量版）
        2. 调用方提供的内置程序目录 search_dirs
        3. 系统 PATH 里的 fluxdown.exe（兜底，用户自己装的）

    内置程序目录必须带 ``portable`` 标记，避免误命中用户桌面版；
    用户显式配置的目录（1）不做此限制——检测 UI 已就全量版给出污染风险警告。
    """
    candidates: list[tuple[Path, bool]] = []

    # 1. 用户配置路径（兼容目录或 exe 文件路径，文件则取其所在目录）
    if configured_path:
        p = Path(configured_path)
        if p.is_file():
            p = p.parent
        if p.is_dir():
            candidates.append((p, False))

    candidates.extend((directory, True) for directory in search_dirs)

    for dir_path, require_portable in candidates:
        if not dir_path.is_dir():
            continue
        if require_portable and not (dir_path / "portable").is_file():
            continue
        for name in _FLUXDOWN_EXE_NAMES:
            exe = dir_path / name
            if exe.is_file():
                return exe

    # 4. 系统 PATH 兜底（不要求 portable 标记，纯兜底）
    found = shutil.which("fluxdown") or shutil.which("fluxdown-cli")
    return Path(found) if found else None


def fluxdown_check_portable(cli_exe: Path) -> bool:
    """判断 CLI 是否运行在便携模式（同目录有 portable 标记文件）。"""
    return (cli_exe.parent / "portable").is_file()


# ---------------------------------------------------------------------------


@_using_fluxdown
async def fluxdown_download(
    url: str,
    destination: Path,
    *,
    cli_exe: Path,
    segments: int = 8,
    proxy: str | None = None,
    checksum: str | None = None,
    timeout: float = 300,
    progress: DownloadProgress | None = None,
) -> tuple[int, FluxdownDownloadRecord]:
    """起子进程调用 FluxDown CLI --local 多线程分段下载。

    返回 (size_bytes, FluxdownDownloadRecord)。成功退出码 0；checksum 失配或 CLI
    内部失败会以非零退出码返回，本函数据此抛 RuntimeError 并把 status 写进 record。
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    record = FluxdownDownloadRecord(
        url=url,
        destination=str(destination),
        segments=segments,
        proxy=proxy,
        checksum=checksum,
    )

    # 删掉旧文件，防止 CLI 把旧文件 size 当作已下载量续传
    if destination.exists():
        destination.unlink()

    # --local 的数据目录由 exe 同目录的 portable 标记决定：换用 MAS 私有副本，
    # 否则任务记录会写进用户自己的 FluxDown 数据库
    local_exe = await asyncio.to_thread(_local_cli_exe, cli_exe)

    args = [
        str(local_exe),
        "add",
        url,
        "--local",
        "-d",
        str(destination.parent),
        "-o",
        destination.name,
        "--segments",
        str(segments),
    ]
    if proxy:
        args += ["--proxy", proxy]
    if checksum:
        args += ["--checksum", checksum]

    logger.info(f"[--local] 开始下载: {url} -> {destination.name}, 分段数={segments}")
    t0 = time.monotonic()
    buf = bytearray()
    last_report = 0.0
    last_output = t0  # 最近一次收到 CLI 输出的时刻（停滞超时基准）

    async def _parse_stream():
        nonlocal last_report, last_output
        downloaded = 0
        total = 0
        async for raw in proc.stdout:
            buf.extend(raw)
            last_output = time.monotonic()
            # CLI --local 输出是纯文本进度行，尝试解析 "...X/Y..." 和 "...Z MB/s..."
            text = raw.decode("utf-8", errors="replace")
            # 尝试提取进度百分比/字节数
            m = re.search(r"(\d+)\s*/\s*(\d+)", text)
            if m:
                try:
                    downloaded = int(m.group(1))
                    total = int(m.group(2))
                except ValueError:
                    pass
            speed = 0.0
            sm = re.search(r"([\d.]+)\s*(?:MB/s|KB/s|B/s)", text)
            if sm:
                try:
                    v = float(sm.group(1))
                    unit = sm.group(0)
                    if "MB/s" in unit:
                        speed = v * 1024 * 1024
                    elif "KB/s" in unit:
                        speed = v * 1024
                    else:
                        speed = v
                except ValueError:
                    pass
            now = time.monotonic()
            if progress and downloaded > 0 and (now - last_report) >= 0.5:
                try:
                    await progress(downloaded, total, speed)
                except Exception:
                    pass
                last_report = now

    def _output_state() -> tuple[int, int]:
        """返回 destination 及同名前缀临时文件的 (总字节数, 最新 mtime_ns)。

        --local 模式只在启动时输出一行任务 ID，之后全程静默但仍在写文件；
        且分段下载会预分配完整临时文件，st_size 从开始就等于总大小（官方
        downloader.rs 明确真实进度须从数据库读取，而 local 独占数据库锁，
        这里取不到），只看大小会把健康下载误判为停滞。Windows 在所有写句柄
        关闭前不保证刷新 mtime，因此这里只把 (总字节数, 最新 mtime) 当辅助
        活动信号，停滞判定以 ``_proc_write_bytes`` 的进程写入计数为准。
        """
        total_bytes = 0
        latest_mtime = 0
        try:
            with os.scandir(destination.parent) as entries:
                for entry in entries:
                    if not entry.name.startswith(destination.name):
                        continue
                    try:
                        if entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            total_bytes += st.st_size
                            latest_mtime = max(latest_mtime, st.st_mtime_ns)
                    except OSError:
                        continue
        except OSError:
            return 0, 0
        return total_bytes, latest_mtime

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None

    def _proc_write_bytes() -> int | None:
        """CLI 进程累计写入字节数；查询失败（已退出/权限）返回 None。

        psutil 的 I/O 计数是比文件大小更直接的"仍在写盘"证据：分段模式
        预分配后文件大小恒定，而写入计数仍持续增长。
        """
        try:
            return psutil.Process(proc.pid).io_counters().write_bytes
        except (psutil.Error, OSError, NotImplementedError):
            return None

    # 停滞超时：timeout 语义 = 持续无"活动"的秒数上限，不是整包总时限。
    # 主判据是进程已写入字节数：--local 分段下载会预分配完整文件（大小从开始
    # 就等于总大小），且 Windows 在所有写句柄关闭前不保证刷新文件 mtime，
    # 只看 size/mtime 会把仍在正常写入的下载误判为停滞；进程 I/O 计数随每次
    # 写系统调用增长，与写句柄状态、文件时间戳都无关。stdout 与文件状态只作
    # 为额外的活动信号，不会因为它们静默就中断下载。
    parse_task = asyncio.ensure_future(_parse_stream())
    stalled = False
    last_activity = t0  # 最近一次观察到的活动时刻（输出或写入）
    last_size_check = t0
    last_file_state = (-1, -1)
    last_write_bytes = -1  # -1 = 尚未采到进程写入计数基线
    no_write_io_warned = False
    try:
        while not parse_task.done():
            now = time.monotonic()
            # 每 0.5s 采样一次文件状态与进程写入计数
            if now - last_size_check >= 0.5:
                current_state = _output_state()
                if current_state != last_file_state:
                    last_file_state = current_state
                    last_activity = now
                write_bytes = _proc_write_bytes()
                if write_bytes is None:
                    # 拿不到计数（psutil 不可用/进程已退出）：本样本无可靠信号
                    last_write_bytes = -1
                else:
                    if last_write_bytes >= 0 and write_bytes != last_write_bytes:
                        last_activity = now
                    last_write_bytes = write_bytes
                last_size_check = now
            last_activity = max(last_activity, last_output)
            remaining = timeout - (time.monotonic() - last_activity)
            if remaining <= 0 and last_write_bytes < 0:
                # 没有可靠写入计数时，不以 size/mtime 长时间不变作为杀掉 local
                # 进程的充分条件：宁可继续等待，也不误杀仍在写盘的下载
                if not no_write_io_warned:
                    logger.warning(
                        f"[--local] 进程写入计数不可用, 暂不按停滞中断: {url}"
                    )
                    no_write_io_warned = True
                last_activity = time.monotonic()
                remaining = timeout
            if remaining <= 0:
                stalled = True
                break
            # 分段等待：parse 结束时立刻返回，同时保证每 0.5s 复查一次文件写入
            await asyncio.wait({parse_task}, timeout=min(remaining, 0.5))
        if stalled:
            # 进程既无输出也无写入：杀掉后 stdout 关闭，parse_task 随之自行结束
            proc.kill()
            await proc.wait()
            record.status = "failed"
            record.error = f"CLI 停滞超时 ({timeout:.0f}s 无输出且进程无写入)"
            record.duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(
                f"[--local] 停滞 {timeout:.0f}s 无输出且进程无写入, 判定中断: {url}"
            )
            raise RuntimeError(
                f"FluxDown CLI 停滞超时: {timeout:.0f}s 无输出且进程无写入"
            ) from None

        await parse_task
        exit_code = await proc.wait()
    except asyncio.CancelledError:
        # 用户取消：必须杀掉 CLI 子进程，否则它在后台继续下载
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        record.status = "failed"
        record.error = "用户取消"
        logger.info(f"[--local] 用户取消,已结束 CLI 进程: {url}")
        raise
    except Exception:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        record.status = "failed"
        raise

    record.duration_ms = int((time.monotonic() - t0) * 1000)

    if exit_code != 0:
        record.status = "failed"
        stderr_tail = buf[-4000:].decode("utf-8", errors="replace") if buf else ""
        record.error = f"exit={exit_code}: {stderr_tail[:300]}"
        logger.warning(f"[--local] 退出码 {exit_code}: {stderr_tail[:200]}")
        raise RuntimeError(f"FluxDown CLI 退出码 {exit_code}: {stderr_tail[:200]}")

    # checksum 校验失败会在 CLI 输出里包含相关关键词
    output = buf.decode("utf-8", errors="replace").lower() if buf else ""
    if "checksum" in output and ("mismatch" in output or "fail" in output):
        record.status = "checksum_fail"
        record.error = "FluxDown 内置 checksum 校验失败"
        raise RuntimeError("FluxDown checksum 校验失败")

    if not destination.is_file():
        record.status = "failed"
        record.error = "CLI 成功退出但文件未落地"
        raise RuntimeError("FluxDown CLI 成功但文件未落地")

    record.size = destination.stat().st_size
    record.status = "success"
    logger.success(
        f"[--local] 下载完成: {destination.name}, 大小={record.size} 字节, 耗时={record.duration_ms}ms"
    )
    return record.size, record


# ---------------------------------------------------------------------------
# 全盘检测：自动发现 FluxDown 并择优推荐


@dataclass
class FluxdownCandidate:
    """一个候选 FluxDown 可执行文件。"""

    path: Path
    is_portable_cli: bool  # 同目录存在 portable 标记 → CLI 便携版；否则是全量版
    dir_mtime: float = 0.0


# 全盘扫描时跳过的目录名（小写比较）；$ 开头的系统目录统一跳过
_SCAN_PRUNE_DIRS = {
    "windows",
    "windowsapps",
    "recycle.bin",
    "system volume information",
    "recovery",
    "perflogs",
    "msocache",
    "node_modules",
    ".git",
    "__pycache__",
    "venv",
    ".venv",
    ".pixi",
    ".cargo",
    "temp",
}

# 全量版桌面程序的 exe 名（无 portable 标记，用它下载会在用户队列里留记录）
_FLUXDOWN_EXE_NAMES = update_native.FLUXDOWN_EXE_NAMES


def _candidate_drives() -> list[str]:
    """由当前平台枚举可扫描的磁盘根目录。"""
    return update_native.candidate_drives()


def _scan_drives(
    drives: list[str],
    budget: float,
    preferred_drive: str | None = None,
) -> list[Path]:
    """按盘扫描 fluxdown*.exe；MAS 所在盘优先，每盘均分时限，超时返回已收集部分。

    C 盘这类目录树很大的盘在时限内可能走不完，属于已知取舍：
    优先保证离 MAS 近的盘（更可能被用户选用的位置）先被扫到。
    """
    found: list[Path] = []

    def _walk(dir_path: str, deadline: float) -> None:
        if time.monotonic() > deadline:
            return
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return
        for entry in entries:
            if time.monotonic() > deadline:
                return
            name = entry.name.lower()
            try:
                if entry.is_file(follow_symlinks=False):
                    if name in _FLUXDOWN_EXE_NAMES:
                        found.append(Path(entry.path))
                elif entry.is_dir(follow_symlinks=False):
                    if name in _SCAN_PRUNE_DIRS or name.startswith("$"):
                        continue
                    _walk(entry.path, deadline)
            except OSError:
                continue

    # MAS 所在盘排最前（就近原则同样适用于扫描顺序）
    ordered = list(drives)
    if preferred_drive:
        pref = preferred_drive.rstrip("\\").lower()
        ordered.sort(key=lambda d: 0 if d.rstrip("\\").lower() == pref else 1)

    t0 = time.monotonic()
    per_drive = budget / len(ordered)
    for idx, drive in enumerate(ordered):
        _walk(drive, t0 + (idx + 1) * per_drive)
    return found


def _common_prefix_len(a: Path, b: Path) -> int:
    """两个路径的公共前缀段数，越大代表离得越近（同父目录得分最高）。"""
    n = 0
    for part_a, part_b in zip(a.parts, b.parts):
        if part_a.lower() != part_b.lower():
            break
        n += 1
    return n


def fluxdown_detect(
    configured_path: str | None = None,
    scan_budget: float = 20.0,
) -> dict:
    """全盘检测 FluxDown：收集候选 → CLI 便携版优先 → 就近优先 → 新目录优先。

    择优顺序：
        1. CLI 便携版（同目录有 ``portable`` 标记）优先于全量版
        2. 与 MAS 同一盘符优先
        3. 与 MAS 路径公共前缀更长（更"近"，含同父目录）优先
        4. exe 所在目录修改时间更新者优先

    返回 dict（可直接展开为 FluxdownDetectOut）：
        path: 择优后的 exe 路径，未找到为 None
        is_portable_cli: 选中项是否 CLI 便携版
        only_full_warning: 设备上没有任何 CLI 便携版、选中项是全量版时为 True
                           ——此时用它下载会在用户 FluxDown 队列里留记录
        scanned_drives: 实际扫描的盘符
        candidates: 全部候选（按择优顺序，最多 8 条）
    """
    raw: list[Path] = []

    # 快速候选：用户配置目录 / MAS 便携包 / PATH（不需要全盘扫描就能命中的位置）
    known_dirs: list[Path] = []
    if configured_path:
        p = Path(configured_path)
        if p.is_dir():
            known_dirs.append(p)
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path.cwd()
    known_dirs.append(base / "res" / "fluxdown-cli")
    known_dirs.append(Path.cwd() / "res" / "fluxdown-cli")
    for dir_path in known_dirs:
        if dir_path.is_dir():
            for name in _FLUXDOWN_EXE_NAMES:
                exe = dir_path / name
                if exe.is_file():
                    raw.append(exe)
    for name in ("fluxdown", "fluxdown-cli"):
        found = shutil.which(name)
        if found:
            raw.append(Path(found))

    # 全盘扫描（时限内尽量找全，用户配置目录即使没有 portable 标记也会被扫出来）
    drives = _candidate_drives()
    mas_drive = str(Path.cwd().drive)
    raw.extend(_scan_drives(drives, scan_budget, mas_drive + "\\"))

    # 去重（Windows 大小写不敏感）
    unique: dict[str, Path] = {}
    for exe in raw:
        unique.setdefault(str(exe).lower(), exe)

    candidates: list[FluxdownCandidate] = []
    for exe in unique.values():
        is_cli = (exe.parent / "portable").is_file()
        try:
            mtime = exe.parent.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append(FluxdownCandidate(exe, is_cli, mtime))

    if not candidates:
        return {
            "path": None,
            "is_portable_cli": False,
            "only_full_warning": False,
            "scanned_drives": drives,
            "candidates": [],
        }

    mas_root = Path.cwd()
    candidates.sort(
        key=lambda c: (
            0 if c.is_portable_cli else 1,
            0 if c.path.drive.lower() == mas_root.drive.lower() else 1,
            -_common_prefix_len(c.path.parent, mas_root),
            -c.dir_mtime,
        )
    )

    best = candidates[0]
    has_cli = any(c.is_portable_cli for c in candidates)
    return {
        "path": str(best.path),
        "is_portable_cli": best.is_portable_cli,
        "only_full_warning": not best.is_portable_cli and not has_cli,
        "scanned_drives": drives,
        "candidates": [
            {"path": str(c.path), "is_portable_cli": c.is_portable_cli}
            for c in candidates[:8]
        ],
    }


# ---------------------------------------------------------------------------
# Server 模式：常驻 fluxdown-agent --server + fluxdownd，跨进程断点续传
#
# 与 --local 单次调用的区别：任务持久化在 MAS 私有数据根 data\fluxdown_server
# 下的 server 数据库，断网/失败后可经 ``fluxdown resume <task_id>`` 从已下载
# 分段续传，不从头。
#
# 与用户全量版 FluxDown 的关系（v0.5.9 实测）：
#   - 数据目录经 FLUXDOWN_DATA_DIR 强制指向 MAS 私有 data\fluxdown_server，
#     与用户主程序及其便携版数据库完全隔离；
#   - 自选 gateway/daemon 端口对且 spawn 前先验空闲，agent 的 terminate_stale
#     （按进程名全杀）路径只在"自己的 daemon 端口被异己占用"时触发，不会触碰
#     用户全量版（17801 上的任何进程 MAS 一概不碰）；
#   - MAS 退出清理一律按 PID，禁止按进程名 taskkill。

_SERVER_GATEWAY_BASE = 27896  # agent 管理 API（HTTP/Web）
_SERVER_DAEMON_BASE = 27897  # daemon RPC（WS），须与 gateway 相邻
_SERVER_READY_TIMEOUT = 20.0  # 管理 API 就绪晚于 ping，给足余量
_SERVER_MAP_NAME = "mas_task_map.json"
_SERVER_TOKEN_NAME = "mas_server.token"

# 任务 status 枚举（TaskDto.status）：0=等待 1=下载中 2=暂停 3=完成 4=失败 5=准备中
_TASK_STATUS_PENDING = 0
_TASK_STATUS_DOWNLOADING = 1
_TASK_STATUS_PAUSED = 2
_TASK_STATUS_DONE = 3
_TASK_STATUS_FAILED = 4
_TASK_STATUS_PREPARING = 5

# 活动态：daemon 仍可能持有输出文件写入权。pending/preparing 虽然还没开始
# 写数据，但会自行转入 downloading，判断"能否覆写目标文件"时必须一并排除。
_ACTIVE_STATUSES = (
    _TASK_STATUS_PENDING,
    _TASK_STATUS_DOWNLOADING,
    _TASK_STATUS_PREPARING,
)


@dataclass
class _ServerHandle:
    """一次成功 spawn 的便携 server 套件。"""

    gateway_port: int
    daemon_port: int
    token: str
    agent_pid: int
    cli_exe: Path
    data_dir: Path


class _ServerState:
    """进程内单例：便携 server 套件的生命周期与 task 映射。"""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.handle: _ServerHandle | None = None
        self.spawned_by_us: bool = False
        self.checked_available: dict[
            str, tuple[float, bool]
        ] = {}  # cli_dir -> (ts, ok)


_server = _ServerState()


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_port_pair() -> tuple[int, int] | None:
    """从基准端口起按 +2 步进找一对都空闲的 (gateway, daemon)。"""
    for offset in range(0, 40, 2):
        g = _SERVER_GATEWAY_BASE + offset
        d = _SERVER_DAEMON_BASE + offset
        if _port_free(g) and _port_free(d):
            return g, d
    return None


def _server_binaries(cli_exe: Path) -> tuple[Path, Path] | None:
    """返回 (fluxdown-agent.exe, fluxdownd.exe)；缺一返回 None。"""
    d = cli_exe.parent
    if update_native.FLUXDOWN_AGENT_NAME is None:
        return None
    agent = d / update_native.FLUXDOWN_AGENT_NAME
    downd = d / update_native.FLUXDOWN_DAEMON_NAME
    if agent.is_file() and downd.is_file():
        return agent, downd
    return None


def _server_data_dir(cli_exe: Path) -> Path:
    """MAS 私有的 server 数据根：token、任务映射、日志都放在其下。

    不能复用 ``cli_exe.parent / "portable_data"``：那是用户便携版自己的数据库
    目录，共用会让 MAS 的任务记录和用户的访问密钥搅在一起，且 spawn 时的
    ``FLUXDOWN_TOKEN_FORCE`` 会连带改写用户自己的数据库密钥。改用 MAS 工作
    目录下的独立数据根后，该变量只覆盖 MAS 私有目录里的密钥，不影响用户的
    便携版数据库与访问密钥。

    ``cli_exe`` 仅为保持调用方签名稳定而保留，数据根与 CLI 位置无关。
    """
    return Path.cwd() / "data" / "fluxdown_server"


def _local_cli_exe(cli_exe: Path) -> Path:
    """把 CLI 复制进 MAS 私有便携目录，让 ``--local`` 的数据落在 MAS 数据根。

    官方 ``--local`` 用 ``resolve_data_dir(None)`` 定位数据目录，只认 exe 同目录
    的 ``portable`` 标记，否则落到用户 ``%LOCALAPPDATA%\\FluxDown``；v0.5.9 的 CLI
    既没有 ``--data-dir`` 参数，也不读 ``FLUXDOWN_DATA_DIR``。因此直接跑用户 CLI
    会把 MAS 的任务记录写进用户自己的数据库。复制一份到私有目录并放置便携标记
    后，exe 同目录即私有根，数据目录随之变成
    ``data/fluxdown_local/portable_data``，与用户本体完全隔离。

    复制失败（磁盘/权限）抛 :class:`RuntimeError`，由上层回退 httpx；绝不退回
    使用用户 CLI，以免污染用户数据。
    """
    root = Path.cwd() / "data" / "fluxdown_local"
    try:
        with _LOCAL_CLI_LOCK:
            root.mkdir(parents=True, exist_ok=True)
            (root / "portable").touch()
            target = root / cli_exe.name
            src_stat = cli_exe.stat()
            stale = True
            if target.is_file():
                dst_stat = target.stat()
                stale = (dst_stat.st_size, dst_stat.st_mtime_ns) != (
                    src_stat.st_size,
                    src_stat.st_mtime_ns,
                )
            if stale:
                # 先写临时名再替换，避免复制中断留下半个不可执行文件。
                # 并行管理命令共用锁，避免争用同一个临时副本。
                tmp = root / f".{cli_exe.name}.tmp"
                shutil.copy2(cli_exe, tmp)
                os.replace(tmp, target)
        return target
    except OSError as error:
        raise RuntimeError(f"无法准备 MAS 私有 FluxDown CLI 副本: {error}") from error


def _server_token_path(cli_exe: Path) -> Path:
    return _server_data_dir(cli_exe) / _SERVER_TOKEN_NAME


def _server_map_path(cli_exe: Path) -> Path:
    return _server_data_dir(cli_exe) / _SERVER_MAP_NAME


def _load_or_create_token(cli_exe: Path) -> str:
    p = _server_token_path(cli_exe)
    try:
        if p.is_file():
            tok = p.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    except OSError:
        pass
    tok = "MasServer-" + secrets.token_hex(8)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(tok, encoding="utf-8")
    except OSError:
        pass
    return tok


def _cli_env(gateway_port: int, token: str) -> dict[str, str]:
    env = os.environ.copy()
    env["FLUXDOWN_URL"] = f"http://127.0.0.1:{gateway_port}"
    env["FLUXDOWN_TOKEN"] = token
    return env


def _run_cli(
    cli_exe: Path, env: dict[str, str], args: list[str], timeout: float = 30.0
) -> tuple[int, str]:
    """同步跑一条 CLI 命令，返回 (exit_code, stdout+stderr)。"""
    try:
        # 管理命令也会初始化 CLI 的便携日志，不能写进用户自己的安装目录。
        private_cli = _local_cli_exe(cli_exe)
        out = subprocess.run(
            [str(private_cli), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=process_platform.platform_process.creation_flags,
        )
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except (OSError, RuntimeError) as e:
        return 1, f"server 不可用: {e}"


def _parse_cli_json(text: str):
    """从 CLI 输出提取首个可解析的 JSON 值（优先对象/数组，其次字符串）。

    CLI 可能把日志混进 stdout：逐个候选起点尝试解析，首个起点失败不会
    挡住后面真正的 JSON（日志里的孤立括号/引号也会被跳过）。
    """
    text = text.strip()
    if not text:
        return None

    def _try_from(start: int):
        # 从最长到最短截断尝试，兼容 JSON 后还跟着日志尾缀的情况
        for end in range(len(text), start, -1):
            try:
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                continue
        return None

    # 先只认 { [（对象/数组才是调用方真正要的），再兜底认 "（JSON 字符串）
    for quote_pass in (False, True):
        for i, ch in enumerate(text):
            if ch in '{["' and (ch == '"') == quote_pass:
                value = _try_from(i)
                if value is not None:
                    return value
    return None


def _ping_ok(cli_exe: Path, gateway_port: int, token: str) -> bool:
    code, out = _run_cli(cli_exe, _cli_env(gateway_port, token), ["ping"], timeout=8)
    return code == 0 and "pong" in out


def _mgmt_ready(cli_exe: Path, gateway_port: int, token: str) -> bool:
    """管理 API 就绪（list 能通），比 ping 晚，ensure 需等到这步。"""
    code, _ = _run_cli(
        cli_exe, _cli_env(gateway_port, token), ["list", "--json"], timeout=10
    )
    return code == 0


def _kill_pid(pid: int) -> None:
    """按 PID 精确结束进程（含子进程树），禁止按进程名。"""
    try:
        process = psutil.Process(pid)
        processes = [process, *process.children(recursive=True)]
        # taskkill /T 依赖系统进程查询，在受限 Windows 环境中会失败；
        # 直接结束本服务的进程句柄，并检查结果，避免静默遗留下载进程。
        for target in processes:
            try:
                target.kill()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=5)
        if alive:
            logger.warning(
                f"FluxDown 服务进程未能退出: {[target.pid for target in alive]}"
            )
    except psutil.NoSuchProcess:
        pass
    except psutil.Error as error:
        logger.warning(f"结束 FluxDown 服务进程失败（PID={pid}）: {error}")


def fluxdown_server_available(cli_exe: Path, enabled: bool) -> bool:
    """可用性检查（30s 缓存）：开关开 + 便携目录有 agent/downd 二进制。"""
    if not enabled:
        return False
    key = str(cli_exe.parent)
    now = time.monotonic()
    hit = _server.checked_available.get(key)
    if hit and (now - hit[0]) < 30.0:
        return hit[1]
    ok = _server_binaries(cli_exe) is not None
    _server.checked_available[key] = (now, ok)
    return ok


def fluxdown_server_ensure(cli_exe: Path) -> _ServerHandle | None:
    """确保便携 server 套件在跑；返回句柄或 None（不可用/启动失败）。

    已存活（ping+管理 API 通）直接复用；否则按五件套环境变量 spawn，
    轮询至管理 API 就绪；超时按 PID 清理后返回 None。
    """
    bins = _server_binaries(cli_exe)
    if bins is None:
        return None
    agent_exe, _ = bins
    # 先准备管理 CLI，再启动进程，避免副本失败留下未登记的 agent。
    try:
        _local_cli_exe(cli_exe)
    except (OSError, RuntimeError):
        logger.warning("[server] 管理 CLI 副本不可用，跳过启动")
        return None
    data_dir = _server_data_dir(cli_exe)
    token = _load_or_create_token(cli_exe)

    with _server.lock:
        h = _server.handle
        if h is not None and os.path.normcase(
            os.path.abspath(str(h.cli_exe))
        ) != os.path.normcase(os.path.abspath(str(cli_exe))):
            # CLI 路径变了（用户改配置/检测到新目录）：旧句柄的端口与数据目录
            # 不再适用，不复用；由我们 spawn 的旧套件按 PID 清理
            if _server.spawned_by_us:
                _kill_pid(h.agent_pid)
            _server.handle = None
            _server.spawned_by_us = False
            h = None
        if (
            h
            and _ping_ok(h.cli_exe, h.gateway_port, h.token)
            and _mgmt_ready(h.cli_exe, h.gateway_port, h.token)
        ):
            logger.debug(f"[server] 复用已就绪套件: gateway={h.gateway_port}")
            return h

        pair = _find_port_pair()
        if pair is None:
            logger.warning("[server] 找不到空闲的 gateway/daemon 端口对")
            return None
        gateway_port, daemon_port = pair

        env = os.environ.copy()
        env.update(
            {
                "FLUXDOWN_DATA_DIR": str(data_dir),
                "FLUXDOWN_DAEMON_URL": f"ws://127.0.0.1:{daemon_port}/rpc",
                "FLUXDOWN_BIND": f"127.0.0.1:{gateway_port}",
                "FLUXDOWN_TOKEN": token,
                "FLUXDOWN_TOKEN_FORCE": "1",
            }
        )
        logs = data_dir / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
            out_log = open(logs / "mas-agent-spawn.out.log", "ab")
            err_log = open(logs / "mas-agent-spawn.err.log", "ab")
        except OSError:
            out_log = subprocess.DEVNULL
            err_log = subprocess.DEVNULL
        try:
            proc = subprocess.Popen(
                [str(agent_exe), "--server"],
                env=env,
                stdout=out_log,
                stderr=err_log,
                creationflags=process_platform.platform_process.agent_flags,
            )
        except OSError:
            logger.warning("[server] agent 进程启动失败")
            return None

        logger.info(
            f"[server] 启动便携套件: agent PID={proc.pid}, gateway={gateway_port}, daemon={daemon_port}"
        )
        deadline = time.monotonic() + _SERVER_READY_TIMEOUT
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break  # agent 已退出
            if _ping_ok(cli_exe, gateway_port, token) and _mgmt_ready(
                cli_exe, gateway_port, token
            ):
                ready = True
                break
            time.sleep(0.3)

        if not ready:
            _kill_pid(proc.pid)
            logger.warning(
                f"[server] 便携套件 {_SERVER_READY_TIMEOUT:.0f}s 内未就绪,已按 PID 清理"
            )
            return None

        h = _ServerHandle(
            gateway_port=gateway_port,
            daemon_port=daemon_port,
            token=token,
            agent_pid=proc.pid,
            cli_exe=cli_exe,
            data_dir=data_dir,
        )
        _server.handle = h
        _server.spawned_by_us = True
        logger.success(f"[server] 便携套件就绪: http://127.0.0.1:{gateway_port}")
        return h


def fluxdown_server_shutdown() -> None:
    """MAS 退出时清理：仅当 server 由本进程 spawn 时，按 PID 结束 agent（daemon 随之退）。

    若 agent 由先前 MAS 进程留下且本进程只是复用，不强行清理（避免误杀）；
    daemon 在无 agent 连接后本就会退出，且下个 MAS 实例 ensure 时会复用/重启。
    """
    with _server.lock:
        if _server.handle is not None and _server.spawned_by_us:
            _kill_pid(_server.handle.agent_pid)
        _server.handle = None
        _server.spawned_by_us = False


atexit.register(fluxdown_server_shutdown)


# --- task_id 映射持久化（续传的钥匙） -------------------------------------


def _map_key(url: str, destination: Path) -> str:
    import hashlib

    return hashlib.sha1(f"{url}|{destination}".encode("utf-8")).hexdigest()


def _load_task_map(cli_exe: Path) -> dict:
    p = _server_map_path(cli_exe)
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, ValueError):
        pass
    return {}


_TASK_MAP_LOCK = threading.Lock()  # 映射读-改-写全程持锁，防并发丢条目


def _save_task_map(cli_exe: Path, m: dict) -> None:
    """原子写映射文件：先写临时文件再 os.replace，避免读到半截 JSON。

    仅限已持有 _TASK_MAP_LOCK 的调用方使用（配合 _load_task_map 做读改写）。
    """
    p = _server_map_path(cli_exe)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def _map_pop(cli_exe: Path, key: str) -> None:
    """带锁删除一个映射条目。"""
    with _TASK_MAP_LOCK:
        m = _load_task_map(cli_exe)
        if m.pop(key, None) is not None:
            _save_task_map(cli_exe, m)


def _map_put(
    cli_exe: Path,
    key: str,
    task_id: str,
    url: str,
    destination: Path,
    proxy: str | None = None,
) -> None:
    """带锁写入/更新一个映射条目（重读全表，fail_count 跨写入保留）。"""
    with _TASK_MAP_LOCK:
        m = _load_task_map(cli_exe)
        m[key] = {
            "task_id": task_id,
            "url": url,
            "save_path": str(destination),
            "updated": time.time(),
            "fail_count": int((m.get(key) or {}).get("fail_count") or 0),
            "proxy_hash": _proxy_hash(proxy),
        }
        _save_task_map(cli_exe, m)


def _proxy_hash(proxy: str | None) -> str:
    """本地续传配置指纹，避免将代理认证信息写进任务映射。"""
    import hashlib
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(proxy or "")
    endpoint = urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[-1]))
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()


def fluxdown_server_forget(cli_exe: Path, url: str, destination: Path) -> None:
    """任务完成（MAS 二次校验通过）后删除映射条目。"""
    _map_pop(cli_exe, _map_key(url, Path(destination)))


def fluxdown_server_task_safe_to_overwrite(
    cli_exe: Path, url: str, destination: Path, *, timeout: int = 15
) -> bool:
    """判断 (url, destination) 对应的 FluxDown server 任务是否已确认停止/不存在。

    用于在改用内置 httpx 等"以 wb 重写 destination"的路径前排除双写：
    - 无映射：从未经 server 下载过 → 安全
    - paused(2)：已暂停，daemon 不再写输出文件 → 安全
    - pending/downloading/preparing(0/1/5)：先 pause 再复查，只有确认离开
      活动态才安全（这些状态随时可能开始写数据）
    - completed/error(3/4)：终态 → 安全
    - 未知状态码（不在 0..5）：语义不明，按不安全处理
    - status 查询失败 / server 不可用：管理通道异常，**不能排除 daemon 仍在
      写**，返回 False，调用方应阻止覆写
    """
    key = _map_key(url, Path(destination))
    entry = _load_task_map(cli_exe).get(key) or {}
    task_id = entry.get("task_id")
    if not task_id:
        return True
    handle = fluxdown_server_ensure(cli_exe)
    if handle is None:
        # server 都起不来，无法证明 daemon 是否仍在写 destination，按不安全处理
        return False
    env = _cli_env(handle.gateway_port, handle.token)

    def _status_code() -> int | None:
        code, out = _run_cli(
            cli_exe, env, ["status", task_id, "--json"], timeout=timeout
        )
        if code != 0:
            return None
        data = _parse_cli_json(out)
        if not isinstance(data, dict):
            return None
        try:
            return int(data.get("status"))
        except (TypeError, ValueError):
            return None

    status = _status_code()
    if status is None:
        return False
    if status == _TASK_STATUS_PAUSED:
        return True
    if status in _ACTIVE_STATUSES:
        # 活动态：先暂停，再复查状态是否真的离开活动态。
        # pause 返回 124（客户端超时）同样不能证明没生效，按未确认处理
        pause_code, _ = _run_cli(cli_exe, env, ["pause", task_id], timeout=10)
        if pause_code != 0:
            return False
        paused = _status_code()
        return paused is not None and paused not in _ACTIVE_STATUSES
    if status in (_TASK_STATUS_DONE, _TASK_STATUS_FAILED):
        return True
    return False


def fluxdown_server_mark_failure(cli_exe: Path, url: str, destination: Path) -> int:
    """把该 (url, destination) 任务的中断次数 +1 并持久化，返回累计次数。

    上层据累计次数决定何时在失败提示中建议改用内置 httpx（用户多次重试仍失败）。
    任务完成（fluxdown_server_forget）后计数随映射一起清零。
    """
    key = _map_key(url, Path(destination))
    with _TASK_MAP_LOCK:
        task_map = _load_task_map(cli_exe)
        entry = task_map.get(key) or {}
        count = int(entry.get("fail_count") or 0) + 1
        task_map[key] = {
            **entry,
            "task_id": entry.get("task_id"),
            "url": url,
            "save_path": str(destination),
            "updated": time.time(),
            "fail_count": count,
        }
        _save_task_map(cli_exe, task_map)
    return count


# --- server 模式下载 -------------------------------------------------------


async def _wait_thread_done(task: "asyncio.Task", *, propagate_cancel: bool = False):
    """等待线程任务结束并返回其结果；等待期间协程被取消也继续等。

    add/resume/map_put 这类子进程或映射写调用的结果（task_id、退出码、
    落盘完成）丢了会导致后台残留下载或映射未持久化，故取消时不能直接
    放弃线程。

    propagate_cancel=True 时，等线程跑完后把暂存的 CancelledError 重新抛出，
    让调用方感知"用户在我等待期间取消了"，进入统一的取消清理；False 时
    静默吞掉取消（用于纯补偿性清理，调用方自己决定后续路径）。
    """
    cancelled: asyncio.CancelledError | None = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as e:
            if task.done():
                # 线程已结束但取消同时到达：把取消重新抛给调用方，
                # 由调用方决定是进入清理还是继续；不静默吞掉
                if propagate_cancel:
                    raise e
                return task.result()
            if cancelled is None:
                cancelled = e
            continue
    if propagate_cancel and cancelled is not None:
        raise cancelled
    return result


async def _to_thread_strong(func, /, *args, propagate_cancel: bool = False):
    """to_thread 的取消安全版：外层协程被取消也等线程跑完再退出。

    propagate_cancel=True 时，若等待期间发生取消，等线程跑完后把
    CancelledError 重新抛给调用方。
    """
    return await _wait_thread_done(
        asyncio.ensure_future(asyncio.to_thread(func, *args)),
        propagate_cancel=propagate_cancel,
    )


def _extract_task_id(out: str) -> str | None:
    """从 add 输出提取 task_id：优先 JSON（数组/对象），其次 'added <uuid>' 文本。"""
    data = _parse_cli_json(out)
    if isinstance(data, list) and data and isinstance(data[0], str):
        return data[0]
    if isinstance(data, dict):
        v = data.get("taskId") or data.get("task_id") or data.get("id")
        return str(v) if v else None
    m = re.search(r"added\s+([0-9a-fA-F-]{36})", out)
    return m.group(1) if m else None


class FluxdownCancelUnconfirmed(RuntimeError):
    """用户取消后无法确认 FluxDown 任务已停止。

    daemon 可能仍在写目标文件，上层不能把它当成"取消成功"静默收场，
    而应按显式失败上报并提示用户检查 FluxDown 状态。

    定义在 cli 这一侧而非 ``app.services.common.update.fluxdown``，因为后者已经
    import 本模块，反向 import 会循环。
    """


_DESTINATION_OWNERS: ContextVar[tuple] = ContextVar(
    "fluxdown_destination_owners", default=()
)


@asynccontextmanager
async def fluxdown_destination_lock(cli_exe: Path, destination: Path):
    """跨协程、跨进程锁住输出文件；取消等待不会遗留后台持锁线程。"""
    import errno
    import hashlib

    key = hashlib.sha256(
        os.path.normcase(str(destination.resolve())).encode()
    ).hexdigest()
    owner = (asyncio.current_task(), key)
    owners = _DESTINATION_OWNERS.get()
    if owner in owners:
        yield
        return
    path = _server_data_dir(cli_exe) / "locks" / f"{key}.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        while True:
            handle.seek(0)
            try:
                file_lock.acquire(handle)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                await asyncio.sleep(0.05)
        token = _DESTINATION_OWNERS.set((*owners, owner))
        try:
            yield
        finally:
            _DESTINATION_OWNERS.reset(token)
            file_lock.release(handle)


@_using_fluxdown
async def fluxdown_server_download(
    url: str,
    destination: Path,
    *,
    cli_exe: Path,
    segments: int = 8,
    proxy: str | None = None,
    timeout: float = 300,
    progress: DownloadProgress | None = None,
) -> tuple[int, FluxdownDownloadRecord]:
    """串行管理同一输出文件的续传、代理切换与下载，避免两个任务同时写入。"""
    async with fluxdown_destination_lock(cli_exe, destination):
        return await _fluxdown_server_download(
            url,
            destination,
            cli_exe=cli_exe,
            segments=segments,
            proxy=proxy,
            timeout=timeout,
            progress=progress,
        )


async def _fluxdown_server_download(
    url: str,
    destination: Path,
    *,
    cli_exe: Path,
    segments: int = 8,
    proxy: str | None = None,
    timeout: float = 300,
    progress: DownloadProgress | None = None,
) -> tuple[int, FluxdownDownloadRecord]:
    """经便携 server 套件下载（add 新任务或 resume 既有任务），支持断点续传。

    失败（非零退出/任务 failed/超时）抛 RuntimeError，但 **保留 task 映射**，
    上层重试时同一 (url, destination) 会走 resume 续传而非重新 add。
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    record = FluxdownDownloadRecord(
        url=url, destination=str(destination), segments=segments, proxy=proxy
    )
    t0 = time.monotonic()

    # ensure 的结果缓存于 _ServerState 单例（线程内完成写入），取消时即使放弃
    # 等待也不丢状态，故此处无需强等待
    handle = await asyncio.to_thread(fluxdown_server_ensure, cli_exe)
    if handle is None:
        record.status = "failed"
        record.error = "server 套件不可用或启动超时"
        record.duration_ms = int((time.monotonic() - t0) * 1000)
        raise RuntimeError("FluxDown server 不可用")

    env = _cli_env(handle.gateway_port, handle.token)
    key = _map_key(url, destination)
    mapping = _load_task_map(cli_exe).get(key) or {}
    task_id: str | None = mapping.get("task_id")

    def _status(tid: str) -> dict | None:
        code, out = _run_cli(cli_exe, env, ["status", tid, "--json"], timeout=15)
        if code != 0:
            return None
        data = _parse_cli_json(out)
        return data if isinstance(data, dict) else None

    # 既有 task：查询服务端是否仍在；None 既可能是"任务已不存在"，也可能是
    # "管理通道异常但 daemon 仍在下载"。前者可安全清映射重 add，后者必须先
    # 尽力暂停再决定是否清除，否则会以同一 destination 启动第二个写入者。
    resumed = False
    # 取消清理前必须先等这条在飞的 CLI 线程落定：add 可能已建出任务（须取回
    # id 落映射），resume 的 124 只代表客户端超时（服务端可能已恢复），两者
    # 都要先拿到结果再决定暂停谁
    inflight_cli: asyncio.Task | None = None

    async def _confirm_paused(*, propagate_cancel: bool = True) -> bool:
        """确认 daemon 任务已停止/已释放输出文件。

        _run_cli 超时不抛异常而返回 124，仅凭调用"发了 pause"不等于成功；
        再查一次 status：失败(None)说明管理通道仍不通，不能排除后台写入，
        不允许上层据此降级 --local 双写。

        propagate_cancel=False 用于取消清理阶段：此时已在取消流程里，二次
        取消不能打断"暂停 + 复查"，否则任务会在无人等待时继续下载。
        """
        try:
            code, _ = await _to_thread_strong(
                _run_cli,
                cli_exe,
                env,
                ["pause", task_id],
                10,
                propagate_cancel=propagate_cancel,
            )
        except Exception:
            return False
        if code == 3:
            return True  # 服务端明确报告任务不存在，文件写入权已释放。
        if code != 0:
            return False
        try:
            st = await _to_thread_strong(
                _status, task_id, propagate_cancel=propagate_cancel
            )
        except Exception:
            return False
        if st is None:
            return False
        # 能查到状态还不够：pause 可能被接受但任务仍处于活动态（pending/
        # downloading/preparing），只有离开活动态才算确认停下，否则会在
        # 无人等待时继续写输出文件
        try:
            status_code = int(st.get("status"))
        except (TypeError, ValueError):
            return False
        return status_code in (2, 3, 4)

    # 既有任务查询 → resume/add → 映射落盘 → 轮询 → 完成归位，整段共用一个
    # 取消作用域：任一阶段被取消都走同一套清理（确认暂停），不吞掉取消，
    # 也不会继续走完成路径。
    try:
        if task_id and mapping.get("proxy_hash") != _proxy_hash(proxy):
            # resume 不接受 --proxy，必须停下旧任务后重建。旧版映射没有指纹，
            # 同样不能假定其网络配置；不删除旧任务的文件，残包沿用下方隔离路径。
            if not await _confirm_paused():
                raise RuntimeError("代理已变更，但 FluxDown 旧任务未确认停止")
            code, _ = await _to_thread_strong(
                _run_cli, cli_exe, env, ["rm", task_id], 15, propagate_cancel=True
            )
            if code not in (0, 3):
                raise RuntimeError("代理已变更，但 FluxDown 旧任务未能移除，保留映射")
            await _to_thread_strong(_map_pop, cli_exe, key, propagate_cancel=True)
            task_id = None
            logger.info("代理配置已变更，使用当前代理重建 FluxDown 下载任务")
        if task_id:
            st0 = await asyncio.to_thread(_status, task_id)
            if st0 is None:
                # 状态未知：尽力暂停（pause 失败也不放弃任务），仅当 pause 返回 0
                # 且重查 status 能拿到响应（任务确已停下）才清映射重新 add；
                # 否则保留映射抛出，让上层按"任务未确认停止"处理。
                # propagate_cancel=True：pause 是进入清理前的最后一步，若用户
                # 此时取消，必须把取消抛给外层 except 统一清理，不能吞掉继续 add
                try:
                    pause_code, _ = await _to_thread_strong(
                        _run_cli,
                        cli_exe,
                        env,
                        ["pause", task_id],
                        10,
                        propagate_cancel=True,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pause_code = 1
                confirmed = pause_code == 3  # 明确 NotFound，可清除取消后残留的映射。
                if pause_code == 0:
                    st_after = await asyncio.to_thread(_status, task_id)
                    # 有响应不等于已停下：pause 可能被接受但任务仍处于活动态，
                    # 必须确认离开 pending/downloading/preparing 才能清映射重建
                    try:
                        after_status = int(st_after.get("status")) if st_after else None
                    except (TypeError, ValueError):
                        after_status = None
                    confirmed = after_status is not None and after_status in (2, 3, 4)
                if confirmed:
                    task_id = None
                    await asyncio.to_thread(_map_pop, cli_exe, key)
                else:
                    record.status = "failed"
                    record.error = "既有任务状态未知且无法确认已停止，保留映射待续传"
                    record.duration_ms = int((time.monotonic() - t0) * 1000)
                    logger.warning(
                        f"[server] 进入时任务 {task_id} 状态未知,无法确认已停止,保留映射"
                    )
                    raise RuntimeError(
                        "FluxDown server status 查询失败（任务未确认停止）"
                    )

        if task_id:
            inflight_cli = asyncio.ensure_future(
                asyncio.to_thread(_run_cli, cli_exe, env, ["resume", task_id], 30)
            )
            code, out = await asyncio.shield(inflight_cli)
            inflight_cli = None
            if code == 0:
                resumed = True
                logger.info(f"[server] 续传任务: {task_id} ({url})")
            else:
                # resume 失败按官方退出码分类（native/cli/src/exit.rs，aria2 语义）：
                # 124=MAS 包装超时、2=HTTP 超时、5=网络/断连——都不能证明服务端
                # 未收到 resume，旧任务可能已在后台恢复写盘，此时清映射重新 add
                # 会产生两个写入者双写同一文件。保留映射按"未确认停止"抛出
                if code in (124, 2, 5):
                    record.status = "failed"
                    record.error = f"resume 通信失败(exit={code})，无法确认旧任务状态，保留映射待续传"
                    record.duration_ms = int((time.monotonic() - t0) * 1000)
                    logger.warning(
                        f"[server] resume 通信失败 (exit={code}, task {task_id}), "
                        "无法确认旧任务状态,保留映射"
                    )
                    raise RuntimeError(
                        "FluxDown server status 查询失败（任务未确认停止）"
                    )
                if code == 3:
                    # 3=NotFound：服务端明确答复任务不存在，归属已确认终止，
                    # 清映射重新 add 是安全的
                    logger.info(
                        f"[server] resume 返回任务不存在 (task {task_id}),重新 add"
                    )
                    task_id = None
                    await asyncio.to_thread(_map_pop, cli_exe, key)
                else:
                    # 其余非零（1/24/32 等）：先查任务真实状态再决定归属，不能
                    # 默认任务已消失；状态字段缺失/非数值同样视为无法确认
                    st1 = await asyncio.to_thread(_status, task_id)
                    raw_status = None if st1 is None else st1.get("status")
                    try:
                        status1 = int(raw_status)  # type: ignore[arg-type]
                    except (TypeError, ValueError):
                        record.status = "failed"
                        record.error = f"resume 失败(exit={code})且任务状态不可确认，保留映射待续传"
                        record.duration_ms = int((time.monotonic() - t0) * 1000)
                        raise RuntimeError(
                            "FluxDown server status 查询失败（任务未确认停止）"
                        )
                    if status1 == _TASK_STATUS_FAILED:
                        # 任务已终止：清映射重新 add
                        logger.info(
                            f"[server] resume 失败且任务已终止 (task {task_id}),重新 add"
                        )
                        task_id = None
                        await asyncio.to_thread(_map_pop, cli_exe, key)
                    elif status1 == _TASK_STATUS_DONE or status1 in _ACTIVE_STATUSES:
                        # 服务端仍持有任务且已完成/活动：resume 实际已生效，
                        # 交给轮询与完成归位，不重新 add
                        resumed = True
                        logger.info(
                            f"[server] resume 返回 exit={code} 但任务状态={status1},按已恢复处理"
                        )
                    else:
                        # paused/未知状态码：无法确认，保守保留映射停止本轮，
                        # 下次重试会再次 resume
                        record.status = "failed"
                        record.error = f"resume 失败(exit={code})，任务状态={status1} 未确认，保留映射待续传"
                        record.duration_ms = int((time.monotonic() - t0) * 1000)
                        raise RuntimeError(
                            "FluxDown server status 查询失败（任务未确认停止）"
                        )

        if task_id is None:
            # 新建任务前把已存在的 destination 改名隔离：FluxDown 默认
            # FileExistsBehavior::Rename，目标重名时会把新包改名（如
            # "download (1).temp"）并回写数据库 fileName，完成时很难对回约定
            # 路径。改名而不是删除，因为无法确认这份残留的归属（可能是上次
            # httpx 或取消留下的残包），删掉可能丢用户数据。
            if destination.exists():
                stale = destination.with_name(
                    f"{destination.name}.stale-{int(time.time())}"
                )
                try:
                    os.replace(destination, stale)
                    logger.warning(
                        f"[server] 目标已存在,改名隔离保留: {destination.name} -> {stale.name}"
                    )
                except OSError as e:
                    logger.warning(f"[server] 目标残留改名失败,继续 add: {e}")
            args = [
                "add",
                url,
                "-d",
                str(destination.parent),
                "-o",
                destination.name,
                "--segments",
                str(segments),
                "--json",
            ]
            if proxy:
                args += ["--proxy", proxy]
            inflight_cli = asyncio.ensure_future(
                asyncio.to_thread(_run_cli, cli_exe, env, args, 60)
            )
            code, out = await asyncio.shield(inflight_cli)
            inflight_cli = None
            new_id: str | None = _extract_task_id(out)
            if code != 0 or not new_id:
                # add 失败：若服务端已把任务建出来了（"added <id>" 后 probe 失败），
                # 取出该 id 并持久化映射 —— 重试时 resume 续传，不重新 add；
                # 同时尽力暂停该任务，防止 daemon 后台继续下载。
                # 若连 id 都没有（add 完全没成功），抛错但**不视为进程异常**：
                # 让上层以可续传语义重试（同 url 会再次尝试 add，已有分段由服务端保留）。
                if new_id:
                    task_id = new_id
                    # 强等待：取消时也必须落盘+暂停，否则 daemon 后台继续下载
                    await _to_thread_strong(
                        _map_put, cli_exe, key, task_id, url, destination, proxy
                    )
                    try:
                        await _to_thread_strong(
                            _run_cli, cli_exe, env, ["pause", task_id], 10
                        )
                    except Exception:
                        pass
                record.status = "failed"
                record.error = f"add 失败 exit={code}: {out[:200]}"
                record.duration_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(f"[server] add 失败 (exit={code}): {out[:200]}")
                raise RuntimeError(f"FluxDown add 失败: {out[:200]}")
            task_id = new_id
            logger.info(f"[server] 新建任务: {url} -> task {task_id}")

        # 持久化映射（失败也留着，供下次 resume；fail_count 跨写入保留）。
        # propagate_cancel=True：等待期间被取消时，落盘完成后立刻把取消
        # 抛给 except，由统一清理负责暂停；避免吞掉取消后继续轮询。
        await _to_thread_strong(
            _map_put,
            cli_exe,
            key,
            task_id,
            url,
            destination,
            proxy,
            propagate_cancel=True,
        )

        # 轮询进度至终态。timeout 语义 = 停滞上限（持续无新字节的秒数），不是总时长：
        # 正常下载永不超时；速率持续为 0 超过 timeout 才判定中断（断网即属此类）。
        last_report = 0.0
        last_downloaded: int | None = None
        last_change = time.monotonic()  # 最近一次字节数增长的时刻
        last_speed_ts = last_change
        last_speed_bytes = 0
        speed = 0.0

        while True:
            st = await asyncio.to_thread(_status, task_id)
            if st is None:
                # status 查询失败不等于任务已停：daemon 可能仍在写输出文件。
                # 只有确认已暂停（pause 返回 0 且 status 能查到）才允许上层
                # 降级 --local；否则保留映射、按可续传中断抛出，避免双写。
                record.status = "failed"
                record.duration_ms = int((time.monotonic() - t0) * 1000)
                if await _confirm_paused():
                    record.error = "status 查询失败（任务已暂停，可安全降级）"
                    logger.warning(
                        f"[server] status 查询失败 (task {task_id}), 已确认暂停, 允许降级"
                    )
                    raise RuntimeError("FluxDown server status 查询失败")
                record.error = "status 查询失败且无法确认任务已停止，保留映射待续传"
                logger.warning(
                    f"[server] status 查询失败 (task {task_id}), 无法确认已停止, 保留映射续传"
                )
                raise RuntimeError("FluxDown server status 查询失败（任务未确认停止）")

            status = int(st.get("status") or 0)
            downloaded = int(st.get("downloadedBytes") or 0)
            total = int(st.get("totalBytes") or 0)

            now = time.monotonic()
            if last_downloaded is None:
                # 首个样本：只建基线，不算速度
                last_downloaded = downloaded
                last_speed_bytes = downloaded
                last_speed_ts = now
                last_change = now
            elif downloaded > last_downloaded:
                dt = now - last_speed_ts
                if dt > 0:
                    speed = (downloaded - last_speed_bytes) / dt
                last_speed_ts = now
                last_speed_bytes = downloaded
                last_downloaded = downloaded
                last_change = now
            else:
                speed = 0.0
                # 等待(0)/下载中(1)/准备中(5) 都算活动态：排队/准备卡死同样要判定
                if status in _ACTIVE_STATUSES and now - last_change > timeout:
                    # 尽力暂停旧任务再抛错：防止 daemon 后台继续下载，
                    # 分发层降 --local 时双写同一文件
                    try:
                        await asyncio.to_thread(
                            _run_cli, cli_exe, env, ["pause", task_id], 10
                        )
                    except Exception:
                        pass
                    record.status = "failed"
                    record.error = (
                        f"下载停滞（{timeout:.0f}s 无新字节），task 已保留可续传"
                    )
                    record.duration_ms = int((time.monotonic() - t0) * 1000)
                    logger.warning(
                        f"[server] 下载停滞 {timeout:.0f}s 无进度 (task {task_id}), 判定中断, task 已保留可续传"
                    )
                    raise RuntimeError(
                        f"FluxDown server 下载停滞: {timeout:.0f}s 无进度"
                    )

            if progress and (now - last_report) >= 0.5 and total > 0:
                try:
                    await progress(downloaded, total, speed)
                except Exception:
                    pass
                last_report = now

            if status == _TASK_STATUS_DONE:
                break
            if status == _TASK_STATUS_FAILED:
                # 尽力暂停（任务已 failed,多为兜底）：防止重试语义下残留活动任务
                try:
                    await asyncio.to_thread(
                        _run_cli, cli_exe, env, ["pause", task_id], 10
                    )
                except Exception:
                    pass
                record.status = "failed"
                record.error = (st.get("errorMessage") or "任务失败")[:300]
                record.duration_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(f"[server] 任务失败 (task {task_id}): {record.error}")
                raise RuntimeError(f"FluxDown 任务失败: {record.error}")

            await asyncio.sleep(0.8)
    except asyncio.CancelledError:
        record.status = "failed"
        record.duration_ms = int((time.monotonic() - t0) * 1000)
        # 取消可能正好落在 add/resume 的 CLI 线程上：先等它落定，add 已建出
        # 任务时要把 id 落映射，否则重试时无从续传
        if inflight_cli is not None:
            try:
                _, out = await _wait_thread_done(inflight_cli)
                salvaged = _extract_task_id(out or "")
                if salvaged and task_id is None:
                    task_id = salvaged
                    await _to_thread_strong(
                        _map_put, cli_exe, key, task_id, url, destination, proxy
                    )
                    logger.info(f"[server] 取消时补救 add: 已持久化 task {task_id}")
            except Exception:
                pass
        if task_id is None:
            # 还没有任何服务端任务，取消本身就是干净退出
            record.error = "用户取消"
            logger.info(f"[server] 用户取消(任务尚未建立): {url}")
            raise
        # 统一清理：无论取消落在哪个阶段，都先等 CLI 落定再确认暂停；
        # 分段保留，下次重试 resume 续传。清理中的二次取消不再传播。
        logger.info(f"[server] 用户取消,确认暂停任务 {task_id}")
        if await _confirm_paused(propagate_cancel=False):
            record.error = "用户取消"
            raise
        # 无法确认已停止：daemon 可能仍在写目标文件，不能谎报"取消成功"，
        # 改为显式失败，让上层按失败上报并提示用户检查 FluxDown 状态
        record.error = (
            "用户取消，但无法确认 FluxDown 任务已停止，"
            "daemon 可能仍在写入目标文件，请检查 FluxDown 状态"
        )
        logger.warning(f"[server] 用户取消但无法确认任务 {task_id} 已停止: {url}")
        raise FluxdownCancelUnconfirmed(record.error)

    record.duration_ms = int((time.monotonic() - t0) * 1000)

    # 完成的落点以服务端最后一帧快照为准：默认 FileExistsBehavior::Rename 会在
    # 目标重名时把新包改名（如 "download (1).temp"）并回写数据库，只判断
    # destination 是否存在会落空，甚至把别人的同名残留当成下载结果
    save_dir = st.get("saveDir")
    file_name = st.get("fileName")
    if not save_dir or not file_name:
        record.status = "failed"
        record.error = "任务完成但服务端未报告 saveDir/fileName，无法定位输出文件"
        raise RuntimeError(record.error)

    actual = Path(str(save_dir)) / str(file_name)
    if not actual.is_file():
        record.status = "failed"
        record.error = f"任务完成但服务端报告的文件不存在: {actual}"
        raise RuntimeError(record.error)

    size = actual.stat().st_size
    same_path = os.path.normcase(os.path.abspath(str(actual))) == os.path.normcase(
        os.path.abspath(str(destination))
    )
    if not same_path:
        if destination.exists():
            # 两侧都存在且不是同一文件：无法判断哪份才是本次任务的产物，
            # 任一方都不删，直接报错，避免误删无主文件
            record.status = "failed"
            record.error = (
                f"任务输出落在 {actual}，约定路径 {destination} 也已存在，拒绝自动覆盖"
            )
            raise RuntimeError(record.error)
        # 归位到约定路径，供上层按原路径做校验/记录
        os.replace(actual, destination)

    record.size = size
    record.status = "success"
    if resumed:
        record.error = None  # 明确无错误；resumed 信息可体现在历史调用方
    logger.success(
        f"[server] 下载完成: {destination.name}, 大小={record.size} 字节, "
        f"耗时={record.duration_ms}ms{' (断点续传)' if resumed else ''}"
    )
    return record.size, record
