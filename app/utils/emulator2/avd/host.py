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

"""魔改 AVD 的宿主侧操作：私有 adb、控制台、进程、硬件加速检查（开机前的整套电脑检查见
:mod:`.precheck`）。

两个实测出来的硬约束（预研 §6.1、§6.14）：

- **adb 只走私有 server（默认 20050，``mas-avd.json`` 的 ``adbServerPort`` 可改）。** 模拟器进程带
  ``ANDROID_ADB_SERVER_PORT=<该端口>`` 启动，只向它注册；我们自己的每条 adb 命令都带 ``-P <该端口>``。
  5037 一次都不碰。server 重启后模拟器不会再来登记，由 :func:`reregister_emulator` 替它登记。
- **起模拟器和 adb server 都不能让它们继承我们的句柄。** 继承了调用方的输出管道，
  读输出的一方就会一直等到模拟器退出。这里用 ``subprocess.Popen`` 把标准输入输出全指到
  文件 / 空设备，Python 在 Windows 上此时只把这几个句柄交给子进程（handle list）。
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import subprocess
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger
from app.utils.platform.common.process_runner import create_subprocess, decode_bytes

from .components import (
    adb_exe,
    adb_server_port,
    avd_home,
    emulator_exe,
    runtime_sdk_dir,
    script_adb_server_port,
)
from .constants import (
    ADB_NO_LOCAL_SCAN_ENV,
    METADATA_FILE,
    PORT_BASE,
    PORT_STEP,
    SHADER_CACHE_DIR,
    avd_name,
)

logger = get_logger("魔改 AVD 宿主")

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
    sdk = str(runtime_sdk_dir(root))
    env.update(
        {
            "ANDROID_SDK_ROOT": sdk,
            "ANDROID_HOME": sdk,
            "ANDROID_AVD_HOME": str(avd_home(root)),
            "ANDROID_ADB_SERVER_PORT": str(adb_server_port(root)),
            # 我们起的 adb server 不去扫 5555–5585，免得连上同机的雷电（见常量说明）
            **ADB_NO_LOCAL_SCAN_ENV,
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


#: 等 adb server 开始监听时的轮询间隔。
_LISTEN_POLL_SECONDS = 0.1


def _wait_listening(
    port: int, timeout: float, process: subprocess.Popen | None = None
) -> bool:
    """等 ``port`` 开始监听，最多 ``timeout`` 秒；返回是否在听。

    不等 ``adb start-server`` 客户端退出：SDK adb 的客户端要 2.08–2.12 秒才返回（第三轮复核实测），
    server 在那之前就已经在听了。客户端带非零返回码退出且端口没在听，就是起不来，不再干等。
    """
    deadline = time.monotonic() + timeout
    while True:
        if _port_listening(port):
            return True
        if process is not None and process.poll() not in (None, 0):
            return _port_listening(port)
        if time.monotonic() >= deadline:
            return False
        time.sleep(_LISTEN_POLL_SECONDS)


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


class AdbPortConflict(RuntimeError):
    """魔改 AVD 要用的 adb server 端口被别的程序（不是 adb）占着。"""


class ScriptAdbPortConflict(AdbPortConflict):
    """脚本专用 adb 端口（``scriptAdbServerPort``）被别的程序占着。"""


class PrivateAdbPortConflict(AdbPortConflict):
    """私有 adb 端口（``adbServerPort``）被别的程序占着。"""


def _port_conflict(
    root: str | Path,
    port: int,
    pid: int | None,
    name: str,
    *,
    label: str,
    key: str,
    other_key: str,
) -> str:
    return (
        f"魔改 AVD 的{label} adb 端口 {port} 被 {name}（PID {pid}）占用，它不是 adb。"
        f"请在 {Path(root) / METADATA_FILE} 里把 {key} 改成一个没被占用的端口"
        f"（不能用 5037 和各实例的控制台 / adb / gRPC 端口，也不能和 {other_key} 相同），"
        f"或者先关掉占用它的程序"
    )


def _private_port_conflict(
    root: str | Path, port: int, pid: int | None, name: str
) -> str:
    return _port_conflict(
        root,
        port,
        pid,
        name,
        label="私有",
        key="adbServerPort",
        other_key="scriptAdbServerPort",
    )


def _port_listener(port: int) -> tuple[bool, int | None, str | None]:
    """``(是否有人在听, 监听进程 PID, 进程名)``；PID / 进程名读不到时为 ``None``。"""
    for conn in psutil.net_connections(kind="tcp"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
            name = None
            if conn.pid:
                with suppress(psutil.Error):
                    name = psutil.Process(conn.pid).name()
            return True, conn.pid, name
    return False, None, None


def _is_adb_process_name(name: str) -> bool:
    return name.lower() in ("adb.exe", "adb")


async def ensure_script_adb_server(root: str | Path, *, timeout: float = 10.0) -> bool:
    """脚本专用 adb server（``scriptAdbServerPort``）没在跑就以脱离方式起来，返回之后它是否在听。

    脚本进程（MaaFW worker、agent …）里的 adb 客户端顺手拉起的 server 会继承那个进程的输出管道：
    读它输出的一方就等不到结束。先由我们起好就没有这个问题。
    查连接表和等监听都放到线程里，不卡事件循环（起 server 要 2 秒左右）。

    端口上在听的不是 adb（按监听进程名判断）时抛 :class:`ScriptAdbPortConflict`，提示去
    ``mas-avd.json`` 改 ``scriptAdbServerPort``：脚本的 adb 连上去只会一直失败。进程名读不到时
    （权限不够）不下结论，按已就绪处理。
    """
    port = script_adb_server_port(root)
    listening, pid, name = await asyncio.to_thread(_port_listener, port)
    if listening:
        if name is not None and not _is_adb_process_name(name):
            raise ScriptAdbPortConflict(
                _port_conflict(
                    root,
                    port,
                    pid,
                    name,
                    label="脚本专用",
                    key="scriptAdbServerPort",
                    other_key="adbServerPort",
                )
            )
        return True
    logger.info(f"启动魔改 AVD 脚本专用 adb server（端口 {port}）")
    process = _popen_detached(
        [str(adb_exe(root)), "-P", str(port), "start-server"],
        env=emulator_env(root),
        stdout=subprocess.DEVNULL,
    )
    return await asyncio.to_thread(_wait_listening, port, timeout, process)


async def ensure_adb_server(root: str | Path, *, timeout: float = 20.0) -> bool:
    """私有 adb server 没在跑就把它起来，最多等 ``timeout`` 秒；返回之后它是否在听。

    必须由我们以脱离方式起：让 adb 客户端在普通命令里顺手拉起 server，server 会继承
    这条命令的输出管道，读输出的协程就一直等不到结束。

    端口上在听的不是 adb（按监听进程名判断）时抛 :class:`PrivateAdbPortConflict`，提示去
    ``mas-avd.json`` 改 ``adbServerPort``；进程名读不到时（权限不够）不下结论，按已就绪处理。
    """
    port = adb_server_port(root)
    listening, pid, name = await asyncio.to_thread(_port_listener, port)
    if listening:
        if name is not None and not _is_adb_process_name(name):
            raise PrivateAdbPortConflict(_private_port_conflict(root, port, pid, name))
        return True
    adb = adb_exe(root)
    logger.info(f"启动魔改 AVD 私有 adb server（端口 {port}）")
    process = _popen_detached(
        [str(adb), "-P", str(port), "start-server"],
        env=emulator_env(root),
        stdout=subprocess.DEVNULL,
    )
    return await asyncio.to_thread(_wait_listening, port, timeout, process)


async def prepare_adb_for_close(
    root: str | Path, console: int, *, timeout: float
) -> str | None:
    """关机前让私有 server 能对这台实例发 ``shell sync``，最多 ``timeout`` 秒。可以 sync 返回 ``None``，
    否则返回不能 sync 的原因。

    server 本来就在听：直接返回（server 认不认识这台实例由 sync 的结果说话）。server 不在：起它，
    等它开始监听；新起的 server 不认识模拟器（模拟器只在开机时登记一次），确认 adb 端口确实是这台
    实例自己的 qemu 在听之后直接替它登记，再等它回到 ``device``。不走 :func:`reregister_emulator`：
    那里的开机期保护（qemu 起来不到 60 秒不登记）和 5 秒等待都不适合关机。
    """
    started = time.monotonic()
    port = adb_server_port(root)
    listening, pid, name = await asyncio.to_thread(_port_listener, port)
    if listening:
        if name is not None and not _is_adb_process_name(name):
            return _private_port_conflict(root, port, pid, name)
        return None
    if not await ensure_adb_server(root, timeout=timeout):
        return f"私有 adb server（端口 {port}）{timeout:.0f} 秒内没起来"
    if await asyncio.to_thread(instance_qemu_on_adb_port, console) is None:
        return f"adb 端口 {console + 1} 上不是这台实例的模拟器，不替它登记"
    serial = serial_of(console)
    try:
        await register_emulator(port, console + 1)
    except (OSError, asyncio.TimeoutError, TimeoutError) as e:
        return f"向新起的私有 adb server 登记 {serial} 失败: {e}"
    while True:
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            return f"新起的私有 adb server 上 {serial} 在 {timeout:.0f} 秒内没有上线"
        code, output = await _run_adb_once(
            root, "get-state", serial=serial, timeout=max(remaining, 0.5)
        )
        if code == 0 and output.strip() == "device":
            logger.info(
                f"关机前私有 adb server 已重新起好并登记 {serial}（用时 "
                f"{(time.monotonic() - started) * 1000:.0f} ms）"
            )
            return None
        await asyncio.sleep(0.1)


#: ``open`` 正在等开机的实例（序列号）。这段时间模拟器还没向私有 server 登记是正常的，
#: 任何路径（含面板每秒的状态轮询）都不替它登记。
BOOTING: set[str] = set()
#: qemu 起来不到这么久也不替它登记：开机还没走到登记那一步（MAS 重启后接管、别处起的都算）。
_REREGISTER_MIN_QEMU_AGE_SECONDS = 60.0


#: 私有 server 上找不到 ``emulator-<端口>`` 时，adb 客户端的报错（新旧两种前缀）。
_DEVICE_NOT_FOUND_MARKS = ("not found",)
#: 重新登记后等设备回到 ``device`` 状态的上限（第 2 步实测 451 ms）。
_REREGISTER_WAIT_SECONDS = 5.0
#: 同一台设备的重新登记串行做，免得轮询并发时一起发。
_REREGISTER_LOCKS: dict[str, asyncio.Lock] = {}


def _console_port_of(serial: str) -> int | None:
    """``emulator-<控制台端口>`` → 控制台端口；不是这种序列号返回 ``None``。"""
    prefix = "emulator-"
    if not serial.startswith(prefix) or not serial[len(prefix) :].isdecimal():
        return None
    port = int(serial[len(prefix) :])
    return port if port >= PORT_BASE and (port - PORT_BASE) % PORT_STEP == 0 else None


def device_missing(serial: str, output: str) -> bool:
    """这条 adb 输出是不是「私有 server 上没有这台设备」。"""
    text = output.lower()
    return serial.lower() in text and any(m in text for m in _DEVICE_NOT_FOUND_MARKS)


def adb_port_owned_by_instance(console: int) -> bool:
    """这台实例的 adb 端口（控制台 + 1）确实由它自己的 qemu 在听。"""
    return instance_qemu_on_adb_port(console) is not None


def instance_qemu_on_adb_port(console: int) -> psutil.Process | None:
    """在听这台实例 adb 端口（控制台 + 1）的、确实是它自己的 qemu 进程；不是返回 ``None``。

    只看「有人在听」不够：端口可能被别的程序占着；往那里登记等于把别人的端口塞给私有 server。
    要求监听进程是 ``qemu-system*``，命令行里 ``-ports`` 是 ``<控制台>,<控制台 + 1>``，
    且 ``-avd`` 是这个端口段对应的实例名 ``mas_<i>``。
    """
    if (console - PORT_BASE) % PORT_STEP:
        return None
    expected_avd = avd_name((console - PORT_BASE) // PORT_STEP)
    pid = None
    for conn in psutil.net_connections(kind="tcp"):
        if (
            conn.status == psutil.CONN_LISTEN
            and conn.laddr
            and conn.laddr.port == console + 1
        ):
            pid = conn.pid
            break
    if not pid:
        return None
    try:
        process = psutil.Process(pid)
        if not process.name().lower().startswith("qemu-system"):
            return None
        cmdline = process.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    pairs = set(zip(cmdline, cmdline[1:]))
    if ("-ports", f"{console},{console + 1}") in pairs and (
        "-avd",
        expected_avd,
    ) in pairs:
        return process
    return None


async def register_emulator(server_port: int, emulator_adb_port: int) -> None:
    """替模拟器向私有 adb server 登记：发 ``host:emulator:<adb 端口>``（4 位十六进制长度 + 内容）。

    模拟器只在开机时向 server 登记一次，server 重启（被别人 kill-server、崩溃）后就再也不认识
    它。这正是模拟器自己开机时发的那条消息，server 不回包；重复发不会出现重复条目
    （10-04 第 2 步实测：451 ms 恢复成 ``emulator-<控制台端口>``，shell 与 emu 控制台都正常）。
    """
    message = f"host:emulator:{emulator_adb_port}"
    payload = f"{len(message):04x}{message}".encode("ascii")
    _, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", server_port), timeout=5
    )
    try:
        writer.write(payload)
        await writer.drain()
        await asyncio.sleep(0.2)
    finally:
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()


async def reregister_emulator(root: str | Path, serial: str) -> bool:
    """私有 server 丢了 ``emulator-<控制台端口>`` 时把它登记回来，返回是否恢复。

    只在这台模拟器的 adb 端口确实由它自己的 qemu 在听（模拟器还活着）时才发，不往空端口登记。
    开机期间不登记（模拟器自己会来登记，替它登记只会白等 5 秒）：``open`` 正在等开机的实例
    （:data:`BOOTING`），以及 qemu 起来不到 60 秒的实例，都直接返回 ``False``。
    """
    console = _console_port_of(serial)
    if console is None or serial in BOOTING:
        return False
    process = await asyncio.to_thread(instance_qemu_on_adb_port, console)
    if process is None:
        return False
    try:
        age = time.time() - process.create_time()
    except psutil.Error:
        return False
    if age < _REREGISTER_MIN_QEMU_AGE_SECONDS:
        return False
    lock = _REREGISTER_LOCKS.setdefault(serial, asyncio.Lock())
    async with lock:
        server_port = adb_server_port(root)
        code, output = await _run_adb_once(root, "get-state", serial=serial, timeout=5)
        if code == 0 and output.strip() == "device":
            return True  # 别的协程刚登记回来
        logger.warning(
            f"私有 adb server（端口 {server_port}）上没有 {serial}，按 adb 端口 "
            f"{console + 1} 重新登记"
        )
        started = time.monotonic()
        try:
            await register_emulator(server_port, console + 1)
        except (OSError, asyncio.TimeoutError, TimeoutError) as e:
            logger.warning(f"重新登记 {serial} 失败: {e}")
            return False
        while time.monotonic() - started < _REREGISTER_WAIT_SECONDS:
            code, output = await _run_adb_once(
                root, "get-state", serial=serial, timeout=5
            )
            if code == 0 and output.strip() == "device":
                logger.info(
                    f"{serial} 已重新登记到私有 adb server（用时 "
                    f"{(time.monotonic() - started) * 1000:.0f} ms）"
                )
                _run_reregister_hooks(root, serial)
                return True
            await asyncio.sleep(0.2)
        logger.warning(
            f"重新登记 {serial} 后 {_REREGISTER_WAIT_SECONDS:.0f} 秒仍未上线"
        )
        return False


async def run_adb(
    root: str | Path,
    *args: str,
    serial: str | None = None,
    timeout: float = ADB_TIMEOUT,
    reregister: bool = True,
) -> tuple[int, str]:
    """跑一条私有 server 上的 adb 命令，返回 ``(返回码, 合并输出)``。**不抛异常。**

    轮询会一秒一条，所以这里不像 ``ProcessRunner`` 那样每条都记 info 日志。
    私有 server 上找不到 ``emulator-<控制台端口>`` 时先重新登记（:func:`reregister_emulator`），
    登记回来就重跑一次。``reregister=False`` 不做这一步：开机等待期间模拟器本来就还没登记，
    关机前的 sync 要守时限，都不该去替它登记。
    """
    code, output = await _run_adb_once(root, *args, serial=serial, timeout=timeout)
    if reregister and code != 0 and serial and device_missing(serial, output):
        if await reregister_emulator(root, serial):
            code, output = await _run_adb_once(
                root, *args, serial=serial, timeout=timeout
            )
    return code, output


async def run_adb_bytes(
    root: str | Path,
    *args: str,
    serial: str | None = None,
    timeout: float = ADB_TIMEOUT,
) -> tuple[int, bytes, str]:
    """同 :func:`run_adb`，但标准输出按原始字节返回（``exec-out screencap -p`` 这类二进制输出），
    标准错误单独解码返回：``(返回码, 输出字节, 错误文本)``。**不抛异常。**"""
    code, stdout, stderr = await _run_adb_raw(
        root, *args, serial=serial, timeout=timeout
    )
    if code != 0 and serial and device_missing(serial, stderr):
        if await reregister_emulator(root, serial):
            code, stdout, stderr = await _run_adb_raw(
                root, *args, serial=serial, timeout=timeout
            )
    return code, stdout, stderr


async def _run_adb_once(
    root: str | Path,
    *args: str,
    serial: str | None = None,
    timeout: float = ADB_TIMEOUT,
) -> tuple[int, str]:
    code, stdout, _ = await _run_adb_raw(
        root, *args, serial=serial, timeout=timeout, merge_stderr=True
    )
    return code, decode_bytes(stdout).strip()


async def _run_adb_raw(
    root: str | Path,
    *args: str,
    serial: str | None = None,
    timeout: float = ADB_TIMEOUT,
    merge_stderr: bool = False,
) -> tuple[int, bytes, str]:
    try:
        await ensure_adb_server(root)
        command = ["-P", str(adb_server_port(root))]
        if serial:
            command += ["-s", serial]
        process = await create_subprocess(
            adb_exe(root),
            *command,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
            if merge_stderr
            else asyncio.subprocess.PIPE,
        )
    except Exception as e:  # noqa: BLE001 - 见 run_adb 的 docstring
        message = f"{type(e).__name__}: {e}"
        return -1, message.encode() if merge_stderr else b"", message
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        with suppress(ProcessLookupError):
            process.kill()
        with suppress(Exception):
            await process.wait()
        message = f"adb {' '.join(args)} 超时（{timeout:.0f} 秒）"
        return -1, message.encode() if merge_stderr else b"", message
    return process.returncode or 0, stdout, decode_bytes(stderr or b"").strip()


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


def shader_cache_dir(root: str | Path) -> Path:
    return Path(root) / SHADER_CACHE_DIR


def launch_emulator(
    root: str | Path, args: list[str], log_path: Path
) -> subprocess.Popen:
    """起 ``emulator.exe``，输出写到 ``log_path``。

    宿主显卡驱动的着色器缓存放 ``<根>\\shader-cache``（``__GL_SHADER_DISK_CACHE_PATH``，
    照启动器 ``-ShaderCache``）：和用户的其它程序分开，需要时我们能自己清。
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = emulator_env(root)
    cache = shader_cache_dir(root)
    cache.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "__GL_SHADER_DISK_CACHE": "1",
            "__GL_SHADER_DISK_CACHE_PATH": str(cache),
            "__GL_SHADER_DISK_CACHE_SKIP_CLEANUP": "1",
        }
    )
    with log_path.open("ab") as log_file:
        return _popen_detached(
            [str(emulator_exe(root)), *args],
            env=env,
            stdout=log_file,
        )


