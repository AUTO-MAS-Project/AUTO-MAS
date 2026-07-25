#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ok-script 控制台壳的配置存储与进程运行器。"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from ..common.events import append_ok_script_run_event
from .descriptor import (
    PROTOCOL_FRAMEWORK_CLI,
    PROTOCOL_LEGACY_EXE,
    PROTOCOL_MAIN_SCRIPT,
    OkProjectDescriptor,
)

AUTO_PROTOCOL = "auto"
SUPPORTED_PROTOCOLS = (
    PROTOCOL_FRAMEWORK_CLI,
    PROTOCOL_MAIN_SCRIPT,
    PROTOCOL_LEGACY_EXE,
)


class OkShellRuntimeError(RuntimeError):
    """控制台壳无法安全完成操作。"""


@dataclass(frozen=True, slots=True)
class OkRunResult:
    """一次脚本子进程运行结果。"""

    protocol: str
    command: tuple[str, ...]
    return_code: int
    timed_out: bool
    duration: float


@dataclass(frozen=True, slots=True)
class OkShellLaunchSpec:
    """控制台壳与 MAS 调度共用的项目启动规格。"""

    protocol: str
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]


class OkConfigStore:
    """只允许访问项目 Manifest 指定配置目录中的 JSON 文件。"""

    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = Path(config_dir).resolve()

    def list(self) -> tuple[str, ...]:
        """列出配置目录内的 JSON 相对路径。"""

        if not self.config_dir.is_dir():
            return ()
        return tuple(
            path.relative_to(self.config_dir).as_posix()
            for path in sorted(self.config_dir.rglob("*.json"))
            if path.is_file()
        )

    def read(self, name: str) -> dict[str, Any]:
        """读取一个 JSON 对象配置。"""

        path = self._resolve(name)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError as exc:
            raise OkShellRuntimeError(f"配置文件不存在: {name}") from exc
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OkShellRuntimeError(f"配置读取失败 {name}: {exc}") from exc
        if not isinstance(data, dict):
            raise OkShellRuntimeError(f"配置顶层必须是对象: {name}")
        return data

    def write(
        self,
        name: str,
        data: dict[str, Any],
        *,
        merge: bool = True,
    ) -> Path:
        """原子写入配置，默认递归合并已有 JSON 对象。"""

        if not isinstance(data, dict):
            raise OkShellRuntimeError("待写入配置的顶层必须是对象")
        path = self._resolve(name)
        payload = data
        if merge and path.is_file():
            payload = _merge_dict(self.read(name), data)

        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                json.dump(payload, temp_file, ensure_ascii=False, indent=2)
                temp_file.write("\n")
                temp_path = Path(temp_file.name)
            temp_path.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise OkShellRuntimeError(f"配置写入失败 {name}: {exc}") from exc
        return path

    def copy_missing_from(self, source_dir: str | Path) -> tuple[str, ...]:
        """从脚本默认目录补齐缺失 JSON，不覆盖用户已有配置。"""

        source = Path(source_dir).resolve()
        if not source.is_dir():
            return ()

        copied: list[str] = []
        for source_path in sorted(path for path in source.rglob("*.json") if path.is_file()):
            relative_name = source_path.relative_to(source).as_posix()
            target_path = self._resolve(relative_name)
            if target_path.exists():
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=target_path.parent,
                    prefix=f".{target_path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temp_file:
                    temp_path = Path(temp_file.name)
                    with source_path.open("rb") as source_file:
                        shutil.copyfileobj(source_file, temp_file)
                temp_path.replace(target_path)
            except OSError as exc:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
                raise OkShellRuntimeError(
                    f"配置补齐失败 {relative_name}: {exc}"
                ) from exc
            copied.append(relative_name)
        return tuple(copied)

    def validate_name(self, name: str) -> str:
        """Validate and normalize one JSON path without touching the file."""

        path = self._resolve(name)
        return path.relative_to(self.config_dir).as_posix()

    def _resolve(self, name: str) -> Path:
        if not isinstance(name, str):
            raise OkShellRuntimeError("配置文件名必须是字符串")
        normalized = name.strip().replace("\\", "/")
        if not normalized:
            raise OkShellRuntimeError("配置文件名不能为空")
        if any(part in ("", ".", "..") for part in normalized.split("/")):
            raise OkShellRuntimeError("配置路径不能包含空段、. 或 ..")
        relative = Path(normalized)
        if relative.is_absolute() or relative.suffix.casefold() != ".json":
            raise OkShellRuntimeError("配置路径必须是 configs 目录内的 .json 相对路径")
        path = (self.config_dir / relative).resolve()
        try:
            path.relative_to(self.config_dir)
        except ValueError as exc:
            raise OkShellRuntimeError("配置路径超出 configs 目录") from exc
        return path


