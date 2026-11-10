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

这个模块只负责一次 CLI 调用：构造参数、隔离 stdout/stderr、解析 ``--json`` 信封，交回 modavd
原样的状态字符串，不依赖 MAS 的业务模型。状态值怎么翻译成 AUTO-MAS 的设备状态、业务异常怎么还原，
由 ``manager.py`` 决定：根目录没有 ``tools\\modavd.exe`` 时不支持；exe 在但不可用时抛
:class:`ModAvdUnavailable`。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

import psutil

from app.utils import get_logger
from app.utils.common.process import runner as _utils_process_runner
from app.utils.common.process.scope import current_process_scope

from .host import AdbPortConflict
from .instances import config_path, read_ini, resolution_for

logger = get_logger("ModAVD CLI")

#: MAS 认得的 modavd 协议版本。2 是 ModAVDManager 0.3.0 去掉 ``restart`` 命令时升的；MAS 重启本来就是
#: 先 stop 再 start，两个都能用。逐个列出而不写成「≥1」，以后再升还能认出不兼容。
SUPPORTED_PROTOCOLS = (1, 2)
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
#: 本进程里所有根目录的 start / create 至少错开这么多秒（重启是先 stop 再 start，跟着 start 错开）。0.36.0（modavd v0.1.0）开机后先把
#: 客体脚本写进用户级的 ``%TEMP%\\modavd-guest``，各根目录共用；几个 modavd 同时第一次写会撞上
#: 「文件被占用」，那次开机少推一个脚本、只在 ``warnings`` 里留一句。错开开机，开机后的设置也就错开；
#: 仍然撞上的由管理器在拉游戏前补跑一次 start。
START_STAGGER_SECONDS = 2.0
#: start 报这些错时实例可能被开了一半（modavd 自己的开机超时不关机），要补一次 stop；
#: ``busy``（别的 modavd 正在开）、``precheck_failed``、``port_conflict`` 这类没开机的不能动。
_STOP_AFTER_START_ERRORS = frozenset(
    {"timeout", "launch_failed", "canceled", "internal"}
)

#: 取消 / 超时收尾时每隔这么多秒看一次装桥是否结束、CLI 是否退出。
_CANCEL_POLL_SECONDS = 2.0
#: 新建被取消 / 超时后，最多等 create CLI 自己退出这么久，再结束它。
_CREATE_CLEANUP_SECONDS = STOP_PROCESS_TIMEOUT_SECONDS
#: ``update status`` / ``recover`` 只看本地、改几次名；``check`` 要联网问一次。
UPDATE_QUICK_TIMEOUT_SECONDS = 300
#: ``update prepare`` / ``install`` 要下载整包，慢网下要很久；modavd 自己有连接和停顿超时，这里只兜底。
UPDATE_LONG_TIMEOUT_SECONDS = 6 * 3600
#: ``update`` 的 ``--source`` / ``--cdk-dpapi`` 只在 Windows 上可用（``--cdk-dpapi`` 是 DPAPI 密文）。
CALLER_UPDATE_OPTIONS_PLATFORM = sys.platform == "win32"
#: 边读边回调 stderr 时单行的上限（进度行很短；超长的行丢掉，不影响结果）。
_STREAM_LINE_LIMIT = 1024 * 1024
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
        details: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.advice = advice
        self.returncode = returncode
        #: 错误信封里的 ``details``（可选，值都是字符串，比如 busy 的 ``reason``）
        self.details: dict[str, str] = dict(details or {})


class ModAvdUnavailable(RuntimeError):
    """根目录有 modavd.exe，但它不可用。"""


@dataclass(frozen=True)
class UpdateProgressEvent:
    """``modavd --json update`` 在 stderr 上的一条进度日志（带 ``progress`` 的那种）。

    ``percent`` 为 -1 表示不知道；``stage`` 是 checking / downloading / extracting / verifying /
    installing，以后可能多出别的值。"""

    stage: str
    message: str
    percent: float
    done_bytes: int
    total_bytes: int


ProcessTimeoutHandler = Callable[[asyncio.subprocess.Process], Awaitable[None]]
#: 按位置收 ``(参数, 时限, 超时收尾, 脱离任务组)``；要边读 stderr 或换环境时另带关键字
#: ``env`` / ``on_stderr_line``（只在用到时传，别的调用点照旧四个位置参数）。
Runner = Callable[..., Awaitable[ProcessOutput]]


