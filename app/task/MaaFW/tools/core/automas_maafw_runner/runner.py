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


import ctypes
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, BinaryIO, Callable, TextIO

import maa as maa_package
from maa.agent_client import AgentClient
from maa.buffer import ImageBuffer
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
from maa.define import MaaImageBufferHandle, MaaSize
from maa.event_sink import NotificationType
from maa.job import Job, JobWithResult
from maa.library import Library
from maa.resource import Resource, ResourceEventSink
from maa.tasker import Tasker, TaskerEventSink
from maa.toolkit import Toolkit
from packaging.version import InvalidVersion, Version

from app.task.MaaFW.tools.core.automas_maafw_agent_env import write_agent_compat_shims
from app.task.MaaFW.tools.core.automas_maafw_runner.environment import (
    describe_runtime_architecture_mismatch,
    project_maafw_runtime_path,
)
from app.task.MaaFW.tools.core.automas_maafw_runtime_pool.host_environment import (
    strip_host_python_environment,
)

# MaaFWRunResult 只在 models 里定义一份：宿主用它 model_validate worker 回传的
# 结果，两边字段一旦分叉，多出来的字段会被 pydantic 静默丢掉（adbReadyTimeout
# 就这么丢过一次，见下方注释）。
try:
    from .models import MaaFWDeviceConfig, MaaFWFailureScreenshot, MaaFWRunResult
    from .run_plan import MaaFWRunPlan, MaaFWTaskRunPlan
except ImportError:
    from models import (  # type: ignore[no-redef]
        MaaFWDeviceConfig,
        MaaFWFailureScreenshot,
        MaaFWRunResult,
    )
    from run_plan import MaaFWRunPlan, MaaFWTaskRunPlan  # type: ignore[no-redef]

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
ENCODINGS = ("utf-8", "gbk", "shift_jis", "utf-16")
# 这些 controller 动作失败意味着游戏/设备根本没就绪。此时任务失败不该继续
# 往下跑——后面每个任务都会在同一个空场景里空转到各自超时，既浪费十几分钟，
# 又可能把「本轮已做过」的完成态错误写回。直接抛出，交给宿主的重试循环。
FATAL_CONTROLLER_ACTIONS = frozenset({"start_app"})
# MaaFramework 在 `Tasker::post_stop` 内部会跑一个同名的伪任务，任何一方调用
# post_stop 都会产生它。脚本侧（如 MaaEnd 的分辨率闸门）用自定义动作强停时，
# 我们只能从这里知道「这一轮不是自己结束的」。
MAAFW_POST_STOP_ENTRY = "MaaTaskerPostStop"
TASK_CONFIG_LOG_VALUE_LIMIT = 1200
# 整行上限。留足余量低于宿主 _FRAMEWORK_UI_LOG_MAX_CHARS(1200)，
# 免得任务配置被当成框架错误诊断截断。
TASK_CONFIG_LOG_LINE_LIMIT = 1000

_MAAFW_INITIALIZED = False
_MAAFW_INIT_LOCK = threading.Lock()


AGENT_CONNECT_RETRY_COUNT = 30
AGENT_CONNECT_RETRY_INTERVAL = 0.2
AGENT_CONNECT_TIMEOUT_MS = 1000
# 冷启动的模拟器要等很久：LDPlayer.open() 在 in_android==1 之后只 sleep 3 秒
# 就返回「启动完成」（不传 package_name 时不走那个 30 秒分支），此时 Android
# 里的 adbd 往往还没起来。第一层不受影响——它把等待交给项目外壳自己做了，
# 内置运行这条等待是唯一的缓冲。
#
# 插件带来的 30 次（30 秒）在雷电冷启动上不够用：真机实测 open() 报完成后
# 30 秒仍是 device not found，手动确认设备最终是能出现的。放宽到 3 分钟，
# 与 MAS 模拟器层自身 Info.MaxWaitTime（默认 300 秒）的耐心量级一致；
# 设备真的起不来时也仍然有界。
ADB_READY_RETRY_COUNT = 180
ADB_READY_RETRY_INTERVAL = 1.0
ADB_COMMAND_TIMEOUT = 5
AGENT_ENV_PATH_DIRS = (
    (),
    ("maafw",),
    ("runtimes", "win-x64"),
    ("libs",),
    ("deps",),
)
# Agent 自举所需的最小依赖包（pip 发行名）
# pip 健康检测超时（秒）
# pip 安装/修复超时（秒）
MAAFW_FAILURE_EVENT_MESSAGES = {
    "Node.NextList.Failed",
    "Node.PipelineNode.Failed",
    "Node.Action.Failed",
    "Tasker.Task.Failed",
}
MAAFW_FAILURE_SUMMARY_LIMIT = 8
# 任务失败截图的文件名里任务名最多保留多少字符。
FAILURE_SCREENSHOT_NAME_LIMIT = 40
_FAILURE_SCREENSHOT_NAME_RE = re.compile(r"[^\w\u4e00-\u9fff.-]+")
# 失败消息里最多回溯几个节点。再往前是正常走过的路径，列出来只会淹没重点。
FAILURE_NODE_NAME_LIMIT = 3
# 等「最早可下发任务」时刻最多等这么久。时刻是宿主按墙钟算的，两边钟对不上时
# 这条上限保证不会把整轮吊死。
TASK_START_GATE_MAX_SECONDS = 600.0


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
    return _is_network_adb_address(address) and (attempt == 0 or (attempt + 1) % 5 == 0)


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
        "connected to" in normalized or "already connected" in normalized
    ) and not any(marker in normalized for marker in failed_markers)


