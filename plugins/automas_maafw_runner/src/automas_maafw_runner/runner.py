#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.


import ast
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable, Literal, TextIO

import maa as maa_package
from maa.agent_client import AgentClient
from maa.controller import (
    AdbController,
    Controller,
    ControllerEventSink,
    MaaAdbInputMethodEnum,
    MaaAdbScreencapMethodEnum,
    MaaWin32InputMethodEnum,
    MaaWin32ScreencapMethodEnum,
    Win32Controller,
)
from maa.event_sink import NotificationType
from maa.job import Job, JobWithResult
from maa.library import Library
from maa.resource import Resource, ResourceEventSink
from maa.tasker import Tasker, TaskerEventSink
from maa.toolkit import Toolkit
from pydantic import BaseModel, Field

try:
    from .run_plan import (
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
        MaaFWTaskRunPlan,
        build_maafw_agent_command_plans,
    )
except ImportError:
    from run_plan import (  # type: ignore[no-redef]
        MaaFWResourceBundlePlan,
        MaaFWRunPlan,
        MaaFWTaskRunPlan,
        build_maafw_agent_command_plans,
    )

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
ENCODINGS = ("utf-8", "gbk", "shift_jis", "utf-16")
MAAFW_DEBUG_LOG_PATH = Path("debug") / "maafw.log"
TASK_CONFIG_LOG_VALUE_LIMIT = 1200

_MAAFW_INITIALIZED = False
_MAAFW_INIT_LOCK = threading.Lock()


MaaFWControllerType = Literal["Adb", "Win32"]
AGENT_CONNECT_RETRY_COUNT = 30
AGENT_CONNECT_RETRY_INTERVAL = 0.2
AGENT_CONNECT_TIMEOUT_MS = 1000
ADB_READY_RETRY_COUNT = 30
ADB_READY_RETRY_INTERVAL = 1.0
ADB_COMMAND_TIMEOUT = 5
AGENT_PROJECT_RUNTIME_DIRS = ("debug", "logs", "temp")
AGENT_ENV_PATH_DIRS = (
    (),
    ("maafw",),
    ("runtimes", "win-x64"),
    ("libs",),
    ("deps",),
)
# Agent 自举所需的最小依赖包（pip 发行名）
AGENT_BOOTSTRAP_PACKAGE = "json-with-comments"
# pip 健康检测超时（秒）
PIP_HEALTH_CHECK_TIMEOUT = 15
# pip 安装/修复超时（秒）
PIP_INSTALL_TIMEOUT = 120
AGENT_ENV_MANIFEST_NAME = ".auto_mas_agent_env.json"
AGENT_COMPAT_SHIM_DIR_NAME = ".auto_mas_shims"
EMBEDDED_AGENT_SERVER_SINK_DECORATORS = {
    "resource_sink",
    "controller_sink",
    "tasker_sink",
    "context_sink",
}
MAAFW_FAILURE_EVENT_MESSAGES = {
    "Node.NextList.Failed",
    "Node.PipelineNode.Failed",
    "Node.Action.Failed",
    "Tasker.Task.Failed",
}
MAAFW_FAILURE_SUMMARY_LIMIT = 8


def _project_maafw_runtime_path(project_path: Path | None) -> Path | None:
    if project_path is None:
        return None

    for candidate in (
        project_path / "maafw",
        project_path / "runtimes" / "win-x64",
    ):
        if (candidate / "MaaFramework.dll").is_file():
            return candidate
    return None