def find_logcat_processes(root: str | Path, serial: str) -> list[psutil.Process]:
    """宿主上正在给这台实例落盘的 ``adb -P <端口> -s <序列号> logcat`` 进程（不管是谁起的）。

    只认自己进程表里的记录不够：后端重启后上一个进程起的 logcat 还在跑，再起就是两份。
    """
    port = str(adb_server_port(root))
    found = []
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if (process.info.get("name") or "").lower() != "adb.exe":
                continue
            cmdline = process.info.get("cmdline") or []
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        pairs = set(zip(cmdline, cmdline[1:]))
        if ("-P", port) in pairs and ("-s", serial) in pairs and "logcat" in cmdline:
            found.append(process)
    return found


#: 重新登记成功后要做的事（例如把随 server 一起断掉的 logcat 落盘重起来）。参数 (根目录, 序列号)。
_REREGISTER_HOOKS: list[Callable[[Path, str], Awaitable[object]]] = []
_HOOK_TASKS: set[asyncio.Task] = set()


def add_reregister_hook(hook: Callable[[Path, str], Awaitable[object]]) -> None:
    if hook not in _REREGISTER_HOOKS:
        _REREGISTER_HOOKS.append(hook)


def _run_reregister_hooks(root: str | Path, serial: str) -> None:
    for hook in _REREGISTER_HOOKS:

        async def run(hook=hook) -> None:
            try:
                await hook(Path(root), serial)
            except Exception as e:  # noqa: BLE001 - 钩子失败不影响已经恢复的连接
                logger.warning(f"{serial} 重新登记后的收尾失败: {e}")

        task = asyncio.create_task(run())
        _HOOK_TASKS.add(task)
        task.add_done_callback(_HOOK_TASKS.discard)