def _is_single_method(value: int) -> bool:
    """位掩码是否只选中了一个方法。

    MaaFW 的 ADB controller 收的是候选集合，原生层测速后自己挑一个；只传一个
    位时不存在候选、也不会测速。日志文案据此区分，免得把「只有这一个」说成
    「测速后选中的其中一个」。
    """

    raw = int(value)
    return raw > 0 and raw & (raw - 1) == 0


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


def describe_loaded_maafw() -> tuple[str, str]:
    """返回实际加载的 MaaFramework 版本与 Python binding 的版本。

    两者未必相同：原生库来自项目自带目录，binding 来自 runner venv。MaaFW 的
    py binding 与原生库是绑定关系，跨 minor 混用**不会报错**，但行为可能不同，
    真机上表现为「资源能导入、识别却不对」这类只在生产复现的问题。
    """

    try:
        loaded = str(Library.version() or "").strip()
    except Exception:  # pragma: no cover - 取不到就当未知，不能因此挡住运行
        loaded = ""
    try:
        from importlib.metadata import version as _dist_version

        binding = str(_dist_version("maafw") or "").strip()
    except Exception:  # pragma: no cover
        binding = ""
    return loaded, binding


def _file_fingerprint(path: Path) -> tuple[int, str] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return len(data), hashlib.sha256(data).hexdigest()


def detect_custom_maafw_build(runtime_path: Path | None) -> bool | None:
    """项目自带的原生库是否与 binding 附带的那份不是同一个二进制。

    版本号相同不等于二进制相同。按版本钉 binding 只能保证「官方发布的同版本」，
    挡不住项目塞进来一份自己改的构建——它报的版本串照样是 X，版本一致性检查
    看不出任何异常。

    两份文件此时都在本地（一份在项目目录，一份在 runner venv 的 ``maa/bin``），
    直接比字节即可，**不需要联网**。这是版本号抓不到、又能廉价拿到的那层证据。

    对 MaaFramework 官方目录里 46 个 Windows 发行包做过全量比对：能确定版本的
    44 个**全部与对应 PyPI wheel 逐字节相同**，无人自带改过的构建。所以这个
    检查平时不会响；它是给「哪天真有人这么干」留的。

    Returns:
        True 表示确实是另一个二进制；False 表示同一份；无法判断时返回 None。
    """

    if runtime_path is None:
        # 没有项目自带的库，本来就直接用 binding 那份，不存在分歧
        return False

    project_dll = runtime_path / "MaaFramework.dll"
    binding_dll = (
        Path(maa_package.__file__).resolve().parent / "bin" / "MaaFramework.dll"
    )
    try:
        if project_dll.resolve() == binding_dll:
            return False  # 同一个文件，谈不上分歧
    except OSError:
        return None

    project_print = _file_fingerprint(project_dll)
    binding_print = _file_fingerprint(binding_dll)
    if project_print is None or binding_print is None:
        return None
    return project_print != binding_print


def _installed_maafw_version(venv_path: Path) -> str | None:
    """读 venv 里已安装的 maafw 版本，读不出就返回 None。

    走 ``dist-info`` 目录名而不是起解释器去 import：诊断发生在失败路径上，
    不该再多花一次进程启动，也不该因为那个 venv 本身有问题而再抛一个异常。
    """

    roots = [venv_path / "Lib" / "site-packages"]
    roots.extend(sorted(venv_path.glob("lib/python*/site-packages")))
    for root in roots:
        try:
            matches = sorted(root.glob("maafw-*.dist-info"))
        except OSError:
            continue
        for match in matches:
            version = match.name[len("maafw-") : -len(".dist-info")]
            if version:
                return version
    return None


def _normalize_maafw_version(value: str) -> str:
    """把版本串归一到可比较的形式。

    两边的写法本来就不同：原生库报的是语义化版本（``v5.13.0-beta.2``），
    PyPI 包报的是 PEP 440（``5.13.0b2``）。只剥 ``v`` 前缀不够——那样
    同一个预发布版会被判成不一致，真机上就误报过一次。
    """

    raw = value.strip().lstrip("vV")
    try:
        return str(Version(raw))
    except InvalidVersion:
        return raw


def _display_maafw_version(value: str) -> str:
    """展示用：保证恰好一个 ``v`` 前缀，不重不缺。"""

    raw = value.strip()
    return "v" + raw.lstrip("vV") if raw else "未知"


