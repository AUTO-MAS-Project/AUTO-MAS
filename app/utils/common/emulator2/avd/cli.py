#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""调用发布包里的 ``tools\\modavd.exe``。

这个模块只负责一次 CLI 调用：构造参数、隔离 stdout/stderr、解析 ``--json`` 信封以及把状态值
翻译成 AUTO-MAS 的公共枚举。根目录是否应该走 CLI、以及业务异常如何和旧实现对齐，由
``manager.py`` 决定：根目录没有 ``tools\\modavd.exe`` 时继续用原来的 Python 实现；exe 在但不可用时抛
:class:`ModAvdUnavailable`，不回退，免得同一台实例两套开关机混用。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Sequence

import psutil

from app.models.emulator import DeviceStatus
from app.utils import get_logger
from app.utils.common.process import runner as _utils_process_runner

from .host import AdbPortConflict

logger = get_logger("魔改 AVD CLI")

SUPPORTED_PROTOCOL = 1
CLI_EXE_RELATIVE_PATH = Path("tools") / "modavd.exe"
DEFAULT_START_TIMEOUT_SECONDS = 300
CREATE_TIMEOUT_SECONDS = 1200
CREATE_PROCESS_MARGIN_SECONDS = 240
STOP_PROCESS_TIMEOUT_SECONDS = 90
INSTALL_PROCESS_TIMEOUT_SECONDS = 900
COMMAND_TIMEOUT_SECONDS = 60
BRIDGE_ROUND_BOOT_SECONDS = 300
BRIDGE_ROUND_STOP_SECONDS = 28
BRIDGE_ROUND_RESTART_SECONDS = 30
#: 本进程里所有根目录的 start / restart / create 至少错开这么多秒。0.36.0（modavd v0.1.0）开机后先把
#: 客体脚本写进用户级的 ``%TEMP%\\modavd-guest``，各根目录共用；几个 modavd 同时第一次写会撞上
#: 「文件被占用」，那次开机少推一个脚本、只在 ``warnings`` 里留一句。错开开机，开机后的设置也就错开；
#: 仍然撞上的由管理器在拉游戏前补跑一次 start。
START_STAGGER_SECONDS = 2.0
#: start / restart 报这些错时实例可能被开了一半（modavd 自己的开机超时不关机），要补一次 stop；
#: ``busy``（别的 modavd 正在开）、``precheck_failed``、``port_conflict`` 这类没开机的不能动。
_STOP_AFTER_START_ERRORS = frozenset(
    {"timeout", "launch_failed", "canceled", "internal"}
)

#: 取消 / 超时收尾时每隔这么多秒看一次装桥是否结束、CLI 是否退出。
_CANCEL_POLL_SECONDS = 2.0
_next_start_at = 0.0


async def _wait_start_turn() -> None:
    """排到下一个开机名额。读和写之间没有 await，不用锁，也不绑事件循环。"""
    global _next_start_at
    now = time.monotonic()
    turn = max(now, _next_start_at)
    _next_start_at = turn + START_STAGGER_SECONDS
    if turn > now:
        await asyncio.sleep(turn - now)


def start_process_timeout(max_wait: int | float) -> float:
    """一轮开机加三轮装桥的总预算，桥安装时不能靠 status 判断 start 是否结束。"""
    boot = float(max_wait)
    return (
        boot
        + 60
        + 3
        * (
            BRIDGE_ROUND_BOOT_SECONDS
            + BRIDGE_ROUND_STOP_SECONDS
            + BRIDGE_ROUND_RESTART_SECONDS
            + boot
            + 60
        )
    )


@dataclass(frozen=True)
class ProcessOutput:
    """子进程的独立输出。``stdout`` 是 JSON，``stderr`` 只包含日志。"""

    returncode: int
    stdout: str
    stderr: str