def decode_bytes(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


def _should_adb_connect(address: str, attempt: int) -> bool:
    return _is_network_adb_address(address) and (
        attempt == 0 or (attempt + 1) % 5 == 0
    )


def _is_network_adb_address(address: str) -> bool:
    host, separator, port = address.rpartition(":")
    return bool(separator and host and port.isdigit())


def _subprocess_detail(result: subprocess.CompletedProcess[str]) -> str:
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if stdout and stderr:
        return f"{stdout}; {stderr}"
    return stderr or stdout or f"exit={result.returncode}"


def _is_adb_connect_success(detail: str) -> bool:
    normalized = detail.lower()
    if not normalized:
        return False
    failed_markers = ("failed", "unable", "cannot", "refused", "timed out")
    return (
        ("connected to" in normalized or "already connected" in normalized)
        and not any(marker in normalized for marker in failed_markers)
    )


def _format_enum_methods(enum_cls: Any, value: int) -> str:
    raw_value = int(value)
    members = getattr(enum_cls, "__members__", {})
    for name, member in members.items():
        if int(member) == raw_value:
            return f"{name}({raw_value})"

    names: list[str] = []
    remaining = raw_value
    for name, member in members.items():
        member_value = int(member)
        if member_value == 0:
            continue
        if raw_value & member_value == member_value:
            names.append(name)
            remaining &= ~member_value

    if names and remaining == 0:
        return f"{'|'.join(names)}({raw_value})"
    if names:
        return f"{'|'.join(names)}+{remaining}({raw_value})"
    return str(raw_value)


def _format_latency(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms"


def _ensure_maafw_client_library_mode(runtime_path: Path | None = None) -> None:
    """Keep MaaFW loaded as a client library inside AUTO-MAS."""

    if runtime_path is not None:
        Library.open(runtime_path, agent_server=False)

    if Library.is_agent_server():
        maa_bin_path = Path(maa_package.__file__).resolve().parent / "bin"
        Library.open(maa_bin_path, agent_server=False)
        if Library.is_agent_server():
            # Library.open() is a no-op after MaaVersion argtypes are initialized.
            Library._is_agent_server = False  # type: ignore[attr-defined]

    # Lock Library.open() into client mode before any accidental maa.agent import.
    Library.version()
    if Library.is_agent_server():
        raise RuntimeError("MaaFW Library is still in AgentServer mode")


@dataclass(frozen=True)
class _EmbeddedAgentScanItem:
    module_name: str
    class_name: str | None = None
    sink_kind: str | None = None


def _load_project_agent_requirements(project_path: Path) -> list[str]:
    """读取 MaaFW 项目自己的 agent 依赖声明，避免串用 AUTO-MAS 依赖版本。"""

    requirements_path = project_path / "requirements.txt"
    packages: list[str] = []
    try:
        with requirements_path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                packages.append(line)
    except FileNotFoundError:
        pass
    except Exception:
        pass

    normalized = {item.split(";", 1)[0].strip().lower() for item in packages}
    if not any(item.startswith(AGENT_BOOTSTRAP_PACKAGE) for item in normalized):
        packages.append(AGENT_BOOTSTRAP_PACKAGE)
    return packages


def _project_agent_requirements_hash(project_path: Path) -> str:
    packages = _load_project_agent_requirements(project_path)
    payload = json.dumps(packages, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _project_interface_hash(project_path: Path) -> str:
    for name in ("interface.json", "interface.jsonc"):
        path = project_path / name
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _build_agent_env_manifest(project_path: Path) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "projectPath": str(project_path.resolve()),
        "interfaceHash": _project_interface_hash(project_path),
        "requirementsHash": _project_agent_requirements_hash(project_path),
        "requirements": _load_project_agent_requirements(project_path),
    }


def _venv_python_path(venv_path: Path) -> Path:
    if os.name == "nt":
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def _is_valid_venv_path(venv_path: Path) -> bool:
    return _venv_python_path(venv_path).is_file() and (venv_path / "pyvenv.cfg").is_file()


def _venv_bootstrap_python() -> str:
    portable_python = Path.cwd() / "environment" / "python" / "python.exe"
    if portable_python.is_file():
        return str(portable_python)
    return sys.executable


def _agent_compat_shim_dir(venv_path: Path) -> Path:
    return venv_path / AGENT_COMPAT_SHIM_DIR_NAME


def _write_agent_compat_shims(venv_path: Path) -> Path:
    shim_dir = _agent_compat_shim_dir(venv_path)
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(
        "\n".join(
            [
                "def _patch_legacy_maafw_resource():",
                "    try:",
                "        import maa.resource as maa_resource_module",
                "        if hasattr(maa_resource_module, 'resource'):",
                "            return",
                "        from maa.agent.agent_server import AgentServer",
                "        maa_resource_module.resource = AgentServer",
                "    except Exception:",
                "        pass",
                "",
                "_patch_legacy_maafw_resource()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return shim_dir


def _ensure_maafw_global_init(project_path: Path | None = None) -> None:
    global _MAAFW_INITIALIZED
    if _MAAFW_INITIALIZED:
        return
    with _MAAFW_INIT_LOCK:
        if _MAAFW_INITIALIZED:
            return
        _ensure_maafw_client_library_mode(_project_maafw_runtime_path(project_path))
        user_path = (project_path or Path.cwd()).resolve()
        option_path = user_path / "config" / "maa_option.json"
        option_path.parent.mkdir(parents=True, exist_ok=True)
        option_path.write_text(
            json.dumps(
                {
                    "logging": True,
                    "save_draw": False,
                    "stdout_level": 2,
                    "save_on_error": False,
                    "draw_quality": 85,
                },
                ensure_ascii=False,
                indent=4,
            ),
            encoding="utf-8",
        )
        Toolkit.init_option(str(user_path))
        _MAAFW_INITIALIZED = True


class MaaFWDeviceConfig(BaseModel):
    type: MaaFWControllerType
    adbPath: str | None = None
    address: str | None = None
    hWnd: int | None = None
    screencapMethods: int = MaaAdbScreencapMethodEnum.Default
    inputMethods: int = MaaAdbInputMethodEnum.Default
    screencapMethod: int = MaaWin32ScreencapMethodEnum.DXGI_DesktopDup
    mouseMethod: int = MaaWin32InputMethodEnum.Seize
    keyboardMethod: int = MaaWin32InputMethodEnum.Seize
    config: dict[str, Any] = Field(default_factory=dict)


class MaaFWRunResult(BaseModel):
    success: bool
    projectName: str
    controllerName: str
    resourceName: str
    completedTasks: list[str] = Field(default_factory=list)
    failedTask: str | None = None
    errorMessage: str | None = None


class MaaFWRunner:
    def __init__(
        self,
        plan: MaaFWRunPlan,
        *,
        send_log: Callable[[str], None] | None = None,
    ) -> None:
        self.plan: MaaFWRunPlan = plan
        self.resource: Resource | None = None
        self.tasker: Tasker | None = None
        self.controller: Any | None = None
        self.agent_clients: list[AgentClient] = []
        self.agent_processes: list[subprocess.Popen] = []
        self.agent_output_threads: list[threading.Thread] = []
        self.event_sinks: list[Any] = []
        self.embedded_agent_sys_paths: list[str] = []
        self.send_log: Callable[[str], None] = send_log or (lambda _: None)
        self._initialized: bool = False
        self._python_env_checked: dict[str, bool] = {}
        self._stop_requested: threading.Event = threading.Event()
        self._task_failure_summaries: list[str] = []
        self._failed_task_errors: list[tuple[str, str]] = []

    def _ensure_initialized(self, device_config: MaaFWDeviceConfig) -> None:
        if self._initialized:
            return

        _ensure_maafw_global_init(Path(self.plan.path))
        self.resource = Resource()
        self.tasker = Tasker()
        self._install_resource_sink()
        self._load_resources()
        self._connect_device(device_config)
        self._start_agents()
        self._initialized = True

    def run(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        self._stop_requested.clear()
        try:
            self._ensure_initialized(device_config)
            completed_tasks = self._run_tasks()
            if self._failed_task_errors:
                first_failed_task, _ = self._failed_task_errors[0]
                error_message = "；".join(
                    f"{task_name}: {message}"
                    for task_name, message in self._failed_task_errors[:3]
                )
                if len(self._failed_task_errors) > 3:
                    error_message += f"；另有 {len(self._failed_task_errors) - 3} 个任务失败"
                return MaaFWRunResult(
                    success=False,
                    projectName=self.plan.projectName,
                    controllerName=self.plan.controllerName,
                    resourceName=self.plan.resourceName,
                    completedTasks=completed_tasks,
                    failedTask=first_failed_task,
                    errorMessage=error_message,
                )
            return MaaFWRunResult(
                success=True,
                projectName=self.plan.projectName,
                controllerName=self.plan.controllerName,
                resourceName=self.plan.resourceName,
                completedTasks=completed_tasks,
            )
        except Exception as exc:
            failed_task = self.plan.tasks[len(self._completed_task_names())].name if (
                len(self._completed_task_names()) < len(self.plan.tasks)
            ) else None
            self.send_log(f"MaaFW 任务执行失败: {exc}")
            return MaaFWRunResult(
                success=False,
                projectName=self.plan.projectName,
                controllerName=self.plan.controllerName,
                resourceName=self.plan.resourceName,
                completedTasks=self._completed_task_names(),
                failedTask=failed_task,
                errorMessage=str(exc),
            )

    def cleanup(self) -> None:
        self._stop_requested.set()
        if self.tasker is not None:
            try:
                _ensure_maafw_client_library_mode()
                if self.tasker.running:
                    self.tasker.post_stop().wait()
            except Exception as exc:
                self.send_log(f"停止 MaaFW tasker 失败: {exc}")

    def reset_for_retry(self) -> None:
        self._stop_requested.set()
        if self.tasker is not None:
            try:
                _ensure_maafw_client_library_mode()
                if self.tasker.running:
                    self.tasker.post_stop().wait()
            except Exception as exc:
                self.send_log(f"停止 MaaFW tasker 准备重试失败: {exc}")

    def shutdown(self) -> None:
        self._stop_requested.set()
        try:
            _ensure_maafw_client_library_mode()
            self.cleanup()
        finally:
            for agent_client in self.agent_clients:
                try:
                    agent_client.disconnect()
                except Exception as exc:
                    self.send_log(f"断开 AgentClient 失败: {exc}")

            for process in self.agent_processes:
                try:
                    if process.poll() is not None:
                        continue
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except Exception as exc:
                        self.send_log(f"强制结束 agent 进程失败: {exc}")
                except Exception as exc:
                    self.send_log(f"结束 agent 进程失败: {exc}")

            for process in self.agent_processes:
                stdout = process.stdout
                if stdout is None:
                    continue
                try:
                    stdout.close()
                except Exception:
                    pass

            for thread in self.agent_output_threads:
                try:
                    thread.join(timeout=0.5)
                except RuntimeError:
                    pass

            self.agent_clients.clear()
            self.agent_processes.clear()
            self.agent_output_threads.clear()
            self.event_sinks.clear()
            self.controller = None
            self.resource = None
            self.tasker = None
            self._initialized = False

    def _load_resources(self) -> None:
        for path_info in [*self.plan.resource.paths, *self.plan.resource.attachedPaths]:
            if not path_info.exists or not path_info.isDir:
                raise RuntimeError(f"资源目录不存在: {path_info.resolved}")
            self._wait_job(self.resource.post_bundle(path_info.resolved))
            self.send_log(f"已加载资源: {path_info.resolved}")

    def _connect_device(self, device_config: MaaFWDeviceConfig) -> None:
        if device_config.type != self.plan.controllerType:
            raise RuntimeError(
                f"设备类型 {device_config.type} 与 controller {self.plan.controllerType} 不一致"
            )

        if device_config.type == "Adb":
            self._resolve_adb_device(device_config)
            self._wait_adb_device_ready(device_config)

        self._log_controller_config(device_config)
        self.controller = self._create_controller(device_config)
        self._install_controller_sink(self.controller)
        self._wait_job(self.controller.post_connection())
        if not self.tasker.bind(self.resource, self.controller):
            raise RuntimeError("无法绑定 MaaFW resource/controller/tasker")
        self._install_tasker_sink()
        self.send_log(f"已连接 controller: {self.plan.controllerName}")

    def _resolve_adb_device(self, device_config: MaaFWDeviceConfig) -> None:
        """Fill a missing ADB path through the active MaaFW Toolkit."""

        if device_config.adbPath:
            return
        if not device_config.address:
            raise RuntimeError("ADB controller 需要设备地址")

        devices = Toolkit.find_adb_devices()
        device = next(
            (
                item
                for item in devices
                if str(getattr(item, "address", "")) == device_config.address
            ),
            None,
        )
        if device is None:
            addresses = [
                str(getattr(item, "address", ""))
                for item in devices
                if str(getattr(item, "address", ""))
            ]
            detail = f"；Toolkit 已发现: {', '.join(addresses)}" if addresses else ""
            raise RuntimeError(
                f"无法按地址发现 ADB 设备: {device_config.address}{detail}"
            )

        adb_path = str(getattr(device, "adb_path", "") or "").strip()
        if not adb_path:
            raise RuntimeError(
                f"MaaFW Toolkit 未返回 ADB 路径: {device_config.address}"
            )
        device_config.adbPath = adb_path
        self.send_log(
            f"已通过 MaaFW Toolkit 发现 ADB: {device_config.address}; 路径={adb_path}"
        )

    def _create_controller(self, device_config: MaaFWDeviceConfig) -> Any:
        if device_config.type == "Adb":
            if not device_config.adbPath or not device_config.address:
                raise RuntimeError("ADB controller 需要 adbPath 和 address")
            # screencapMethods/inputMethods 为 0 (Null) 时回退到 MaaFW 默认值，
            # 确保含 EmulatorExtras 的默认截图/输入集合被启用。
            screencap_methods = device_config.screencapMethods or MaaAdbScreencapMethodEnum.Default
            input_methods = device_config.inputMethods or MaaAdbInputMethodEnum.Default
            return AdbController(
                device_config.adbPath,
                device_config.address,
                screencap_methods,
                input_methods,
                device_config.config,
            )

        if device_config.type == "Win32":
            if not device_config.hWnd:
                raise RuntimeError("Win32 controller 需要窗口句柄，请先扫描或填写 HWnd")
            # screencapMethod 为 0 (Null) 时回退到 DXGI_DesktopDup，避免控制器无法截图。
            screencap_method = device_config.screencapMethod or MaaWin32ScreencapMethodEnum.DXGI_DesktopDup
            mouse_method = device_config.mouseMethod or MaaWin32InputMethodEnum.Seize
            keyboard_method = device_config.keyboardMethod or MaaWin32InputMethodEnum.Seize
            return Win32Controller(
                device_config.hWnd,
                screencap_method,
                mouse_method,
                keyboard_method,
            )

        raise RuntimeError(
            "AUTO-MAS MaaFW Direct currently supports only Adb/Win32 "
            f"controllers; use the project UI for {device_config.type}"
        )

    def _log_controller_config(self, device_config: MaaFWDeviceConfig) -> None:
        if device_config.type == "Adb":
            self.send_log(
                "ADB controller 配置: "
                f"截图方式={_format_enum_methods(MaaAdbScreencapMethodEnum, device_config.screencapMethods)}; "
                f"触控方式={_format_enum_methods(MaaAdbInputMethodEnum, device_config.inputMethods)}; "
                f"地址={device_config.address}"
            )
            if device_config.config:
                self.send_log(
                    "ADB controller 扩展配置: "
                    f"{json.dumps(device_config.config, ensure_ascii=False)}"
                )
            return

        if device_config.type == "Win32":
            self.send_log(
                "Win32 controller 配置: "
                f"截图方式={_format_enum_methods(MaaWin32ScreencapMethodEnum, device_config.screencapMethod)}; "
                f"鼠标方式={_format_enum_methods(MaaWin32InputMethodEnum, device_config.mouseMethod)}; "
                f"键盘方式={_format_enum_methods(MaaWin32InputMethodEnum, device_config.keyboardMethod)}; "
                f"HWnd={device_config.hWnd}"
            )

    def _wait_adb_device_ready(self, device_config: MaaFWDeviceConfig) -> None:
        if not device_config.adbPath or not device_config.address:
            return

        last_detail = ""
        network_connect_logged = False
        for attempt in range(ADB_READY_RETRY_COUNT):
            connect_detail = ""
            if _should_adb_connect(device_config.address, attempt):
                connected, connect_detail = self._connect_adb_network_device(
                    device_config,
                )
                if connected and not network_connect_logged:
                    self.send_log(
                        f"ADB 网络设备已连接: {device_config.address}; "
                        f"{connect_detail}"
                    )
                    network_connect_logged = True

            try:
                result = subprocess.run(
                    [
                        device_config.adbPath,
                        "-s",
                        device_config.address,
                        "get-state",
                    ],
                    capture_output=True,
                    timeout=ADB_COMMAND_TIMEOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                state = (result.stdout or "").strip()
                detail = (result.stderr or state or "").strip()
                if result.returncode == 0 and state == "device":
                    self.send_log(
                        f"ADB 设备已就绪: {device_config.address}; "
                        f"延迟={self._measure_adb_latency(device_config)}"
                    )
                    return
                last_detail = detail or f"exit={result.returncode}"
            except subprocess.TimeoutExpired:
                last_detail = f"get-state 超时 ({ADB_COMMAND_TIMEOUT}s)"
            except Exception as exc:
                last_detail = str(exc)

            if connect_detail and not network_connect_logged:
                last_detail = (
                    f"{last_detail}; connect: {connect_detail}"
                    if last_detail
                    else f"connect: {connect_detail}"
                )

            should_log = (
                attempt == 0
                or attempt == ADB_READY_RETRY_COUNT - 1
                or (attempt + 1) % 5 == 0
            )
            if should_log:
                self.send_log(
                    f"ADB 设备未就绪，等待重试 "
                    f"({attempt + 1}/{ADB_READY_RETRY_COUNT}): "
                    f"{device_config.address}; {last_detail}"
                )
            time.sleep(ADB_READY_RETRY_INTERVAL)

        raise RuntimeError(
            f"ADB 设备未就绪: {device_config.address}; 最后状态: {last_detail}\n"
            f"请确认模拟器已完全启动，且 "
            f"`{device_config.adbPath} devices` 中该设备状态为 device，而不是 offline/unauthorized。"
        )

    def _measure_adb_latency(self, device_config: MaaFWDeviceConfig) -> str:
        if not device_config.adbPath or not device_config.address:
            return "unknown"

        try:
            started_at = time.perf_counter()
            result = subprocess.run(
                [
                    device_config.adbPath,
                    "-s",
                    device_config.address,
                    "shell",
                    "echo",
                    "auto_mas_ready",
                ],
                capture_output=True,
                timeout=ADB_COMMAND_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            elapsed = time.perf_counter() - started_at
        except subprocess.TimeoutExpired:
            return f"检测超时 ({ADB_COMMAND_TIMEOUT}s)"
        except Exception as exc:
            return str(exc)

        detail = _subprocess_detail(result)
        if result.returncode == 0 and "auto_mas_ready" in (result.stdout or ""):
            return _format_latency(elapsed)
        return f"检测失败: {detail}"

    def _connect_adb_network_device(
        self,
        device_config: MaaFWDeviceConfig,
    ) -> tuple[bool, str]:
        if not device_config.adbPath or not device_config.address:
            return False, ""

        try:
            result = subprocess.run(
                [
                    device_config.adbPath,
                    "connect",
                    device_config.address,
                ],
                capture_output=True,
                timeout=ADB_COMMAND_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return False, f"connect 超时 ({ADB_COMMAND_TIMEOUT}s)"
        except Exception as exc:
            return False, str(exc)

        detail = _subprocess_detail(result)
        return result.returncode == 0 and _is_adb_connect_success(detail), detail

    def _start_agents(self) -> None:
        self._load_embedded_agents()
        self.prepare_agent_python_envs()

        for agent_plan in self.plan.agents:
            if agent_plan.embedded:
                continue
            agent_client = self._create_agent_client(agent_plan.childExec)
            if not agent_client.bind(self.resource):
                raise RuntimeError("AgentClient 绑定资源失败")

            identifier = agent_client.identifier
            if not identifier:
                raise RuntimeError("AgentClient 未返回可用连接标识")
            command = [
                item if item != "<socket_id>" else identifier
                for item in agent_plan.command
            ]
            env = self._build_agent_env(agent_plan)
            creationflags = (
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            self.send_log(
                f"启动 Agent 子进程: {Path(command[0]).name} "
                f"(cwd={agent_plan.cwd})"
            )
            process = subprocess.Popen(
                command,
                cwd=agent_plan.cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.agent_clients.append(agent_client)
            self.agent_processes.append(process)
            self._start_agent_output_reader(process, Path(command[0]).name)
            try:
                self._connect_agent_client(
                    agent_client,
                    process,
                    Path(command[0]).name,
                )
            except Exception:
                with suppress(Exception):
                    process.terminate()
                raise

            if not agent_client.register_sink(
                self.resource,
                self.controller,
                self.tasker,
            ):
                raise RuntimeError("AgentClient 注册 sink 失败")

            self.send_log(f"Agent 已启动: {command[0]}")

    def prepare_agent_python_envs(self) -> None:
        """Prepare all MaaFW agent Python environments without starting agents."""

        if not self.plan.agents:
            self.send_log("[Python环境] 当前 MaaFW 项目没有声明 Agent")
            return

        process_agents = [agent for agent in self.plan.agents if not agent.embedded]
        if not process_agents:
            self.send_log("[Python环境] 所有 Agent 均为 embedded，跳过子进程 Python 环境准备")
            return

        self.send_log(f"[Python环境] 开始准备 {len(process_agents)} 个 Agent 环境")
        from automas_maafw_agent_env.env import prepare_agent_envs

        prepare_agent_envs(
            Path(self.plan.path),
            process_agents,
            send_log=self.send_log,
        )
        self.send_log("[Python环境] Agent 环境准备完成")

    def _load_embedded_agents(self) -> None:
        embedded_agents = [agent for agent in self.plan.agents if agent.embedded]
        if not embedded_agents:
            return
        raise RuntimeError(
            "embedded Agent must run as an isolated subprocess in AUTO-MAS; "
            "rebuild the MaaFW run plan before starting agents"
        )

    def _resolve_embedded_agent_paths(self, agent_plan: Any) -> tuple[Path, Path | None]:
        project_path = Path(self.plan.path)
        entry_path: Path | None = None
        for raw_arg in agent_plan.childArgs:
            raw_path = str(raw_arg)
            if not raw_path.lower().endswith(".py"):
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = project_path / candidate
            entry_path = candidate.resolve()
            break

        if entry_path is None:
            default_entry = project_path / "agent" / "main.py"
            entry_path = default_entry.resolve() if default_entry.is_file() else None

        if entry_path is not None and entry_path.is_file():
            return entry_path.parent, entry_path
        return project_path / "agent", entry_path

    def _load_embedded_agent_custom(self, agent_root: Path) -> bool:
        if not agent_root.is_dir():
            raise RuntimeError(f"Embedded Agent 目录不存在: {agent_root}")
        if self.resource is None or self.controller is None or self.tasker is None:
            raise RuntimeError("Embedded Agent 需要先初始化 resource/controller/tasker")

        scan_items = self._scan_embedded_agent_modules(agent_root)
        if not scan_items:
            self.send_log(f"[Embedded Agent] 未扫描到装饰器: {agent_root}")
            return False
        modules = sorted({item.module_name for item in scan_items})
        implicit_sinks = [
            item
            for item in scan_items
            if item.class_name is not None and item.sink_kind is not None
        ]

        self._purge_embedded_modules(agent_root)
        self._purge_module_name("agent")
        added_paths = self._add_embedded_sys_paths(agent_root)
        restore_patch = self._patch_embedded_agent_decorators()
        before_actions = set(self.resource.custom_action_list or [])
        before_recognitions = set(self.resource.custom_recognition_list or [])
        before_event_sinks = len(self.event_sinks)
        try:
            for module_name in modules:
                self._purge_module_name(module_name)
                self.send_log(f"[Embedded Agent] 导入模块: {module_name}")
                importlib.import_module(module_name)
            for item in implicit_sinks:
                self._register_embedded_implicit_sink(item)
        finally:
            restore_patch()
            self._remove_embedded_sys_paths(added_paths)

        actions = sorted(set(self.resource.custom_action_list or []) - before_actions)
        recognitions = sorted(
            set(self.resource.custom_recognition_list or []) - before_recognitions
        )
        sink_count = len(self.event_sinks) - before_event_sinks
        self.send_log(
            "[Embedded Agent] 注册完成: "
            f"actions={actions or []}, recognitions={recognitions or []}, sinks={sink_count}"
        )
        return bool(actions or recognitions or sink_count)

    def _scan_embedded_agent_modules(self, agent_root: Path) -> list[_EmbeddedAgentScanItem]:
        items: set[_EmbeddedAgentScanItem] = set()
        for file_path in sorted(agent_root.rglob("*.py")):
            if "__pycache__" in file_path.parts:
                continue
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            module_name = self._embedded_module_name(agent_root, file_path)
            if not module_name:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                has_sink_decorator = False
                for decorator in node.decorator_list:
                    decorator_kind = self._embedded_agent_decorator_kind(decorator)
                    if decorator_kind is None:
                        continue
                    items.add(_EmbeddedAgentScanItem(module_name=module_name))
                    has_sink_decorator = has_sink_decorator or decorator_kind.endswith(
                        "_sink"
                    )

                if has_sink_decorator:
                    continue

                implicit_sink_kind = self._implicit_embedded_sink_kind(node)
                if implicit_sink_kind is not None:
                    items.add(
                        _EmbeddedAgentScanItem(
                            module_name=module_name,
                            class_name=node.name,
                            sink_kind=implicit_sink_kind,
                        )
                    )

        return sorted(
            items,
            key=lambda item: (
                item.module_name,
                item.class_name or "",
                item.sink_kind or "",
            ),
        )

    @staticmethod
    def _embedded_agent_decorator_kind(decorator: ast.expr) -> str | None:
        if not isinstance(decorator, ast.Call):
            return None
        func = decorator.func
        if not isinstance(func, ast.Attribute):
            return None

        owner = func.value
        owner_name = owner.id if isinstance(owner, ast.Name) else ""
        if owner_name in {"resource", "Resource", "AgentServer"}:
            if func.attr == "custom_action":
                return "action"
            if func.attr == "custom_recognition":
                return "recognition"
        if owner_name == "AgentServer" and func.attr in EMBEDDED_AGENT_SERVER_SINK_DECORATORS:
            return func.attr
        return None

    @staticmethod
    def _implicit_embedded_sink_kind(node: ast.ClassDef) -> str | None:
        for base in node.bases:
            base_name = ""
            if isinstance(base, ast.Name):
                base_name = base.id
            elif isinstance(base, ast.Attribute):
                base_name = base.attr
            if base_name == "ResourceEventSink":
                return "resource_sink"
            if base_name == "ControllerEventSink":
                return "controller_sink"
            if base_name == "TaskerEventSink":
                return "tasker_sink"
            if base_name == "ContextEventSink":
                return "context_sink"
        return None

    @staticmethod
    def _embedded_module_name(agent_root: Path, file_path: Path) -> str | None:
        try:
            relative = file_path.relative_to(agent_root)
        except ValueError:
            return None
        parts = list(relative.with_suffix("").parts)
        if not parts:
            return None
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else None

    def _patch_embedded_agent_decorators(self) -> Callable[[], None]:
        _ensure_maafw_client_library_mode()
        import maa.resource as maa_resource_module
        from maa.agent.agent_server import AgentServer

        sentinel = object()
        old_resource = getattr(maa_resource_module, "resource", sentinel)
        old_custom_action = AgentServer.__dict__.get("custom_action", sentinel)
        old_custom_recognition = AgentServer.__dict__.get(
            "custom_recognition", sentinel
        )
        old_resource_sink = AgentServer.__dict__.get("resource_sink", sentinel)
        old_controller_sink = AgentServer.__dict__.get("controller_sink", sentinel)
        old_tasker_sink = AgentServer.__dict__.get("tasker_sink", sentinel)
        old_context_sink = AgentServer.__dict__.get("context_sink", sentinel)

        setattr(maa_resource_module, "resource", self.resource)
        AgentServer.custom_action = staticmethod(self.resource.custom_action)
        AgentServer.custom_recognition = staticmethod(
            self.resource.custom_recognition
        )
        AgentServer.resource_sink = staticmethod(
            self._embedded_resource_sink_decorator
        )
        AgentServer.controller_sink = staticmethod(
            self._embedded_controller_sink_decorator
        )
        AgentServer.tasker_sink = staticmethod(
            self._embedded_tasker_sink_decorator
        )
        AgentServer.context_sink = staticmethod(
            self._embedded_context_sink_decorator
        )

        def restore() -> None:
            if old_resource is sentinel:
                with suppress(AttributeError):
                    delattr(maa_resource_module, "resource")
            else:
                setattr(maa_resource_module, "resource", old_resource)
            for name, old_value in {
                "custom_action": old_custom_action,
                "custom_recognition": old_custom_recognition,
                "resource_sink": old_resource_sink,
                "controller_sink": old_controller_sink,
                "tasker_sink": old_tasker_sink,
                "context_sink": old_context_sink,
            }.items():
                if old_value is sentinel:
                    with suppress(AttributeError):
                        delattr(AgentServer, name)
                else:
                    setattr(AgentServer, name, old_value)

        return restore

    def _embedded_resource_sink_decorator(self) -> Callable[[type[Any]], type[Any]]:
        def wrapper(sink_class: type[Any]) -> type[Any]:
            sink = sink_class()
            if self.resource is not None:
                self.resource.add_sink(sink)
            self.event_sinks.append(sink)
            return sink_class

        return wrapper

    def _embedded_controller_sink_decorator(self) -> Callable[[type[Any]], type[Any]]:
        def wrapper(sink_class: type[Any]) -> type[Any]:
            sink = sink_class()
            if self.controller is not None:
                self.controller.add_sink(sink)
            self.event_sinks.append(sink)
            return sink_class

        return wrapper

    def _embedded_tasker_sink_decorator(self) -> Callable[[type[Any]], type[Any]]:
        def wrapper(sink_class: type[Any]) -> type[Any]:
            sink = sink_class()
            if self.tasker is not None:
                self.tasker.add_sink(sink)
            self.event_sinks.append(sink)
            return sink_class

        return wrapper

    def _embedded_context_sink_decorator(self) -> Callable[[type[Any]], type[Any]]:
        def wrapper(sink_class: type[Any]) -> type[Any]:
            sink = sink_class()
            if self.tasker is not None and hasattr(self.tasker, "add_context_sink"):
                self.tasker.add_context_sink(sink)
            self.event_sinks.append(sink)
            return sink_class

        return wrapper

    def _register_embedded_implicit_sink(self, item: _EmbeddedAgentScanItem) -> None:
        if item.class_name is None or item.sink_kind is None:
            return
        module = sys.modules.get(item.module_name)
        if module is None:
            return
        sink_class = getattr(module, item.class_name, None)
        if sink_class is None:
            self.send_log(
                f"[Embedded Agent] 跳过不存在的 sink: {item.module_name}.{item.class_name}"
            )
            return

        sink = sink_class()
        if item.sink_kind == "resource_sink":
            if self.resource is not None:
                self.resource.add_sink(sink)
            self.event_sinks.append(sink)
            return
        if item.sink_kind == "controller_sink":
            if self.controller is not None:
                self.controller.add_sink(sink)
            self.event_sinks.append(sink)
            return
        if item.sink_kind == "tasker_sink":
            if self.tasker is not None:
                self.tasker.add_sink(sink)
            self.event_sinks.append(sink)
            return
        if item.sink_kind == "context_sink":
            if self.tasker is not None and hasattr(self.tasker, "add_context_sink"):
                self.tasker.add_context_sink(sink)
            self.event_sinks.append(sink)

    def _add_embedded_sys_paths(self, agent_root: Path) -> list[str]:
        added_paths: list[str] = []
        for path in (str(agent_root), str(agent_root.parent)):
            if path in sys.path:
                continue
            sys.path.insert(0, path)
            added_paths.append(path)
            self.embedded_agent_sys_paths.append(path)
        return added_paths

    def _remove_embedded_sys_paths(self, paths: list[str]) -> None:
        for path in paths:
            with suppress(ValueError):
                sys.path.remove(path)
            with suppress(ValueError):
                self.embedded_agent_sys_paths.remove(path)

    @staticmethod
    def _purge_embedded_modules(agent_root: Path) -> None:
        for module_name, module in list(sys.modules.items()):
            if not isinstance(module_name, str):
                continue
            module_file = getattr(module, "__file__", None)
            if not module_file:
                continue
            try:
                if Path(module_file).resolve().is_relative_to(agent_root):
                    del sys.modules[module_name]
            except (OSError, ValueError, KeyError):
                continue

    @staticmethod
    def _purge_module_name(module_name: str) -> None:
        prefix = module_name + "."
        for key in list(sys.modules.keys()):
            if isinstance(key, str) and (key == module_name or key.startswith(prefix)):
                with suppress(KeyError):
                    del sys.modules[key]

    def _create_agent_client(self, label: str) -> AgentClient:
        try:
            agent_client = AgentClient()
            self.send_log(
                f"AgentClient 使用 IPC 模式: "
                f"{label}, identifier={agent_client.identifier}"
            )
            return agent_client
        except Exception as exc:
            if os.name == "nt":
                try:
                    agent_client = AgentClient.create_tcp()
                    self.send_log(
                        f"AgentClient IPC 模式创建失败，已回退 TCP: "
                        f"{label}, identifier={agent_client.identifier}"
                    )
                    return agent_client
                except Exception as tcp_exc:
                    raise RuntimeError(
                        f"创建 AgentClient 失败: {label}: IPC={exc}; TCP={tcp_exc}"
                    ) from tcp_exc
            raise RuntimeError(f"创建 AgentClient 失败: {label}: {exc}") from exc

    def _connect_agent_client(
        self,
        agent_client: AgentClient,
        process: subprocess.Popen,
        label: str,
    ) -> None:
        last_error: Exception | None = None
        if not agent_client.set_timeout(AGENT_CONNECT_TIMEOUT_MS):
            self.send_log(f"AgentClient 设置连接超时失败: {label}")
        for attempt in range(1, AGENT_CONNECT_RETRY_COUNT + 1):
            exit_code = process.poll()
            if exit_code is not None:
                raise RuntimeError(f"Agent 进程已退出，无法连接: {label}, exit={exit_code}")

            try:
                if agent_client.connect():
                    if not agent_client.set_timeout(-1):
                        self.send_log(f"AgentClient 恢复运行超时失败: {label}")
                    if attempt > 1:
                        self.send_log(f"AgentClient 已连接: {label}, 尝试次数 {attempt}")
                    return
            except Exception as exc:
                last_error = exc

            time.sleep(AGENT_CONNECT_RETRY_INTERVAL)

        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"AgentClient 连接超时: {label}{detail}")

    def _start_agent_output_reader(
        self,
        process: subprocess.Popen,
        label: str,
    ) -> None:
        if process.stdout is None:
            return

        thread = threading.Thread(
            target=self._read_agent_output,
            args=(process.stdout, label),
            name=f"maafw-agent-log-{process.pid}",
            daemon=True,
        )
        thread.start()
        self.agent_output_threads.append(thread)

    def _read_agent_output(self, stream: BinaryIO | TextIO, label: str) -> None:
        try:
            while True:
                line = stream.readline()
                if line in ("", b""):
                    break
                message = self._decode_agent_output_line(line).rstrip()
                if message:
                    self.send_log(f"[Agent:{label}] {message}")
        except ValueError:
            return
        except Exception as exc:
            self.send_log(f"读取 agent 输出失败: {exc}")

    @staticmethod
    def _decode_agent_output_line(line: bytes | str) -> str:
        text = decode_bytes(line) if isinstance(line, bytes) else line
        return ANSI_ESCAPE_RE.sub("", text)

    def _install_resource_sink(self) -> None:
        try:
            sink = _MaaFWResourceLogSink(self.send_log)
            if self.resource.add_sink(sink) is not None:
                self.event_sinks.append(sink)
        except Exception as exc:
            self.send_log(f"注册 MaaFW resource 日志监听失败: {exc}")

    def _install_controller_sink(self, controller: Controller) -> None:
        try:
            sink = _MaaFWControllerLogSink(self.send_log)
            if controller.add_sink(sink) is not None:
                self.event_sinks.append(sink)
        except Exception as exc:
            self.send_log(f"注册 MaaFW controller 日志监听失败: {exc}")

    def _install_tasker_sink(self) -> None:
        try:
            sink = _MaaFWTaskerLogSink(
                self.send_log,
                self._record_task_failure_summary,
            )
            if self.tasker.add_sink(sink) is not None:
                self.event_sinks.append(sink)
        except Exception as exc:
            self.send_log(f"注册 MaaFW tasker 日志监听失败: {exc}")

    def _build_agent_env(self, agent_plan: Any) -> dict[str, str]:
        """构造 agent 子进程环境，严格隔离 AUTO-MAS 自身环境。

        清理 VIRTUAL_ENV、PYTHONHOME、旧 PYTHONPATH 等会导致串环境的变量，
        再显式设置当前项目所需的 PYTHONPATH；PATH 前置 agent Python 目录、
        Scripts 目录、项目根目录与项目必要 dll 目录。
        """
        env = os.environ.copy()
        env.update(self.plan.piEnv)

        project_path = Path(self.plan.path)

        # 清理 AUTO-MAS 自身环境变量，防止 agent 串到 MAS .venv
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONUSERBASE", None)
        env.pop("PIP_TARGET", None)
        env.pop("PIP_PREFIX", None)
        env.pop("PIP_USER", None)
        # 不继承 MAS 的 PYTHONPATH，显式设置为当前项目根目录
        python_path_items: list[str] = []
        if getattr(agent_plan, "runtimeKind", None) == "isolated_venv":
            venv_path_str = getattr(agent_plan, "isolatedVenvPath", None)
            if venv_path_str:
                try:
                    python_path_items.append(
                        str(_write_agent_compat_shims(Path(venv_path_str)))
                    )
                except Exception as exc:
                    self.send_log(f"[Python环境] 写入 Agent 兼容层失败: {exc}")
        python_path_items.append(str(project_path))
        env["PYTHONPATH"] = os.pathsep.join(python_path_items)
        env["PYTHONIOENCODING"] = "utf-8"

        # PATH 前置：agent Python 目录、Scripts 目录、项目根目录、项目必要 dll 目录
        python_exe = Path(agent_plan.executable)
        path_items: list[str] = []
        python_dir = python_exe.parent
        if python_dir.is_dir():
            path_items.append(str(python_dir))
            scripts_dir = python_dir / ("Scripts" if os.name == "nt" else "bin")
            if scripts_dir.is_dir():
                path_items.append(str(scripts_dir))
        path_items.append(str(project_path))
        for parts in AGENT_ENV_PATH_DIRS:
            candidate = project_path.joinpath(*parts)
            if candidate.is_dir():
                path_items.append(str(candidate))

        current_path = env.get("PATH", "")
        env["PATH"] = (
            os.pathsep.join([*path_items, current_path])
            if current_path
            else os.pathsep.join(path_items)
        )
        return env

    def _prepare_agent_project_dirs(self) -> None:
        project_path = Path(self.plan.path)
        try:
            for dir_name in AGENT_PROJECT_RUNTIME_DIRS:
                (project_path / dir_name).mkdir(exist_ok=True)
        except Exception as exc:
            raise RuntimeError(f"准备 MaaFW agent 运行目录失败: {exc}") from exc

    def _prepare_agent_python_env(self, agent_plan: Any) -> None:
        """在启动 agent 子进程前准备 Python 环境，严格按 runtime_kind 分支处理。

        - project_python: 使用项目自带 Python，仅检查健康状态，不自动改 release 目录
        - isolated_venv: 创建/复用项目专属隔离 venv，安装项目 requirements.txt
        - external: 用户自备环境，不做任何操作

        绝不使用 AUTO-MAS 自身 Python 替代项目 Python，绝不污染 MAS .venv。
        """
        runtime_kind = getattr(agent_plan, "runtimeKind", None)
        python_exe = agent_plan.command[0]
        project_path = Path(self.plan.path)
        self.send_log(
            f"[Python环境] Agent {agent_plan.childExec} 使用 "
            f"{runtime_kind or 'external'}: {python_exe}"
        )

        try:
            resolved_python = str(Path(python_exe).resolve())
        except Exception:
            resolved_python = python_exe

        if resolved_python in self._python_env_checked:
            self.send_log(f"[Python环境] 已检查过该 Python，跳过重复检查: {python_exe}")
            return

        if runtime_kind == "isolated_venv":
            self._prepare_isolated_venv_env(agent_plan, project_path)
            self._python_env_checked[resolved_python] = True
            return

        if runtime_kind == "project_python":
            self._prepare_project_python_env(python_exe, project_path)
            self._python_env_checked[resolved_python] = True
            return

        # external 或未知 runtime_kind：用户自备环境，不做任何操作
        self.send_log(f"[Python环境] 跳过外部环境检测: {python_exe}")

    def _prepare_project_python_env(
        self,
        python_exe: str,
        project_path: Path,
    ) -> None:
        """准备项目自带 Python 环境：只检测健康状态，不自动修改 release。

        项目自带 Python 属于用户提供的 MaaFW release 内容。这里不运行
        ensurepip/pip install，不升级 maafw，也不补装依赖，避免持久修改 release 目录。
        """
        self.send_log(f"[Python环境] 检测项目 Python: {python_exe}")
        test_env = self._build_agent_env_for_pip(project_path)

        pip_ok = self._check_pip_health(
            python_exe, cwd=str(project_path), env=test_env
        )
        if not pip_ok:
            raise RuntimeError(
                f"项目 Python 环境 pip 不可用，请手动修复后重试：\n"
                f"  Python 路径: {python_exe}\n"
                f"  处理建议:\n"
                f"    方法1: 重新下载并解压完整 MaaFW 项目包\n"
                f"    方法2: 在项目目录中手动修复该项目自带 Python 的 pip 环境\n"
                f"  AUTO-MAS 不会自动修改项目 release 目录。"
            )

    def _prepare_isolated_venv_env(
        self,
        agent_plan: Any,
        project_path: Path,
    ) -> None:
        """准备项目专属隔离 venv 环境。

        使用 AUTO-MAS 的 sys.executable 引导创建 venv，但 agent 实际运行在
        隔离 venv 中，不会污染 AUTO-MAS 自身 .venv。依赖声明来自
        MaaFW 项目自己的 requirements.txt。
        """
        venv_path_str = getattr(agent_plan, "isolatedVenvPath", None)
        if not venv_path_str:
            raise RuntimeError("隔离 venv 路径未提供，无法创建隔离环境")

        venv_path = Path(venv_path_str)
        python_exe = agent_plan.command[0]

        self.send_log(f"[Python环境] 准备隔离 venv: {venv_path}")
        had_valid_venv = _is_valid_venv_path(venv_path)
        if self._should_rebuild_isolated_venv(venv_path, project_path):
            self._reset_isolated_venv(venv_path)
            had_valid_venv = False
        self._ensure_isolated_venv(venv_path)
        _write_agent_compat_shims(venv_path)

        test_env = self._build_agent_env_for_pip(project_path)
        # 隔离 venv 的 PYTHONPATH 指向项目根目录
        test_env["PYTHONPATH"] = str(project_path)

        pip_ok = self._check_pip_health(
            python_exe, cwd=str(project_path), env=test_env
        )
        if not pip_ok:
            self.send_log("[Python环境] 隔离 venv pip 异常，尝试 ensurepip 修复...")
            if not self._try_ensurepip(
                python_exe, cwd=str(project_path), env=test_env
            ):
                raise RuntimeError(
                    f"隔离 venv pip 无法自动修复: {python_exe}"
                )

        if had_valid_venv and self._is_isolated_venv_manifest_current(
            venv_path,
            project_path,
        ):
            self.send_log("[Python环境] 隔离 venv 依赖清单未变化，跳过 pip install")
            return

        # 隔离 venv 安装 MaaFW 项目自己的 requirements.txt
        if not self._ensure_agent_packages(
            python_exe,
            runtime_kind="isolated_venv",
            project_path=project_path,
            cwd=str(project_path),
            env=test_env,
        ):
            raise RuntimeError(f"隔离 venv 依赖安装失败: {python_exe}")
        self._write_isolated_venv_manifest(venv_path, project_path)

    def _is_isolated_venv_manifest_current(
        self,
        venv_path: Path,
        project_path: Path,
    ) -> bool:
        manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return False

        expected = _build_agent_env_manifest(project_path)
        return (
            manifest.get("projectPath") == expected["projectPath"]
            and manifest.get("interfaceHash") == expected["interfaceHash"]
            and manifest.get("requirementsHash") == expected["requirementsHash"]
        )

    def _should_rebuild_isolated_venv(
        self,
        venv_path: Path,
        project_path: Path,
    ) -> bool:
        if venv_path.exists() and not _is_valid_venv_path(venv_path):
            self.send_log("[Python环境] 隔离 venv 不完整，将重建")
            return True

        if not _is_valid_venv_path(venv_path):
            return False

        manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.send_log("[Python环境] 隔离 venv 缺少依赖清单，将重建")
            return True
        except Exception as exc:
            self.send_log(f"[Python环境] 隔离 venv 依赖清单异常，将重建: {exc}")
            return True

        expected = _build_agent_env_manifest(project_path)
        if manifest.get("projectPath") != expected["projectPath"]:
            self.send_log("[Python环境] 隔离 venv 项目路径已变化，将重建")
            return True
        if manifest.get("interfaceHash") != expected["interfaceHash"]:
            self.send_log("[Python环境] MaaFW 项目 interface 已变化，将重建隔离 venv")
            return True
        if manifest.get("requirementsHash") != expected["requirementsHash"]:
            self.send_log("[Python环境] MaaFW 项目 requirements 已变化，将重建隔离 venv")
            return True
        return False

    def _reset_isolated_venv(self, venv_path: Path) -> None:
        if venv_path.parent.name != "maafw_agent_venvs" or not venv_path.name.startswith(
            "maafw_venv_"
        ):
            raise RuntimeError(f"拒绝重建非托管隔离 venv: {venv_path}")
        shutil.rmtree(venv_path, ignore_errors=True)
        self.send_log(f"[Python环境] 已清理旧隔离 venv: {venv_path}")

    def _write_isolated_venv_manifest(
        self,
        venv_path: Path,
        project_path: Path,
    ) -> None:
        manifest_path = venv_path / AGENT_ENV_MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(
                _build_agent_env_manifest(project_path),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _ensure_isolated_venv(self, venv_path: Path) -> None:
        """创建或复用项目专属隔离 venv。

        使用便携包基础 Python 或 AUTO-MAS 的 sys.executable 引导创建 venv（仅用于 venv 创建），
        agent 实际运行在隔离 venv 中，不会污染 AUTO-MAS 自身 .venv。
        """
        if _is_valid_venv_path(venv_path):
            self.send_log(f"[Python环境] 隔离 venv 已存在: {venv_path}")
            return

        if venv_path.exists():
            self._reset_isolated_venv(venv_path)

        venv_path.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_python = _venv_bootstrap_python()
        self.send_log(
            f"[Python环境] 创建隔离 venv: {venv_path} "
            f"(引导 Python: {bootstrap_python})"
        )
        try:
            result = subprocess.run(
                [
                    bootstrap_python,
                    "-m",
                    "venv",
                    str(venv_path),
                ],
                capture_output=True,
                timeout=PIP_INSTALL_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise RuntimeError(
                    f"创建隔离 venv 失败 (exit={result.returncode}): {detail[:500]}"
                )
            if not _is_valid_venv_path(venv_path):
                raise RuntimeError(f"创建隔离 venv 后结构不完整: {venv_path}")
            self.send_log(f"[Python环境] 隔离 venv 创建成功: {venv_path}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"创建隔离 venv 超时 ({PIP_INSTALL_TIMEOUT}s): {venv_path}"
            )

    def _build_agent_env_for_pip(self, project_path: Path) -> dict[str, str]:
        """构建与 agent 运行时一致的环境变量（清理 MAS 环境变量），用于 pip 检测。

        与 _build_agent_env 不同的是，此方法不依赖 agent_plan，用于 pip 检测阶段。
        """
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONUSERBASE", None)
        env.pop("PIP_TARGET", None)
        env.pop("PIP_PREFIX", None)
        env.pop("PIP_USER", None)
        env["PYTHONPATH"] = str(project_path)
        return env

    def _check_pip_health(self, python_exe: str, *, cwd: str | None = None, env: dict[str, str] | None = None) -> bool:
        """检测 pip 是否能正常执行 install 命令（模拟 agent 真实使用场景）。

        使用 python -c 尝试加载 pip._internal.commands.install，
        因为 pip --version 不会加载 install 子模块，无法检测到 backports.zstd 冲突。
        """
        try:
            # 先做简单的 --version 检测
            result = subprocess.run(
                [python_exe, "-m", "pip", "--version"],
                capture_output=True,
                timeout=PIP_HEALTH_CHECK_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            if result.returncode != 0:
                error_detail = (result.stderr or result.stdout or "").strip()
                self.send_log(f"[Python环境] pip --version 失败 (exit={result.returncode}): {error_detail[:500]}")
                return False

            # 关键检测：尝试加载 install 子命令（这是真正会触发 backports.zstd 崩溃的地方）
            result2 = subprocess.run(
                [
                    python_exe, "-c",
                    "from pip._internal.commands.install import InstallCommand; print('install command OK')",
                ],
                capture_output=True,
                timeout=PIP_HEALTH_CHECK_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            if result2.returncode == 0:
                version_info = result.stdout.strip()
                self.send_log(f"[Python环境] pip 健康: {version_info}")
                return True

            error_detail = (result2.stderr or result2.stdout or "").strip()
            zstd_err = "backports.zstd" in error_detail or "ZstdError" in error_detail
            if zstd_err:
                self.send_log("[Python环境] pip install 子命令加载失败（backports.zstd 冲突）")
            else:
                self.send_log(f"[Python环境] pip install 检测失败 (exit={result2.returncode}): {error_detail[:500]}")
            return False
        except subprocess.TimeoutExpired:
            self.send_log(f"[Python环境] pip 检测超时 ({PIP_HEALTH_CHECK_TIMEOUT}s)")
            return False
        except Exception as exc:
            self.send_log(f"[Python环境] pip 检测异常: {exc}")
            return False

    def _try_ensurepip(self, python_exe: str, *, cwd: str | None = None, env: dict[str, str] | None = None) -> bool:
        """尝试 python -m ensurepip --upgrade 修复 pip。"""
        self.send_log("[Python环境] 修复策略 A (ensurepip)...")
        try:
            result = subprocess.run(
                [python_exe, "-m", "ensurepip", "--upgrade"],
                capture_output=True,
                timeout=PIP_INSTALL_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            if result.returncode == 0 and self._check_pip_health(python_exe, cwd=cwd, env=env):
                self.send_log("[Python环境] ensurepip 修复成功")
                return True
            detail = (result.stderr or result.stdout or "").strip()
            self.send_log(f"[Python环境] ensurepip 未成功: {detail[:300]}")
        except subprocess.TimeoutExpired:
            self.send_log(f"[Python环境] ensurepip 超时 ({PIP_INSTALL_TIMEOUT}s)")
        except Exception as exc:
            self.send_log(f"[Python环境] ensurepip 执行异常: {exc}")
        return False

    def _ensure_agent_packages(
        self,
        python_exe: str,
        *,
        runtime_kind: str,
        project_path: Path | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> bool:
        """按 runtime_kind 预安装 agent 依赖，绝不无版本升级 maafw。

        - project_python: 用户自带环境，不自动安装依赖
        - isolated_venv: 安装 MaaFW 项目自己的 requirements.txt
        """
        if runtime_kind == "project_python":
            self.send_log("[Python环境] 项目自带 Python 不自动安装依赖")
            return True

        if runtime_kind == "isolated_venv":
            if project_path is None:
                raise RuntimeError("隔离 venv 依赖安装缺少 MaaFW 项目路径")
            packages = _load_project_agent_requirements(project_path)
            self.send_log(
                f"[Python环境] 隔离 venv 安装项目依赖: {', '.join(packages)}"
            )
            return self._pip_install(
                python_exe,
                packages,
                cwd=cwd,
                env=env,
            )

        self.send_log(
            f"[Python环境] runtime_kind={runtime_kind}，跳过依赖安装"
        )
        return True

    def _pip_install(
        self,
        python_exe: str,
        packages: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> bool:
        """执行 pip install（不带 --upgrade），返回是否成功。"""
        try:
            result = subprocess.run(
                [
                    python_exe,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    *packages,
                ],
                capture_output=True,
                timeout=PIP_INSTALL_TIMEOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
                env=env,
            )
            if result.returncode == 0:
                self.send_log(
                    f"[Python环境] pip install 完成: {', '.join(packages)}"
                )
                return True
            detail = (result.stderr or result.stdout or "").strip()
            self.send_log(
                f"[Python环境] pip install 未成功（将由 agent 自举尝试）: "
                f"{detail[:300]}"
            )
        except subprocess.TimeoutExpired:
            self.send_log(
                f"[Python环境] pip install 超时 ({PIP_INSTALL_TIMEOUT}s)，"
                f"将由 agent 自举尝试"
            )
        except Exception as exc:
            self.send_log(
                f"[Python环境] pip install 异常: {exc}，将由 agent 自举尝试"
            )
        return False

    def _run_tasks(self) -> list[str]:
        completed_tasks: list[str] = []
        self._completed_tasks = completed_tasks
        self._failed_task_errors = []
        for task in self.plan.tasks:
            if self._stop_requested.is_set():
                raise RuntimeError("MaaFW 任务已停止")
            tasker = self.tasker
            if tasker is None:
                raise RuntimeError("MaaFW tasker 已释放，无法继续投递任务")
            self.send_log(_format_task_config_log(task))
            self.send_log(f"正在运行任务: {task.name}")
            self._task_failure_summaries.clear()
            try:
                if task.pipelineOverride:
                    job = tasker.post_task(task.entry, task.pipelineOverride)
                else:
                    job = tasker.post_task(task.entry)
                self._wait_job(job)
            except Exception as exc:
                if self._stop_requested.is_set():
                    raise RuntimeError("MaaFW 任务已停止") from exc
                message = str(exc)
                self._failed_task_errors.append((task.name, message))
                self.send_log(f"任务失败，将继续后续任务: {task.name}: {message}")
                time.sleep(0.1)
                continue
            if self._stop_requested.is_set():
                raise RuntimeError("MaaFW 任务已停止")
            completed_tasks.append(task.name)
            self.send_log(f"任务完成: {task.name}")
            time.sleep(0.1)
        return completed_tasks

    def _completed_task_names(self) -> list[str]:
        completed_tasks = getattr(self, "_completed_tasks", [])
        return list(completed_tasks)

    def _wait_job(self, job: Job | JobWithResult) -> None:
        job.wait()
        if job.failed:
            detail = None
            if isinstance(job, JobWithResult):
                detail = job.get()
            raise RuntimeError(self._build_job_failure_message(detail))

    def _record_task_failure_summary(self, message: str, details: dict[str, Any]) -> None:
        if message not in MAAFW_FAILURE_EVENT_MESSAGES:
            return
        summary = _format_maafw_failure_event(message, details)
        if not summary:
            return
        if summary in self._task_failure_summaries:
            self._task_failure_summaries.remove(summary)
        self._task_failure_summaries.append(summary)
        if len(self._task_failure_summaries) > MAAFW_FAILURE_SUMMARY_LIMIT:
            del self._task_failure_summaries[:-MAAFW_FAILURE_SUMMARY_LIMIT]

    def _build_job_failure_message(self, detail: Any | None) -> str:
        parts = ["任务执行失败"]
        detail_summary = _format_maafw_task_detail(detail)
        if detail_summary:
            parts.append(detail_summary)
        if self._task_failure_summaries:
            parts.append(
                "失败事件: " + "；".join(self._task_failure_summaries[-3:])
            )
        return ": ".join(parts)

def prepare_maafw_agent_python_envs(
    project_path: str | Path,
    interface_model: Any,
    *,
    send_log: Callable[[str], None] | None = None,
) -> list[Any]:
    """Prepare MaaFW agent Python envs without loading resources or starting agents."""

    resolved_project_path = Path(project_path).resolve()
    plugin_result = _prepare_maafw_agent_python_envs_from_plugin(
        resolved_project_path,
        interface_model,
        send_log=send_log,
    )
    if plugin_result is not None:
        return plugin_result

    agent_plans = build_maafw_agent_command_plans(
        resolved_project_path,
        interface_model.agent,
    )
    plan = MaaFWRunPlan(
        path=str(resolved_project_path),
        projectName=interface_model.name,
        projectLabel=getattr(interface_model, "label", None),
        controllerName="",
        controllerType="Adb",
        resourceName="",
        resource=MaaFWResourceBundlePlan(name="", label=None),
        agents=agent_plans,
        piEnv={},
        tasks=[],
        skippedTasks=[],
    )
    runner = MaaFWRunner(plan, send_log=send_log)
    runner.prepare_agent_python_envs()
    return agent_plans


def _prepare_maafw_agent_python_envs_from_plugin(
    project_path: Path,
    interface_model: Any,
    *,
    send_log: Callable[[str], None] | None,
) -> list[Any] | None:
    try:
        from automas_maafw_agent_env import MaaFWAgentEnvService
    except Exception:
        return None

    try:
        service = MaaFWAgentEnvService()
        result = service.prepare_env(
            project_path,
            interface_model,
            send_log=send_log,
        )
        return list(getattr(result, "plans", []))
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


class _MaaFWResourceLogSink(ResourceEventSink):
    def __init__(self, send_log: Callable[[str], None]) -> None:
        super().__init__()
        self.send_log = send_log

    def on_resource_loading(
        self,
        resource: Resource,
        noti_type: NotificationType,
        detail: ResourceEventSink.ResourceLoadingDetail,
    ) -> None:
        self.send_log(
            f"[MaaFW Resource] {_notification_label(noti_type)}: {detail.path}"
        )


class _MaaFWControllerLogSink(ControllerEventSink):
    def __init__(self, send_log: Callable[[str], None]) -> None:
        super().__init__()
        self.send_log = send_log

    def on_controller_action(
        self,
        controller: Controller,
        noti_type: NotificationType,
        detail: ControllerEventSink.ControllerActionDetail,
    ) -> None:
        if noti_type == NotificationType.Failed:
            self.send_log(
                f"[MaaFW Controller] {_notification_label(noti_type)}: {detail.action}"
            )


class _MaaFWTaskerLogSink(TaskerEventSink):
    def __init__(
        self,
        send_log: Callable[[str], None],
        record_failure: Callable[[str, dict[str, Any]], None],
    ) -> None:
        super().__init__()
        self.send_log = send_log
        self.record_failure = record_failure

    def on_tasker_task(
        self,
        tasker: Tasker,
        noti_type: NotificationType,
        detail: TaskerEventSink.TaskerTaskDetail,
    ) -> None:
        self.send_log(
            f"[MaaFW Tasker] {_notification_label(noti_type)}: {detail.entry}"
        )

    def on_raw_notification(
        self,
        tasker: Tasker,
        msg: str,
        details: dict[str, Any],
    ) -> None:
        self.record_failure(msg, details)


def _notification_label(noti_type: NotificationType) -> str:
    if noti_type == NotificationType.Starting:
        return "开始"
    if noti_type == NotificationType.Succeeded:
        return "成功"
    if noti_type == NotificationType.Failed:
        return "失败"
    return "事件"


def _format_task_config_log(task: MaaFWTaskRunPlan) -> str:
    option_text = json.dumps(
        task.logOptions,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(option_text) > TASK_CONFIG_LOG_VALUE_LIMIT:
        option_text = option_text[:TASK_CONFIG_LOG_VALUE_LIMIT] + "..."

    override_text = ", ".join(task.overrideNodes[:12]) or "-"
    if len(task.overrideNodes) > 12:
        override_text += f", ...(+{len(task.overrideNodes) - 12})"
    return (
        "MaaFW 任务配置: "
        f"name={task.name}; entry={task.entry}; options={option_text}; "
        f"override_nodes={override_text}"
    )


def _format_maafw_task_detail(detail: Any | None) -> str:
    if detail is None:
        return ""

    parts: list[str] = []
    entry = getattr(detail, "entry", None)
    if entry:
        parts.append(f"entry={entry}")

    task_id = getattr(detail, "task_id", None)
    if task_id is not None:
        parts.append(f"task_id={task_id}")

    status = _format_maafw_status(getattr(detail, "status", None))
    if status:
        parts.append(f"status={status}")

    node_id_list = getattr(detail, "node_id_list", None)
    if node_id_list:
        tail = list(node_id_list)[-5:]
        parts.append(f"last_nodes={tail}")

    return ", ".join(parts)


def _format_maafw_status(status: Any | None) -> str:
    if status is None:
        return ""

    status_value = getattr(status, "_status", status)
    name = getattr(status_value, "name", None)
    value = getattr(status_value, "value", None)
    if name is not None and value is not None:
        return f"{name}({value})"
    if value is not None:
        return str(value)
    return str(status_value)


def _format_maafw_failure_event(message: str, details: dict[str, Any]) -> str:
    parts = [message]

    name = details.get("name") or details.get("entry")
    if name:
        parts.append(str(name))

    node_details = details.get("node_details")
    if isinstance(node_details, dict):
        node_name = node_details.get("name")
        node_id = node_details.get("node_id")
        if node_name and node_id is not None:
            parts.append(f"node={node_name}({node_id})")
        elif node_name:
            parts.append(f"node={node_name}")

    action_details = details.get("action_details")
    if isinstance(action_details, dict):
        action_name = action_details.get("name")
        if action_name:
            parts.append(f"action={action_name}")

    texts = _collect_maafw_detail_texts(details)
    if texts:
        parts.append("text=" + " / ".join(texts[:3]))

    focus = details.get("focus")
    focus_texts = _collect_maafw_focus_texts(focus)
    if focus_texts:
        parts.append("focus=" + " / ".join(focus_texts[:2]))

    return ", ".join(parts)


def _collect_maafw_detail_texts(value: Any) -> list[str]:
    texts: list[str] = []

    def walk(item: Any) -> None:
        if len(texts) >= 3:
            return
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text and text not in texts:
                texts.append(_short_maafw_text(text))
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return texts


def _collect_maafw_focus_texts(focus: Any) -> list[str]:
    if isinstance(focus, dict):
        return [
            _short_maafw_text(str(value))
            for value in focus.values()
            if value
        ]
    if isinstance(focus, str) and focus:
        return [_short_maafw_text(focus)]
    return []


def _short_maafw_text(text: str, limit: int = 80) -> str:
    sanitized = " ".join(text.split())
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 3] + "..."