def _ensure_maafw_global_init(
    project_path: Path | None = None,
    send_log: Callable[[str], None] | None = None,
) -> None:
    global _MAAFW_INITIALIZED
    if _MAAFW_INITIALIZED:
        return
    with _MAAFW_INIT_LOCK:
        if _MAAFW_INITIALIZED:
            return
        runtime_path = project_maafw_runtime_path(project_path)
        # 架构不符时 Library.open 必然失败，但原生层的报错定位不到「装错了包」。
        # 提前判断只是把同一个失败说清楚，不会挡下原本能跑的情况。
        architecture_error = describe_runtime_architecture_mismatch(runtime_path)
        if architecture_error:
            raise RuntimeError(architecture_error)
        _ensure_maafw_client_library_mode(runtime_path)
        if send_log is not None:
            loaded, binding = describe_loaded_maafw()
            source = str(runtime_path) if runtime_path else "runner 运行环境自带"
            send_log(
                "MaaFramework 实际加载: "
                f"{_display_maafw_version(loaded)}; 来源={source}"
            )
            versions_differ = (
                loaded
                and binding
                and _normalize_maafw_version(loaded)
                != _normalize_maafw_version(binding)
            )
            if versions_differ:
                # 只警告不拦截：现有项目正是这么跑起来的，贸然拦下会让原本能跑的
                # 直接失败。但必须让人看见——这类不一致不会报错，只会行为不同。
                send_log(
                    "⚠ MaaFramework 版本不一致: 原生库 "
                    f"{_display_maafw_version(loaded)} 与 Python binding "
                    f"{_display_maafw_version(binding)} 不是同一版本。"
                    "MaaFW 的 binding 与原生库"
                    "是绑定关系，跨版本混用不报错但行为可能不同，"
                    "识别异常时请优先怀疑这里"
                )
            elif detect_custom_maafw_build(runtime_path):
                # 版本号相同但二进制不同：项目自带的是改过的构建。按版本钉
                # binding 只保证「官方发布的同版本」，挡不住这种情况，而版本
                # 一致性检查同样看不出来——只有比字节能发现。
                send_log(
                    "MaaFramework 原生库为项目自带的非官方构建（版本同为 "
                    f"{_display_maafw_version(loaded)}，二进制与官方发行版不同）。"
                    "这是项目的选择，MAS 按其自带的库运行"
                )
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


# MaaFWDeviceConfig 统一从 models 导入（见文件头部的 import）。这里原本还有一份同名
# 类，比 models 那份少了 adbReadyTimeout；宿主按 models 那份序列化 job 文件、worker 按
# 这份反序列化，pydantic 默认 extra="ignore" 把该字段静默丢掉，模拟器等待时长设置因此
# 从落地起就没生效过。各方法的默认值不会因此改变：宿主每次都显式写全本 controller 用到
# 的字段，另一类 controller 的字段消费点本来就写成 `... or XxxEnum.Default`。