class CLIError(RuntimeError):
    """``modavd --json`` 的错误信封。"""

    def __init__(
        self,
        code: str,
        message: str,
        advice: str = "",
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.advice = advice
        self.returncode = returncode


class ModAvdUnavailable(RuntimeError):
    """根目录有 modavd.exe，但它不可用；不允许悄悄切回 Python 实现。"""


ProcessTimeoutHandler = Callable[[asyncio.subprocess.Process], Awaitable[None]]
Runner = Callable[
    [Sequence[str], float, ProcessTimeoutHandler | None, bool], Awaitable[ProcessOutput]
]


async def _run_process(
    args: Sequence[str],
    timeout: float,
    *,
    timeout_handler: ProcessTimeoutHandler | None = None,
    breakaway: bool = False,
) -> ProcessOutput:
    """启动一次 modavd；超时处理只针对 CLI 进程，不碰它脱离出来的模拟器。"""

    try:
        process = await _utils_process_runner.create_subprocess(
            *args,
            breakaway=breakaway,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError) as exc:
        raise CLIError("internal", f"启动 modavd 失败: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.CancelledError:
        try:
            if timeout_handler is not None:
                await asyncio.shield(timeout_handler(process))
        except Exception as exc:  # noqa: BLE001 - kill/wait 仍必须执行
            logger.warning(f"modavd 取消收尾失败: {exc}")
        finally:
            if process.returncode is None:
                process.kill()
            with suppress(Exception):
                await process.wait()
        raise
    except asyncio.TimeoutError as exc:
        try:
            if timeout_handler is not None:
                await timeout_handler(process)
        except Exception as handler_error:  # noqa: BLE001 - timeout 本身优先返回
            logger.warning(f"modavd 超时收尾失败: {handler_error}")
        finally:
            if process.returncode is None:
                process.kill()
            await process.communicate()
        raise CLIError("timeout", f"modavd 命令超过 {timeout:.0f} 秒未结束") from exc

    return ProcessOutput(
        process.returncode or 0,
        _utils_process_runner.decode_bytes(stdout),
        _utils_process_runner.decode_bytes(stderr),
    )


def _as_text(value: object) -> str:
    return value if isinstance(value, str) else str(value or "")


def _parse_envelope(output: ProcessOutput, *, allow_nonzero_ok: bool = False) -> Any:
    """解析一行 JSON 信封；错误信封即使退出码不为零也保留其 code/message。"""

    if output.stderr.strip():
        # 日志已经和 stdout 分开收取；不把它拼进返回值，避免污染 JSON。
        logger.debug("modavd: {}", output.stderr.strip())

    stderr_lines = [line.strip() for line in output.stderr.splitlines() if line.strip()]
    stderr_tail = stderr_lines[-1][-300:] if stderr_lines else ""
    try:
        envelope = json.loads(output.stdout.lstrip("\ufeff").strip())
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        detail = f"；stderr: {stderr_tail}" if stderr_tail else ""
        raise CLIError(
            "internal",
            f"modavd 返回的 JSON 无法解析（退出码 {output.returncode}）{detail}",
            returncode=output.returncode,
        ) from exc

    if not isinstance(envelope, dict):
        raise CLIError(
            "internal",
            f"modavd 返回的 JSON 不是对象{('；stderr: ' + stderr_tail) if stderr_tail else ''}",
            returncode=output.returncode,
        )

    if envelope.get("ok") is True:
        if output.returncode != 0 and not allow_nonzero_ok:
            raise CLIError(
                "internal",
                f"modavd 成功信封却返回退出码 {output.returncode}",
                returncode=output.returncode,
            )
        return envelope.get("data")

    error = envelope.get("error")
    if isinstance(error, dict):
        code = _as_text(error.get("code")) or "internal"
        message = _as_text(error.get("message")) or code
        advice = _as_text(error.get("advice"))
    else:
        code = "internal"
        message = f"modavd 命令失败（退出码 {output.returncode}）"
        advice = ""
    raise CLIError(code, message, advice, output.returncode)


_VERSION_CACHE: dict[str, tuple[int, int, str | None]] = {}


def _exe_cache_key(exe: Path) -> tuple[str, int, int]:
    stat = exe.stat()
    return os.path.normcase(str(exe.resolve())), stat.st_size, stat.st_mtime_ns


async def resolve_cli(root: str | Path) -> "ModAvdCli | None":
    """按 exe 是否存在选择 CLI；存在但检测失败就抛，不回退 Python。"""
    cli = ModAvdCli(root)
    if not cli.executable_available:
        return None
    try:
        key, size, mtime_ns = _exe_cache_key(cli.exe)
    except OSError as exc:
        raise ModAvdUnavailable(f"modavd 不可用：读取 {cli.exe} 失败：{exc}") from exc
    cached = _VERSION_CACHE.get(key)
    if cached is not None and cached[:2] == (size, mtime_ns):
        if cached[2] is None:
            return cli
        raise ModAvdUnavailable(cached[2])
    try:
        version = await cli.version()
    except CLIError as exc:
        # 起进程失败、超时、临时 JSON 损坏都不缓存；下一次查询应有机会恢复。
        raise ModAvdUnavailable(f"modavd 不可用：{exc.message}") from exc
    if not isinstance(version, dict):
        raise ModAvdUnavailable("modavd 不可用：version --json 没有返回对象")
    protocol = version.get("protocol")
    if protocol != SUPPORTED_PROTOCOL:
        direction = (
            "更旧"
            if isinstance(protocol, int) and protocol < SUPPORTED_PROTOCOL
            else "更新"
        )
        message = (
            f"modavd 协议 {protocol}（比 MAS 认识的 {SUPPORTED_PROTOCOL} {direction}），"
            "请更新 ModAVD 或 MAS"
        )
        _VERSION_CACHE[key] = (size, mtime_ns, message)
        raise ModAvdUnavailable(message)
    _VERSION_CACHE[key] = (size, mtime_ns, None)
    return cli


def map_cli_error(error: CLIError) -> RuntimeError:
    """把无须额外上下文的 CLI 错误映射成旧管理器会抛的异常。

    ``precheck_failed`` 的 CLI 信封没有旧版 ``PrecheckItem`` 的细分 ID，因此用一条合成的阻断项
    保留原来的异常类型；管理器如果已经从 ``check --json`` 得到了更细的项目，可以继续自己构造。
    """

    message = error.message
    if error.advice:
        message = f"{message}（建议：{error.advice}）"
    if error.code == "invalid_argument":
        return ValueError(message)
    if error.code == "port_conflict":
        return AdbPortConflict(message)
    if error.code == "precheck_failed":
        from .precheck import PrecheckFailed, PrecheckItem

        return PrecheckFailed(
            PrecheckItem(
                "precheck",
                "魔改 AVD 开机前检查",
                False,
                True,
                error.message,
                error.advice,
            )
        )
    return RuntimeError(message)


def map_status(status: str | None, busy: str | None = "") -> DeviceStatus:
    """将 modavd 的字符串状态翻译为公共 ``DeviceStatus``。"""

    busy_value = (busy or "").strip().lower()
    status_value = (status or "").strip().lower()
    # 新建的初始化（后台开机、装输入法和执行桥、关机）做完前一律是新建中，不管那几次开机从外面看像什么
    if status_value == "creating" or busy_value == "creating":
        return DeviceStatus.CREATING
    if busy_value == "stopping":
        return DeviceStatus.CLOSEING
    if busy_value:
        return DeviceStatus.STARTING
    if status_value == "starting":
        return DeviceStatus.STARTING
    if status_value == "create_failed":
        return DeviceStatus.ERROR
    if status_value == "online":
        return DeviceStatus.ONLINE
    if status_value == "offline":
        return DeviceStatus.OFFLINE
    return DeviceStatus.STARTING


class ModAvdCli:
    """单个发布根目录的 modavd CLI 客户端。"""

    def __init__(
        self,
        root: str | Path,
        *,
        exe: str | Path | None = None,
        runner: Runner | None = None,
    ) -> None:
        self.root = Path(root)
        self.exe = Path(exe) if exe is not None else self.root / CLI_EXE_RELATIVE_PATH
        self._runner = runner or _run_process

    @property
    def executable_available(self) -> bool:
        return self.exe.is_file()

    async def _stop_after_cancel(
        self, index: str | int, process: asyncio.subprocess.Process, label: str
    ) -> None:
        """取消 start/restart 时等待装桥这一轮完成，再优雅 stop；超时才杀 CLI。"""
        index = str(index)
        deadline = asyncio.get_running_loop().time() + STOP_PROCESS_TIMEOUT_SECONDS
        while (
            process.returncode is None and asyncio.get_running_loop().time() < deadline
        ):
            bridging = False
            with suppress(CLIError):
                data = await self.status(index)
                bridging = (
                    isinstance(data, dict)
                    and str(data.get("busy") or "").lower() == "bridging"
                )
            if not bridging:
                with suppress(Exception):
                    parent = psutil.Process(process.pid)
                    bridging = any(
                        "modavd-bridge.ps1" in " ".join(child.cmdline()).lower()
                        for child in parent.children(recursive=True)
                    )
            if bridging:
                logger.warning(
                    f"modavd {label} 取消时正在装桥，等待这一轮结束: {index}"
                )
                await asyncio.sleep(_CANCEL_POLL_SECONDS)
                continue
            try:
                await self.stop(index)
            except CLIError as exc:
                logger.warning(f"modavd {label} 取消收尾 stop 失败: {exc.message}")
            await asyncio.sleep(_CANCEL_POLL_SECONDS)
        if process.returncode is None:
            logger.warning(f"modavd {label} 取消收尾超时，结束 CLI 进程: {index}")
            process.kill()
            with suppress(Exception):
                await process.wait()
        try:
            await self.stop(index)
        except CLIError as exc:
            logger.warning(f"modavd {label} 取消后补 stop 失败: {exc.message}")

    async def _stop_if_running(self, index: str | int, label: str) -> None:
        try:
            data = await self.status(index)
            if isinstance(data, dict) and data.get("running"):
                await self.stop(index)
        except CLIError as exc:
            logger.warning(f"modavd {label} 退出后补 stop 失败: {exc.message}")

    def _args(
        self,
        command: str,
        *command_args: str,
        include_root: bool = True,
    ) -> list[str]:
        args = [str(self.exe)]
        if include_root:
            args.extend(("--root", str(self.root)))
        args.extend(("--json", command, *command_args))
        return args

    async def _call(
        self,
        command: str,
        *command_args: str,
        include_root: bool = True,
        timeout: float = COMMAND_TIMEOUT_SECONDS,
        allow_nonzero_ok: bool = False,
        timeout_handler: ProcessTimeoutHandler | None = None,
        breakaway: bool = False,
    ) -> Any:
        try:
            output = await self._runner(
                self._args(command, *command_args, include_root=include_root),
                timeout,
                timeout_handler,
                breakaway,
            )
        except CLIError:
            raise
        except asyncio.TimeoutError as exc:
            raise CLIError(
                "timeout", f"modavd 命令超过 {timeout:.0f} 秒未结束"
            ) from exc
        except (OSError, ValueError) as exc:
            raise CLIError("internal", f"运行 modavd 失败: {exc}") from exc
        return _parse_envelope(output, allow_nonzero_ok=allow_nonzero_ok)

    async def version(self) -> Any:
        return await self._call("version", include_root=False)

    async def check(self, *, memory: int | str | None = None) -> Any:
        args: list[str] = []
        if memory is not None:
            args.extend(("--memory", str(memory)))
        return await self._call("check", *args)

    async def list(self) -> Any:
        return await self._call("list")

    async def info(self, index: str | int) -> Any:
        return await self._call("info", str(index))

    async def status(self, index: str | int) -> Any:
        return await self._call("status", str(index))

    async def create(
        self,
        *,
        index: str | int | None = None,
        title: str | None = None,
        memory: int | str | None = None,
        cpu: int | None = None,
        data_gb: int | None = None,
        fps: int | None = None,
    ) -> Any:
        args: list[str] = []
        if index is not None:
            args.extend(("--index", str(index)))
        if title is not None:
            args.extend(("--title", title))
        if memory is not None:
            args.extend(("--memory", str(memory)))
        if cpu is not None:
            args.extend(("--cpu", str(cpu)))
        if data_gb is not None:
            args.extend(("--data-gb", str(data_gb)))
        if fps is not None:
            args.extend(("--fps", str(fps)))
        create_timeout = CREATE_TIMEOUT_SECONDS
        legacy_args = list(args)
        args.extend(("--timeout", str(create_timeout)))
        process_timeout = create_timeout + CREATE_PROCESS_MARGIN_SECONDS
        existing: set[str] = set()
        if index is None:
            listing = await self.list()
            raw_items = (
                listing.get("instances", []) if isinstance(listing, dict) else []
            )
            existing = {
                str(raw.get("index"))
                for raw in raw_items
                if isinstance(raw, dict) and raw.get("index") is not None
            }

        async def stop_targets(targets: list[str], *, force: bool = False) -> None:
            for item in dict.fromkeys(targets):
                try:
                    await self.stop(item, force=force)
                except CLIError as exc:
                    logger.warning(
                        f"modavd create 收尾 stop {item} 失败: {exc.message}"
                    )

        async def find_targets() -> list[str]:
            listing = await self.list()
            items = listing.get("instances", []) if isinstance(listing, dict) else []
            targets: list[str] = []
            for raw in items:
                if not isinstance(raw, dict) or raw.get("index") is None:
                    continue
                item = str(raw["index"])
                status = str(raw.get("status") or "").lower()
                if item not in existing and status in {"creating", "create_failed"}:
                    targets.append(item)
            return targets

        async def bridge_running(
            process: asyncio.subprocess.Process, targets: list[str]
        ) -> bool:
            for item in targets:
                with suppress(CLIError):
                    data = await self.status(item)
                    if (
                        isinstance(data, dict)
                        and str(data.get("busy") or "").lower() == "bridging"
                    ):
                        return True
            with suppress(Exception):
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    cmdline = " ".join(child.cmdline()).lower()
                    if "modavd-bridge.ps1" in cmdline:
                        return True
            return False

        async def stop_created_cli(process: asyncio.subprocess.Process) -> None:
            indices: list[str] = []
            if index is not None:
                indices.append(str(index))
            else:
                with suppress(CLIError):
                    indices = await find_targets()
            deadline = asyncio.get_running_loop().time() + STOP_PROCESS_TIMEOUT_SECONDS
            while (
                process.returncode is None
                and asyncio.get_running_loop().time() < deadline
            ):
                if await bridge_running(process, indices):
                    await asyncio.sleep(_CANCEL_POLL_SECONDS)
                    continue
                await stop_targets(indices)
                await asyncio.sleep(_CANCEL_POLL_SECONDS)
                if not indices and process.returncode is not None:
                    break
            if process.returncode is None:
                process.kill()
                with suppress(Exception):
                    await process.wait()
            await stop_targets(indices)

        # v0.2.0 起 create 会无头开一次机，和 start 一样要错开
        await _wait_start_turn()
        try:
            return await self._call(
                "create",
                *args,
                timeout=process_timeout,
                timeout_handler=stop_created_cli,
                breakaway=True,
            )
        except CLIError as error:
            if (
                error.code not in {"invalid_argument", "usage"}
                or "--timeout" not in error.message
            ):
                raise
            return await self._call(
                "create",
                *legacy_args,
                timeout=process_timeout,
                timeout_handler=stop_created_cli,
                breakaway=True,
            )

    async def set(
        self,
        index: str | int,
        *,
        title: str | None = None,
        memory: int | str | None = None,
        cpu: int | None = None,
        data_gb: int | None = None,
        fps: int | None = None,
    ) -> Any:
        args = [str(index)]
        if title is not None:
            args.extend(("--title", title))
        if memory is not None:
            args.extend(("--memory", str(memory)))
        if cpu is not None:
            args.extend(("--cpu", str(cpu)))
        if data_gb is not None:
            args.extend(("--data-gb", str(data_gb)))
        if fps is not None:
            args.extend(("--fps", str(fps)))
        return await self._call("set", *args, timeout=COMMAND_TIMEOUT_SECONDS)

    async def delete(self, index: str | int) -> Any:
        return await self._call(
            "delete", str(index), "--yes", timeout=COMMAND_TIMEOUT_SECONDS
        )

    async def start(
        self,
        index: str | int,
        *,
        window: bool = False,
        timeout: int | float | None = None,
    ) -> Any:
        boot_timeout = int(timeout or DEFAULT_START_TIMEOUT_SECONDS)
        args = [str(index)]
        if window:
            args.append("--window")
        args.extend(("--timeout", str(boot_timeout)))
        process_timeout = start_process_timeout(boot_timeout)

        async def stop_started_cli(process: asyncio.subprocess.Process) -> None:
            logger.warning(
                f"modavd start 超时，先请求 stop，再等待 start CLI 进程退出: {index}"
            )
            await self._stop_after_cancel(index, process, "start")

        await _wait_start_turn()
        try:
            return await self._call(
                "start",
                *args,
                timeout=process_timeout,
                timeout_handler=stop_started_cli,
            )
        except CLIError as error:
            if error.code in _STOP_AFTER_START_ERRORS:
                await self._stop_if_running(index, "start")
            raise
        except asyncio.CancelledError:
            await self._stop_if_running(index, "start")
            raise

    async def stop(self, index: str | int, *, force: bool = False) -> Any:
        args = [str(index)]
        if force:
            args.append("--force")
        return await self._call("stop", *args, timeout=STOP_PROCESS_TIMEOUT_SECONDS)

    async def restart(
        self,
        index: str | int,
        *,
        window: bool = False,
        timeout: int | float | None = None,
        force: bool = False,
    ) -> Any:
        boot_timeout = int(timeout or DEFAULT_START_TIMEOUT_SECONDS)
        args = [str(index)]
        if window:
            args.append("--window")
        args.extend(("--timeout", str(boot_timeout)))
        if force:
            args.append("--force")
        process_timeout = start_process_timeout(boot_timeout)

        async def stop_restarted_cli(process: asyncio.subprocess.Process) -> None:
            logger.warning(
                f"modavd restart 超时，先请求 stop，再等待 CLI 进程退出: {index}"
            )
            await self._stop_after_cancel(index, process, "restart")

        await _wait_start_turn()
        try:
            return await self._call(
                "restart",
                *args,
                timeout=process_timeout,
                timeout_handler=stop_restarted_cli,
            )
        except CLIError as error:
            if error.code in _STOP_AFTER_START_ERRORS:
                await self._stop_if_running(index, "restart")
            raise
        except asyncio.CancelledError:
            await self._stop_if_running(index, "restart")
            raise

    async def stop_all(self, *, force: bool = False) -> Any:
        args = ["--all"]
        if force:
            args.append("--force")
        return await self._call(
            "stop",
            *args,
            timeout=STOP_PROCESS_TIMEOUT_SECONDS,
            allow_nonzero_ok=True,
        )

    async def shell(
        self,
        index: str | int,
        *command: str,
        timeout: int | float = 5,
    ) -> Any:
        args = [str(index), "--timeout", str(int(timeout)), "--", *command]
        return await self._call("shell", *args, timeout=float(timeout) + 10)

    async def window(self, index: str | int, *, visible: bool) -> Any:
        """显示或隐藏一个已带窗口开机的实例。"""

        return await self._call("window", str(index), "show" if visible else "hide")

    async def install(self, index: str | int, apk: str | Path) -> Any:
        """在在线实例里安装 APK；游戏包可能很大，进程时限固定至少 900 秒。"""

        return await self._call(
            "install",
            str(index),
            str(apk),
            timeout=INSTALL_PROCESS_TIMEOUT_SECONDS,
        )


__all__ = [
    "CLIError",
    "CLI_EXE_RELATIVE_PATH",
    "COMMAND_TIMEOUT_SECONDS",
    "DEFAULT_START_TIMEOUT_SECONDS",
    "INSTALL_PROCESS_TIMEOUT_SECONDS",
    "ModAvdCli",
    "ModAvdUnavailable",
    "ProcessOutput",
    "resolve_cli",
    "CREATE_PROCESS_MARGIN_SECONDS",
    "CREATE_TIMEOUT_SECONDS",
    "START_STAGGER_SECONDS",
    "STOP_PROCESS_TIMEOUT_SECONDS",
    "SUPPORTED_PROTOCOL",
    "map_cli_error",
    "map_status",
    "start_process_timeout",
]