async def _collect(
    process: asyncio.subprocess.Process,
    on_stderr_line: Callable[[str], None] | None,
) -> tuple[bytes, bytes]:
    """读完 stdout 和 stderr；给了 ``on_stderr_line`` 时 stderr 按行边读边回调。"""
    if on_stderr_line is None:
        return await process.communicate()
    assert process.stdout is not None and process.stderr is not None
    stderr_stream = process.stderr

    async def read_stderr() -> bytes:
        chunks: list[bytes] = []
        while True:
            try:
                line = await stderr_stream.readline()
            except ValueError:
                # 超长的一行：丢掉这一段，接着读
                continue
            if not line:
                return b"".join(chunks)
            chunks.append(line)
            text = _utils_process_runner.decode_bytes(line).strip()
            if not text:
                continue
            try:
                on_stderr_line(text)
            except Exception as error:  # noqa: BLE001 - 回调出错不影响命令本身
                logger.warning(f"处理 modavd 输出失败: {error}")

    stdout, stderr = await asyncio.gather(process.stdout.read(), read_stderr())
    await process.wait()
    return stdout, stderr


async def _run_process(
    args: Sequence[str],
    timeout: float,
    timeout_handler: ProcessTimeoutHandler | None = None,
    breakaway: bool = False,
    *,
    env: Mapping[str, str] | None = None,
    on_stderr_line: Callable[[str], None] | None = None,
) -> ProcessOutput:
    """启动一次 modavd；命令超时回收 CLI，任务停止仍由任务进程组统一清理。

    参数按 :data:`Runner` 的位置约定收：``ModAvdCli._call`` 按位置传四个参数。``env`` 是子进程的
    整份环境（``None`` 继承 MAS 的）；``on_stderr_line`` 给了就按行边读边回调 stderr（``update``
    的进度），否则一次读完。参数列表不进日志和错误（``update`` 的 ``--cdk-dpapi`` 在里面）。"""

    extra: dict[str, Any] = {}
    if env is not None:
        extra["env"] = dict(env)
    if on_stderr_line is not None:
        extra["limit"] = _STREAM_LINE_LIMIT
    try:
        process = await _utils_process_runner.create_subprocess(
            *args,
            breakaway=breakaway,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **extra,
        )
    except (OSError, ValueError) as exc:
        raise CLIError("internal", f"启动 modavd 失败: {exc}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(
            _collect(process, on_stderr_line), timeout
        )
    except (asyncio.CancelledError, TimeoutError) as exc:

        async def cleanup() -> None:
            try:
                scope = current_process_scope.get()
                if timeout_handler is not None and not (
                    scope is not None and scope.closed
                ):
                    handler = asyncio.create_task(timeout_handler(process))
                    try:
                        await _utils_process_runner.wait_for_process_cleanup(
                            handler, timeout=STOP_PROCESS_TIMEOUT_SECONDS
                        )
                    except TimeoutError:
                        handler.cancel()
                        handler.add_done_callback(
                            lambda task: None if task.cancelled() else task.exception()
                        )
                        logger.warning("modavd 实例收尾超时，转入 CLI 强制清理")
            except Exception as error:  # noqa: BLE001 - CLI 仍须回收
                logger.warning(f"modavd 收尾失败: {error}")
            finally:
                await _utils_process_runner.stop_process(process)

        closing = asyncio.create_task(cleanup())
        closing.add_done_callback(
            lambda task: None if task.cancelled() else task.exception()
        )
        try:
            await _utils_process_runner.wait_for_process_cleanup(
                closing, timeout=STOP_PROCESS_TIMEOUT_SECONDS + 10
            )
        except Exception as error:
            if isinstance(exc, asyncio.CancelledError):
                raise exc from error
            raise CLIError(
                "timeout", f"modavd 命令超过 {timeout:.0f} 秒未结束"
            ) from error
        if isinstance(exc, asyncio.CancelledError):
            raise
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
    details: dict[str, str] = {}
    if isinstance(error, dict):
        code = _as_text(error.get("code")) or "internal"
        message = _as_text(error.get("message")) or code
        advice = _as_text(error.get("advice"))
        raw_details = error.get("details")
        if isinstance(raw_details, dict):
            details = {str(key): _as_text(value) for key, value in raw_details.items()}
    else:
        code = "internal"
        message = f"modavd 命令失败（退出码 {output.returncode}）"
        advice = ""
    raise CLIError(code, message, advice, output.returncode, details)