class MaaFWRunner:
    def __init__(
        self,
        plan: MaaFWRunPlan,
        *,
        send_log: Callable[[str], None] | None = None,
        failure_screenshot_dir: Path | None = None,
        failure_screenshot_prefix: str = "",
        task_start_not_before: float | None = None,
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
        self._external_stop_seen: threading.Event = threading.Event()
        self._self_stop_lock: threading.Lock = threading.Lock()
        self._pending_self_stops: int = 0
        self._task_failure_summaries: list[str] = []
        self._failed_controller_actions: set[str] = set()
        self._failed_task_errors: list[tuple[str, str]] = []
        self._failure_screenshot_dir: Path | None = failure_screenshot_dir
        self._failure_screenshot_prefix: str = failure_screenshot_prefix
        self._failure_screenshots: list[MaaFWFailureScreenshot] = []
        self._task_start_not_before: float | None = task_start_not_before

    @property
    def failure_screenshots(self) -> list[MaaFWFailureScreenshot]:
        return list(self._failure_screenshots)

    def _ensure_initialized(self, device_config: MaaFWDeviceConfig) -> None:
        if self._initialized:
            return

        _ensure_maafw_global_init(Path(self.plan.path), self.send_log)
        # 先确认设备真的连得上，再去加载原生插件与资源。
        # 这两步对 M9A 这类项目要几秒并会载入 DLL，设备没起来时全是白做的功，
        # 失败还要再逐个拆掉。冷启动的模拟器可能要等几分钟，更不该让它压在
        # 已经初始化了一半的 MaaFramework 上。
        self._preflight_device(device_config)
        self._load_native_plugins()
        self.resource = Resource()
        self.tasker = Tasker()
        self._install_resource_sink()
        self._load_resources()
        self._connect_device(device_config)
        self._start_agents()
        self._initialized = True

    def _load_native_plugins(self) -> None:
        for path_info in self.plan.nativePluginPaths:
            plugin_path = Path(path_info.resolved)
            if not path_info.exists:
                raise RuntimeError(
                    f"MaaFW native plugin 路径不存在: {path_info.resolved}"
                )

            # Tasker.load_plugin accepts a library path, not an arbitrary
            # distribution directory.  Some releases (notably M9A) keep
            # static ``.lib`` import libraries beside the actual plugin DLL;
            # passing the whole directory makes MaaFW try to load both the
            # directory and the .lib files as Win32 libraries.  Resolve only
            # loadable DLLs while preserving explicit file entries in a
            # project manifest.
            if path_info.isFile:
                candidates = (
                    [plugin_path] if plugin_path.suffix.casefold() == ".dll" else []
                )
            elif path_info.isDir:
                candidates = sorted(
                    (item for item in plugin_path.rglob("*.dll") if item.is_file()),
                    key=lambda item: str(item).casefold(),
                )
            else:
                candidates = []

            if not candidates:
                self.send_log(
                    f"MaaFW native plugin 路径未找到可加载 DLL，已跳过: {path_info.resolved}"
                )
                continue

            for candidate in candidates:
                if path_info.isFile:
                    # Preserve the explicit-file contract; directory entries
                    # are handled by the filtered candidate path below.
                    loaded = Tasker.load_plugin(path_info.resolved)
                else:
                    loaded = Tasker.load_plugin(str(candidate))
                if loaded is False:
                    raise RuntimeError(f"MaaFW native plugin 加载失败: {candidate}")
                self.send_log(f"已加载 MaaFW native plugin: {candidate}")

    def run(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        self._stop_requested.clear()
        self._external_stop_seen.clear()
        self._failure_screenshots = []
        try:
            self._ensure_initialized(device_config)
            self._wait_task_start_gate()
            completed_tasks = self._run_tasks()
            if self._failed_task_errors:
                first_failed_task, _ = self._failed_task_errors[0]
                if len(self._failed_task_errors) == 1:
                    # 只有一个任务失败时不带任务名——宿主侧已经拼上了任务标签，
                    # 再带一次就成了「拜访好友：任务执行失败：VisitFriends: ...」。
                    error_message = self._failed_task_errors[0][1]
                else:
                    error_message = "；".join(
                        f"{task_name}: {message}"
                        for task_name, message in self._failed_task_errors[:3]
                    )
                    if len(self._failed_task_errors) > 3:
                        error_message += (
                            f"；另有 {len(self._failed_task_errors) - 3} 个任务失败"
                        )
                return MaaFWRunResult(
                    success=False,
                    projectName=self.plan.projectName,
                    controllerName=self.plan.controllerName,
                    resourceName=self.plan.resourceName,
                    completedTasks=completed_tasks,
                    failedTask=first_failed_task,
                    errorMessage=error_message,
                    failureScreenshots=self.failure_screenshots,
                )
            return MaaFWRunResult(
                success=True,
                projectName=self.plan.projectName,
                controllerName=self.plan.controllerName,
                resourceName=self.plan.resourceName,
                completedTasks=completed_tasks,
            )
        except Exception as exc:
            failed_task = (
                self.plan.tasks[len(self._completed_task_names())].name
                if (len(self._completed_task_names()) < len(self.plan.tasks))
                else None
            )
            self.send_log(f"MaaFW 任务执行失败: {exc}")
            return MaaFWRunResult(
                success=False,
                projectName=self.plan.projectName,
                controllerName=self.plan.controllerName,
                resourceName=self.plan.resourceName,
                completedTasks=self._completed_task_names(),
                failedTask=failed_task,
                errorMessage=str(exc),
                failureScreenshots=self.failure_screenshots,
            )

    def cleanup(self) -> None:
        self._stop_requested.set()
        if self.tasker is not None:
            try:
                _ensure_maafw_client_library_mode()
                if self.tasker.running:
                    self._post_self_stop()
            except Exception as exc:
                self.send_log(f"停止 MaaFW tasker 失败: {exc}")

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

    def _preflight_device(self, device_config: MaaFWDeviceConfig) -> None:
        """在加载插件与资源之前先把设备连通性确认掉。

        只做不依赖 resource/tasker/controller 的检查：类型一致性、ADB 路径解析
        与设备就绪等待。冷启动的模拟器可能要等几分钟，先做这一步就不必为一台
        起不来的设备付出 MaaFramework 初始化与资源加载的代价。
        """

        if device_config.type != self.plan.controllerType:
            raise RuntimeError(
                f"设备类型 {device_config.type} 与 controller {self.plan.controllerType} 不一致"
            )

        if device_config.type != "Adb":
            return

        adb_path_source = "上游配置"
        if not device_config.adbPath:
            adb_path_source = "MaaFW Toolkit 自动发现"
        self._resolve_adb_device(device_config)
        connection_mode = (
            "TCP/IP"
            if _is_network_adb_address(device_config.address or "")
            else "本地/USB serial"
        )
        self.send_log(
            "ADB 连接方式: "
            f"{connection_mode}; 地址={device_config.address}; "
            f"ADB 路径={device_config.adbPath}; 路径来源={adb_path_source}"
        )
        self._wait_adb_device_ready(device_config)

    def _connect_device(self, device_config: MaaFWDeviceConfig) -> None:
        self._log_controller_config(device_config)
        self.controller = self._create_controller(device_config)
        self._install_controller_sink(self.controller)
        self._wait_job(self.controller.post_connection())
        if not self.tasker.bind(self.resource, self.controller):
            raise RuntimeError("无法绑定 MaaFW resource/controller/tasker")
        self._install_tasker_sink()
        if device_config.type == "Adb":
            screencap_methods = (
                device_config.screencapMethods or MaaAdbScreencapMethodEnum.Default
            )
            input_methods = device_config.inputMethods or MaaAdbInputMethodEnum.Default
            screencap_single = _is_single_method(screencap_methods)
            input_single = _is_single_method(input_methods)
            parts = [
                f"ADB controller 最终连接: controller={self.plan.controllerName}",
                f"地址={device_config.address}",
                f"ADB 路径={device_config.adbPath}",
                ("截图方法=" if screencap_single else "传入截图候选集合=")
                + _format_enum_methods(MaaAdbScreencapMethodEnum, screencap_methods),
                ("输入方法=" if input_single else "传入输入候选集合=")
                + _format_enum_methods(MaaAdbInputMethodEnum, input_methods),
            ]
            # 只有真的传了多个候选才需要提测速——Python binding 不暴露选中项，
            # 得去原生层日志里看。只传一个时没有候选也没有测速，别误导。
            if not (screencap_single and input_single):
                parts.append(
                    "候选集合由原生层测速后择一，MaaFW Python binding 未公开"
                    "选中项，可在本次运行的 MaaFW 框架日志中查看"
                )
            self.send_log("; ".join(parts))
        else:
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
            screencap_methods = (
                device_config.screencapMethods or MaaAdbScreencapMethodEnum.Default
            )
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
            screencap_method = (
                device_config.screencapMethod
                or MaaWin32ScreencapMethodEnum.DXGI_DesktopDup
            )
            mouse_method = device_config.mouseMethod or MaaWin32InputMethodEnum.Seize
            keyboard_method = (
                device_config.keyboardMethod or MaaWin32InputMethodEnum.Seize
            )
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
            screencap_methods = (
                device_config.screencapMethods or MaaAdbScreencapMethodEnum.Default
            )
            input_methods = device_config.inputMethods or MaaAdbInputMethodEnum.Default
            screencap_label = (
                "截图方法" if _is_single_method(screencap_methods) else "截图候选集合"
            )
            input_label = (
                "输入方法" if _is_single_method(input_methods) else "输入候选集合"
            )
            self.send_log(
                "ADB controller 传入: "
                f"{screencap_label}="
                f"{_format_enum_methods(MaaAdbScreencapMethodEnum, screencap_methods)}; "
                f"{input_label}="
                f"{_format_enum_methods(MaaAdbInputMethodEnum, input_methods)}; "
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
        # 宿主下发了该模拟器的等待预算就用它，否则退回常量
        retry_count = ADB_READY_RETRY_COUNT
        configured_timeout = getattr(device_config, "adbReadyTimeout", None)
        if isinstance(configured_timeout, int) and configured_timeout > 0:
            retry_count = max(1, int(configured_timeout / ADB_READY_RETRY_INTERVAL))

        for attempt in range(retry_count):
            connect_detail = ""
            if _should_adb_connect(device_config.address, attempt):
                connected, connect_detail = self._connect_adb_network_device(
                    device_config,
                )
                if connected and not network_connect_logged:
                    self.send_log(
                        f"ADB 网络设备已连接: {device_config.address}; {connect_detail}"
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
                    latency = self._measure_adb_latency(device_config)
                    self.send_log(
                        f"ADB 连接测速: {device_config.address}; 往返延迟={latency}"
                    )
                    self.send_log(f"ADB 设备已就绪: {device_config.address}")
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
                attempt == 0 or attempt == retry_count - 1 or (attempt + 1) % 15 == 0
            )
            if should_log:
                self.send_log(
                    f"ADB 设备未就绪，等待重试 "
                    f"({attempt + 1}/{retry_count}): "
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
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.send_log(
                f"启动 Agent 子进程: {Path(command[0]).name} (cwd={agent_plan.cwd})"
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
                    agent_plan,
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
            self.send_log(
                "[Python环境] 所有 Agent 均为 embedded，跳过子进程 Python 环境准备"
            )
            return

        self.send_log(f"[Python环境] 开始准备 {len(process_agents)} 个 Agent 环境")
        from app.task.MaaFW.tools.core.automas_maafw_agent_env.env import (
            prepare_agent_envs,
        )

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
        agent_plan: Any = None,
    ) -> None:
        last_error: Exception | None = None
        if not agent_client.set_timeout(AGENT_CONNECT_TIMEOUT_MS):
            self.send_log(f"AgentClient 设置连接超时失败: {label}")
        for attempt in range(1, AGENT_CONNECT_RETRY_COUNT + 1):
            exit_code = process.poll()
            if exit_code is not None:
                raise RuntimeError(
                    f"Agent 进程已退出，无法连接: {label}, exit={exit_code}"
                )

            try:
                if agent_client.connect():
                    if not agent_client.set_timeout(-1):
                        self.send_log(f"AgentClient 恢复运行超时失败: {label}")
                    if attempt > 1:
                        self.send_log(
                            f"AgentClient 已连接: {label}, 尝试次数 {attempt}"
                        )
                    return
            except Exception as exc:
                last_error = exc

            time.sleep(AGENT_CONNECT_RETRY_INTERVAL)

        detail = f": {last_error}" if last_error else ""
        hint = self._describe_agent_maafw_mismatch(agent_plan)
        raise RuntimeError(f"AgentClient 连接超时: {label}{detail}{hint}")

    def _describe_agent_maafw_mismatch(self, agent_plan: Any) -> str:
        """连不上时补一句版本诊断。

        AgentServer 与 AgentClient 之间有协议版本号，跨版本会被直接拒绝握手；
        原生日志里写着 ``Protocol version mismatch``，但传到用户眼前只剩一句
        「连接超时」，看不出该动什么。这里现读两侧版本拼出真正的原因。

        **只在失败路径上跑**：正常连上时零开销，也不会因为判断失误挡下本来
        能跑起来的组合。
        """

        venv_path = getattr(agent_plan, "isolatedVenvPath", None)
        if not venv_path:
            return ""
        agent_version = _installed_maafw_version(Path(venv_path))
        runner_version, _ = describe_loaded_maafw()
        if not agent_version or not runner_version:
            return ""
        if _normalize_maafw_version(agent_version) == _normalize_maafw_version(
            runner_version
        ):
            return ""
        return (
            f"；agent 隔离 venv 里的 maafw 是 {agent_version}，runner 加载的"
            f" MaaFramework 是 {_display_maafw_version(runner_version)}，"
            "两者的 Agent 协议版本不兼容。删掉该 venv 让它重建即可"
        )

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

    def _record_controller_action_failure(self, action: str) -> None:
        self._failed_controller_actions.add(action)

    def _install_controller_sink(self, controller: Controller) -> None:
        try:
            sink = _MaaFWControllerLogSink(
                self.send_log,
                self._record_controller_action_failure,
            )
            if controller.add_sink(sink) is not None:
                self.event_sinks.append(sink)
        except Exception as exc:
            self.send_log(f"注册 MaaFW controller 日志监听失败: {exc}")

    def _install_tasker_sink(self) -> None:
        try:
            sink = _MaaFWTaskerLogSink(
                self.send_log,
                self._record_task_failure_summary,
                self._note_tasker_entry,
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
        # 先按共用名单剔除 worker 自己与宿主的 Python 变量，再叠加项目 interface 声明的
        # 环境：项目给自己 agent 设的值要保留。worker 自己需要 PYTHONSAFEPATH（见
        # build_runner_environment），但不能透传给项目 agent：agent 以 `python ./agent/main.py`
        # 启动，靠脚本目录进 sys.path[0] 才能 import 同级模块，官方模板就是这么写的，
        # 继承过去会当场 ModuleNotFoundError——它随 PYTHON* 前缀一起被剔除。
        env = strip_host_python_environment()
        env.update(self.plan.piEnv)

        project_path = Path(self.plan.path)

        # 不继承 MAS 的 PYTHONPATH，显式设置为当前项目根目录
        python_path_items: list[str] = []
        if getattr(agent_plan, "runtimeKind", None) == "isolated_venv":
            venv_path_str = getattr(agent_plan, "isolatedVenvPath", None)
            if venv_path_str:
                try:
                    python_path_items.append(
                        str(write_agent_compat_shims(Path(venv_path_str)))
                    )
                except Exception as exc:
                    self.send_log(f"[Python环境] 写入 Agent 兼容层失败: {exc}")
        python_path_items.append(str(project_path))
        env["PYTHONPATH"] = os.pathsep.join(python_path_items)
        env["PYTHONIOENCODING"] = "utf-8"

        # PATH 前置：agent Python 目录、Scripts 目录、项目根目录、项目必要 dll 目录。
        # 再把 maa 包的 bin 放在项目路径之后、宿主 PATH 之前：项目自带的原生库
        # 仍然优先，缺库的项目则从当前 maafw 包拿到同版本的 DLL。
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

        maa_bin_path = Path(maa_package.__file__).resolve().parent / "bin"
        if maa_bin_path.is_dir():
            path_items.append(str(maa_bin_path))

        current_path = env.get("PATH", "")
        env["PATH"] = (
            os.pathsep.join([*path_items, current_path])
            if current_path
            else os.pathsep.join(path_items)
        )
        return env

    def _post_self_stop(self) -> None:
        """MAS 自己发起停止，并给随之而来的 MaaTaskerPostStop 通知记账。

        通知是异步送达的，可能晚到下一轮 `run()` 清完标志之后才到；不记账就会被
        `_note_tasker_entry` 当成脚本侧强停，把重试的第一个任务判成失败、后面的
        全部跳过。`post_stop()` 返回即代表停止任务已入队、通知必然会来；它抛异常
        时没有入队，所以计数必须放在调用返回之后。
        """

        if self.tasker is None:
            return
        job = self.tasker.post_stop()
        with self._self_stop_lock:
            self._pending_self_stops += 1
        job.wait()

    def _note_tasker_entry(self, noti_type: NotificationType, entry: str) -> None:
        """从 tasker 事件流里捕获「被外部强停」。"""

        if entry != MAAFW_POST_STOP_ENTRY:
            return
        # 一次 post_stop 会先后发出 Starting 和 Succeeded 两条通知。只认第一条，
        # 记账才能和 `_post_self_stop` 的调用一一对应。
        if noti_type != NotificationType.Starting:
            return
        with self._self_stop_lock:
            if self._pending_self_stops > 0:
                self._pending_self_stops -= 1
                return
        if self._stop_requested.is_set():
            return
        self._external_stop_seen.set()

    def _external_stop_active(self, tasker: Tasker | None) -> bool:
        """tasker 是不是被脚本侧强停了。

        主判据是同步查询 `MaaTaskerStopping`，不是上面那个事件标志：事件是异步
        送达的，实测比 `job.wait()` 返回晚约 19ms，光靠它会漏掉**当前**这个任务，
        于是它照旧被记成「任务完成」——这正是要修的 bug。
        post_stop 因果上必然早于 wait() 返回，所以此刻 stopping 一定还是 true。
        事件标志留作兜底，覆盖两个任务之间到达的强停。
        """

        if self._stop_requested.is_set():
            return False
        if self._external_stop_seen.is_set():
            return True
        if tasker is None:
            return False
        try:
            if bool(tasker.stopping):
                self._external_stop_seen.set()
                return True
        except Exception:
            # 老版本 MaaFW 没有 MaaTaskerStopping，退回只靠事件标志。
            return False
        return False

    def _wait_task_start_gate(self) -> None:
        """桌面游戏刚启动时，等到宿主给的时刻再投递第一个任务。

        窗口出现时 Unity 游戏还在黑屏加载，登录界面要二三十秒后才渲染；MaaEnd 的
        SceneManager 见连续画面不变十几秒就判「环境识别异常」直接失败。资源、
        controller、agent 的初始化已经在前面做完，这里只补足剩余的等待；游戏早就
        在跑（重试轮次、AttachOnly、宿主没给时刻）时剩余 ≤ 0，直接过。用 stop
        事件的 wait 而不是 sleep，取消能立即打断。
        """

        not_before = self._task_start_not_before
        if not_before is None:
            return
        remaining = min(not_before - time.time(), TASK_START_GATE_MAX_SECONDS)
        if remaining <= 0:
            return
        self.send_log(f"游戏刚启动，再等 {remaining:.0f}s 让画面加载完成后下发任务")
        if self._stop_requested.wait(timeout=remaining):
            raise RuntimeError("MaaFW 任务已停止")

    def _run_tasks(self) -> list[str]:
        completed_tasks: list[str] = []
        self._completed_tasks = completed_tasks
        self._failed_task_errors = []
        total_tasks = len(self.plan.tasks)
        for index, task in enumerate(self.plan.tasks):
            if self._stop_requested.is_set():
                raise RuntimeError("MaaFW 任务已停止")
            tasker = self.tasker
            if tasker is None:
                raise RuntimeError("MaaFW tasker 已释放，无法继续投递任务")
            display_name = _task_display_name(task)
            self.send_log(_format_task_config_log(task))
            self.send_log(f"正在运行任务: {display_name}")
            self._task_failure_summaries.clear()
            self._failed_controller_actions.clear()
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
                self._capture_failure_screenshot(task.name)
                fatal = sorted(
                    self._failed_controller_actions & FATAL_CONTROLLER_ACTIONS
                )
                if fatal:
                    actions = "、".join(fatal)
                    raise RuntimeError(
                        f"游戏未能启动（{actions} 失败），本轮剩余任务已跳过: "
                        f"{display_name}: {message}"
                    ) from exc
                if self._external_stop_active(tasker):
                    self.send_log(
                        f"任务被脚本侧强制停止，本轮剩余任务已跳过: "
                        f"{display_name}: {message}"
                    )
                    break
                # 这条现在会实时出现在任务日志里，措辞不能对最后一个
                # 任务说「将继续后续任务」。
                if index + 1 < total_tasks:
                    self.send_log(
                        f"任务失败，将继续后续任务: {display_name}: {message}"
                    )
                else:
                    self.send_log(f"任务失败: {display_name}: {message}")
                time.sleep(0.1)
                continue
            if self._stop_requested.is_set():
                raise RuntimeError("MaaFW 任务已停止")
            # MaaFW 会把「被 post_stop 打断」的入口回报成 Task.Succeeded——强停是
            # 由 pipeline 里的动作节点触发的，那个节点本身返回成功。只看
            # `job.failed` 会把一件没做的事记成「任务完成」，整轮还可能被报成
            # 全部成功。这里必须独立判一次。
            if self._external_stop_active(tasker):
                message = "任务被脚本侧强制停止（MaaTaskerPostStop）"
                self._failed_task_errors.append((task.name, message))
                self._capture_failure_screenshot(task.name)
                self.send_log(
                    f"任务未完成，本轮剩余任务已跳过: {display_name}: {message}"
                )
                break
            completed_tasks.append(task.name)
            self.send_log(f"任务完成: {display_name}")
            time.sleep(0.1)
        return completed_tasks

    def _capture_failure_screenshot(self, task_name: str) -> None:
        """把任务失败当刻的画面存成 PNG，随运行结果回传宿主。

        画面就是用户排查时最想看的那一眼——卡在哪个弹窗、哪个界面。
        取消（stop_requested）不算失败，不截；controller 已经没了也截不到。
        截图失败只记一行日志，绝不能反过来影响任务结果。
        """

        directory = self._failure_screenshot_dir
        controller = self.controller
        if directory is None or controller is None or self._stop_requested.is_set():
            return
        try:
            data = _encode_current_screen_png(controller)
            directory.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%H%M%S")
            name = _FAILURE_SCREENSHOT_NAME_RE.sub("_", task_name).strip("._")
            name = name[:FAILURE_SCREENSHOT_NAME_LIMIT] or "task"
            prefix = (
                f"{self._failure_screenshot_prefix}."
                if self._failure_screenshot_prefix
                else ""
            )
            path = directory / f"{prefix}failed-{stamp}-{name}.png"
            path.write_bytes(data)
        except Exception as exc:
            self.send_log(f"任务失败截图未能保存: {exc}")
            return
        self._failure_screenshots.append(
            MaaFWFailureScreenshot(task=task_name, path=str(path))
        )
        self.send_log(f"任务失败截图已保存: {path}")

    def _completed_task_names(self) -> list[str]:
        completed_tasks = getattr(self, "_completed_tasks", [])
        return list(completed_tasks)

    def _wait_job(self, job: Job | JobWithResult) -> None:
        # MaaFW returns a Job wrapper even when the native Tasker rejects a
        # task (for example, an invalid pipeline override); in that case the
        # native task id is 0 and ``job.failed`` is not reliable.  Treat it as
        # a submission failure instead of reporting an instant success.
        if getattr(job, "job_id", 1) == 0:
            raise RuntimeError("MaaFW tasker 未接受任务（task_id=0）")
        job.wait()
        if job.failed:
            detail = None
            if isinstance(job, JobWithResult):
                detail = job.get()
            raise RuntimeError(self._build_job_failure_message(detail))

    def _record_task_failure_summary(
        self, message: str, details: dict[str, Any]
    ) -> None:
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

    def _resolve_node_names(self, detail: Any | None) -> list[str]:
        """把最后几个节点的数字 id 解析成名字。

        数字 id 对用户没有任何意义，节点名才说明它停在哪一步。只取末尾几个：
        再往前是正常走过的路径，列出来只会淹没重点。逐个容错——取不到就跳过，
        诊断信息不该因为取不到名字而失败。
        """

        node_ids = list(getattr(detail, "node_id_list", None) or [])
        if not node_ids or self.tasker is None:
            return []

        names: list[str] = []
        for node_id in node_ids[-FAILURE_NODE_NAME_LIMIT:]:
            try:
                node = self.tasker.get_node_detail(int(node_id))
            except Exception:  # pragma: no cover - 诊断信息，取不到就算了
                continue
            name = str(getattr(node, "name", "") or "").strip()
            if name and (not names or names[-1] != name):
                names.append(name)
        return names

    def _build_job_failure_message(self, detail: Any | None) -> str:
        """给用户看的失败原因。

        只说「哪里坏了」，不重复任务名，也不带「任务执行失败」——宿主侧已经
        拼上了任务标签和这句话。内部标识（task_id、节点数字 id）同样不进来：
        它们对用户没有意义，且完整内容已经在本次运行的 *.maafw.log 里。
        """

        parts: list[str] = []

        names = self._resolve_node_names(detail)
        if names:
            parts.append("最后停在 " + " → ".join(names))
        elif getattr(detail, "entry", None):
            # 连节点名都取不到时，入口名至少还能定位到是哪条流程
            parts.append(f"入口 {detail.entry} 未能走完")

        events = self._describe_failure_events(detail)
        if events:
            parts.append(events)

        return "；".join(parts)

    def _describe_failure_events(self, detail: Any | None) -> str:
        """框架报的失败事件，去掉与节点信息重复的部分。"""

        if not self._task_failure_summaries:
            return ""
        entry = str(getattr(detail, "entry", "") or "").strip()
        kept: list[str] = []
        for summary in self._task_failure_summaries[-3:]:
            # `Tasker.Task.Failed, <entry>` 只是重复上面已经说过的入口名
            if entry and summary.strip() in (
                f"Tasker.Task.Failed, {entry}",
                f"Tasker.Task.Failed {entry}",
            ):
                continue
            kept.append(summary)
        return "框架失败事件: " + "；".join(kept) if kept else ""


def _encode_current_screen_png(controller: Any) -> bytes:
    """截一张当前画面并让 MaaFramework 自己编码成 PNG。

    运行池 venv 里只有 maa + numpy，没有 cv2 / PIL，Python 侧编不了图；
    而 ``MaaImageBufferGetEncoded`` 是 C API 一直导出的函数（返回 PNG 字节），
    只是 Python 绑定从没声明过它，这里自己补上 ctypes 签名。
    """

    job = controller.post_screencap()
    job.wait()
    if job.failed:
        raise RuntimeError("controller 截图失败")
    framework = Library.framework()
    get_encoded = framework.MaaImageBufferGetEncoded
    get_encoded.restype = ctypes.c_void_p
    get_encoded.argtypes = [MaaImageBufferHandle]
    get_encoded_size = framework.MaaImageBufferGetEncodedSize
    get_encoded_size.restype = MaaSize
    get_encoded_size.argtypes = [MaaImageBufferHandle]

    buffer = ImageBuffer()
    if not framework.MaaControllerCachedImage(controller._handle, buffer._handle):
        raise RuntimeError("读取截图缓存失败")
    size = int(get_encoded_size(buffer._handle))
    address = get_encoded(buffer._handle)
    if not size or not address:
        raise RuntimeError("截图缓存为空")
    return ctypes.string_at(address, size)


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
    def __init__(
        self,
        send_log: Callable[[str], None],
        record_action_failure: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.send_log = send_log
        self.record_action_failure = record_action_failure

    def on_controller_action(
        self,
        controller: Controller,
        noti_type: NotificationType,
        detail: ControllerEventSink.ControllerActionDetail,
    ) -> None:
        if noti_type == NotificationType.Failed:
            self.record_action_failure(str(detail.action or ""))
            self.send_log(
                f"[MaaFW Controller] {_notification_label(noti_type)}: {detail.action}"
            )


class _MaaFWTaskerLogSink(TaskerEventSink):
    def __init__(
        self,
        send_log: Callable[[str], None],
        record_failure: Callable[[str, dict[str, Any]], None],
        note_entry: Callable[[NotificationType, str], None] | None = None,
    ) -> None:
        super().__init__()
        self.send_log = send_log
        self.record_failure = record_failure
        self.note_entry = note_entry

    def on_tasker_task(
        self,
        tasker: Tasker,
        noti_type: NotificationType,
        detail: TaskerEventSink.TaskerTaskDetail,
    ) -> None:
        self.send_log(
            f"[MaaFW Tasker] {_notification_label(noti_type)}: {detail.entry}"
        )
        if self.note_entry is not None:
            self.note_entry(noti_type, detail.entry)

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
    display_name = _task_display_name(task)
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

    def compose(options: str) -> str:
        return (
            "MaaFW 任务配置: "
            f"label={display_name}; name={task.name}; entry={task.entry}; options={options}; "
            f"override_nodes={override_text}"
        )

    line = compose(option_text)
    # 整行也要收进限额。此前只有 options 单独受限，override_nodes 名字一长
    # （MaaEnd 的 _AutoEcoFarmEnterCameraModeFallbackReleaseOnError 之流）整行
    # 就会超过宿主转发日志的上限，被那条**给框架错误用的**兜底按 240 字符
    # 拦腰截断，JSON 断在半个键上、还被冠以「框架错误详情」。宁可在这里多砍
    # options，也要保证 override_nodes 与结尾完整。
    if len(line) > TASK_CONFIG_LOG_LINE_LIMIT:
        room = TASK_CONFIG_LOG_LINE_LIMIT - (len(line) - len(option_text))
        option_text = option_text[: max(0, room - 3)] + "..." if room > 3 else "..."
        line = compose(option_text)
    return line


def _task_display_name(task: MaaFWTaskRunPlan) -> str:
    label = task.label
    if isinstance(label, str) and label.strip() and not label.lstrip().startswith("$"):
        return label.strip()
    return task.name


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
        return [_short_maafw_text(str(value)) for value in focus.values() if value]
    if isinstance(focus, str) and focus:
        return [_short_maafw_text(focus)]
    return []


def _short_maafw_text(text: str, limit: int = 80) -> str:
    sanitized = " ".join(text.split())
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 3] + "..."