def _merge_dict(
    original: dict[str, Any],
    updates: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(original)
    for key, value in updates.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dict(current, value)
        else:
            merged[key] = value
    return merged


class OkShellRunner:
    """按能力探测结果运行 ok-script 项目并转发所有文本输出。"""

    def __init__(
        self,
        manifest: OkProjectDescriptor,
        *,
        output: Callable[[str, str], None] | None = None,
        event_path: str | Path | None = None,
    ) -> None:
        self.manifest = manifest
        self.output = output or self._print_output
        self.event_path = Path(event_path).resolve() if event_path else None

    def available_protocols(self) -> tuple[str, ...]:
        """返回经过运行前探测后可用的协议。"""

        available: list[str] = []
        for protocol in SUPPORTED_PROTOCOLS:
            if protocol not in self.manifest.protocols:
                continue
            if protocol == PROTOCOL_FRAMEWORK_CLI:
                if self._supports_framework_cli():
                    available.append(protocol)
            elif protocol == PROTOCOL_MAIN_SCRIPT:
                if self._has_main_script():
                    available.append(protocol)
            elif self._has_executable():
                available.append(protocol)
        return tuple(available)

    def build_command(
        self,
        task: str,
        *,
        protocol: str = AUTO_PROTOCOL,
        exit_after: bool = True,
        available_protocols: tuple[str, ...] | None = None,
    ) -> tuple[str, tuple[str, ...]]:
        """选择协议并构建命令，不启动任务进程。"""

        task = task.strip()
        if not task:
            raise OkShellRuntimeError("任务名或任务序号不能为空")

        available = self._resolve_available_protocols(available_protocols)
        if protocol == AUTO_PROTOCOL:
            if not available:
                raise OkShellRuntimeError(
                    "没有可用运行协议；请检查项目 Python、main.py 或 EXE"
                )
            selected = available[0]
        else:
            if protocol not in SUPPORTED_PROTOCOLS:
                raise OkShellRuntimeError(f"不支持的运行协议: {protocol}")
            if protocol not in available:
                raise OkShellRuntimeError(f"运行协议不可用: {protocol}")
            selected = protocol

        selector = self._selector_for(task, selected)
        if selected == PROTOCOL_FRAMEWORK_CLI:
            python = self._python()
            command = [
                str(python),
                "-m",
                "ok.cli",
                "run_task",
                selector,
                "-c",
                self.manifest.config_target,
            ]
        elif selected == PROTOCOL_MAIN_SCRIPT:
            command = [
                str(self._python()),
                str(self.manifest.main_script),
                "-t",
                selector,
            ]
        else:
            command = [str(self.manifest.executable), "-t", selector]
        if exit_after:
            command.append("-e")
        return selected, tuple(command)

    def build_launch_spec(
        self,
        task: str,
        *,
        protocol: str = AUTO_PROTOCOL,
        exit_after: bool = True,
        available_protocols: tuple[str, ...] | None = None,
    ) -> OkShellLaunchSpec:
        """构建可由控制台或 MAS 调度器复用的安全启动规格。"""

        selected, command = self.build_command(
            task,
            protocol=protocol,
            exit_after=exit_after,
            available_protocols=available_protocols,
        )
        return OkShellLaunchSpec(
            protocol=selected,
            command=command,
            cwd=self.command_cwd(selected),
            environment=self.build_environment(),
        )

    def command_cwd(self, protocol: str) -> Path:
        """返回协议对应的项目工作目录。"""

        if protocol == PROTOCOL_FRAMEWORK_CLI:
            return self.manifest.working_dir
        return self.manifest.root_path

    def run(
        self,
        task: str,
        *,
        protocol: str = AUTO_PROTOCOL,
        exit_after: bool = True,
        timeout: float | None = None,
    ) -> OkRunResult:
        """供独立 CLI 壳运行任务；MAS 生产调度使用 RunController。"""

        if timeout is not None and timeout <= 0:
            raise OkShellRuntimeError("运行超时必须大于 0")
        launch_spec = self.build_launch_spec(
            task,
            protocol=protocol,
            exit_after=exit_after,
        )
        started_at = time.monotonic()
        self.emit_event(
            "run_started",
            task=task,
            message="控制台壳已启动项目进程",
            protocol=launch_spec.protocol,
            command=list(launch_spec.command),
        )
        log_offset = self._initial_log_offset()

        try:
            process = subprocess.Popen(
                launch_spec.command,
                cwd=launch_spec.cwd,
                env=launch_spec.environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            self.emit_event(
                "run_failed",
                task=task,
                message=f"脚本进程启动失败: {exc}",
                success=False,
            )
            raise OkShellRuntimeError(f"脚本进程启动失败: {exc}") from exc

        messages: queue.Queue[tuple[str, str | None]] = queue.Queue()
        threads = (
            self._start_reader(process.stdout, "stdout", messages),
            self._start_reader(process.stderr, "stderr", messages),
        )
        timed_out = False
        open_streams = len(threads)
        try:
            while process.poll() is None or open_streams:
                open_streams = self._drain_messages(messages, open_streams)
                log_offset = self._read_log(log_offset)
                if timeout is not None and time.monotonic() - started_at >= timeout:
                    timed_out = True
                    self._stop_process(process)
                if process.poll() is None or open_streams:
                    time.sleep(0.05)
        except KeyboardInterrupt:
            self._stop_process(process)
            self.emit_event(
                "run_failed",
                task=task,
                message="任务已取消",
                success=False,
            )
            raise
        finally:
            for thread in threads:
                thread.join(timeout=1)
            self._drain_messages(messages, open_streams)
            self._read_log(log_offset)
            if process.poll() is None:
                self._stop_process(process)

        return_code = process.returncode if process.returncode is not None else 1
        duration = time.monotonic() - started_at
        self.emit_event(
            "process_exited" if return_code == 0 and not timed_out else "run_failed",
            task=task,
            message=(
                "脚本进程已退出，等待项目成功日志或结构化完成事件"
                if return_code == 0 and not timed_out
                else f"脚本进程异常退出，退出码 {return_code}"
            ),
            success=False if return_code != 0 or timed_out else None,
            returnCode=return_code,
            timedOut=timed_out,
            duration=duration,
        )
        return OkRunResult(
            protocol=launch_spec.protocol,
            command=launch_spec.command,
            return_code=return_code,
            timed_out=timed_out,
            duration=duration,
        )

    def _resolve_available_protocols(
        self,
        available_protocols: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        """使用调用方探测结果，或为独立 CLI 执行动态探测。"""

        if available_protocols is None:
            return self.available_protocols()

        resolved: list[str] = []
        for protocol in available_protocols:
            if protocol not in SUPPORTED_PROTOCOLS:
                raise OkShellRuntimeError(f"不支持的运行协议: {protocol}")
            if protocol not in self.manifest.protocols:
                raise OkShellRuntimeError(
                    f"项目 descriptor 未声明运行协议: {protocol}"
                )
            if protocol == PROTOCOL_FRAMEWORK_CLI:
                available = (
                    self.manifest.python_executable is not None
                    and self.manifest.python_executable.is_file()
                )
            elif protocol == PROTOCOL_MAIN_SCRIPT:
                available = self._has_main_script()
            else:
                available = self._has_executable()
            if not available:
                raise OkShellRuntimeError(f"运行协议不可用: {protocol}")
            if protocol not in resolved:
                resolved.append(protocol)
        return tuple(resolved)

    def _supports_framework_cli(self) -> bool:
        try:
            result = subprocess.run(
                [str(self._python()), "-m", "ok.cli", "--help"],
                cwd=self.command_cwd(PROTOCOL_FRAMEWORK_CLI),
                env=self.build_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        output = f"{result.stdout}\n{result.stderr}"
        return result.returncode == 0 and "run_task" in output

    def build_environment(self) -> dict[str, str]:
        """构建外部项目进程环境，保证 MAS 与 CLI 使用同一编码规则。"""

        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        # 外部项目不得继承 MAS 开发环境的模块搜索路径，否则可能误探测到
        # 另一个项目安装的 ok.cli 并选择错误协议。
        environment["PYTHONPATH"] = str(self.manifest.root_path)
        return environment

    def _build_environment(self) -> dict[str, str]:
        """兼容旧调用方，新的运行链请使用 :meth:`build_environment`。"""

        return self.build_environment()

    def _has_main_script(self) -> bool:
        return (
            self.manifest.main_script is not None
            and self.manifest.main_script.is_file()
            and self.manifest.python_executable is not None
            and self.manifest.python_executable.is_file()
        )

    def _has_executable(self) -> bool:
        return (
            self.manifest.executable is not None
            and self.manifest.executable.is_file()
        )

    def _python(self) -> Path:
        python = self.manifest.python_executable
        if python is None or not python.is_file():
            raise OkShellRuntimeError("项目 Python 解释器不存在")
        return python

    def _selector_for(self, task: str, protocol: str) -> str:
        for item in self.manifest.tasks:
            if task in {item.selector, item.class_name, item.label, str(item.index)}:
                if protocol == PROTOCOL_FRAMEWORK_CLI:
                    return item.selector
                return str(item.index)
        return task

    @staticmethod
    def _start_reader(
        stream: IO[str] | None,
        source: str,
        messages: queue.Queue[tuple[str, str | None]],
    ) -> threading.Thread:
        def read_stream() -> None:
            if stream is not None:
                try:
                    for line in stream:
                        messages.put((source, line.rstrip("\r\n")))
                finally:
                    stream.close()
            messages.put((source, None))

        thread = threading.Thread(target=read_stream, daemon=True)
        thread.start()
        return thread

    def _drain_messages(
        self,
        messages: queue.Queue[tuple[str, str | None]],
        open_streams: int,
    ) -> int:
        while True:
            try:
                source, line = messages.get_nowait()
            except queue.Empty:
                return open_streams
            if line is None:
                open_streams -= 1
                continue
            self.output(source, line)
            self.emit_event("step", message=line, source=source)

    def _initial_log_offset(self) -> int:
        try:
            return self.manifest.log_path.stat().st_size
        except OSError:
            return 0

    def _read_log(self, offset: int) -> int:
        path = self.manifest.log_path
        try:
            size = path.stat().st_size
            if size < offset:
                offset = 0
            with path.open("r", encoding="utf-8", errors="replace") as log_file:
                log_file.seek(offset)
                for line in log_file:
                    text = line.rstrip("\r\n")
                    self.output("log", text)
                    self.emit_event("step", message=text, source="log")
                return log_file.tell()
        except OSError:
            return offset

    @staticmethod
    def _stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def emit_event(self, event: str, **payload: object) -> None:
        """写入 MAS 兼容的结构化运行事件。"""

        if self.event_path is None:
            return
        try:
            append_ok_script_run_event(self.event_path, event, **payload)
        except OSError as exc:
            raise OkShellRuntimeError(f"事件日志写入失败: {exc}") from exc

    @staticmethod
    def _print_output(source: str, message: str) -> None:
        target = sys.stderr if source == "stderr" else sys.stdout
        print(f"[{source}] {message}", file=target, flush=True)