def start_logcat(root: str | Path, serial: str, log_path: Path) -> subprocess.Popen:
    """把客体 logcat 持续写到宿主文件。模拟器一关，adb logcat 自己退出。"""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        return _popen_detached(
            [
                str(adb_exe(root)),
                "-P",
                str(adb_server_port(root)),
                "-s",
                serial,
                "logcat",
                "-v",
                "threadtime",
                "-b",
                "main,system,crash,events",
            ],
            env=emulator_env(root),
            stdout=log_file,
        )


# ---- 宿主调度 -------------------------------------------------------------


def _l3_groups() -> list[tuple[int, int]]:
    """每个 L3 缓存的 (容量字节, 处理器掩码)。只读 ``GetLogicalProcessorInformationEx``。"""
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return []
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info.restype = ctypes.c_int
    get_info.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    relation_cache = 2
    length = ctypes.c_uint32(0)
    get_info(relation_cache, None, ctypes.byref(length))
    if not length.value:
        return []
    buffer = ctypes.create_string_buffer(length.value)
    if not get_info(relation_cache, buffer, ctypes.byref(length)):
        return []
    raw = buffer.raw[: length.value]
    groups: list[tuple[int, int]] = []
    offset = 0
    while offset + 48 <= len(raw):
        size = int.from_bytes(raw[offset + 4 : offset + 8], "little")
        if size <= 0:
            break
        # CACHE_RELATIONSHIP：Level 在 +8，CacheSize 在 +12，GroupMask.Mask 在 +40
        if raw[offset + 8] == 3:
            groups.append(
                (
                    int.from_bytes(raw[offset + 12 : offset + 16], "little"),
                    int.from_bytes(raw[offset + 40 : offset + 48], "little"),
                )
            )
        offset += size
    return groups


