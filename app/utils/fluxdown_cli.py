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
    from app.utils.fluxdown_cli import fluxdown_download, fluxdown_find_cli

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

try:
    import aiofiles
except ImportError:
    aiofiles = None

from app.utils.logger import get_logger

logger = get_logger("FluxDown")

DownloadProgress = Callable[[int, int, float], Awaitable[None]]


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
    status: str = ""  # success | failed | checksum_fail | fluxdown_fallback
    error: str | None = None
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "destination": self.destination,
            "size": self.size,
            "duration_ms": self.duration_ms,
            "segments": self.segments,
            "proxy": self.proxy,
            "checksum": self.checksum,
            "status": self.status,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------


def fluxdown_find_cli(configured_path: str | None = None) -> Path | None:
    """定位 FluxDown CLI 二进制，返回路径或 None。

    查找顺序：
        1. 用户显式配置的 Update.FluxdownPath（尊重用户选择，可为全量版）
        2. MAS 可执行文件所在目录下的 res/fluxdown-cli/（随打包一起带）
        3. MAS 源码仓库 res/fluxdown-cli/（开发态运行时找得到）
        4. 系统 PATH 里的 fluxdown.exe（兜底，用户自己装的）

    自动定位的目录（2/3）必须带 ``portable`` 标记，避免误命中用户桌面版；
    用户显式配置的目录（1）不做此限制——检测 UI 已就全量版给出污染风险警告。
    """
    import os as _os
    import sys as _sys

    candidates: list[Path] = []

    # 1. 用户配置路径（兼容目录或 exe 文件路径，文件则取其所在目录）
    if configured_path:
        p = Path(configured_path)
        if p.is_file():
            p = p.parent
        if p.is_dir():
            candidates.append(p)

    # 2. MAS 安装目录（打包后可执行文件旁边）下的 res/fluxdown-cli/
    if getattr(_sys, "frozen", False):
        base = Path(_sys.executable).parent
    else:
        base = Path(_os.getcwd())
    candidates.append(base / "res" / "fluxdown-cli")
    # 兜底：Path.cwd() 下也找找（开发态从任意目录启动）
    candidates.append(Path.cwd() / "res" / "fluxdown-cli")

    for idx, dir_path in enumerate(candidates):
        if not dir_path.is_dir():
            continue
        if idx > 0 and not (dir_path / "portable").is_file():
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

    args = [
        str(cli_exe), "add", url, "--local",
        "-d", str(destination.parent),
        "-o", destination.name,
        "--segments", str(segments),
    ]
    if proxy:
        args += ["--proxy", proxy]
    if checksum:
        args += ["--checksum", checksum]

    logger.info(f"[--local] 开始下载: {url} -> {destination.name}, 分段数={segments}")
    t0 = time.monotonic()
    buf = bytearray()
    last_report = 0.0

    async def _parse_stream():
        nonlocal last_report
        downloaded = 0
        total = 0
        async for raw in proc.stdout:
            buf.extend(raw)
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

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert proc.stdout is not None

    try:
        try:
            await asyncio.wait_for(_parse_stream(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            record.status = "failed"
            record.error = f"CLI 超时 ({timeout}s)"
            record.duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(f"[--local] 下载超时 ({timeout}s): {url}")
            raise RuntimeError(f"FluxDown CLI 超时: {timeout}s") from None

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
    "windows", "windowsapps", "recycle.bin", "system volume information",
    "recovery", "perflogs", "msocache", "node_modules", ".git",
    "__pycache__", "venv", ".venv", ".pixi", ".cargo", "temp",
}

# 全量版桌面程序的 exe 名（无 portable 标记，用它下载会在用户队列里留记录）
_FLUXDOWN_EXE_NAMES = (
    "fluxdown.exe",
    "fluxdown-cli.exe",
    "fluxdown-desktop.exe",
)


def _candidate_drives() -> list[str]:
    """枚举本机存在的盘符根目录。"""
    import string

    return [
        f"{letter}:\\"
        for letter in string.ascii_uppercase
        if Path(f"{letter}:\\").exists()
    ]


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
# 与 --local 单次调用的区别：任务持久化在便携 portable_data\\flux_down.db，
# 断网/失败后可经 ``fluxdown resume <task_id>`` 从已下载分段续传，不从头。
#
# 与用户全量版 FluxDown 的关系（v0.5.9 实测）：
#   - 数据目录经 FLUXDOWN_DATA_DIR 强制指向便携 portable_data，与用户主程序隔离；
#   - 自选 gateway/daemon 端口对且 spawn 前先验空闲，agent 的 terminate_stale
#     （按进程名全杀）路径只在"自己的 daemon 端口被异己占用"时触发，不会触碰
#     用户全量版（17801 上的任何进程 MAS 一概不碰）；
#   - MAS 退出清理一律按 PID，禁止按进程名 taskkill。

_SERVER_GATEWAY_BASE = 27896  # agent 管理 API（HTTP/Web）
_SERVER_DAEMON_BASE = 27897   # daemon RPC（WS），须与 gateway 相邻
_SERVER_READY_TIMEOUT = 20.0  # 管理 API 就绪晚于 ping，给足余量
_SERVER_MAP_NAME = "mas_task_map.json"
_SERVER_TOKEN_NAME = "mas_server.token"

# 任务 status 枚举（实测）：1=等待 2=下载中 3=完成 4=失败
_TASK_STATUS_DONE = 3
_TASK_STATUS_FAILED = 4


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
        self.checked_available: dict[str, tuple[float, bool]] = {}  # cli_dir -> (ts, ok)


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
    agent = d / "fluxdown-agent.exe"
    downd = d / "fluxdownd.exe"
    if agent.is_file() and downd.is_file():
        return agent, downd
    return None


def _server_data_dir(cli_exe: Path) -> Path:
    return cli_exe.parent / "portable_data"


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


def _run_cli(cli_exe: Path, env: dict[str, str], args: list[str], timeout: float = 30.0) -> tuple[int, str]:
    """同步跑一条 CLI 命令，返回 (exit_code, stdout+stderr)。"""
    try:
        out = subprocess.run(
            [str(cli_exe), *args],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 1, str(e)


def _parse_cli_json(text: str):
    """从 CLI 输出提取首个 JSON 值（对象/数组/字符串），失败返回 None。"""
    text = text.strip()
    if not text:
        return None
    # CLI 可能把日志混进 stdout：从首个 { [ " 开始尝试
    for i, ch in enumerate(text):
        if ch in "{[\"":
            try:
                return json.loads(text[i:])
            except (ValueError, json.JSONDecodeError):
                # 截断到行尾找完整 JSON
                for end in range(len(text), i, -1):
                    try:
                        return json.loads(text[i:end])
                    except (ValueError, json.JSONDecodeError):
                        continue
                return None
    return None


def _ping_ok(cli_exe: Path, gateway_port: int, token: str) -> bool:
    code, out = _run_cli(cli_exe, _cli_env(gateway_port, token), ["ping"], timeout=8)
    return code == 0 and "pong" in out


def _mgmt_ready(cli_exe: Path, gateway_port: int, token: str) -> bool:
    """管理 API 就绪（list 能通），比 ping 晚，ensure 需等到这步。"""
    code, _ = _run_cli(cli_exe, _cli_env(gateway_port, token), ["list", "--json"], timeout=10)
    return code == 0


def _kill_pid(pid: int) -> None:
    """按 PID 精确结束进程（含子进程树），禁止按进程名。"""
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


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
    data_dir = _server_data_dir(cli_exe)
    token = _load_or_create_token(cli_exe)

    with _server.lock:
        h = _server.handle
        if h and _ping_ok(h.cli_exe, h.gateway_port, h.token) and _mgmt_ready(h.cli_exe, h.gateway_port, h.token):
            logger.debug(f"[server] 复用已就绪套件: gateway={h.gateway_port}")
            return h

        pair = _find_port_pair()
        if pair is None:
            logger.warning("[server] 找不到空闲的 gateway/daemon 端口对")
            return None
        gateway_port, daemon_port = pair

        env = os.environ.copy()
        env.update({
            "FLUXDOWN_DATA_DIR": str(data_dir),
            "FLUXDOWN_DAEMON_URL": f"ws://127.0.0.1:{daemon_port}/rpc",
            "FLUXDOWN_BIND": f"127.0.0.1:{gateway_port}",
            "FLUXDOWN_TOKEN": token,
            "FLUXDOWN_TOKEN_FORCE": "1",
        })
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
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0),
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
            if _ping_ok(cli_exe, gateway_port, token) and _mgmt_ready(cli_exe, gateway_port, token):
                ready = True
                break
            time.sleep(0.3)

        if not ready:
            _kill_pid(proc.pid)
            logger.warning(f"[server] 便携套件 {_SERVER_READY_TIMEOUT:.0f}s 内未就绪,已按 PID 清理")
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


def _save_task_map(cli_exe: Path, m: dict) -> None:
    p = _server_map_path(cli_exe)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def fluxdown_server_forget(cli_exe: Path, url: str, destination: Path) -> None:
    """任务完成（MAS 二次校验通过）后删除映射条目。"""
    m = _load_task_map(cli_exe)
    if m.pop(_map_key(url, Path(destination)), None) is not None:
        _save_task_map(cli_exe, m)


def fluxdown_server_mark_failure(cli_exe: Path, url: str, destination: Path) -> int:
    """把该 (url, destination) 任务的中断次数 +1 并持久化，返回累计次数。

    上层据累计次数决定何时在失败提示中建议改用内置 httpx（用户多次重试仍失败）。
    任务完成（fluxdown_server_forget）后计数随映射一起清零。
    """
    key = _map_key(url, Path(destination))
    task_map = _load_task_map(cli_exe)
    entry = task_map.get(key) or {}
    count = int(entry.get("fail_count") or 0) + 1
    task_map[key] = {
        "task_id": entry.get("task_id"),
        "url": url,
        "save_path": str(destination),
        "updated": time.time(),
        "fail_count": count,
    }
    _save_task_map(cli_exe, task_map)
    return count


# --- server 模式下载 -------------------------------------------------------


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

    handle = await asyncio.to_thread(fluxdown_server_ensure, cli_exe)
    if handle is None:
        record.status = "failed"
        record.error = "server 套件不可用或启动超时"
        record.duration_ms = int((time.monotonic() - t0) * 1000)
        raise RuntimeError("FluxDown server 不可用")

    env = _cli_env(handle.gateway_port, handle.token)
    key = _map_key(url, destination)
    task_map = _load_task_map(cli_exe)
    task_id: str | None = (task_map.get(key) or {}).get("task_id")

    def _status(tid: str) -> dict | None:
        code, out = _run_cli(cli_exe, env, ["status", tid, "--json"], timeout=15)
        if code != 0:
            return None
        data = _parse_cli_json(out)
        return data if isinstance(data, dict) else None

    # 既有 task：先确认服务端还在（可能被用户清理过 DB）
    if task_id and await asyncio.to_thread(_status, task_id) is None:
        task_id = None
        task_map.pop(key, None)

    resumed = False
    if task_id:
        code, out = await asyncio.to_thread(
            _run_cli, cli_exe, env, ["resume", task_id], 30
        )
        if code == 0:
            resumed = True
            logger.info(f"[server] 续传任务: {task_id} ({url})")
        else:
            # resume 失败（可能任务状态不可恢复）→ 重新 add
            task_id = None
            task_map.pop(key, None)

    if task_id is None:
        args = [
            "add", url,
            "-d", str(destination.parent),
            "-o", destination.name,
            "--segments", str(segments),
            "--json",
        ]
        if proxy:
            args += ["--proxy", proxy]
        code, out = await asyncio.to_thread(_run_cli, cli_exe, env, args, 60)
        data = _parse_cli_json(out)
        new_id: str | None = None
        if isinstance(data, list) and data and isinstance(data[0], str):
            new_id = data[0]
        elif isinstance(data, dict):
            new_id = data.get("taskId") or data.get("task_id") or data.get("id")
        if code != 0 or not new_id:
            # add 失败：若服务端已把任务建出来了（"added <id>" 后 probe 失败），
            # 取出该 id 并持久化映射 —— 重试时 resume 续传，不重新 add。
            # 若连 id 都没有（add 完全没成功），抛错但**不视为进程异常**：
            # 让上层以可续传语义重试（同 url 会再次尝试 add，已有分段由服务端保留）。
            m = re.search(r"added\s+([0-9a-fA-F-]{36})", out)
            if m:
                task_id = m.group(1)
                task_map[key] = {
                    "task_id": task_id,
                    "url": url,
                    "save_path": str(destination),
                    "updated": time.time(),
                    "fail_count": int((task_map.get(key) or {}).get("fail_count") or 0),
                }
                await asyncio.to_thread(_save_task_map, cli_exe, task_map)
            record.status = "failed"
            record.error = f"add 失败 exit={code}: {out[:200]}"
            record.duration_ms = int((time.monotonic() - t0) * 1000)
            logger.warning(f"[server] add 失败 (exit={code}): {out[:200]}")
            raise RuntimeError(f"FluxDown add 失败: {out[:200]}")
        task_id = new_id
        logger.info(f"[server] 新建任务: {url} -> task {task_id}")

    # 持久化映射（失败也留着，供下次 resume；fail_count 跨写入保留）
    task_map[key] = {
        "task_id": task_id,
        "url": url,
        "save_path": str(destination),
        "updated": time.time(),
        "fail_count": int((task_map.get(key) or {}).get("fail_count") or 0),
    }
    await asyncio.to_thread(_save_task_map, cli_exe, task_map)

    # 轮询进度至终态。timeout 语义 = 停滞上限（持续无新字节的秒数），不是总时长：
    # 正常下载永不超时；速率持续为 0 超过 timeout 才判定中断（断网即属此类）。
    last_report = 0.0
    last_downloaded: int | None = None
    last_change = time.monotonic()  # 最近一次字节数增长的时刻
    last_speed_ts = last_change
    last_speed_bytes = 0
    speed = 0.0
    try:
        while True:
            st = await asyncio.to_thread(_status, task_id)
            if st is None:
                record.status = "failed"
                record.error = "status 查询失败（server 可能已退出）"
                record.duration_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(f"[server] status 查询失败 (task {task_id}), server 可能已退出")
                raise RuntimeError("FluxDown server status 查询失败")

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
                if status == 2 and now - last_change > timeout:
                    record.status = "failed"
                    record.error = f"下载停滞（{timeout:.0f}s 无新字节），task 已保留可续传"
                    record.duration_ms = int((time.monotonic() - t0) * 1000)
                    logger.warning(
                        f"[server] 下载停滞 {timeout:.0f}s 无进度 (task {task_id}), 判定中断, task 已保留可续传"
                    )
                    raise RuntimeError(f"FluxDown server 下载停滞: {timeout:.0f}s 无进度")

            if progress and (now - last_report) >= 0.5 and total > 0:
                try:
                    await progress(downloaded, total, speed)
                except Exception:
                    pass
                last_report = now

            if status == _TASK_STATUS_DONE:
                break
            if status == _TASK_STATUS_FAILED:
                record.status = "failed"
                record.error = (st.get("errorMessage") or "任务失败")[:300]
                record.duration_ms = int((time.monotonic() - t0) * 1000)
                logger.warning(f"[server] 任务失败 (task {task_id}): {record.error}")
                raise RuntimeError(f"FluxDown 任务失败: {record.error}")

            await asyncio.sleep(0.8)
    except asyncio.CancelledError:
        # 用户取消：暂停 server 任务（分段保留,下次重试 resume 续传），
        # 否则 daemon 会在后台继续下载
        logger.info(f"[server] 用户取消,暂停任务 {task_id}")
        await asyncio.to_thread(_run_cli, cli_exe, env, ["pause", task_id], 10)
        record.status = "failed"
        record.error = "用户取消"
        raise

    record.duration_ms = int((time.monotonic() - t0) * 1000)
    if not destination.is_file():
        record.status = "failed"
        record.error = "任务完成但文件未落地"
        raise RuntimeError("FluxDown server 任务完成但文件未落地")

    record.size = destination.stat().st_size
    record.status = "success"
    if resumed:
        record.error = None  # 明确无错误；resumed 信息可体现在历史调用方
    logger.success(
        f"[server] 下载完成: {destination.name}, 大小={record.size} 字节, "
        f"耗时={record.duration_ms}ms{' (断点续传)' if resumed else ''}"
    )
    return record.size, record