def parse_update_progress(line: str) -> UpdateProgressEvent | None:
    """``update`` 的一行 stderr 日志里的进度；不是 JSON、没有 ``progress`` 的行返回 ``None``。

    认不得的键不管，缺的数字按 -1 / 0 算（契约：日志行以后还可能多出键）。"""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    progress = record.get("progress")
    if not isinstance(progress, dict):
        return None

    def number(value: object, default: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return float(value)

    return UpdateProgressEvent(
        stage=_as_text(progress.get("stage")),
        message=_as_text(record.get("msg")),
        percent=number(progress.get("percent"), -1),
        done_bytes=int(number(progress.get("done_bytes"), 0)),
        total_bytes=int(number(progress.get("total_bytes"), 0)),
    )


def _forward_progress(
    callback: Callable[[UpdateProgressEvent], None], line: str
) -> None:
    event = parse_update_progress(line)
    if event is not None:
        callback(event)


_VERSION_CACHE: dict[str, tuple[int, int, str | None]] = {}
#: ``help update`` 里有没有 ``--source``（新命令行才有 ``--source`` / ``--cdk-dpapi``），按 exe 缓存。
_UPDATE_OPTIONS_CACHE: dict[str, tuple[int, int, bool]] = {}


def _exe_cache_key(exe: Path) -> tuple[str, int, int]:
    stat = exe.stat()
    return os.path.normcase(str(exe.resolve())), stat.st_size, stat.st_mtime_ns


async def resolve_cli(root: str | Path) -> "ModAvdCli | None":
    """exe 不在返回 ``None``；在就做版本检查，检测失败抛 :class:`ModAvdUnavailable`。"""
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
    if protocol not in SUPPORTED_PROTOCOLS or isinstance(protocol, bool):
        direction = (
            "更旧"
            if isinstance(protocol, int) and protocol < min(SUPPORTED_PROTOCOLS)
            else "更新"
        )
        known = " / ".join(str(item) for item in SUPPORTED_PROTOCOLS)
        message = (
            f"modavd 协议 {protocol}（比 MAS 认识的 {known} {direction}），"
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
                "ModAVD 开机前检查",
                False,
                True,
                error.message,
                error.advice,
            )
        )
    return RuntimeError(message)


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
        """取消 start 时等待装桥这一轮完成，再优雅 stop；超时才杀 CLI。"""
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
        env: Mapping[str, str] | None = None,
        on_stderr_line: Callable[[str], None] | None = None,
    ) -> Any:
        extra: dict[str, Any] = {}
        if env is not None:
            extra["env"] = env
        if on_stderr_line is not None:
            extra["on_stderr_line"] = on_stderr_line
        try:
            output = await self._runner(
                self._args(command, *command_args, include_root=include_root),
                timeout,
                timeout_handler,
                breakaway,
                **extra,
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

    async def _resolution_args(self, resolution: int | None) -> list[str]:
        if resolution is None:
            return []
        help_data = await self._call("help", "create", include_root=False)
        commands = help_data.get("commands", []) if isinstance(help_data, dict) else []
        if any(
            str(option.get("flag", "")).split(" ", 1)[0] == "--resolution"
            for command in commands
            for option in command.get("options", [])
        ):
            return ["--resolution", str(resolution)]
        if resolution == 720:
            return []  # Old packaged CLIs only support 720p.
        raise CLIError(
            "unsupported",
            "当前 ModAVD 命令行不支持 1080p 分辨率档位",
            "请更新 ModAVD 包内管理器后重试",
        )

    async def create(
        self,
        *,
        index: str | int | None = None,
        title: str | None = None,
        memory: int | str | None = None,
        cpu: int | None = None,
        data_gb: int | None = None,
        fps: int | None = None,
        resolution: int | None = None,
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
        args.extend(await self._resolution_args(resolution))
        create_timeout = CREATE_TIMEOUT_SECONDS
        legacy_args = list(args)
        args.extend(("--timeout", str(create_timeout)))
        process_timeout = create_timeout + CREATE_PROCESS_MARGIN_SECONDS
        # 新建前就在的实例不是这次建的：超时 / 取消收尾时只能关这次新建出来的那台。指定了编号也要记，
        # 那个编号上原来就有实例时 modavd 会拒绝新建，收尾不能把那台正在用的关掉
        listing = await self.list()
        raw_items = listing.get("instances", []) if isinstance(listing, dict) else []
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
                if index is not None and item != str(index):
                    continue
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
            # 这次新建出来的实例可能晚一点才列得出来（取消时文件还没建好，或某一次 list 失败）：
            # 每一轮都重新找，找到过的都记着；查不到只是这一轮没找到，不顶掉原来的取消 / 超时
            indices: list[str] = []

            async def discover() -> None:
                with suppress(CLIError):
                    for item in await find_targets():
                        if item not in indices:
                            indices.append(item)

            deadline = asyncio.get_running_loop().time() + _CREATE_CLEANUP_SECONDS
            while (
                process.returncode is None
                and asyncio.get_running_loop().time() < deadline
            ):
                await discover()
                if await bridge_running(process, indices):
                    await asyncio.sleep(_CANCEL_POLL_SECONDS)
                    continue
                await stop_targets(indices)
                await asyncio.sleep(_CANCEL_POLL_SECONDS)
            if process.returncode is None:
                process.kill()
                with suppress(Exception):
                    await process.wait()
            # CLI 退出或被结束以后再找一次：模拟器是脱离 CLI 起的，它最后那几步可能刚把实例开起来
            await discover()
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
        resolution: int | None = None,
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
        args.extend(await self._resolution_args(resolution))
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
        if resolution_for(read_ini(config_path(self.root, index))) == 1080:
            # Old CLIs rewrite 1080p to 720p on start. Refuse before they can write.
            await self._resolution_args(1080)
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

    async def update_caller_options(self) -> bool:
        """这个命令行的 ``update`` 收不收 ``--source`` / ``--cdk-dpapi``（看 ``help update`` 的
        ``options``，按 exe 缓存）。已发布的 v0.6.0 及更早没有。"""
        try:
            key, size, mtime_ns = _exe_cache_key(self.exe)
        except OSError:
            key, size, mtime_ns = "", -1, -1
        cached = _UPDATE_OPTIONS_CACHE.get(key) if key else None
        if cached is not None and cached[:2] == (size, mtime_ns):
            return cached[2]
        try:
            help_data = await self._call("help", "update", include_root=False)
        except CLIError as error:
            # 查不出就按旧命令行处理（不缓存，下次再问）：不带这两个选项，更新照样能做
            logger.warning(
                f"modavd help update 失败，这次不传更新源和 CDK: {error.message}"
            )
            return False
        commands = help_data.get("commands", []) if isinstance(help_data, dict) else []
        supported = any(
            str(option.get("flag", "")).split(" ", 1)[0] == "--source"
            for command in commands
            if isinstance(command, dict)
            for option in command.get("options", []) or []
            if isinstance(option, dict)
        )
        if key:
            _UPDATE_OPTIONS_CACHE[key] = (size, mtime_ns, supported)
        return supported

    async def update(
        self,
        action: str = "status",
        *,
        automas_version: str | None = None,
        source: str | None = None,
        cdk_dpapi: str | None = None,
        env: Mapping[str, str] | None = None,
        on_progress: Callable[[UpdateProgressEvent], None] | None = None,
    ) -> Any:
        """``modavd update <action>``，返回 ``update.Status``。

        - ``automas_version``：调用方 AUTO-MAS 的版本（新版要求更高的 AUTO-MAS 时 modavd 不装），只给
          ``check`` / ``prepare`` / ``install`` 传。
        - ``source`` / ``cdk_dpapi``：这一次的更新源（github / mirrorchyan）和 Mirror 酱 CDK（DPAPI 密文的
          base64，空串表示这次不用 CDK）。有这两个选项的命令行（Windows）上每次两个一起传，没有就都不传
          （modavd 用自己存的设置）；``recover`` 不收。``cdk_dpapi`` 的值不进日志和错误。
        - ``env``：子进程的整份环境（MAS 的代理）；``on_progress``：stderr 上带 ``progress`` 的日志行。
        """
        args = [action]
        if automas_version and action in {"check", "prepare", "install"}:
            args.extend(("--automas-version", automas_version))
        if (
            action != "recover"
            and (source is not None or cdk_dpapi is not None)
            and CALLER_UPDATE_OPTIONS_PLATFORM
            and await self.update_caller_options()
        ):
            args.extend(("--source", source or "github"))
            args.extend(("--cdk-dpapi", cdk_dpapi or ""))
        on_line = (
            None if on_progress is None else partial(_forward_progress, on_progress)
        )
        quick = action in {"status", "check", "recover"}
        return await self._call(
            "update",
            *args,
            timeout=UPDATE_QUICK_TIMEOUT_SECONDS
            if quick
            else UPDATE_LONG_TIMEOUT_SECONDS,
            env=env,
            on_stderr_line=on_line,
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
    "SUPPORTED_PROTOCOLS",
    "UPDATE_LONG_TIMEOUT_SECONDS",
    "UPDATE_QUICK_TIMEOUT_SECONDS",
    "UpdateProgressEvent",
    "map_cli_error",
    "parse_update_progress",
    "start_process_timeout",
]
