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

"""官方模拟器的宿主侧操作：私有 adb、控制台、进程、硬件加速与内存检查。

两个实测出来的硬约束（预研 §6.1、§6.14）：

- **adb 只走私有 server（20050）。** 模拟器进程带 ``ANDROID_ADB_SERVER_PORT=20050`` 启动，
  只向它注册；我们自己的每条 adb 命令都带 ``-P 20050``。5037 一次都不碰。
- **起模拟器和 adb server 都不能让它们继承我们的句柄。** 继承了调用方的输出管道，
  读输出的一方就会一直等到模拟器退出。这里用 ``subprocess.Popen`` 把标准输入输出全指到
  文件 / 空设备，Python 在 Windows 上此时只把这几个句柄交给子进程（handle list）。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger
from app.utils.platform.common.process_runner import create_subprocess, decode_bytes

from .components import adb_exe, avd_home, emulator_exe, sdk_dir
from .constants import ADB_SERVER_PORT, HOST_MEMORY_OVERHEAD_MB

logger = get_logger("官方模拟器宿主")

#: 单条 adb 命令的默认超时。
ADB_TIMEOUT = 20.0
#: 硬件加速检查结果缓存多久：每次启动前都查，但几秒内连开几台不必重复起进程。
_ACCEL_CACHE_SECONDS = 120.0
_accel_cache: dict[str, tuple[float, bool, str]] = {}

#: Windows 进程创建标志：不弹控制台、脱离监督器 Job（模拟器不随后端退出，Runtime 契约 C8）。
_DETACHED_FLAGS = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0)
    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
)
_BREAKAWAY = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)


def serial_of(console_port: int) -> str:
    return f"emulator-{console_port}"


def emulator_env(root: str | Path) -> dict[str, str]:
    """模拟器进程的环境变量：SDK、AVD 目录都指向这条安装，adb 只注册到私有 server。"""
    env = dict(os.environ)
    sdk = str(sdk_dir(root))
    env.update(
        {
            "ANDROID_SDK_ROOT": sdk,
            "ANDROID_HOME": sdk,
            "ANDROID_AVD_HOME": str(avd_home(root)),
            "ANDROID_ADB_SERVER_PORT": str(ADB_SERVER_PORT),
        }
    )
    return env


def _popen_detached(
    args: list[str], *, env: dict[str, str], stdout
) -> subprocess.Popen:
    """起一个不继承我们句柄、不随后端退出的进程。父进程所在 Job 不许脱离时去掉该位重试。"""
    kwargs = dict(
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        close_fds=True,
        cwd=str(Path(args[0]).parent),
    )
    try:
        return subprocess.Popen(args, creationflags=_DETACHED_FLAGS, **kwargs)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 5:
            raise
        logger.warning("父进程所在 Job 不允许脱离，模拟器将留在当前 Job 里")
        return subprocess.Popen(
            args, creationflags=_DETACHED_FLAGS & ~_BREAKAWAY, **kwargs
        )


def _port_listening(port: int) -> bool:
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
            return True
    return False


def busy_ports(ports: list[int]) -> list[int]:
    """哪些端口已经有人在监听。只看系统连接表，不去连它（连模拟器的 adb 端口会打扰它）。"""
    wanted = set(ports)
    busy: set[int] = set()
    for conn in psutil.net_connections(kind="tcp"):
        if (
            conn.status == psutil.CONN_LISTEN
            and conn.laddr
            and conn.laddr.port in wanted
        ):
            busy.add(conn.laddr.port)
    return sorted(busy)


async def ensure_adb_server(root: str | Path) -> None:
    """私有 adb server 没在跑就把它起来。

    必须由我们以脱离方式起：让 adb 客户端在普通命令里顺手拉起 server，server 会继承
    这条命令的输出管道，读输出的协程就一直等不到结束。
    """
    if await asyncio.to_thread(_port_listening, ADB_SERVER_PORT):
        return
    adb = adb_exe(root)
    logger.info(f"启动官方模拟器私有 adb server（端口 {ADB_SERVER_PORT}）")
    process = _popen_detached(
        [str(adb), "-P", str(ADB_SERVER_PORT), "start-server"],
        env=emulator_env(root),
        stdout=subprocess.DEVNULL,
    )
    with suppress(subprocess.TimeoutExpired):
        await asyncio.to_thread(process.wait, 20)


async def run_adb(
    root: str | Path,
    *args: str,
    serial: str | None = None,
    timeout: float = ADB_TIMEOUT,
) -> tuple[int, str]:
    """跑一条私有 server 上的 adb 命令，返回 ``(返回码, 合并输出)``。**不抛异常。**

    轮询会一秒一条，所以这里不像 ``ProcessRunner`` 那样每条都记 info 日志。
    """
    try:
        await ensure_adb_server(root)
        command = ["-P", str(ADB_SERVER_PORT)]
        if serial:
            command += ["-s", serial]
        process = await create_subprocess(
            adb_exe(root),
            *command,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as e:  # noqa: BLE001 - 见 docstring
        return -1, f"{type(e).__name__}: {e}"
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        with suppress(ProcessLookupError):
            process.kill()
        with suppress(Exception):
            await process.wait()
        return -1, f"adb {' '.join(args)} 超时（{timeout:.0f} 秒）"
    return process.returncode or 0, decode_bytes(stdout).strip()


# ---- 控制台 ---------------------------------------------------------------


class ConsoleError(RuntimeError):
    """模拟器控制台命令失败。"""


def _console_token() -> str:
    """控制台鉴权 token。模拟器首次启动时写到用户目录。"""
    path = Path(os.environ.get("USERPROFILE") or Path.home()) / (
        ".emulator_console_auth_token"
    )
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


async def _read_until_status(reader: asyncio.StreamReader) -> tuple[bool, str]:
    lines: list[str] = []
    while True:
        raw = await reader.readline()
        if not raw:
            return False, "\n".join(lines)
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "OK":
            return True, "\n".join(lines)
        if line.startswith("KO"):
            lines.append(line)
            return False, "\n".join(lines)
        lines.append(line)


async def console_command(port: int, command: str, *, timeout: float = 10.0) -> str:
    """直接连模拟器控制台（``telnet 127.0.0.1 <控制台端口>``）发一条命令。

    与 ``adb emu`` 等价，但不依赖 adb server：私有 server 万一被别人杀掉，模拟器不会重新
    注册，``adb emu`` 就再也找不到它，而控制台一直在。
    """

    async def talk() -> str:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        try:
            ok, text = await _read_until_status(reader)
            if not ok:
                raise ConsoleError(f"控制台 {port} 没有就绪: {text}")
            token = _console_token()
            if token:
                writer.write(f"auth {token}\r\n".encode())
                await writer.drain()
                ok, text = await _read_until_status(reader)
                if not ok:
                    raise ConsoleError(f"控制台 {port} 鉴权失败: {text}")
            writer.write(f"{command}\r\n".encode())
            await writer.drain()
            ok, text = await _read_until_status(reader)
            if not ok:
                raise ConsoleError(f"控制台命令 {command!r} 失败: {text}")
            with suppress(Exception):
                writer.write(b"quit\r\n")
                await writer.drain()
            return text
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    try:
        return await asyncio.wait_for(talk(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError) as e:
        raise ConsoleError(f"控制台 {port} 命令 {command!r} 超时") from e
    except OSError as e:
        raise ConsoleError(f"连不上控制台 {port}: {e}") from e


# ---- 进程 -----------------------------------------------------------------


def _cmdline_matches(cmdline: list[str], avd: str, console_port: int) -> bool:
    """按 ``-avd <名>`` 与 ``-ports <控制台>,`` 同时精确匹配，绝不误认别的模拟器。

    只看 AVD 名不够：另一个根目录里也可能有同名的 ``mas_0``；只看端口也不够。
    """
    has_avd = has_port = False
    for position, token in enumerate(cmdline[:-1]):
        following = cmdline[position + 1]
        if token == "-avd" and following == avd:
            has_avd = True
        elif token == "-ports" and following.split(",", 1)[0] == str(console_port):
            has_port = True
    return has_avd and has_port


def find_qemu_process(avd: str, console_port: int) -> psutil.Process | None:
    """找这台实例的 qemu 进程（``qemu-system-x86_64[-headless].exe``）。没有返回 ``None``。"""
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            if not name.startswith("qemu-system"):
                continue
            cmdline = process.info.get("cmdline") or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if _cmdline_matches(cmdline, avd, console_port):
            return process
    return None


def process_cpu_seconds(process: psutil.Process) -> float | None:
    try:
        times = process.cpu_times()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return float(times.user + times.system)


def kill_process_tree(process: psutil.Process) -> None:
    """强杀 qemu 进程（和它可能带着的子进程）。只杀这一台，别的模拟器不受影响。"""
    with suppress(psutil.NoSuchProcess):
        for child in process.children(recursive=True):
            with suppress(psutil.NoSuchProcess):
                child.kill()
        process.kill()


def launch_emulator(
    root: str | Path, args: list[str], log_path: Path
) -> subprocess.Popen:
    """起 ``emulator.exe``，输出写到 ``log_path``。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        return _popen_detached(
            [str(emulator_exe(root)), *args],
            env=emulator_env(root),
            stdout=log_file,
        )