def big_l3_cpus() -> list[int] | None:
    """X3D 处理器上大 L3 那组核心的编号；L3 不分大小（普通处理器）返回 ``None``。"""
    groups = sorted(_l3_groups(), reverse=True)
    if len(groups) < 2 or groups[0][0] <= groups[-1][0]:
        return None
    mask = groups[0][1]
    return [cpu for cpu in range(64) if mask >> cpu & 1]


def tune_host_scheduling(process: psutil.Process) -> str:
    """qemu 提到「高于正常」优先级；X3D 处理器上绑到大 L3 那组核心。返回说明给日志。

    09-28 在 7950X3D 上 A/B（崩坏三）：绑到 3D V-cache 那组核心，qemu CPU 降约 20%、游戏主线程
    每帧 CPU 降约 25%；高频那组不比默认好。只在 L3 大小不一（X3D）时绑，其余交给 Windows。
    """
    notes: list[str] = []
    try:
        process.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        notes.append("优先级高于正常")
    except (psutil.Error, AttributeError, OSError) as e:
        notes.append(f"设优先级失败（{e}）")
    cpus = big_l3_cpus()
    if cpus:
        try:
            process.cpu_affinity(cpus)
            notes.append(f"绑定大 L3 核心 {cpus[0]}–{cpus[-1]}")
        except (psutil.Error, OSError, ValueError) as e:
            notes.append(f"绑核失败（{e}）")
    return "，".join(notes)


# ---- 电脑检查 -------------------------------------------------------------


@dataclass(frozen=True)
class AccelCheck:
    ok: bool
    detail: str


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