# ---- 电脑检查 -------------------------------------------------------------


@dataclass(frozen=True)
class AccelCheck:
    ok: bool
    detail: str


#: 硬件加速不可用时给用户的说法。
ACCEL_GUIDE = (
    "这台电脑的硬件虚拟化（Windows 虚拟机监控程序平台）不可用，官方模拟器无法启动。"
    "请先在 BIOS 里打开 CPU 虚拟化（Intel VT-x / AMD SVM），再在「启用或关闭 Windows 功能」"
    "里勾选「Windows 虚拟机监控程序平台」并重启电脑"
)


def parse_accel_check(returncode: int, output: str) -> AccelCheck:
    """``emulator -accel-check`` 的判定：返回码 0 且说「usable」才算可用。"""
    text = (output or "").strip()
    usable = returncode == 0 and "usable" in text.lower()
    return AccelCheck(usable, text)


async def check_acceleration(root: str | Path, *, use_cache: bool = True) -> AccelCheck:
    """``emulator.exe -accel-check``：WHPX 是否可用。"""
    key = str(Path(root))
    cached = _accel_cache.get(key)
    if use_cache and cached and time.monotonic() - cached[0] < _ACCEL_CACHE_SECONDS:
        return AccelCheck(cached[1], cached[2])
    try:
        process = await create_subprocess(
            emulator_exe(root),
            "-accel-check",
            env=emulator_env(root),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
        result = parse_accel_check(process.returncode or 0, decode_bytes(stdout))
    except Exception as e:  # noqa: BLE001 - 查不了当不可用，原因给用户
        result = AccelCheck(False, f"{type(e).__name__}: {e}")
    _accel_cache[key] = (time.monotonic(), result.ok, result.detail)
    return result


def check_host_memory(memory_mb: int) -> None:
    """宿主可用内存够不够起这台：按「客体内存 + 1.5 GB」估。不够直接拒绝。"""
    available_mb = psutil.virtual_memory().available // (1024 * 1024)
    needed_mb = int(memory_mb) + HOST_MEMORY_OVERHEAD_MB
    if available_mb < needed_mb:
        raise RuntimeError(
            f"电脑可用内存不足：这台官方模拟器实例分配了 {memory_mb / 1024:.0f} GB 内存，"
            f"启动约需 {needed_mb / 1024:.1f} GB，当前只剩 {available_mb / 1024:.1f} GB。"
            "请关闭部分程序，或在实例设置里调小内存"
        )
