from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Mapping

import psutil

import app.core.notify.formats.maafw as _format_maafw
from app.core import Config, Notify, Publisher
from app.core.notify.task_content import (
    NOTIFY_SCREENSHOT_LIMIT as NOTIFY_SCREENSHOT_LIMIT,
)
from app.core.notify.task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from app.core.notify.task_content import screenshot_entries as screenshot_entries
from app.core.ws import protocol
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.notification import LocalNotice
from app.models.schema import (
    HistoryAttachmentInput,
    HistorySnapshotStatistic,
    HistoryStatus,
    HistoryWrite,
    WSTaskNoticeData,
)
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import execute_script_task, power
from app.task.emulator_core import close_emulator, resolve_host_adb
from app.task.MaaFW.tools.core.controller_win32.service import (
    MaaFWWin32ControllerService,
    controller_has_window_rules,
)
from app.task.MaaFW.tools.core.interface.models import (
    MaaFWController,
    MaaFWInterface,
    resolve_task_instance_name,
)
from app.task.MaaFW.tools.core.interface.preview import (
    build_adb_emulator_extra_capabilities,
    interface_display_name,
)
from app.task.MaaFW.tools.core.interface.service import (
    MaaFWInterfaceService,
)
from app.task.MaaFW.tools.core.interface.task_config import (
    excluded_task_ids_for_weekday,
    find_missing_task_names,
)
from app.task.MaaFW.tools.core.runner.environment import (
    AGENT_PIP_CONSTRAINT_DIR_ENV,
    ARCHITECTURE_MISMATCH_MARKERS,
    MaaFWRunnerEnvironment,
    describe_project_runtime_architecture_mismatch,
)
from app.task.MaaFW.tools.core.runner.models import (
    MaaFWDeviceConfig,
    MaaFWRunPlan,
    MaaFWRunResult,
    MaaFWSkippedTaskPlan,
)
from app.task.MaaFW.tools.core.runner.pipeline_override import (
    SECRET_INPUTS_SNAPSHOT_KEY,
)
from app.task.MaaFW.tools.core.runner.run_events import (
    CATEGORY_ENVIRONMENT,
    CATEGORY_GAME_UPDATE_REQUIRED,
    CATEGORY_HOST_ERROR,
    CATEGORY_PRETASK_FAILED,
    CATEGORY_RESOURCE_FAILURE,
    CATEGORY_RUN_TIMEOUT,
    CATEGORY_SIGNAL,
    CATEGORY_USER_STOPPED,
    RUN_RECORD_EVENT_TYPE,
    STAGE_CLIENT,
    STAGE_ENVIRONMENT,
    STAGE_PRETASK,
)
from app.task.MaaFW.tools.core.runner.run_plan import (
    ALL_TASKS_SKIPPED_MESSAGE,
    NO_RUNNABLE_TASKS_MESSAGE,
    QUEUE_SKIPPED_TASK_REASON,
    MaaFWRunPlanError,
    describe_stale_option_values,
    resolve_run_selection,
    select_snapshot_tasks,
)
from app.task.MaaFW.tools.core.runner.service import MaaFWRunnerService
from app.task.MaaFW.tools.core.runtime_pool.host_environment import (
    path_without_host_venv,
    strip_host_python_environment,
    subprocess_proxy_scope,
)
from app.task.MaaFW.tools.core.worker_protocol import (
    AUDIENCE_UI,
    SIGNAL_SCREENSHOT_KINDS,
    UI_LOG_MAX_CHARS,
    WorkerEventServer,
    encode_job,
    event_audience,
    event_channel_supported,
    forwards_to_ui,
    strip_ansi,
)
from app.utils import UTC4, ProcessInfo, ProcessManager, get_logger
from app.utils import game_apk as _utils_game_apk
from app.utils import io as _utils_io

from .embedded_project import resolve_maafw_project_root
from .flavor import (
    no_default_fallback_inputs,
    off_day_scope,
    resolve_flavor,
    resolve_game_update_hook,
    unselectable_entries,
)
from .game_package import resolve_game_package
from .game_resolution import UnityGameResolutionOverride, parse_resolution_option
from .option_secrets import (
    collect_run_password_values,
    collect_script_password_values,
    log_redaction_notice,
    open_task_snapshot,
    redact_secret_text,
    secret_byte_pairs,
    secret_log_variants,
)
from .project_logs import copy_project_log_delta, snapshot_project_logs
from .project_path import (
    is_project_updating,
    release_project_path,
    release_project_path_sync,
    try_reserve_project_path,
)
from .resource_failure import (
    MAX_NATIVE_ERROR_LINES,
    describe_resource_failure,
    native_error_excerpt,
    read_native_error_lines,
)
from .run_record import (
    RUN_RECORD_HISTORY_KEY,
    MaaFWRunRecorder,
    format_incident_lines,
)
from .run_report import (
    CATEGORY_REASONS,
    MaaFWAttemptReport,
    failure_summary,
    format_timeline,
    human_reason,
)
from .signal_notice import (
    MAINTENANCE_LAST_STATUS,
    MAINTENANCE_SKIP_MESSAGE,
    SERVER_MAINTENANCE,
    SIGNAL_USER_MESSAGES,
    MaaFWSignalTracker,
)
from .update_credentials import resolve_update_proxy_url

logger = get_logger("MaaFW 插件自动代理")


# MaaFW 的 ADB 截图/输入方法枚举（EmulatorExtras 硬件加速相关）在此镜像为整型常量，
# 而非 `from maa.controller import MaaAdb*Enum`。本模块受导入边界约束
# （tests/plugins/test_maafw_import_boundaries.py 禁止导入时把 maa 载入 sys.modules），
# 直接 import maa 会加载原生绑定，故改为对齐 plugins/pypi/site-packages/maa/define.py
# 的取值：
#   screencap Default = All & ~RawByNetcat & ~MinicapDirect & ~MinicapStream = -57
#   screencap EmulatorExtras = 1 << 6 (64)
#   input Default = All & ~EmulatorExtras = -9；input All = ~0 = -1；EmulatorExtras = 1 << 3 (8)
# 任务取消后等环境准备线程收尾的最长时间。Runtime 关机只给后端约 5 秒，
# 安装线程若还在等 uv 子进程退出，超过这个值就不再等它。
_PREPARE_ENVIRONMENT_CANCEL_GRACE_SECONDS = 2.0
# 放弃等待后仍让收尾任务在后台跑完（准备恰好成功时要释放租约），
# 这里持有强引用，免得任务对象被回收。
_ABANDONED_PREPARATION_CLEANUPS: set[asyncio.Task[None]] = set()

_ADB_SCREENCAP_DEFAULT = -57
_ADB_SCREENCAP_EMULATOR_EXTRAS = 1 << 6
_ADB_INPUT_DEFAULT = -9
_ADB_INPUT_ALL = -1
_ADB_INPUT_EMULATOR_EXTRAS = 1 << 3
# 雷电专用：MinitouchAndAdbKey(2) | AdbShell(1)，故意不带 Maatouch(4)。
#
# MaaFW 的 ADB 文本输入只有两条实现：Maatouch 走 MaaTouch 的 `t` 命令，
# AdbShell / MinitouchAndAdbKey 走 adb config 里可替换的 `InputText` 命令
# （默认 `input text`）。前者按键盘映射逐字符注入，`input text` 也只认 ASCII，
# 两条都打不进中文——2026-09-12 生产实测 M9A 兑换码「魔精小A邀泥收看1999泡面番」
# 被 Maatouch 重打 265 次、输入框始终为空，整次运行撞硬超时。
# 雷电自己的 `ldconsole action --key call.input --value <文本>` 能把任意文本
# 提交到当前焦点的输入框（实测中文 35 ms 落地），所以在雷电上把 Maatouch 从
# 候选里摘掉，让文本走 MinitouchAndAdbKey 的 `InputText` 命令并替换成 ldconsole。
# 触控仍是 minitouch 协议，雷电 adbd 本身是 root，minitouch 可用（实测 init 508 ms）。
_ADB_INPUT_LDPLAYER_CONSOLE_TEXT = (1 << 1) | 1
# 名字与取值照抄 MaaFramework 绑定库 ``maa/define.py``（main 分支）。Foreground /
# Background 是组合名：原生层在组合里按顺序择一可用的方式，FOS、MaaNTE、mpa 的默认
# Win32 控制器写的就是 Background。运行时绑定库 / 原生库认不认得某个值由 worker 再判一次
# （runner._supported_win32_method），这里只负责把名字翻成数。
_WIN32_SCREENCAP_METHODS = {
    "GDI": 1,
    "FramePool": 1 << 1,
    "DXGI_DesktopDup": 1 << 2,
    "DXGI_DesktopDup_Window": 1 << 3,
    "PrintWindow": 1 << 4,
    "ScreenDC": 1 << 5,
    "Foreground": (1 << 3) | (1 << 5),
    "Background": (1 << 1) | (1 << 4),
}
_WIN32_INPUT_METHODS = {
    "Seize": 1,
    "SendMessage": 1 << 1,
    "PostMessage": 1 << 2,
    "LegacyEvent": 1 << 3,
    "PostThreadMessage": 1 << 4,
    "SendMessageWithCursorPos": 1 << 5,
    "PostMessageWithCursorPos": 1 << 6,
    "SendMessageWithWindowPos": 1 << 7,
    "PostMessageWithWindowPos": 1 << 8,
    "Interception": 1 << 9,
    "AnchoredTouch": 1 << 10,
}
_SUBPROCESS_OUTPUT_ENCODINGS = ("utf-8", "gbk", "shift_jis", "utf-16")
_RUN_OVERVIEW_LOG_VALUE_LIMIT = 1200
# 与日志去向判定（worker_protocol.forwards_to_ui）用同一个上限
_FRAMEWORK_UI_LOG_MAX_CHARS = UI_LOG_MAX_CHARS
# worker 输出转发每处理这么多行（事件通道上是这么多条）就让出一次事件循环。取 50 是因为
# 原生诊断的洪峰约每秒几十行，这个粒度下让出频率约每秒一次，开销可忽略。
_RELAY_YIELD_EVERY_LINES = 50
# worker stdout / stderr 单行上限（字节）。更长的一行丢掉、记一句，读取继续。协议事件走独立的
# 事件通道、按帧传，不受它限制；stdout 上只剩原生诊断，以及事件通道建不起来时退回的旧格式事件。
_WORKER_STREAM_LINE_LIMIT = 16 * 1024 * 1024
# 启动/附着游戏后定位其窗口的等待秒数
WINDOW_SEARCH_TIMEOUT_SECONDS = 5.0
# Game.WaitTime 填 0 时等游戏窗口出现的上限（秒）
_WINDOW_READY_FALLBACK_SECONDS = 60
# 脚本页没有填窗口句柄的入口，提示不能让用户去找一个不存在的设置。
_WIN32_NO_WINDOW_RULES_MESSAGE = (
    "该项目的这个 Win32 控制器没有声明窗口匹配规则（interface 里的 class_regex / "
    "window_regex），MAS 无法确定要控制哪个窗口，为避免控制错窗口不运行；请换用项目的"
    "其他控制器，或请项目方在 interface 里补上窗口匹配规则"
)

# 环境级失败：解释器自身坏了、依赖没装上。重试只会原样再失败一遍，而每次重试
# 还要重启一遍模拟器/游戏——默认 RunTimesLimit=3，白等好几分钟才告诉用户同一件事。
# 判据取消息标记而不是异常类型：这些错误跨了 runtime_pool 与 runner 两个包，
# 而 runner_task 有意不在模块层导入 runtime_pool（那会让所有请求都付出导入成本）。
_UNRETRYABLE_ENVIRONMENT_MARKERS = (
    "MaaFW runtime Python 自检失败",
    "MaaFW runtime ABI 探测失败",
    "runtime Python identity could not be verified",
    "MaaFW Runner 环境准备失败",
    "MaaFW Runner 环境准备超时",
    # 项目自带的 MaaFramework 与本机架构不符：换哪次尝试都是同一份库。运行前自检一般已
    # 拦下，这里兜住 worker 侧才发现的情况（异常与任务失败两条路都认）。
    *ARCHITECTURE_MISMATCH_MARKERS,
)
# 资源包加载失败（节点重名、JSON 写错、资源目录不在）：资源文件一次尝试到下一次不会自己变，
# 重试只会原样再失败、还要白白重启游戏 / 模拟器。与上面的环境级失败分开说：不是运行环境的事。
_RESOURCE_FAILURE_STOP_MESSAGE = (
    "资源包加载失败，重试也不会有别的结果，已停止本轮（不再重启游戏/模拟器）"
)
# 资源包加载失败后换了载荷、立刻再跑的那一次：（开头那行，之后「上一次（…）」里的称呼）。
# 不计入尝试次数，所以不编号。
_RERUN_AFTER_CLEANUP = (
    "已清理残留，立即重新运行（不计入尝试次数）",
    "清理残留后的重新运行",
)
_RERUN_AFTER_SWITCH = (
    "已换上同项目其他脚本在用的版本，立即重新运行（不计入尝试次数）",
    "换版本后的重新运行",
)
# 用户点停止后，等核对 / 清理线程收尾的上限：到点就不等了，预约交给它完成后再放。
_RELEASE_CHECK_CANCEL_GRACE_SECONDS = 30.0
# worker 到点自己停任务、截图、回传结果需要一点时间；宿主的硬超时在此之后才到，
# 只兜 worker 没能停下来的情况（原生层卡死、agent 自定义动作不返回）。
_RUN_DEADLINE_GRACE_SECONDS = 90.0
# worker 把结果发回来之后还要收尾（断开 agent、结束 agent 进程）才退出。agent 卡死时
# 这一步可能拖很久，而结果已经在手里了：给有限时间，到点强杀，别让宽限期把已经
# 拿到的截图和进度一起作废。
_WORKER_EXIT_AFTER_RESULT_SECONDS = 30.0
# 运行前设置（interface pretask）进程退出后，管道里剩下的输出最多再读这么久。pretask 常常
# 拉起启动器 / 游戏，它们可能继承了 pretask 的输出管道句柄，管道要等它们退出才到 EOF，
# 所以等待以 pretask 进程退出为准、不等 EOF（见 ``_run_pretasks``）。
_PRETASK_OUTPUT_DRAIN_SECONDS = 2.0
# 等 pretask 进程退出时查一次退出码的间隔：asyncio 的 ``Process.wait()`` 要等管道全部
# 关闭才返回，会被继承了管道的游戏卡住，只能看 ``returncode``。
_PRETASK_EXIT_POLL_SECONDS = 0.2
# 运行前设置输出的行尾：与 ``str.splitlines()`` 对这三种写法同口径，\r\n 算一次换行
_PRETASK_LINE_END_RE = re.compile(rb"\r\n|\r|\n")
# 超时或停止时，跟 pretask 进程一起结束的后代：只认这些脚本解释器，且一路往下只穿过
# 脚本解释器。游戏、启动器以及它们再起的任何进程都不碰（游戏的生命周期交给客户端）。
_PRETASK_SCRIPT_HOST_NAMES = frozenset(
    {
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "pyw.exe",
        "cmd.exe",
        "powershell.exe",
        "pwsh.exe",
        "wscript.exe",
        "cscript.exe",
    }
)
# 管道在 pretask 退出后仍被别的程序占着时，把剩下的输出读完的后台任务（只写后端日志）。
# 不读的话那个程序写满管道缓冲就会卡在写输出上；任务要有强引用，不然会被回收。
_PRETASK_BACKGROUND_DRAINS: set[asyncio.Task[None]] = set()
# 判断运行前设置留下的半行有没有看得见的内容时要去掉的部分：完整或被截断的 CSI 控制序列
# （含 \x1b[?25h 这类带私有参数的）与其余控制字符
_PRETASK_TAIL_NOISE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]?|[\x00-\x1f\x7f]")
# 哪些 worker 日志 / 原生诊断进界面的几组文案规则在 worker_protocol（forwards_to_ui）：
# worker 发事件时按它定 audience，宿主只对旧格式事件与 stdout 上的原生诊断再用它判。


def _avd_adb_path(manager_path: str | Path) -> Path:
    """魔改 AVD 这条安装的 adb：SDK 的 ``platform-tools\\adb.exe``（指定了本地 SDK 时取它的）。"""
    from app.utils import emulator2 as _utils_emulator2

    return _utils_emulator2.avd.components.adb_exe(
        _utils_emulator2.avd.components.root_from_manager_exe(manager_path)
    )


@dataclass(frozen=True)
class MaaFWAdbControlProfile:
    """描述某模拟器实例的 ADB EmulatorExtras 能力与 controller extras 配置。"""

    emulator_type: str | None
    screencap_extra: bool
    input_extra: bool
    config: dict[str, Any]


class MaaFWPretaskError(RuntimeError):
    """项目运行前设置失败，文案可直接显示给用户。"""


async def _abandon_environment_preparation(
    prepare_task: "asyncio.Future[Any]",
    *,
    release: Any,
    grace_seconds: float,
    send_log: Any = None,
) -> None:
    """任务取消后有界等待环境准备收尾。

    调用方已把取消令牌置位。准备若在 ``grace_seconds`` 内以异常结束（安装被
    终止），直接返回；若恰好成功，释放拿到的租约。超过限期就不再等：收尾任务
    继续在后台跑，准备线程随 uv 子进程被杀而尽快结束。
    """

    async def release_after_prepare() -> None:
        try:
            prepared_after_cancel = await prepare_task
        except BaseException:
            return
        with suppress(Exception):
            await asyncio.to_thread(release, prepared_after_cancel)

    cleanup_task = asyncio.create_task(release_after_prepare())
    try:
        await asyncio.wait_for(asyncio.shield(cleanup_task), timeout=grace_seconds)
    except asyncio.TimeoutError:
        _ABANDONED_PREPARATION_CLEANUPS.add(cleanup_task)
        cleanup_task.add_done_callback(_ABANDONED_PREPARATION_CLEANUPS.discard)
        if send_log is not None:
            send_log(
                "[MaaFW Runner] 环境准备未能在 "
                f"{grace_seconds:g} 秒内响应取消，已放弃等待"
            )
    except asyncio.CancelledError:
        # 再次被取消：同样不再等，收尾留给后台任务。
        _ABANDONED_PREPARATION_CLEANUPS.add(cleanup_task)
        cleanup_task.add_done_callback(_ABANDONED_PREPARATION_CLEANUPS.discard)


class _MaaFWRunTimeoutError(RuntimeError):
    """worker 在宽限期内也没停下，宿主强杀了它。"""


class _MaaFWGameUpdateRequired(RuntimeError):
    """特调的游戏更新钩子判定客户端要手动更新：本用户本次判失败，不重试。"""


class _FrameworkLogWriter:
    """在专用线程中按提交顺序写入一次运行的框架日志。"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._queue: queue.Queue[tuple[str, str, str] | None] = queue.Queue()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._open_error: Exception | None = None
        self._write_error: Exception | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="maafw-framework-log-writer",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._open_error is not None:
            self.close()
            raise self._open_error

    def write(self, source: str, message: str) -> None:
        if self._thread is None:
            return
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S.%f")[:-3]
        try:
            self._queue.put((timestamp, source, str(message or "")))
        except Exception:
            return

    def close(self) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.join()
        self._queue.put(None)
        thread.join()
        self._thread = None
        if self._write_error is not None:
            raise RuntimeError(
                f"MaaFW 框架日志写入不完整: {self._write_error}"
            ) from self._write_error

    def _run(self) -> None:
        log_file: Any | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            log_file = self.path.open(
                "a",
                encoding="utf-8",
                buffering=1,
            )
        except Exception as exc:
            self._open_error = exc
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                try:
                    if item is None:
                        return
                    timestamp, source, message = item
                    cleaned = _clean_framework_output(message)
                    for line in cleaned.splitlines() or [""]:
                        try:
                            log_file.write(f"[{timestamp}] [{source}] {line}\n")
                        except Exception as exc:
                            if self._write_error is None:
                                self._write_error = exc
                            continue
                except Exception as exc:
                    if self._write_error is None:
                        self._write_error = exc
                finally:
                    self._queue.task_done()
        finally:
            try:
                log_file.close()
            except Exception as exc:
                if self._write_error is None:
                    self._write_error = exc


class MaaFWPluginAutoProxyTask(TaskExecuteBase):
    """MaaFW 插件版 AutoProxy 执行器。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: Any,
        user_config: Mapping[uuid.UUID, Any],
        emulator_manager: DeviceBase | None,
        project_update_logs: list[str] | None = None,
        signal_tracker: MaaFWSignalTracker | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.project_update_logs = list(project_update_logs or [])
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.project_path = resolve_maafw_project_root(
            str(self.script_info.script_id), self.script_config
        ).resolve()
        self.interface_model: MaaFWInterface | None = None
        self.base_run_plan: MaaFWRunPlan | None = None
        self.run_plan: MaaFWRunPlan | None = None
        self.cur_user_log: LogRecord | None = None
        # 运行前检查时本用户的日志还没建（特调钩子建计划时的提示就在这时候到），
        # 先攒在这里，prepare() 建好日志时并进去
        self._pending_user_log: list[str] = []
        # 与 MAA 等专项同口径：user_start_time 是本用户这一轮的开始（统计通知用），
        # cur_user_log_started_at 是当前这次尝试的开始（日志记录与 history 文件名用）
        self.user_start_time: datetime | None = None
        self.cur_user_log_started_at: datetime | None = None
        # 每次尝试的结构化结果：worker 回报的人话摘要、失败任务名（推送的时间线与结果行用，
        # 见 run_report）、完成清单（运行记录不可用时的退路）与失败截图。
        self._attempt_reports: list[dict[str, Any]] = []
        # on_crash 记下的异常原文：还没进第一次尝试就崩了时，推送靠它说原因
        self._crash_message: str | None = None
        # 当前这次尝试给用户看的称呼（「第 2 次尝试」「清理残留后的重新运行」），与日志开头
        # 那行同口径：通知的任务详情和失败截图标签用它，不用 _record_attempt 的内部序号——
        # 清理后的重跑不计入尝试次数，内部序号会比日志多 1。
        self._attempt_title: str | None = None
        self._history_temp = tempfile.TemporaryDirectory(prefix="mas-maafw-run-")
        self._history_attachments: dict[int, list[HistoryAttachmentInput]] = {}
        self._history_statuses: dict[int, HistoryStatus] = {}
        self._history_saved = False
        self._user_finalized = False
        self._user_teardown_pending = False
        self._notification_screenshots: list[tuple[str, bytes]] = []
        self.check_result = "-"
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.run_complete = False
        # 本用户运行期间的「保持显示开启」请求，见 main_task。
        self._display_hold: Any = None
        self.opened_emulator = False
        self.opened_game = False
        self.game_process_manager = ProcessManager()
        # 启动游戏前临时改写的 Unity 注册表分辨率，游戏关闭后恢复；None 表示没改
        self.game_resolution_override: UnityGameResolutionOverride | None = None
        # 本轮游戏刚启动的单调时钟时刻，据此算首个任务的最早下发时刻。只在游戏是刚
        # 启动的才记：桌面游戏是窗口出现那一刻（MAS 拉起、或接管时等到窗口冒出来），
        # 模拟器是 MAS 随模拟器把游戏拉到前台那一刻。None 表示游戏早就在跑。
        self.game_started_at: float | None = None
        # 模拟器冷启动游戏时为真：闸门改按「画面有内容 + 客体读盘停下来」放行，上限仍是
        # Game.WaitTime（加载页和动态标题都一直在动，像素判断分不出两者）。桌面路径始终为假。
        self.game_start_disk_quiet = False
        self.project_lock_key: str | None = None
        self.runner_process: asyncio.subprocess.Process | None = None
        self.pretask_process: asyncio.subprocess.Process | None = None
        # 正在进行的运行前设置清理（见 _terminate_pretask_process）
        self.pretask_cleanup: asyncio.Task[None] | None = None
        self._cached_adb_address: str | None = None
        self._cached_device_info: DeviceInfo | None = None
        self._cached_adb_path: str | None = None
        self._cached_adb_profile: MaaFWAdbControlProfile | None = None
        # 随模拟器拉起的游戏包名（空串表示没拉起），交给特调的游戏更新钩子
        self._launched_package_name = ""
        # 游戏更新钩子每个用户每次运行只调一次，重试重新开模拟器时不再查
        self._game_update_checked = False
        self.maafw_runtime_pool_root: Path | None = None
        self.maafw_runtime_pool_id: str | None = None
        # 本轮（整个脚本）的信号账：同一资源已确认维护时后续用户直接跳过，收尾时由
        # 管理器按「信号 + 资源」各发一条通知。管理器传入共享的一份。
        self.signal_tracker = signal_tracker or MaaFWSignalTracker()
        # 本用户这次运行命中的信号（worker 回报），决定收尾怎么结算。
        self.run_signal: str | None = None
        # 运行前检查发现同一资源本轮已确认在维护、本用户没启动就跳过。
        self.maintenance_skipped = False
        # 运行前检查时项目预约被占（手动更新、编辑页准备环境 / 导入），本用户没跑成。
        self.project_busy_skipped = False
        # 队列里 interface 已没有的任务名（项目更新改了 name），建计划时填，进任务报告
        self.missing_task_names: list[str] = []
        # 本次运行里各次尝试已完成的任务名（累计，按份数）：重试时剔掉特调声明的
        # skip_on_retry_entries；剔了什么每次重试开头按当前计划的 skippedTasks 写一行
        self._completed_this_run: list[str] = []
        # 已完成过、但在队列里有多份同名的任务名：重试时不剔、全部重跑，开头写一行说明
        self._retry_rerun_duplicates: list[str] = []
        # 本次尝试收到的原生 ERR 行（worker stdout / stderr，``[json=`` 起已丢）与本次运行的
        # 原生日志副本里的 ERR 行：资源包加载失败时据此说出具体原因，后者优先（见 resource_failure）。
        self._stdout_native_errors: list[str] = []
        self._attempt_native_errors: list[str] = []
        # 资源包加载失败后的发行包核对每个用户每次运行只做一次；清理过就额外再跑一次（不占重试
        # 次数），``_extra_attempts`` 记多出来的几次。
        self._release_check_done = False
        self._extra_attempts = 0
        self._release_check_task: asyncio.Task[Any] | None = None
        # 结构化运行记录（每次尝试一份）：worker 推的阶段 / 任务起止 + 宿主自己的阶段，
        # 进 history 的 data、调度台进度与推送里单列的原地打转 / 单任务超时。
        self._run_record = MaaFWRunRecorder()

    async def check(self) -> str:
        proxy_times = (
            self.cur_user_config.Data.ProxyTimes
            if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d")
            == self.curdate
            else 0
        )
        if (
            self.script_config.Run.ProxyTimesLimit != 0
            and proxy_times >= self.script_config.Run.ProxyTimesLimit
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限，跳过该用户"

        if not await self._try_enter_project_path():
            # 项目被占着没跑成：记「异常」而不是「跳过」。「跳过」不进异常用户，
            # 脚本会记「完成」、汇总是 0 完成 / 0 未完成，「仅失败时」也不推送。
            # 与 manager 层「正在切换版本，已跳过」同一口径。
            self.cur_user_item.status = "异常"
            self.project_busy_skipped = True
            if is_project_updating(self.project_path):
                return "项目正在更新，本次未运行该用户"
            return (
                "项目正被编辑页的准备运行环境、导入或另一次运行占用，本次未运行该用户"
            )

        keep_reservation = False
        try:
            loop = asyncio.get_running_loop()

            def send_plan_log(message: str) -> None:
                # 运行计划在工作线程里构建，特调钩子的用户日志要回到事件循环线程
                # 再写 script_info.log（与 send_runner_log 同一做法），否则撞上
                # 「no running event loop」，整份计划都算构建失败。
                loop.call_soon_threadsafe(self._append_log, message)

            try:
                # 特调建计划可能提交配置；取消后先等线程结束，不能让它越过 X 锁释放。
                build_task = asyncio.create_task(
                    asyncio.to_thread(self._load_run_state_for_check, send_plan_log)
                )
                try:
                    state = await asyncio.shield(build_task)
                except asyncio.CancelledError:
                    while not build_task.done():
                        try:
                            await asyncio.shield(build_task)
                        except asyncio.CancelledError:
                            continue
                        except Exception:
                            break
                    with suppress(Exception):
                        build_task.result()
                    raise
                (
                    self.interface_model,
                    self.base_run_plan,
                    self.run_plan,
                    game_path_error,
                ) = state
            except Exception as exc:
                self.cur_user_item.status = "异常"
                return f"无法构建 MaaFW 运行计划，请检查项目和任务配置: {exc}"

            if not self.run_plan.tasks:
                self.cur_user_item.status = "跳过"
                return _period_all_done_message(self.run_plan)

            # 本轮前面的用户已经撞上同一资源的停服维护：不再拉起游戏 / 模拟器，
            # 并进那条维护通知的用户列表。代理次数、上次状态都不动。
            maintenance = self.signal_tracker.maintenance(self.run_plan.resourceName)
            if maintenance is not None:
                maintenance.add_user(str(self.cur_user_uid), self.cur_user_item.name)
                self.cur_user_item.status = "跳过"
                self.maintenance_skipped = True
                return MAINTENANCE_SKIP_MESSAGE

            if self.run_plan.controllerType == "Adb":
                emulator_id = self.script_config.Emulator.Id
                emulator_index = self.script_config.Emulator.Index
                if emulator_id == "-" or emulator_index in ("", "-"):
                    self.cur_user_item.status = "异常"
                    return (
                        "当前 MaaFW controller 需要 ADB，请在脚本管理页选择模拟器和实例"
                    )
            elif game_path_error is not None:
                self.cur_user_item.status = "异常"
                return game_path_error

            # 项目自带的 MaaFramework 与本机架构不符时 worker 里必然加载失败；在这里先说清楚
            # （还没拉起游戏 / 模拟器），并按导入来源 Info.Path 判断重新导入能不能解决。
            architecture_error = await asyncio.to_thread(
                self._describe_runtime_architecture_mismatch
            )
            if architecture_error:
                self.cur_user_item.status = "异常"
                return architecture_error

            keep_reservation = True
            return "Pass"
        finally:
            if not keep_reservation:
                await self._release_project_path()

    def _describe_runtime_architecture_mismatch(self) -> str | None:
        source = str(self.script_config.Info.Path or "").strip()
        return describe_project_runtime_architecture_mismatch(
            self.project_path, source_path=Path(source) if source else None
        )

    async def prepare(self) -> None:
        start_time = datetime.now().astimezone()
        self.user_start_time = start_time
        self.cur_user_log_started_at = start_time
        self.cur_user_log = LogRecord()
        self.cur_user_item.add_log_record(start_time, self.cur_user_log)
        content = self.cur_user_log.content
        content.extend(self.project_update_logs)
        content.extend(self._pending_user_log)
        self._pending_user_log.clear()
        if content:
            self.script_info.log = "".join(content[-80:])
        # 窗口在这里重建，行号也得跟着回到这份日志的开头；更新日志本身就超过 80 行时，
        # 与 _append_log 用同一套算法把滑出去的行数补上。
        self.script_info.log_first_line = (
            sum(chunk.count("\n") for chunk in content[:-80]) + 1
        )

    async def main_task(self) -> None:
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.check_result = await self.check()
        if self.check_result != "Pass":
            # 也记一行后端日志：否则只有 WS 通知，事后日志里只见「任务开始」紧接「任务结束」。
            # 「异常」是失败，按 WARNING 记；「跳过」（次数用完、周期已完成）是正常分支。
            (logger.warning if self.cur_user_item.status == "异常" else logger.info)(
                f"MFW 用户运行前检查未通过（{self.cur_user_item.name}，{self.cur_user_item.status}）：{self.check_result}"
            )
            # 项目被占用不逐个弹窗：所有用户撞的是同一件事，10 个用户就弹 10 次、响 10 次
            # 提示音。与 embedded_manager._check 那条「整个脚本一句话跳过，别让每个用户在
            # runner_task 里各报一遍」同一用意；「异常」状态、本用户日志与统计
            # 照常记（见下面与 final_task），汇总与「仅失败时」推送照常带上它。
            if self.cur_user_item.status == "异常" and not self.project_busy_skipped:
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=(
                            f"用户 {self.cur_user_item.name} 检查未通过: "
                            f"{self.check_result}"
                        ),
                    ),
                )
            if self.maintenance_skipped or self.project_busy_skipped:
                # 同一资源已确认在维护、或项目被占用没跑成：记一份本用户的日志，让代理
                # 结果汇总与统计信息写明原因（其他跳过原因照旧不记），未派发用户不建历史。
                # 前面拿到的运行前更新日志也随这份内存日志保留。
                # 窗口与行号由 _append_log 按本用户日志算好（前面可能还有更新日志与
                # 检查阶段的特调提示），不再改写成只剩这一行
                await self.prepare()
                self._append_log(self.check_result)
                if self.cur_user_log is not None:
                    self.cur_user_log.status = self.check_result
            else:
                # 没有本用户的日志：窗口只剩检查结果这一行，行号回到 1，
                # 不接着上一个用户的行号往下数
                self.script_info.log_first_line = 1
                self.script_info.log = self.check_result
            return

        await self._mark_run_started()
        await self.prepare()
        self.cur_user_item.status = "运行"
        logger.info(f"开始代理 MaaFW 用户: {self.cur_user_uid}")
        if self.run_plan is not None:
            selected_preset = str(
                self.cur_user_config.Task.SelectedPreset or ""
            ).strip()
            self._append_log(
                _format_run_overview_log(
                    self.run_plan,
                    selected_preset=selected_preset,
                )
            )
            for warning in self.run_plan.warnings:
                self._append_log(f"MaaFW 运行计划提示: {warning}")

        # Windows 到点熄屏后，鹰角启动器这类网页界面不出画面，项目的运行前设置在里面什么都
        # 认不出（2026-10-17/18 生产 MaaEnd「🚀启动游戏（PC）」两晚失败，亮屏 5 秒即过）。
        # 整个用户运行期间保持显示开启，屏已熄就先叫醒；收尾时撤销，final_task 再兜一次。
        self._ensure_display_hold()
        self._user_teardown_pending = True
        # 执行任务前脚本（每用户仅一次，重试不重复跑）。
        # 用户后脚本和清理在受保护的 final_task 中配对执行。
        if self.cur_user_config.Info.IfScriptBeforeTask:
            await execute_script_task(
                self.cur_user_config.Info.ScriptBeforeTask, "脚本前任务"
            )

        # 上一次尝试的失败摘要与是否重启过客户端：新一次另起日志后界面从头显示，
        # 不在开头写一句，用户只看到「尝试次数: 2/3」，不知道为什么重来。
        previous_failure: str | None = None
        previous_restarted = False
        # 项目的运行前设置（interface pretask，如 MaaEnd 的「启动游戏（PC）」）放进每次
        # 尝试里：它自己失败要能重试；游戏被本轮的「关闭游戏」任务或重启关掉后，重试也要
        # 靠它重新拉起，否则第 2、3 次在找窗口那一步当场失败。
        pretasks_done = False
        # 上一次失败后 MAS 自己起的游戏 / 模拟器是否已关掉（关的时候报错也算：两个关闭
        # 函数不论成败都清掉 opened_*，下一轮会重新拉起），这时运行前设置要重跑
        client_reset = False
        # 资源包加载失败后换了载荷、立刻再跑的那一次不计入尝试次数：日志里不给它编号，之后的
        # 序号扣掉它，分母一律是用户配的 RunTimesLimit（用户配 3 次就是「x/3」）。
        # ``index + 1`` 仍是内部序号（_record_attempt、_reset_client_for_retry 用）。
        rerun_note: tuple[str, str] | None = None
        previous_label = ""
        index = -1
        while True:
            # 不用 range：资源包加载失败后清理过载荷时额外再跑一次（_extra_attempts），上限会变。
            index += 1
            if index >= self._attempt_limit() or self.run_complete:
                break

            # 每次尝试单独一份日志（界面与 history 都分开）：第一次沿用 prepare()
            # 建的那份，开头有更新检查与运行总览；之后每次另起。
            if index > 0:
                self._start_attempt_log()

            if rerun_note is not None:
                header, current_label = rerun_note
                self._append_log(f"用户 {self.cur_user_item.name} - {header}")
                rerun_note = None
                self._attempt_title = current_label
            else:
                ordinal = index + 1 - self._extra_attempts
                self._append_log(
                    f"用户 {self.cur_user_item.name} - 尝试次数: "
                    f"{ordinal}/{self.script_config.Run.RunTimesLimit}"
                )
                current_label = f"第 {ordinal} 次"
                self._attempt_title = f"{current_label}尝试"
            if index > 0 and previous_failure:
                self._append_log(
                    f"上一次（{previous_label}）：{previous_failure}"
                    + ("，已重启游戏/模拟器" if previous_restarted else "")
                )
            previous_label = current_label
            self._begin_run_record_attempt(index + 1)

            try:
                if index > 0:
                    self._log_retry_skipped_tasks()
                if self.run_plan is None or self.interface_model is None:
                    raise RuntimeError("MaaFW 运行计划尚未初始化")
                self._ensure_display_hold()
                if not pretasks_done or await self._pretasks_need_rerun(client_reset):
                    # 先清标记：重跑到一半失败时，下一轮不能因为窗口已被拉起就跳过
                    pretasks_done = False
                    # 计划里没有运行前设置时不记这一段（getattr：记录是旁路，不多读计划）
                    with self._run_record.stage(
                        STAGE_PRETASK,
                        enabled=bool(getattr(self.run_plan, "pretasks", None)),
                    ):
                        await self._run_pretasks()
                    pretasks_done = True
                with self._run_record.stage(STAGE_CLIENT):
                    await self._ensure_desktop_game_started()
                    device_config = await self._build_device_config(
                        self.run_plan,
                        self.interface_model,
                    )
                result = await self._run_maafw(device_config)
            except _MaaFWGameUpdateRequired as exc:
                # 游戏客户端要手动更新：重试多少次都一样，本用户本次直接判失败。
                # 说明已由 _ensure_game_updated 写进运行日志，这里不再重复。
                message = str(exc)
                self._record_attempt(
                    index + 1, [], message, category=CATEGORY_GAME_UPDATE_REQUIRED
                )
                if self.cur_user_log is not None:
                    self.cur_user_log.status = message
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=message),
                )
                with suppress(Exception):
                    await Notify.send_notice(
                        LocalNotice(
                            title="游戏需要手动更新！",
                            message=message,
                            ticker=f"{self.cur_user_item.name}的游戏需要手动更新",
                            duration_seconds=3,
                        )
                    )
                break
            except Exception as exc:
                message = (
                    str(exc)
                    if isinstance(exc, MaaFWPretaskError)
                    else f"MaaFW 运行异常: {exc}"
                )
                self._append_log(message, warning=True)
                unretryable = _is_unretryable_failure(message)
                self._record_attempt(
                    index + 1,
                    [],
                    message,
                    # 宿主自己抛的多是 MAS 写的人话（「当前 controller 需要 ADB，请在脚本管理页
                    # 选择模拟器」「Path未配置」），推送照它说；带的排障片段由 run_report 滤掉。
                    # 整次运行超时有固定说法，不用异常原文
                    user_message=(
                        None if isinstance(exc, _MaaFWRunTimeoutError) else str(exc)
                    ),
                    category=(
                        CATEGORY_PRETASK_FAILED
                        if isinstance(exc, MaaFWPretaskError)
                        else CATEGORY_RUN_TIMEOUT
                        if isinstance(exc, _MaaFWRunTimeoutError)
                        else CATEGORY_ENVIRONMENT
                        if unretryable
                        else CATEGORY_HOST_ERROR
                    ),
                )
                if unretryable:
                    self._append_log(
                        "运行环境不可用，重试也不会有别的结果，已停止本轮",
                        warning=True,
                    )
                if self.cur_user_log is not None:
                    self.cur_user_log.status = message
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=message),
                )
                if unretryable:
                    break
                previous_failure = message
                (
                    previous_restarted,
                    client_reset,
                ) = await self._reset_client_for_retry(index + 1)
                continue

            await self._mark_period_tasks_completed(result.completedTasks)
            if result.signal is not None:
                # 项目声明的信号节点命中：停服维护 = 本次跳过，需要更新客户端 = 失败；
                # 两种都是重试多少次都一样，不重启游戏 / 模拟器，直接收尾。
                await self._finish_on_signal(index + 1, result)
                break
            if result.success:
                self.run_complete = True
                if self.cur_user_log is not None:
                    self.cur_user_log.status = "Success!"
                completed_task_labels = _format_completed_task_labels(
                    self.run_plan,
                    result.completedTasks,
                )
                self._append_log("MaaFW 任务完成: " + ", ".join(completed_task_labels))
                self._record_attempt(index + 1, completed_task_labels, None)
            else:
                if result.resourceFailure is not None:
                    # 资源包没能加载：原因只在原生 ERR 行里，换成一句人话（取不到才保留
                    # 「详见 .maafw.log」）。
                    message = await asyncio.to_thread(
                        describe_resource_failure,
                        result.resourceFailure.kind,
                        result.resourceFailure.path,
                        self._attempt_native_errors,
                        project_root=self.project_path,
                        secrets=self._secret_log_variants(),
                    )
                elif result.timedOut:
                    message = self._timed_out_user_summary(result)
                else:
                    message = _failed_task_user_summary(result, self.run_plan)
                    retry_skipped = (
                        sum(
                            1
                            for skipped in self.run_plan.skippedTasks
                            if skipped.reason == _RETRY_SKIP_REASON
                        )
                        if self.run_plan is not None
                        else 0
                    )
                    total = (
                        len(self.run_plan.tasks) + retry_skipped
                        if self.run_plan is not None
                        else 0
                    )
                    done = len(result.completedTasks) + retry_skipped
                    if total > 1 and done > 0:
                        message += f"（共 {total} 个任务，完成 {done} 个）"
                if self.cur_user_log is not None:
                    self.cur_user_log.status = message
                self._append_log(message, warning=True)
                self._record_attempt(
                    index + 1,
                    _format_completed_task_labels(self.run_plan, result.completedTasks),
                    message,
                    user_message=result.userMessage,
                    failed_task=result.failedTask,
                    screenshots=[
                        (
                            _format_completed_task_labels(self.run_plan, [shot.task])[
                                0
                            ],
                            Path(shot.path),
                        )
                        for shot in result.failureScreenshots
                    ],
                    category=_result_failure_category(result),
                )
                if result.resourceFailure is not None:
                    # 不重启游戏 / 模拟器：资源加载失败不改变游戏状态，换载荷也不碰它们。
                    # 只有刚把载荷里的旧版本残留清掉、视图换过时立刻再跑一次（不占重试次数）。
                    rerun_note = await self._recover_resource_failure(
                        result.resourceFailure.kind
                    )
                    if rerun_note is not None:
                        self._extra_attempts += 1
                        previous_failure = message
                        previous_restarted = False
                        client_reset = False
                        continue
                    break
                if _is_unretryable_failure(result.errorMessage or ""):
                    # worker 在任务里报的环境级失败（如原生库架构不符）：每轮都一样，
                    # 不再为它起停模拟器 / 游戏重试。
                    self._append_log(
                        "运行环境不可用，重试也不会有别的结果，已停止本轮",
                        warning=True,
                    )
                    break
                await self._refresh_run_plan_after_period_update(result.completedTasks)
                if self.run_plan is not None and not self.run_plan.tasks:
                    self.run_complete = True
                    # 计划被重试跳过剔空的，不能说成「周期任务」
                    self._append_log(
                        "MaaFW 剩余任务都已完成，停止本轮重试"
                        if _retry_skipped_tasks(self.run_plan)
                        else "MaaFW 剩余周期任务已完成，停止本轮重试"
                    )
                else:
                    previous_failure = message
                    (
                        previous_restarted,
                        client_reset,
                    ) = await self._reset_client_for_retry(index + 1)

    async def final_task(self) -> None:
        if self._user_finalized:
            return
        self._user_finalized = True
        self.task_info.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=self.check_result == "Pass"
            and not self.run_complete
            and self.run_signal != SERVER_MAINTENANCE
            and not self.stopped_manually,
        )
        try:
            await self._finalize_user()
        except Exception as error:
            if not self._history_saved:
                with suppress(Exception):
                    await self.on_crash(error)
            raise
        finally:
            try:
                if not self._history_saved:
                    await self._save_user_history()
            finally:
                await asyncio.to_thread(self._history_temp.cleanup)

    async def _finalize_user(self) -> None:
        if self._user_teardown_pending:
            self._user_teardown_pending = False
            # 后脚本可能仍需使用模拟器，必须先完成，再关闭资源与保存历史。
            if self.cur_user_config.Info.IfScriptAfterTask:
                await execute_script_task(
                    self.cur_user_config.Info.ScriptAfterTask, "脚本后任务"
                )
        self._release_display_hold()
        await self._shutdown_runner()
        if self.check_result != "Pass":
            if self.maintenance_skipped:
                # 维护连带跳过：同样是跳过不是失败，代理次数不动；上次状态
                # 与统计信息都写明原因。
                self.cur_user_config.Data.LastProxyStatus = MAINTENANCE_LAST_STATUS
                await self.cur_user_config.commit()
                await self._save_user_history()
                await self._push_user_statistics()
            elif self.project_busy_skipped:
                # 没跑成：统计信息写明原因；代理次数与上次状态不动。
                await self._save_user_history()
                await self._push_user_statistics()
            await self._release_project_path()
            return

        await self._close_emulator()
        await self._close_game()
        if self.run_complete:
            if (
                self.cur_user_config.Data.ProxyTimes == 0
                and self.cur_user_config.Info.RemainedDay != -1
            ):
                self.cur_user_config.Info.RemainedDay = (
                    self.cur_user_config.Info.RemainedDay - 1
                )
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = (
                self.cur_user_config.Data.ProxyTimes + 1
            )
            await self.cur_user_config.commit()
            self.cur_user_config.Data.LastProxyStatus = "成功"
            await self.cur_user_config.commit()
            self.cur_user_item.status = "完成"
        elif self.run_signal == SERVER_MAINTENANCE:
            # 维护是跳过不是失败：代理次数、剩余天数不动，下次定时照常再跑
            self.cur_user_config.Data.LastProxyStatus = MAINTENANCE_LAST_STATUS
            await self.cur_user_config.commit()
            self.cur_user_item.status = "跳过"
        else:
            self.cur_user_config.Data.LastProxyStatus = "失败"
            await self.cur_user_config.commit()
            if self.cur_user_item.status == "运行":
                self.cur_user_item.status = "异常"

        await self._save_user_history()
        if self.run_complete:
            await self._send_success_notify()
        await self._push_user_statistics()
        await self._release_project_path()

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        self.cur_user_item.progress = None
        logger.exception(f"MaaFW 内置运行任务出现异常: {e}")
        # 还没进第一次尝试就崩了（prepare、脚本前任务出错）时推送靠它说原因
        self._crash_message = str(e)
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"MaaFW 内置运行任务出现异常: {e}"
            if self.cur_user_log_started_at is not None:
                self._history_statuses[id(self.cur_user_log)] = "error"
        try:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"MaaFW 内置运行任务出现异常: {e}",
                ),
            )
        except Exception:
            pass
        await self._shutdown_runner()
        await self._close_emulator()
        await self._close_game()
        await self._release_project_path()

    def _mas_manages_game_launch(self) -> bool:
        """MAS 是否负责启动/关闭游戏。

        只有两种模式：DirectExe（默认；MAS 启动，结束后一律由 MAS 关闭）与
        AttachOnly（脚本或用户自己启停，MAS 只接管窗口、不启动也不关闭）。
        此前这里根本没读过 LaunchMode，Win32 controller 无论哪种模式都强制索要 exe。
        配置激活后 LaunchMode 一定有默认值，这里的兜底
        只是防御性的。
        """

        mode = str(self.script_config.Game.LaunchMode or "DirectExe").strip()
        return mode != "AttachOnly"

    def _resolve_game_launch_path(self) -> Path | None:
        """DirectExe 模式下 MAS 要启动的客户端 exe。"""

        raw = str(self.script_config.Game.LaunchPath or "").strip()
        return Path(raw) if raw else None

    def _load_run_state_for_check(
        self,
        send_log: Callable[[str], None] | None = None,
    ) -> tuple[MaaFWInterface, MaaFWRunPlan, MaaFWRunPlan, str | None]:
        interface_model = MaaFWInterfaceService().load(self.project_path)
        base_run_plan = self._build_run_plan(interface_model, send_log=send_log)
        run_plan = self._filter_period_once_tasks(base_run_plan)

        game_path_error: str | None = None
        if (
            run_plan.tasks
            and run_plan.controllerType == "Win32"
            and (not _optional_int(self.script_config.Device.HWnd))
            and (
                not controller_has_window_rules(
                    _find_controller(interface_model, run_plan.controllerName)
                )
            )
        ):
            # 控制器一条窗口匹配规则都没写，又没指定句柄：以前会随便抓桌面上第一个窗口。
            # 在拉起游戏之前就报。
            game_path_error = _WIN32_NO_WINDOW_RULES_MESSAGE
        elif (
            run_plan.tasks
            and run_plan.controllerType == "Win32"
            and self._mas_manages_game_launch()
        ):
            game_path = self._resolve_game_launch_path()
            if game_path is None or not game_path.is_file():
                game_path_error = "当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe"
        return interface_model, base_run_plan, run_plan, game_path_error

    def _build_run_plan(
        self,
        interface_model: MaaFWInterface,
        *,
        send_log: Callable[[str], None] | None = None,
    ) -> MaaFWRunPlan:
        # 不看 Info.IfQuickConfig：MaaFW 没有可退回的原生配置，用户页上配的任务队列就是
        # 唯一的任务来源。开关在界面上已经不提供，这里若还读它，被隐藏的旧值会让页面上
        # 能改、运行时却不生效。
        task_snapshot = _load_json_dict(self.cur_user_config.Task.TaskSnapshot)
        selected_preset = str(self.cur_user_config.Task.SelectedPreset or "").strip()
        controller_name, resource_name = self._select_run_selection(interface_model)
        effective_preset = (
            selected_preset if selected_preset and not task_snapshot else None
        )
        # 特调类型（脚本配置类声明了 FLAVOR）：先把快照归一化成实例 id 列表，交给
        # 钩子装饰（首尾任务、切号绑定之类），再按装饰后的列表建计划。通用 MaaFW
        # 没有钩子，仍按快照直接建计划，行为不变。
        flavor = resolve_flavor(self.script_config)
        # 脚本级键位（Game.Hotkeys）：坏 JSON / 不是对象当空，字段级的校验在建计划时做。
        script_hotkeys = _load_script_hotkeys(self.script_config.Game.Hotkeys)
        missing_skips: list[MaaFWSkippedTaskPlan] = []
        unselectable_names: list[str] = []
        try:
            # 密码字段（PI v2.10.0）在配置里是密文，只在这份内存副本里解开交给计划；
            # 用户配置本身不动，运行后的整表写回也就写不出明文。
            task_snapshot = open_task_snapshot(task_snapshot, interface_model)
            # 项目更新改了任务 name 后，队列里的旧 id 在归一化时就被滤掉了，运行日志里
            # 一点痕迹都没有。先按原始快照把它们找出来，建完计划记成跳过。
            missing_names = find_missing_task_names(task_snapshot, interface_model)
            missing_skips = [
                MaaFWSkippedTaskPlan(name=name, reason="interface 内已无该任务")
                for name in missing_names
            ]
            self.missing_task_names = list(dict.fromkeys(missing_names))
            # 项目改了 case 名后，保存的值在归一化时被静默换回默认值；同样先按原始快照找出来，
            # 进计划的提示（运行日志开头列出）
            stale_warnings: list[str] = []
            if task_snapshot:
                try:
                    stale_warnings = describe_stale_option_values(
                        self.project_path, interface_model, task_snapshot
                    )
                except Exception:  # noqa: BLE001 - 只是提示，算不出来不挡运行
                    logger.opt(exception=True).warning("MaaFW 失效选项值检查失败")
            # 运行日按本机今天的星期判（与队列「执行日期」同口径），只在开跑建计划时判这一次：
            # 结果固化在 base_run_plan 里，重试从它重建、不再重判，跨零点重试也不翻
            # 今天不跑的实例与红灯一样在建计划之前排除，不校验它们的选项（坏配置不挡整轮）
            iso_weekday = datetime.now().isoweekday()
            off_day_ids = excluded_task_ids_for_weekday(task_snapshot, iso_weekday)
            off_day_reason = (
                f"今天{_WEEKDAY_NAMES[iso_weekday - 1]}{_OFF_DAY_REASON_SUFFIX}"
            )
            if flavor is None:
                plan = MaaFWRunnerService().build_plan(
                    self.project_path,
                    interface_model,
                    controller_name=controller_name,
                    resource_name=resource_name,
                    selected_preset=effective_preset,
                    task_snapshot=task_snapshot or None,
                    script_hotkeys=script_hotkeys,
                    excluded_task_reasons=dict.fromkeys(off_day_ids, off_day_reason),
                )
                return _with_skipped_tasks(
                    _with_warnings(plan, stale_warnings), missing_skips
                )
            task_ids, task_options, global_options = select_snapshot_tasks(
                interface_model,
                selected_preset=effective_preset,
                task_snapshot=task_snapshot or None,
            )
            # 特调声明不可选的任务先剔：装饰钩子看到的就是剔完的队列（剔空了它不补首尾）
            task_ids, task_options = _drop_unselectable_tasks(
                interface_model,
                task_ids,
                task_options,
                unselectable_entries(flavor),
                send_log=send_log if send_log is not None else logger.info,
                dropped_names=unselectable_names,
            )
            # 今天不在运行日的实例不交给装饰钩子：钩子看到的是今天真要跑的队列（剔空了 M9A
            # 就不补启动 / 关闭游戏）。钩子自己按固定规则补回的同一实例（受管任务）照常跑，
            # 不受运行日影响；其余的仍按原位置交给核心，由核心在建计划前排除、记成跳过
            # （不校验选项），全被排除时计划为空。引擎判出的集合经 off_day_scope 交给钩子，
            # 钩子另读快照自动补任务时用它，不必自己再判一次星期。
            off_day_set = set(off_day_ids) & set(task_ids)
            with off_day_scope(off_day_ids):
                decorated_ids, decorated_options = flavor.decorate_selection(
                    interface_model,
                    [task_id for task_id in task_ids if task_id not in off_day_set],
                    {
                        key: value
                        for key, value in task_options.items()
                        if key not in off_day_set
                    },
                    script_config=self.script_config,
                    user_config=self.cur_user_config,
                    resource_name=resource_name,
                    # 本方法在工作线程里跑：没给线程安全的回调就只进后端日志。
                    send_log=send_log if send_log is not None else logger.info,
                )
            off_day_set -= set(decorated_ids)
            off_day_extra = [task_id for task_id in task_ids if task_id in off_day_set]
            task_ids = [*decorated_ids, *off_day_extra]
            task_options = {
                **decorated_options,
                **{
                    task_id: task_options[task_id]
                    for task_id in off_day_extra
                    if task_id in task_options
                },
            }
            plan = MaaFWRunnerService().build_plan(
                self.project_path,
                interface_model,
                controller_name=controller_name,
                resource_name=resource_name,
                # 特调路径把已选任务拆成 task_ids 交给核心；仍带上原始快照，
                # 让核心把用户显式设为跳过的实例写进 skippedTasks。
                task_snapshot=task_snapshot,
                task_ids=task_ids,
                task_options=task_options,
                global_options=global_options,
                script_hotkeys=script_hotkeys,
                # 从密文解出来的字段单独交过去，保留特调路径的密码处理口径
                secret_inputs=(task_snapshot or {}).get(SECRET_INPUTS_SNAPSHOT_KEY),
                # 特调声明不回落 default 的字符串字段（M9A 的自定义兑换码）
                no_default_fallback_inputs=no_default_fallback_inputs(flavor),
                excluded_task_reasons=dict.fromkeys(off_day_extra, off_day_reason),
            )
            plan = _mark_nonfatal_tasks(_mark_abort_round_tasks(plan, flavor), flavor)
            return _with_skipped_tasks(
                _with_warnings(plan, stale_warnings), missing_skips
            )
        except Exception as exc:
            message = str(exc)
            if (
                NO_RUNNABLE_TASKS_MESSAGE in message
                or ALL_TASKS_SKIPPED_MESSAGE in message
            ):
                # 队列里只剩虚影时「没有可执行任务」说不清原因，把对不上的任务名带上；
                # 只剩不可选任务时同理（前面的「已跳过」行在用户日志里，报错里看不到）。
                # 别的报错（拆用户、找不到 controller……）与它们无关，不附加
                if missing_skips:
                    names = "、".join(
                        dict.fromkeys(item.name for item in missing_skips)
                    )
                    message = f"{message}（interface 内已无：{names}）"
                if unselectable_names:
                    names = "、".join(unselectable_names)
                    message = f"{message}（已跳过不可选任务：{names}）"
            raise MaaFWRunPlanError(message) from exc

    def _select_run_selection(
        self, interface_model: MaaFWInterface
    ) -> tuple[str | None, str | None]:
        """``(交给建计划的 controller 名, 实际生效的 resource 名)``，口径见 ``resolve_run_selection``。

        用户在脚本页显式选的 controller 优先。这里曾把「配了模拟器」排在前面，于是先在 ADB
        模式下选过模拟器、之后把控制方式改成 Win32 的用户会被静默改回 ADB：Emulator.Id 还留着
        旧值（Win32 分支下模拟器下拉被隐藏，用户没有入口清它），运行时回落到第一个 Adb
        controller，按 Win32 编排的任务被 run_plan 过滤掉，或者直接报「当前 controller/resource
        下没有可执行任务」。特调在保存与启动期整理用户配置时用同一个函数判资源。
        """

        return resolve_run_selection(
            interface_model,
            configured_controller=str(self.script_config.Info.Controller or ""),
            emulator_selected=self.script_config.Emulator.Id != "-",
            configured_resource=str(self.script_config.Info.Resource or ""),
        )

    async def _build_device_config(
        self,
        plan: MaaFWRunPlan,
        interface_model: MaaFWInterface,
    ) -> MaaFWDeviceConfig:
        if plan.controllerType == "Adb":
            address, device_info = await self._resolve_adb_address()
            adb_path = await self._resolve_adb_path(address, device_info)
            await self._ensure_game_updated(address, adb_path)
            adb_profile = await self._build_adb_control_profile()
            return MaaFWDeviceConfig(
                type="Adb",
                adbPath=adb_path,
                address=address,
                screencapMethods=self._resolve_adb_screencap_methods(adb_profile),
                inputMethods=self._resolve_adb_input_methods(adb_profile),
                config=adb_profile.config,
                adbReadyTimeout=self._resolve_adb_ready_timeout(),
                emulatorPid=getattr(device_info, "process_id", None),
                emulatorStartedAt=getattr(device_info, "process_started_at", None),
            )

        if plan.controllerType == "Win32":
            controller = _find_controller(interface_model, plan.controllerName)
            win32_config = controller.win32
            mouse = win32_config.mouse if win32_config else None
            keyboard = win32_config.keyboard if win32_config else None
            if mouse is None and keyboard is None and win32_config is not None:
                # MFAA 的写法：只写 input 时鼠标、键盘都用它
                mouse = keyboard = win32_config.input
            return MaaFWDeviceConfig(
                type="Win32",
                hWnd=await self._resolve_window_handle(controller),
                screencapMethod=_resolve_win32_method(
                    self.script_config.Device.Win32ScreencapMethod,
                    win32_config.screencap if win32_config else None,
                    _WIN32_SCREENCAP_METHODS,
                    "DXGI_DesktopDup",
                    label=f"controller {controller.name} 的 Win32 截图方式",
                    warn=self._append_log,
                    combinable=True,
                ),
                mouseMethod=_resolve_win32_method(
                    self.script_config.Device.Win32MouseMethod,
                    mouse,
                    _WIN32_INPUT_METHODS,
                    "Seize",
                    label=f"controller {controller.name} 的 Win32 鼠标输入方式",
                    warn=self._append_log,
                ),
                keyboardMethod=_resolve_win32_method(
                    self.script_config.Device.Win32KeyboardMethod,
                    keyboard,
                    _WIN32_INPUT_METHODS,
                    "Seize",
                    label=f"controller {controller.name} 的 Win32 键盘输入方式",
                    warn=self._append_log,
                ),
            )

        raise RuntimeError(f"当前仅支持 Adb/Win32 controller: {plan.controllerType}")

    async def _resolve_game_package(self) -> str:
        """这次要不要顺带把游戏拉起来，拉哪个包。返回空串表示只开模拟器。

        脚本配置里填了就以它为准：从项目里认包名是启发式的（``StartApp`` 只是约定，
        不是 interface 规格里的字段），用户必须有办法推翻它。

        认不出来不是错误——很多项目本来就自己在 pipeline 里开游戏。但要让用户看得见
        为什么没启动，否则「填了没反应」和「没填也没反应」在界面上长得一模一样。
        """
        manual = str(self.script_config.Game.PackageName or "").strip()
        if manual:
            self._append_log(f"游戏包名: {manual}（脚本配置）")
            return manual

        if self.run_plan is None:
            return ""

        resolution = await asyncio.to_thread(
            resolve_game_package,
            [
                Path(item.resolved)
                for item in self.run_plan.resource.paths
                if item.exists and item.isDir
            ],
            [
                task.pipelineOverride
                for task in self.run_plan.tasks
                if task.pipelineOverride
            ],
        )

        if resolution.reason == "resolved":
            self._append_log(f"游戏包名: {resolution.package}（从项目识别）")
            return resolution.package

        if resolution.reason == "ambiguous":
            self._append_log(
                f"项目里识别到多个游戏包名（{'、'.join(resolution.candidates)}），"
                "无法确定用哪个，本次不随模拟器启动游戏；"
                "需要的话在脚本管理页填写游戏包名"
            )
        else:
            self._append_log(
                "未能从项目里识别出游戏包名，本次不随模拟器启动游戏；"
                "需要的话在脚本管理页填写游戏包名"
            )
        return ""

    async def _resolve_adb_address(self) -> tuple[str, DeviceInfo | None]:
        if self._cached_adb_address is not None:
            return self._cached_adb_address, self._cached_device_info
        if self.emulator_manager is None:
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器")

        emulator_index = self.script_config.Emulator.Index
        if emulator_index in ("", "-"):
            raise RuntimeError("当前 controller 需要 ADB，请在脚本管理页选择模拟器实例")

        package_name = await self._resolve_game_package()
        self._launched_package_name = package_name
        self._append_log(f"正在启动模拟器: {emulator_index}")
        self.opened_emulator = True
        device_info = await self.emulator_manager.open(
            emulator_index, package_name, **self._mod_avd_open_kwargs()
        )
        # 只有冷启动（进程原本不在，launched）才等：进程本来就在（在前台 already-running、
        # 从后台切回 resumed）、没给包名、拉起失败都不等；旧式模拟器管理器不回报拉应用
        # 结果，同样不等
        if getattr(device_info, "app_launch", "") == "launched":
            self.game_started_at = time.monotonic()
            self.game_start_disk_quiet = True
            self._append_log(f"已随模拟器启动游戏: {package_name}")
        else:
            self.game_started_at = None
            self.game_start_disk_quiet = False
        if Config.setting.Function.IfSilence:
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        if not device_info.adb_address or device_info.adb_address == "Unknown":
            raise RuntimeError("模拟器未返回可用 ADB 地址")

        self._cached_adb_address = device_info.adb_address
        self._cached_device_info = device_info
        self._append_log(f"模拟器启动完成，ADB 地址: {device_info.adb_address}")
        return device_info.adb_address, device_info

    async def _resolve_adb_path(
        self,
        address: str,
        device_info: DeviceInfo | None,
    ) -> str | None:
        if self._cached_adb_path is not None:
            return self._cached_adb_path
        configured_path = str(self.script_config.Device.AdbPath or "").strip()
        if configured_path and Path(configured_path).exists():
            self._cached_adb_path = configured_path
            self._append_log(f"ADB 路径选择: 脚本配置; 路径={configured_path}")
            return configured_path
        if configured_path:
            self._append_log(
                f"脚本配置的 ADB 路径不存在，继续自动解析: {configured_path}"
            )

        manager = self.emulator_manager
        get_adb_path = getattr(manager, "get_adb_path", None)
        if callable(get_adb_path):
            with suppress(Exception):
                manager_adb_path = get_adb_path()
                if manager_adb_path is not None:
                    manager_adb_path = Path(manager_adb_path)
                    if manager_adb_path.exists():
                        self._cached_adb_path = str(manager_adb_path)
                        self._append_log(
                            "ADB 路径选择: MAS 模拟器管理器; "
                            f"路径={self._cached_adb_path}"
                        )
                        return self._cached_adb_path

        derived_path = self._derive_adb_path_from_emulator_config()
        if derived_path is not None and derived_path.exists():
            self._cached_adb_path = str(derived_path)
            self._append_log(
                f"ADB 路径选择: 模拟器安装目录; 路径={self._cached_adb_path}"
            )
            return self._cached_adb_path

        title = f"（{device_info.title}）" if device_info else ""
        self._append_log(
            f"主程序未解析到 ADB 路径{title}，将由 MaaFW Runner 按设备地址发现"
        )
        return None

    async def _ensure_game_updated(self, address: str, adb_path: str | None) -> None:
        """模拟器启动后、第一个任务下发前，调特调的游戏更新钩子（契约见 flavor.py）。

        每个用户每次运行只调一次。钩子判定要手动更新时抛 ``_MaaFWGameUpdateRequired``，
        由 main_task 判失败且不重试；钩子自己出错只记警告，照常运行。
        """

        if self._game_update_checked:
            return
        self._game_update_checked = True
        mode = str(self.script_config.Run.GameUpdateMode or "Off")
        hook = resolve_game_update_hook(self.script_config)
        if mode == "Off" or hook is None or self.run_plan is None:
            return

        async def report(text: str) -> None:
            self._append_log(text)

        self._append_log("正在检查游戏客户端更新")
        try:
            # 魔改 AVD 实例：钩子在宿主进程里调 adb（game_apk），改走 MAS 私有 server，
            # 不落到 5037；其余模拟器不接管
            with _utils_game_apk.adb_runner_scope(await resolve_host_adb(self)):
                result = await hook(
                    script_config=self.script_config,
                    resource_name=self.run_plan.resourceName,
                    package_name=self._launched_package_name,
                    adb_path=adb_path,
                    adb_address=address,
                    if_auto_install=mode == "AutoInstall",
                    progress=report,
                )
        except Exception as exc:
            logger.opt(exception=True).warning(f"游戏更新检查异常: {exc}")
            self._append_log(f"游戏更新检查出错，本次照常运行: {exc}")
            return

        self._append_log(result.message)
        if result.status == "NeedManualUpdate":
            raise _MaaFWGameUpdateRequired(result.message)

    def _derive_adb_path_from_emulator_config(self) -> Path | None:
        emulator_id = self.script_config.Emulator.Id
        if emulator_id == "-":
            return None

        # 一条配置可以纳管多个模拟器安装, 那种情况下持久化的 Info.Path 是空的,
        # 得先问管理器这个设备号落在哪条安装上。
        emulator_index = self.script_config.Emulator.Index
        with suppress(Exception):
            resolve_device = getattr(self.emulator_manager, "resolve_device", None)
            if resolve_device is not None and emulator_index not in ("", "-"):
                device_ref = resolve_device(emulator_index)
                if device_ref is not None and device_ref.emulator_type == "avd":
                    # 魔改 AVD 的 adb 在 SDK 的 platform-tools 里（认 sdkRoot），不在主程序旁边
                    return _avd_adb_path(device_ref.manager_path)
                if device_ref is not None and device_ref.manager_path:
                    return Path(device_ref.manager_path).parent / "adb.exe"

        with suppress(Exception):
            emulator_config = Config.EmulatorConfig[emulator_id]
            emulator_path = emulator_config.Info.Path
            if emulator_path is None:
                return None
            return emulator_path.parent / "adb.exe"
        return None

    async def _build_adb_control_profile(self) -> MaaFWAdbControlProfile:
        """解析当前模拟器的 EmulatorExtras 能力，并构造 MuMu/雷电 controller extras 配置。"""
        if self._cached_adb_profile is not None:
            return self._cached_adb_profile

        emulator_id = self.script_config.Emulator.Id
        emulator_index = self.script_config.Emulator.Index
        if emulator_id == "-" or emulator_index in ("", "-"):
            self._cached_adb_profile = MaaFWAdbControlProfile(None, False, False, {})
            return self._cached_adb_profile

        # 魔改 AVD 在下面的 try 之外：它没有退回默认配置这条路（截图不许回落到普通 adb），
        # 构造不出 AVDExtras 配置就直接报错
        avd_ref = None
        with suppress(Exception):
            resolve_device = getattr(self.emulator_manager, "resolve_device", None)
            avd_ref = resolve_device(emulator_index) if resolve_device else None
        if avd_ref is not None and avd_ref.emulator_type == "avd":
            self._cached_adb_profile = self._build_avd_adb_profile(avd_ref)
            return self._cached_adb_profile

        try:
            # 先问管理器这个设备号的真实归属。持久化的 Info.Type 在纳管多个安装时
            # 不等于设备的真实类型, 直接读它会让雷电专用截图被跳过——而雷电上普通
            # ADB 截图取不到游戏的 GPU 渲染层, 识别会全程无命中。
            native_index = emulator_index
            resolve_device = getattr(self.emulator_manager, "resolve_device", None)
            device_ref = resolve_device(emulator_index) if resolve_device else None
            if device_ref is not None:
                emulator_type = device_ref.emulator_type
                emulator_path = Path(device_ref.manager_path)
                native_index = device_ref.native_index
            else:
                emulator_config = Config.EmulatorConfig[emulator_id]
                emulator_type = str(emulator_config.Info.Type or "")
                emulator_path = emulator_config.Info.Path
                if emulator_path is None:
                    raise ValueError("Path未配置，请检查路径设置")
            # build_adb_emulator_extra_capabilities 通过 find_spec 探测运行时 maa，
            # 不会把 maa 载入 sys.modules，满足导入边界约束；返回 {type: {screencap,input}}。
            capabilities = build_adb_emulator_extra_capabilities()
            capability = capabilities.get(emulator_type, {})
            screencap_extra = bool(capability.get("screencap", False))
            input_extra = bool(capability.get("input", False))
            if emulator_type == "ldplayer":
                # 没有截图增强也要进来：文本输入改走 ldconsole 与截图增强无关
                config = await self._build_ldplayer_adb_controller_config(
                    emulator_path,
                    emulator_index,
                    native_index,
                    with_extras=screencap_extra,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    screencap_extra,
                    input_extra,
                    config,
                )
                return self._cached_adb_profile
            if emulator_type == "mumu" and (screencap_extra or input_extra):
                config = self._build_mumu_adb_controller_config(
                    emulator_path,
                    emulator_index,
                    native_index,
                )
                self._cached_adb_profile = MaaFWAdbControlProfile(
                    emulator_type,
                    screencap_extra,
                    input_extra,
                    config,
                )
                return self._cached_adb_profile
            self._cached_adb_profile = MaaFWAdbControlProfile(
                emulator_type,
                screencap_extra,
                input_extra,
                {},
            )
            return self._cached_adb_profile
        except Exception as exc:
            logger.warning(f"构造 MaaFW ADB extra 配置失败，使用默认配置: {exc}")

        self._cached_adb_profile = MaaFWAdbControlProfile(None, False, False, {})
        return self._cached_adb_profile

    def _mod_avd_open_kwargs(self) -> dict[str, Any]:
        """Emulator 2.0 门面的 ``open`` 要知道调用方能不能用魔改 AVD（MaaFW 脚本一律放行）；
        旧式模拟器管理器不收这个参数。"""
        from app.utils import emulator2 as _utils_emulator2

        if isinstance(self.emulator_manager, _utils_emulator2.facade.Emulator2Manager):
            return {"allow_mod_avd": True}
        return {}

    def _build_avd_adb_profile(self, device_ref: Any) -> MaaFWAdbControlProfile:
        """魔改 AVD：只给 AVDExtras 截图，推流开关走私有 adb server。任何一步不成立都抛错。"""
        from app.utils import emulator2 as _utils_emulator2

        capability = build_adb_emulator_extra_capabilities().get("avd", {})
        if not capability.get("screencap"):
            raise RuntimeError(
                "当前 MaaFW 运行时不带模拟器截图增强（MaaAdbControlUnit），"
                "魔改 AVD 上截图不能回落到普通 adb，本次不运行"
            )
        adb_path = _avd_adb_path(device_ref.manager_path)
        if not adb_path.is_file():
            raise RuntimeError(f"找不到魔改 AVD 的 adb：{adb_path}")
        root = _utils_emulator2.avd.components.root_from_manager_exe(
            device_ref.manager_path
        )
        console = _utils_emulator2.avd.constants.console_port(device_ref.native_index)
        config = _utils_emulator2.avd.maafw_extras.build_maafw_avd_config(
            adb_path, _utils_emulator2.avd.components.adb_server_port(root), console
        )
        self._append_log(
            f"魔改 AVD 截图走 AVDExtras（共享内存 SHM_videmulator{console}），不回落普通 adb"
        )
        return MaaFWAdbControlProfile("avd", True, False, config)

    async def _script_adb_env(self) -> dict[str, str]:
        """魔改 AVD 实例上叠加给 worker（agent 与它们起的 adb 继承）和 pretask 的环境变量：
        ``ANDROID_ADB_SERVER_PORT=<scriptAdbServerPort>``（默认 20049）。脚本用 SDK 的新版 adb，
        放在 5037 上会和雷电 / MuMu 自带的旧版 adb 互杀 server。其余模拟器返回空字典。"""
        emulator_index = self.script_config.Emulator.Index
        if self.script_config.Emulator.Id == "-" or emulator_index in ("", "-"):
            return {}
        device_ref = None
        with suppress(Exception):
            resolve_device = getattr(self.emulator_manager, "resolve_device", None)
            device_ref = resolve_device(emulator_index) if resolve_device else None
        if device_ref is None or device_ref.emulator_type != "avd":
            return {}
        from app.utils import emulator2 as _utils_emulator2

        root = _utils_emulator2.avd.components.root_from_manager_exe(
            device_ref.manager_path
        )
        # 先由 MAS 以脱离方式起好：worker 里的 adb 顺手拉起的 server 会继承 worker 的输出管道
        try:
            await _utils_emulator2.avd.host.ensure_script_adb_server(root)
        except _utils_emulator2.avd.host.ScriptAdbPortConflict:
            raise  # 端口被别的程序占着，worker 里的 adb 连上去只会一直失败，直接报给用户
        except Exception:  # noqa: BLE001 - 起不来就交给 worker 自己的 adb
            pass
        return _utils_emulator2.avd.components.script_adb_env(root)

    def _check_avd_runtime_version(self, maafw_version: str | None) -> None:
        """魔改 AVD 要 AVDExtras：运行环境的 MaaFramework 低于 5.7.0 时明确报错，不让它静默回落。"""
        profile = self._cached_adb_profile
        if profile is None or profile.emulator_type != "avd":
            return
        from app.utils import emulator2 as _utils_emulator2

        supported = _utils_emulator2.avd.maafw_extras.avd_extras_supported(
            maafw_version
        )
        if supported is False:
            raise RuntimeError(
                f"项目使用的 MaaFramework {maafw_version} 低于 5.7.0，不支持魔改 AVD 的截图通道"
                "（AVDExtras）；请把项目更新到带 MaaFramework 5.7.0 以上的版本"
            )
        if supported is None:
            self._append_log(
                "认不出项目使用的 MaaFramework 版本，无法预先确认是否支持魔改 AVD 截图通道"
                "（AVDExtras，5.7.0 起）；不支持时连接会直接失败"
            )

    def _resolve_adb_ready_timeout(self) -> int | None:
        """按该模拟器自己的 Info.MaxWaitTime 决定等 adb 的耐心。

        LDPlayer.open() 在 in_android==1 之后只 sleep 3 秒就返回「启动完成」
        （不传 package_name 时不走 30 秒分支），此时 Android 里的 adbd 常常还
        没起来。第一层把等待交给项目外壳，内置运行这条等待是唯一的缓冲，
        插件版固定 30 秒在冷启动的雷电上不够用。

        取不到模拟器配置时返回 None，由 runner 用自己的常量兜底。
        """

        manager = self.emulator_manager
        config = getattr(manager, "config", None) if manager is not None else None
        if config is None:
            return None
        try:
            value = int(config.Info.MaxWaitTime)
        except Exception:  # noqa: BLE001 - 取不到就交给 runner 兜底
            return None
        return value if value > 0 else None

    def _resolve_adb_screencap_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_method = _ADB_SCREENCAP_EMULATOR_EXTRAS
        if profile.emulator_type == "avd":
            # 魔改 AVD 只给 AVDExtras，不让测速有机会选普通 adb（约 250 ms）
            return extra_method
        if profile.emulator_type in {"ldplayer", "mumu"}:
            default_methods = _ADB_SCREENCAP_DEFAULT
            if profile.screencap_extra:
                # 只给模拟器增强这一种，与第一层写死的 ScreencapMethods=64 一致。
                #
                # 此前返回的是 default_methods | extra_method，而 -57 本身已含
                # 1<<6，等于把全部方法交给 MaaFW 测速。雷电上 ADB 系截图
                # （RawWithGzip 等）拿不到游戏的 GPU 渲染层：图有正常的
                # 1280x720，内容却是空的，于是识别全程无命中、一次点击都发不出，
                # 每个任务空转到超时。测速只比快慢、不比对不对，必然选错。
                return extra_method
            return _remove_method(default_methods, extra_method, default_methods)
        return _remove_method(
            int(self.script_config.Device.AdbScreencapMethods),
            extra_method,
            _remove_method(
                _ADB_SCREENCAP_DEFAULT, extra_method, _ADB_SCREENCAP_DEFAULT
            ),
        )

    def _resolve_adb_input_methods(self, profile: MaaFWAdbControlProfile) -> int:
        extra_input_method = _ADB_INPUT_EMULATOR_EXTRAS
        if profile.emulator_type == "mumu" and profile.input_extra:
            return _ADB_INPUT_ALL
        if profile.emulator_type == "ldplayer" and _has_input_text_command(
            profile.config
        ):
            # 文本已改走 ldconsole，见 _ADB_INPUT_LDPLAYER_CONSOLE_TEXT
            return _ADB_INPUT_LDPLAYER_CONSOLE_TEXT
        if profile.emulator_type in {"ldplayer", "mumu", "avd"}:
            # 魔改 AVD：AVDExtras 没有输入，默认会选中 Maatouch（官方镜像上 minitouch 不可用）
            return _ADB_INPUT_DEFAULT

        configured = int(self.script_config.Device.AdbInputMethods)
        if not profile.input_extra:
            return _remove_method(
                configured,
                extra_input_method,
                _ADB_INPUT_DEFAULT,
            )
        return configured

    async def _build_ldplayer_adb_controller_config(
        self,
        emulator_path: Path,
        emulator_index: str,
        native_index: str | None = None,
        *,
        with_extras: bool = True,
    ) -> dict[str, Any]:
        """雷电的 ADB controller config：截图增强 extras + 走 ldconsole 的文本输入。

        ``with_extras`` 为 False（运行时 maa 没有雷电截图增强）时不写 ``extras``，
        但文本输入命令照写：它只依赖安装目录里的 ``ldconsole.exe``。
        """
        emulator_root = emulator_path.parent
        # 兜底必须用原生索引: 雷电 extras 的 index 与 ADB 序列号都按它算,
        # 纳管多个安装时设备号与原生索引不是一回事。
        index = int(native_index if native_index is not None else emulator_index)
        pid = 0

        # get_device_info 仅存在于部分模拟器管理器（雷电有，MuMu 无），
        # 且 list2 可能超时/异常，故整体兜底为实例索引 + pid=0。
        if self.emulator_manager is not None:
            try:
                devices = await self.emulator_manager.get_device_info(emulator_index)
                device = devices.get(emulator_index)
                if device is not None:
                    index = device.idx
                    pid = device.pid
            except Exception as exc:
                logger.warning(
                    f"获取雷电模拟器 extra 信息失败，使用实例索引兜底: {exc}"
                )

        ld_config: dict[str, Any] = {
            "enable": True,
            "index": index,
            "path": str(emulator_root).replace("\\", "/"),
            "pid": pid,
        }
        ld_library = emulator_root / "ldopengl64.dll"
        if ld_library.exists():
            ld_config["lib"] = str(ld_library).replace("\\", "/")

        config: dict[str, Any] = {}
        if with_extras:
            config["extras"] = {"ld": ld_config}
        command = _ldplayer_input_text_command(emulator_root, index)
        if command is not None:
            config["command"] = {"InputText": command}
        return config

    @staticmethod
    def _build_mumu_adb_controller_config(
        emulator_path: Path,
        emulator_index: str,
        native_index: str | None = None,
    ) -> dict[str, Any]:
        emulator_root = emulator_path.parent.parent
        # 与雷电分支同口径: MuMu extras 的 index 也按原生索引算,
        # 纳管多个安装时设备号与原生索引不是一回事。
        mumu_config: dict[str, Any] = {
            "enable": True,
            "index": int(native_index if native_index is not None else emulator_index),
            "path": str(emulator_root).replace("\\", "/"),
        }
        for library in (
            emulator_root / "nx_main" / "sdk" / "external_renderer_ipc.dll",
            emulator_root / "shell" / "sdk" / "external_renderer_ipc.dll",
        ):
            if library.exists():
                mumu_config["lib"] = str(library).replace("\\", "/")
                break

        return {
            "extras": {
                "mumu": mumu_config,
            },
        }

    async def _resolve_window_handle(self, controller: MaaFWController) -> int:
        configured_hwnd = self.script_config.Device.HWnd
        parsed_hwnd = _optional_int(configured_hwnd)
        if parsed_hwnd:
            return parsed_hwnd
        if not controller_has_window_rules(controller):
            raise RuntimeError(_WIN32_NO_WINDOW_RULES_MESSAGE)
        matches = await asyncio.to_thread(_match_controller_windows, controller)
        if not matches:
            raise RuntimeError("未找到匹配 MaaFW Win32 controller 的窗口")
        if len(matches) > 1:
            # 仍取第一个（行为不变），但让用户看得见：多开、同名的启动器 / 浏览器
            # 标签页都会命中同一条正则，接错窗口时日志里要能找到原因。
            candidates = "; ".join(
                f"hWnd={item.hWnd}, class={item.className}, title={item.windowName}"
                for item in matches
            )
            self._append_log(
                f"控制器 {controller.name} 的窗口规则匹配到 {len(matches)} 个窗口，"
                f"本次使用第一个（hWnd={matches[0].hWnd}）。候选: {candidates}。"
                "接错窗口时请先关掉多余的同名窗口再运行"
            )
        return int(matches[0].hWnd)

    async def _run_maafw(self, device_config: MaaFWDeviceConfig) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")
        limit_minutes = self.script_config.Run.RunTimeLimit
        timeout = limit_minutes * 60
        task_limit_seconds, task_limit_overrides = task_time_limits_from_config(
            self.script_config
        )
        loop_guard = loop_guard_from_config(self.script_config)
        # 截止时刻交给 worker：到点它自己停任务、截图、把已完成的任务带回来。
        # 宿主这层只在 worker 没停下时才强杀，那时既没有截图也没有进度。
        run_deadline_at = time.time() + timeout
        try:
            return await asyncio.wait_for(
                self._run_maafw_worker(
                    device_config,
                    run_deadline_at=run_deadline_at,
                    task_time_limit_seconds=task_limit_seconds,
                    task_time_limit_overrides=task_limit_overrides,
                    loop_guard=loop_guard,
                ),
                timeout=timeout + _RUN_DEADLINE_GRACE_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            await self._terminate_runner_process()
            raise _MaaFWRunTimeoutError(
                f"MaaFW 任务运行超时（限制 {limit_minutes} 分钟，worker 未能自行停止，已强制结束）"
            ) from exc
        except asyncio.CancelledError:
            await self._terminate_runner_process()
            raise

    async def _run_maafw_worker(
        self,
        device_config: MaaFWDeviceConfig,
        *,
        run_deadline_at: float | None = None,
        task_time_limit_seconds: int = 0,
        task_time_limit_overrides: dict[str, int] | None = None,
        loop_guard: bool = False,
    ) -> MaaFWRunResult:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")

        service = MaaFWRunnerService()
        loop = asyncio.get_running_loop()
        runtime_pool_root = self.maafw_runtime_pool_root
        runtime_pool_id = str(self.maafw_runtime_pool_id or "").strip()
        if runtime_pool_root is None or not runtime_pool_id:
            raise RuntimeError(
                "MaaFW 运行任务缺少由 maafw.runtime_pool.v1 注入的 root/poolId"
            )
        native_debug_log_path = self.project_path / "debug" / "maafw.log"
        (
            native_debug_log_offset,
            native_debug_log_rotations,
        ) = await asyncio.to_thread(
            _snapshot_native_debug_log_state, native_debug_log_path
        )
        # 项目 agent 自己写的日志（debug/custom、go-service …）同样记下起点，收尾时只另存本次新写的。
        try:
            project_log_marks = await asyncio.to_thread(
                snapshot_project_logs, self.project_path
            )
        except Exception as exc:
            project_log_marks = {}
            self._append_log(f"MaaFW 项目日志起点记录失败，本次按全部新写处理: {exc}")

        def send_runner_log(message: str) -> None:
            loop.call_soon_threadsafe(self._append_log, message)

        # 密码字段（PI v2.10.0）的原文会随 override 进原生日志与 worker 输出：复制、转发、
        # 摘录失败原因前都换成占位（协议要求不得把原文写进日志）。
        secrets = self._secret_log_variants()
        self._stdout_native_errors = []
        self._attempt_native_errors = []
        prepare_cancel_event = threading.Event()
        # 与运行前更新 / 预检同一份解析：脚本级 Update.ProxyAddress 优先，留空跟随
        # 全局。运行时装依赖也走它，否则「更新能走代理、真跑时装不上」。
        proxy_url = resolve_update_proxy_url(self.script_config)

        def _prepare_environment_with_proxy() -> MaaFWRunnerEnvironment:
            # 代理作用域按线程登记，要在 to_thread 的目标函数体内进入：池的 uv /
            # pip 子进程、以及这里派生出的 worker 环境（worker 内的 agent pip 与
            # 项目 agent 再从它继承）都从 strip_host_python_environment 拿到代理变量。
            with subprocess_proxy_scope(proxy_url):
                return service.prepare_environment(
                    self.project_path,
                    runtime_pool_root=runtime_pool_root,
                    runtime_pool_id=runtime_pool_id,
                    lease_owner=f"automas-script-maafw:{self.script_info.script_id}",
                    lease_ttl_seconds=max(
                        600, int(self.script_config.Run.RunTimeLimit or 120) * 60 + 600
                    ),
                    import_paths=[Config.source_path],
                    send_log=send_runner_log,
                    cancel_event=prepare_cancel_event,
                )

        prepare_environment_task = asyncio.create_task(
            asyncio.to_thread(_prepare_environment_with_proxy)
        )
        try:
            with self._run_record.stage(STAGE_ENVIRONMENT):
                runner_environment = await asyncio.shield(prepare_environment_task)
        except asyncio.CancelledError:
            # 取消要传进安装线程：置位令牌后正在跑的 uv/pip 子进程会被终止。
            # 然后只等有限时间——后端关机时 Runtime 只给几秒，等不到就放弃，
            # 租约释放交给后台任务或 TTL。
            prepare_cancel_event.set()
            await _abandon_environment_preparation(
                prepare_environment_task,
                release=service.release_environment,
                grace_seconds=_PREPARE_ENVIRONMENT_CANCEL_GRACE_SECONDS,
                send_log=self._append_log,
            )
            raise
        attempt_key = id(self.cur_user_log)
        history_dir = Path(self._history_temp.name) / uuid.uuid4().hex
        await asyncio.to_thread(history_dir.mkdir, parents=True, exist_ok=True)
        history_stamp = "run"
        worker_id: str | None = None
        event_server: WorkerEventServer | None = None
        # 事件通道建不起来时的原因：worker.log 建好后写进去（这次运行退回 stdout 传事件）
        event_server_failure: str | None = None
        try:
            self._check_avd_runtime_version(runner_environment.maafw_version)
            runner_plan = self.run_plan
            if runner_environment.maafw_version:
                runner_plan = self.run_plan.model_copy(deep=True)
                runner_plan.piEnv["PI_CLIENT_MAAFW_VERSION"] = (
                    f"v{runner_environment.maafw_version.lstrip('v')}"
                )
            payload = service.create_job_payload(
                runner_plan,
                device_config,
                # 失败截图和本次尝试的 .log / .maafw.log 放一起。
                failure_screenshot_dir=history_dir,
                failure_screenshot_prefix=history_stamp,
                task_start_not_before=self._task_start_not_before(),
                task_start_gate_mode=(
                    "disk_quiet" if self.game_start_disk_quiet else "screen"
                ),
                run_deadline_at=run_deadline_at,
                task_time_limit_seconds=task_time_limit_seconds,
                task_time_limit_overrides=task_time_limit_overrides,
                loop_guard=loop_guard,
            )
            # job 经 worker 的 stdin 交过去、不再落盘；升级前的版本写过 job 文件，宿主与 worker
            # 一起被硬杀时会留在盘上（里面可能有解密后的密码选项），照旧清掉。
            await asyncio.to_thread(_sweep_legacy_runner_jobs)
            # 事件（日志、结果）走独立通道（Windows 命名管道）；建不起来就让 worker 照旧写
            # stdout，这次运行不受影响。没有这条通道的平台直接用 stdout，不记。
            if event_channel_supported():
                try:
                    event_server = WorkerEventServer.open()
                except OSError as exc:
                    event_server_failure = (
                        f"MaaFW 事件通道建立失败（{exc!r}），本次运行事件改走标准输出"
                    )
                    logger.warning(event_server_failure)
            job_bytes = encode_job(
                payload,
                event_channel=event_server.spec if event_server is not None else None,
            )
            # 魔改 AVD 实例：worker 及其 agent、adb 子进程的 adb 走脚本专用 server。
            # 另拷一份，不改运行环境对象里那份（可能被缓存复用）
            script_env = await self._script_adb_env()
            worker_env = {
                **runner_environment.env,
                **script_env,
                # worker 起 agent 时把 maafw 的 pip 约束文件写在这里（AUTO-MAS 自己的数据目录，
                # 不进项目视图），见 runner._inject_agent_pip_constraint。
                AGENT_PIP_CONSTRAINT_DIR_ENV: str(_maafw_agent_constraints_dir()),
            }
            process = await asyncio.create_subprocess_exec(
                str(runner_environment.python_executable),
                "-m",
                "app.task.MaaFW.tools.core.runner.worker",
                cwd=str(Path.cwd()),
                env=worker_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # 默认 64 KiB：agent 原样转发的输出、原生 ERROR 日志里整份 pipeline JSON
                # 都可能更长，超了 readline 就抛错、读取任务退出，worker 写满管道后挂到硬超时
                limit=_WORKER_STREAM_LINE_LIMIT,
            )
            worker_id = service.register_worker(process)
        except BaseException:
            if event_server is not None:
                event_server.close()
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)
            raise
        self.runner_process = process
        result_payload: dict[str, Any] | None = None
        result_received = asyncio.Event()
        stderr_lines: list[str] = []
        # 两份文件：``.worker.log`` 是 MAS 自己这一侧（runner 事件、worker 的
        # stdout/stderr），``.maafw.log`` 是项目 ``debug/maafw.log`` 本次运行部分的
        # 原样副本——不加前缀、不改编码，和脚本作者自己用 MFAA 跑出来的一模一样，
        # 出问题可以直接转交。以前两者混在一个文件里、原生每行还带一个抄写时刻，
        # 脚本作者拿到手第一反应是"这日志不对"。
        worker_log_path = history_dir / f"{history_stamp}.worker.log"
        native_log_path = history_dir / f"{history_stamp}.maafw.log"
        framework_log_writer: _FrameworkLogWriter | None = None

        try:
            writer = _FrameworkLogWriter(worker_log_path)
            await asyncio.to_thread(writer.start)
            framework_log_writer = writer
            self._append_log(f"MaaFW worker 日志写入中: {worker_log_path}")
        except Exception as exc:
            if framework_log_writer is not None:
                with suppress(Exception):
                    await asyncio.to_thread(framework_log_writer.close)
                framework_log_writer = None
            self._append_log(f"MaaFW worker 日志创建失败: {exc}")
        except BaseException:
            # 在这里被停止：事件通道还没交给读取任务、下面的收尾也走不到，先关掉它（worker
            # 由 _run_maafw 结束）。不关的话管道句柄留在宿主里一直不释放。
            if event_server is not None:
                event_server.close()
            raise

        def write_framework_log(source: str, message: str) -> None:
            if framework_log_writer is None:
                return
            framework_log_writer.write(source, message)

        # 项目有 password 输入框时第一行写打码说明：问题包导出凭它判断这份日志能不能往外发
        redaction_notice = self._log_redaction_notice()
        if redaction_notice:
            write_framework_log("runner", redaction_notice)
        if event_server_failure:
            write_framework_log("runner", event_server_failure)

        def handle_event(event: dict[str, Any]) -> None:
            """worker 发来的一个协议事件（事件通道或 stdout 退回格式，已打码），按类型分发。"""

            nonlocal result_payload
            event_type = event.get("type")
            if event_type == "log":
                message = str(event.get("message") or "")
                write_framework_log("runner", message)
                # 去向由 worker 定好（audience）；旧格式事件不带，按原来的文案规则判
                if event_audience(event) == AUDIENCE_UI:
                    self._append_log(_framework_ui_message(message))
            elif event_type == "result" and isinstance(event.get("data"), dict):
                result_payload = event["data"]
                result_received.set()
            elif event_type == RUN_RECORD_EVENT_TYPE:
                # 结构化运行记录：只进记录与调度台进度，不进日志
                self._on_run_record_event(event.get("data"))
            elif event_type == "error":
                message = str(event.get("message") or "")
                write_framework_log("runner-error", message)
                # Keep the complete error in the per-run framework log,
                # but apply the same native-noise filter as ordinary
                # framework diagnostics.  Worker error events can contain
                # an entire native parser/backtrace blob and must not
                # flood the user-facing task log.
                if event_audience(event) == AUDIENCE_UI:
                    self._append_log(_framework_ui_message(message))

        async def read_events() -> None:
            """读事件通道：worker 打开管道、核对令牌后逐条分发；读到 EOF（worker 关闭管道或已退出、
            已写进去的都读完了）时结束。"""

            if event_server is None:
                return
            processed = 0
            try:
                async for event in event_server.events(
                    lambda note: write_framework_log("runner", note)
                ):
                    processed += 1
                    if processed % _RELAY_YIELD_EVERY_LINES == 0:
                        await asyncio.sleep(0)  # 同 read_stdout：别独占事件循环
                    handle_event(_redact_worker_event(event, secrets))
            finally:
                # 不再读了就立刻关掉：worker 再写会出错、改走 stdout，不会对着没人读的管道卡住
                event_server.close()

        async def feed_job() -> None:
            """把 job 写进 worker 的 stdin 再关掉；worker 先退出时写不进去，记一句就算了。"""

            stdin = process.stdin
            if stdin is None:
                return
            try:
                stdin.write(job_bytes)
                await stdin.drain()
            except (OSError, RuntimeError) as exc:
                write_framework_log(
                    "runner", f"MaaFW job 写入 worker 标准输入失败: {exc!r}"
                )
            finally:
                with suppress(Exception):
                    stdin.close()

        async def read_stdout() -> None:
            if process.stdout is None:
                return
            processed = 0
            async for raw_line in _iter_stream_lines(
                process.stdout,
                lambda: write_framework_log("worker-stdout", _STREAM_OVERRUN_NOTE),
            ):
                # StreamReader 缓冲里有数据时 `async for` 不会挂起，会一路取到
                # 缓冲耗尽为止。MaaFramework 的原生诊断动辄每秒几十行、单次运行
                # 几千行，这个循环于是能连续独占事件循环数十秒——真机上表现为
                # 界面日志停更、API 不响应、点了停止没反应，等这波处理完才一起
                # 恢复。定期显式让出，代价可以忽略。
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)
                # Worker protocol events are UTF-8 JSON, while MaaFramework
                # native diagnostics may be written directly to stdout using
                # the Windows ACP/GBK code page.  Decode protocol lines
                # strictly first and use the existing multi-codec fallback
                # for native text so Chinese diagnostics are not persisted as
                # replacement characters.
                try:
                    line = raw_line.decode("utf-8", errors="strict").strip()
                except UnicodeDecodeError:
                    line = _decode_subprocess_output(raw_line).strip()
                if not line:
                    continue
                # 事件通道连上后 stdout 只剩原生诊断；通道建不起来、或中途断了，worker 把
                # 协议事件照旧一行一个 JSON 写在这里。
                event = _parse_worker_protocol_line(line, secrets)
                if event is None:
                    line = redact_secret_text(line, secrets)
                    write_framework_log("worker-stdout", line)
                    self._note_native_error(line)
                    if _should_forward_framework_log(line):
                        self._append_log(_framework_ui_message(line))
                    continue
                handle_event(event)

        async def read_stderr() -> None:
            if process.stderr is None:
                return
            processed = 0
            async for raw_line in _iter_stream_lines(
                process.stderr,
                lambda: write_framework_log("worker-stderr", _STREAM_OVERRUN_NOTE),
            ):
                processed += 1
                if processed % _RELAY_YIELD_EVERY_LINES == 0:
                    await asyncio.sleep(0)  # 同 read_stdout：别独占事件循环
                line = _clean_framework_output(
                    _decode_subprocess_output(raw_line)
                ).strip()
                if not line:
                    continue
                line = redact_secret_text(line, secrets)
                write_framework_log("worker-stderr", line)
                self._note_native_error(line)
                stderr_lines.append(line)
                del stderr_lines[:-20]

        feed_task = asyncio.create_task(feed_job())
        events_task = asyncio.create_task(read_events())
        stdout_task = asyncio.create_task(read_stdout())
        stderr_task = asyncio.create_task(read_stderr())

        async def drain_readers(*, propagate_errors: bool) -> None:
            # worker 已经退出（或已被结束）：stdin 不用再写。事件通道把管道里剩下的读完、读到
            # EOF 就结束（写的一方没了，已写进去的照样读得出）；worker 从没打开过管道的话立刻
            # 结束，不再等。第二次调用时读取任务都已结束，这里不会再等。
            feed_task.cancel()
            if event_server is not None:
                event_server.worker_exited()
            _, pending_readers = await asyncio.wait(
                (stdout_task, stderr_task, events_task),
                timeout=5.0,
            )
            for task in pending_readers:
                task.cancel()
            reader_results = await asyncio.gather(
                stdout_task,
                stderr_task,
                events_task,
                return_exceptions=True,
            )
            await asyncio.gather(feed_task, return_exceptions=True)
            if propagate_errors:
                for result in reader_results:
                    if isinstance(result, Exception):
                        raise result

        try:
            returncode = await self._wait_worker_exit(process, result_received)
            await drain_readers(propagate_errors=True)
        finally:
            if process.returncode is None:
                await self._terminate_runner_process()
            elif self.runner_process is process:
                self.runner_process = None
            await drain_readers(propagate_errors=False)
            if event_server is not None:
                event_server.close()
            # worker 已退出：调度台不再显示「第几个任务」，重试时由新 worker 重新推
            self.cur_user_item.progress = None
            if framework_log_writer is not None:
                try:
                    await asyncio.to_thread(framework_log_writer.close)
                except Exception as exc:
                    self._append_log(f"MaaFW worker 日志保存不完整: {exc}")
            try:
                copied = await asyncio.to_thread(
                    _copy_native_debug_log_delta,
                    native_debug_log_path,
                    native_debug_log_offset,
                    native_debug_log_rotations,
                    native_log_path,
                    secrets,
                )
            except Exception as exc:
                self._append_log(f"MaaFW 原生日志复制失败: {exc}")
            else:
                if copied:
                    self._append_log(f"MaaFW 原生日志已保存: {native_log_path}")
            # 资源包加载失败时找原因用：原生日志副本是 UTF-8、已打码，优先用它；worker stdout
            # 里同一行按控制台代码页转过，非 ASCII 的节点名 / 路径可能已成了「?」。
            native_errors = (
                await asyncio.to_thread(read_native_error_lines, native_log_path)
                if native_log_path.is_file()
                else []
            )
            self._attempt_native_errors = native_errors or list(
                self._stdout_native_errors
            )
            # 项目自己写的日志本次新增的部分：与 .maafw.log 同目录同前缀，按脚本全部用户的密码打码。
            project_log_path = history_dir / f"{history_stamp}.project.log"
            try:
                project_logs = await asyncio.to_thread(
                    copy_project_log_delta,
                    self.project_path,
                    project_log_marks,
                    project_log_path,
                    secrets=self._project_log_secret_variants(secrets),
                )
            except Exception as exc:
                self._append_log(f"MaaFW 项目日志保存失败: {exc}")
            else:
                if project_logs.segments:
                    self._append_log(
                        f"MaaFW 项目日志已保存: {project_log_path}"
                        f"（{len(project_logs.segments)} 个文件，"
                        f"{project_logs.written_bytes} 字节）"
                    )
            attachments = self._history_attachments.setdefault(attempt_key, [])
            for path, kind, role in (
                (worker_log_path, "log", "worker_log"),
                (native_log_path, "log", "native_log"),
                (project_log_path, "log", "project_log"),
            ):
                if path.is_file():
                    attachments.append(
                        HistoryAttachmentInput(
                            path=path, kind=kind, role=role, display_name=path.name
                        )
                    )
            for image in history_dir.iterdir():
                if image.is_file() and image.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                }:
                    attachments.append(
                        HistoryAttachmentInput(
                            path=image,
                            kind="image",
                            role="failure_screenshot",
                            display_name=image.name,
                        )
                    )
            with suppress(Exception):
                await asyncio.to_thread(service.release_environment, runner_environment)
            service.unregister_worker(worker_id)

        if result_payload is not None:
            return MaaFWRunResult.model_validate(result_payload)
        message = f"MaaFW runner worker exited without result: {returncode}"
        detail = "\n".join(stderr_lines[-5:]).strip()
        if detail and _should_forward_framework_log(detail):
            message += f": {_framework_ui_message(detail)}"
        elif detail:
            # Native stderr is already preserved in the per-run framework log.
            # Do not copy parser/backtrace blobs into the normal task log when
            # the worker exits without a protocol result.
            message += (
                ": MaaFW worker 未返回任务结果，完整输出已保存到本次运行的 .worker.log"
            )
        raise RuntimeError(message)

    def _note_native_error(self, line: str) -> None:
        """worker 转来的一行是原生 ERR 行就留下（``[json=`` 起丢掉、有条数上限）；续行不要。"""

        excerpt = native_error_excerpt(line)
        if excerpt is None:
            return
        self._stdout_native_errors.append(excerpt)
        del self._stdout_native_errors[:-MAX_NATIVE_ERROR_LINES]

    def _run_password_values(self) -> list[str]:
        """本次运行要打码的密码值：计划里 password 字段的值 + 该用户快照里全部密文解开的值
        （项目撤掉了 password 标记的字段建计划时照样解开，见 option_secrets）。"""

        if self.run_plan is None or self.interface_model is None:
            return []
        return collect_run_password_values(
            self.run_plan,
            self.interface_model,
            getattr(self, "cur_user_config", None),
        )

    def _secret_log_variants(self) -> list[str]:
        """本次运行要打码的密码值在日志里可能出现的写法（见 option_secrets）。"""

        return secret_log_variants(self._run_password_values())

    def _project_log_secret_variants(self, plan_variants: list[str]) -> list[str]:
        """项目日志不一定是本次运行的用户写的（上一个用户留下的片段也可能落在本次新增里），
        所以按脚本全部用户的密码打码，再并上本次运行计划里的。"""

        try:
            values = collect_script_password_values(
                self.script_config, self.interface_model
            )
        except Exception as exc:  # noqa: BLE001 - 取不到时退回本次运行计划里的
            logger.debug(f"收集脚本全部用户的密码失败，只按本次运行的打码: {exc}")
            return plan_variants
        return sorted(
            set(plan_variants) | set(secret_log_variants(values)),
            key=len,
            reverse=True,
        )

    def _log_redaction_notice(self) -> str | None:
        """项目有 password 输入框或本次有要打码的值时写进 ``.worker.log`` 开头的打码说明。"""

        if self.run_plan is None or self.interface_model is None:
            return None
        return log_redaction_notice(self.interface_model, self._run_password_values())

    async def _wait_worker_exit(
        self,
        process: asyncio.subprocess.Process,
        result_received: asyncio.Event,
    ) -> int | None:
        """等 worker 退出；结果已经回传的话只再等有限时间。"""

        exit_task = asyncio.ensure_future(process.wait())
        result_task = asyncio.ensure_future(result_received.wait())
        try:
            await asyncio.wait(
                {exit_task, result_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if exit_task.done():
                return exit_task.result()
            try:
                return await asyncio.wait_for(
                    asyncio.shield(exit_task),
                    timeout=_WORKER_EXIT_AFTER_RESULT_SECONDS,
                )
            except asyncio.TimeoutError:
                self._append_log(
                    "MaaFW worker 已回传结果但迟迟不退出，强制结束以免拖过时限"
                )
                await self._terminate_runner_process()
                return process.returncode
        finally:
            for task in (exit_task, result_task):
                if not task.done():
                    task.cancel()

    async def _shutdown_runner(self) -> None:
        await self._terminate_pretask_process()
        await self._terminate_runner_process()

    async def _pretasks_need_rerun(self, client_reset: bool) -> bool:
        """重试前判断要不要再跑一遍已经成功过的运行前设置。

        只在客户端已经不在时重跑：MAS 刚关掉自己起的游戏 / 模拟器，或者 Win32 下
        控制器的窗口已经找不到（游戏由运行前设置拉起、被队列里的「关闭游戏」任务关掉，
        MAS 不知道它是谁起的）。游戏还开着时不重跑，免得项目的启动脚本对着已在运行的
        游戏再走一遍。固定 HWnd、控制器没有窗口规则这两种只是「看不出窗口在不在」，
        不挡前一种：MAS 自己关掉的客户端一定不在了。
        """

        if self.run_plan is None or not self.run_plan.pretasks:
            return False
        if client_reset:
            self._append_log("游戏/模拟器已在上一次失败后关闭，重新应用运行前设置")
            return True
        if self.run_plan.controllerType != "Win32" or self.interface_model is None:
            return False
        if _optional_int(self.script_config.Device.HWnd):
            return False
        controller = _find_controller(
            self.interface_model, self.run_plan.controllerName
        )
        if not controller_has_window_rules(controller):
            return False
        if await asyncio.to_thread(_match_controller_windows, controller):
            return False
        self._append_log("未找到游戏窗口，重新应用运行前设置")
        return True

    async def _run_pretasks(self) -> None:
        if self.run_plan is None:
            raise RuntimeError("MaaFW 运行计划尚未初始化")

        # 宿主的 VIRTUAL_ENV、PYTHON* 等不往下传，PATH 去掉宿主 venv 的脚本目录（Runtime 经
        # uv run 起后端时它排最前）：pretask 脚本里再起 python 不该落到 MAS 自己的环境上
        env = strip_host_python_environment()
        if "PATH" in env:
            env["PATH"] = path_without_host_venv(env["PATH"]) or ""
        # 与 agent 同口径（runner._build_agent_env）：pretask 多是项目自带 Python 跑的
        # 脚本，输出与读文件都按 UTF-8；对非 Python 程序这两个变量无害。
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env.update(self.run_plan.piEnv)
        # 魔改 AVD 实例：pretask 若用 adb，也走脚本专用 server（同 worker）
        env.update(await self._script_adb_env())
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # 运行前设置没有自己的时限设置：沿用本脚本的「单次运行时间限制」（RunTimeLimit），
        # 一次尝试里全部运行前设置合计不超过它（MaaFW 豁免了 HardTimeLimit，这里是它缺的外层兜底；
        # worker 那一段另起计时，见 ``_run_maafw``）。
        limit_minutes = self.script_config.Run.RunTimeLimit or 120
        loop = asyncio.get_running_loop()
        pretasks_started_at = loop.time()
        deadline = pretasks_started_at + float(limit_minutes) * 60
        secret_variants = self._secret_log_variants()
        for pretask in self.run_plan.pretasks:
            display_name = _task_display_name(pretask)
            if loop.time() >= deadline:
                # 前面的运行前设置已经用完时限：这一条不再启动（启动了也只会被立刻结束）
                self._append_log(
                    f"运行前设置合计已用 {int(loop.time() - pretasks_started_at)} 秒，"
                    f"超过单次运行时间限制（{limit_minutes} 分钟），"
                    f"不再启动运行前设置 {display_name}",
                    warning=True,
                )
                raise MaaFWPretaskError(
                    f"运行前设置「{display_name}」未启动：运行前设置合计已超过单次运行时间限制 "
                    f"{limit_minutes} 分钟"
                )
            self._append_log(f"开始应用运行前设置: {display_name}")
            started_at = loop.time()
            process = await asyncio.create_subprocess_exec(
                pretask.executable,
                *pretask.args,
                cwd=self.run_plan.path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
            )
            self.pretask_process = process
            # 输出按行实时进运行日志（以前 communicate() 要等进程结束才一次性写出）；末尾
            # 若干行另留一份，失败时从里面摘原因。
            tail: list[str] = []

            def write_line(text: str, tail: list[str] = tail) -> None:
                tail.append(text)
                if len(tail) > 200:
                    del tail[:-200]
                self._append_log(f"[运行前设置] {text}")

            # 打码放在 pump 里做：detach 之后改写后端日志的输出也要过同一套打码
            pump = _PretaskOutputPump(
                write_line,
                redact=lambda line: redact_secret_text(line, secret_variants),
            )
            reader = asyncio.create_task(pump.run(process.stdout))
            timed_out = False
            held = False
            try:
                exited = await _wait_pretask_exit(process, deadline - loop.time())
                if not exited:
                    timed_out = True
                    self._append_log(
                        f"运行前设置 {display_name} 运行了 "
                        f"{int(loop.time() - started_at)} 秒仍未结束，运行前设置合计已用 "
                        f"{int(loop.time() - pretasks_started_at)} 秒，超过单次运行时间限制"
                        f"（{limit_minutes} 分钟），结束它（它启动的游戏 / 启动器不受影响）",
                        warning=True,
                    )
                    await self._terminate_pretask_process()
            except asyncio.CancelledError:
                # 停止：进程由 _shutdown_runner 结束；输出交给后台读完，不在这里等。
                pump.detach(display_name)
                _keep_pretask_drain(reader)
                raise
            finally:
                if process.returncode is not None and self.pretask_process is process:
                    self.pretask_process = None

            try:
                done, _ = await asyncio.wait(
                    {reader}, timeout=_PRETASK_OUTPUT_DRAIN_SECONDS
                )
            except asyncio.CancelledError:
                pump.detach(display_name)
                _keep_pretask_drain(reader)
                raise
            if reader in done:
                if not reader.cancelled() and reader.exception() is not None:
                    logger.warning(
                        f"读取运行前设置 {display_name} 的输出失败: {reader.exception()}"
                    )
            else:
                # 还没换行的半行不在这里写出（可能是被拆开的密码前半段），留着和之后的
                # 输出拼成整行、打码后写后端日志
                held = pump.detach(display_name)
                _keep_pretask_drain(reader)
                self._append_log(
                    f"运行前设置 {display_name} 已退出，但输出管道仍被它启动的程序"
                    "（多半是游戏或启动器）占用，不再等待之后的输出"
                    + (
                        "；最后一行还没换行，输出完整后连同之后的输出写进后端日志"
                        if held
                        else ""
                    )
                )
            detail = "\n".join(tail).strip()
            if timed_out:
                raise MaaFWPretaskError(
                    f"运行前设置「{display_name}」超时（运行前设置合计超过单次运行时间限制 "
                    f"{limit_minutes} 分钟仍未结束，已结束）"
                )
            if process.returncode != 0:
                self._append_log(
                    f"运行前设置 {display_name} 执行失败（退出码 {process.returncode}）",
                    warning=True,
                )
                # 半行还留在缓冲里时，tail 的最后一行是更早的输出（可能是「成功」那一行），
                # 不拿它冒充失败原因；半行本身也不写（可能是密码前半段）
                reason = (
                    "最后一行输出还没换行，完整内容稍后写进后端日志"
                    if held
                    else _pretask_failure_reason(detail)
                )
                raise MaaFWPretaskError(f"运行前设置「{display_name}」失败：{reason}")
            self._append_log(f"运行前设置完成: {display_name}")

    async def _terminate_pretask_process(self) -> None:
        # 清理放进独立任务、用 shield 等：超时分支正在清理时用户点了停止（调用方被取消），
        # 清理照样做完；_shutdown_runner 随后进来会等同一个清理任务，而不是看到
        # pretask_process 已清空就直接返回，留下没结束的 pretask 或脚本子进程。
        cleanup = self.pretask_cleanup
        if cleanup is None or cleanup.done():
            process = self.pretask_process
            self.pretask_process = None
            if process is None or process.returncode is not None:
                return
            cleanup = asyncio.create_task(
                _kill_pretask_process(process, self._append_log)
            )
            self.pretask_cleanup = cleanup
        await asyncio.shield(cleanup)

    async def _terminate_runner_process(self) -> None:
        process = self.runner_process
        self.runner_process = None
        if process is None or process.returncode is not None:
            return

        # 必须在 terminate 之前把后代记下来：Windows 的 TerminateProcess 是立即
        # 且不可捕获的，worker 的 shutdown() 没机会跑；而父进程一死，子进程就
        # 被重新挂到别处，事后再按父子关系已经查不到它们。
        descendants = await asyncio.to_thread(_snapshot_descendants, process.pid)

        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass
        except Exception as exc:
            logger.warning(f"MaaFW runner worker 清理失败: {exc}")

        if descendants:
            await asyncio.to_thread(_terminate_snapshot, descendants)

    def _filter_period_once_tasks(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        daily_tasks = set(_load_json_list(self.script_config.Run.DailyOnceTasks))
        weekly_tasks = set(_load_json_list(self.script_config.Run.WeeklyOnceTasks))
        monthly_tasks = set(_load_json_list(self.script_config.Run.MonthlyOnceTasks))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return plan

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        runnable_tasks = []
        skipped_tasks = []
        # 周期限制按任务算，不按队列里的份数算：同一个任务被重复加入队列时，
        # 本轮也只安排一次。否则「仅一次」在一轮内形同虚设，而且先跑的那份一
        # 成功就会把整个任务名记成已完成，还没跑的副本会被当作已完成跳过。
        period_limited_seen: set[str] = set()
        for task in plan.tasks:
            daily_done = (
                task.name in daily_tasks
                and records["daily"].get(task.name) == daily_key
            )
            weekly_done = (
                task.name in weekly_tasks
                and records["weekly"].get(task.name) == weekly_key
            )
            monthly_done = (
                task.name in monthly_tasks
                and records["monthly"].get(task.name) == monthly_key
            )
            if daily_done or weekly_done or monthly_done:
                if daily_done:
                    reason = "今日已正常完成"
                elif monthly_done:
                    reason = "本月已正常完成"
                else:
                    reason = "本周已正常完成"
                skipped_tasks.append(
                    MaaFWSkippedTaskPlan(
                        name=task.name,
                        label=task.label,
                        entry=task.entry,
                        reason=reason,
                    )
                )
                continue
            if (
                task.name in daily_tasks
                or task.name in weekly_tasks
                or task.name in monthly_tasks
            ):
                if task.name in period_limited_seen:
                    skipped_tasks.append(
                        MaaFWSkippedTaskPlan(
                            name=task.name,
                            label=task.label,
                            entry=task.entry,
                            reason="本轮已安排一次",
                        )
                    )
                    continue
                period_limited_seen.add(task.name)
            runnable_tasks.append(task)
        return plan.model_copy(
            update={
                "tasks": runnable_tasks,
                "skippedTasks": [*plan.skippedTasks, *skipped_tasks],
            },
        )

    async def _refresh_run_plan_after_period_update(
        self, completed_tasks: list[str]
    ) -> None:
        """重试前重建计划：从 ``base_run_plan`` 重新按周期过滤，再剔掉本次运行已完成的。

        ``completed_tasks`` 是刚结束这次尝试的 ``completedTasks``（任务名，不是 entry）。
        剔除必须跟在重建之后：重建会把上一次剔掉的任务放回来，所以按累计结果每次都重剔。
        """

        self._completed_this_run.extend(completed_tasks)
        if self.base_run_plan is not None:
            plan = await asyncio.to_thread(
                self._filter_period_once_tasks,
                self.base_run_plan,
            )
            self.run_plan = self._skip_tasks_completed_this_run(plan)

    def _skip_tasks_completed_this_run(self, plan: MaaFWRunPlan) -> MaaFWRunPlan:
        """剔掉特调声明的 ``skip_on_retry_entries`` 里、本次运行已完成过的任务。

        按 entry 认任务、按任务名计份数；同名任务在队列里有多份时全部重跑（见下面注释）。
        没有声明的特调与通用 MaaFW 原样返回。剔掉的记进 ``skippedTasks``，每次重试开头
        据此写一行（``_log_retry_skipped_tasks``）。
        """

        flavor = resolve_flavor(self.script_config)
        entries = set(getattr(flavor, "skip_on_retry_entries", None) or ())
        if not entries:
            return plan
        remaining = Counter(self._completed_this_run)
        # runner 只回报任务名，同名的几份（比如关卡不同的两份「作战」）分不清完成的是
        # 哪一份：按队列顺序剔会剔掉失败的那份、把完成的再跑一遍。所以名字在计划里
        # 不止一份时一份都不剔，全部重跑（#1296 之前的行为）；只有一份的照常剔。
        occurrences = Counter(task.name for task in plan.tasks)
        self._retry_rerun_duplicates = [
            task.name
            for task in plan.tasks
            if task.entry in entries
            and occurrences[task.name] > 1
            and remaining[task.name] > 0
        ]
        tasks = []
        skipped: list[MaaFWSkippedTaskPlan] = []
        for task in plan.tasks:
            if (
                task.entry in entries
                and occurrences[task.name] == 1
                and remaining[task.name] > 0
            ):
                remaining[task.name] -= 1
                skipped.append(
                    MaaFWSkippedTaskPlan(
                        name=task.name,
                        label=task.label,
                        entry=task.entry,
                        reason=_RETRY_SKIP_REASON,
                    )
                )
                continue
            tasks.append(task)
        if not skipped:
            return plan
        return plan.model_copy(
            update={"tasks": tasks, "skippedTasks": [*plan.skippedTasks, *skipped]}
        )

    def _log_retry_skipped_tasks(self) -> None:
        """重试开头写一行被重试跳过的任务。

        不一次性消费：上一次尝试 worker 崩溃时计划原样沿用，这一行要照样写。
        """

        if self.run_plan is None:
            return
        skipped = _retry_skipped_tasks(self.run_plan)
        if skipped:
            self._append_log(
                f"{_RETRY_SKIP_REASON}，不再补跑: "
                + "、".join(_task_display_name(task) for task in skipped)
            )
        duplicates = list(dict.fromkeys(self._retry_rerun_duplicates))
        if duplicates:
            labels = _format_completed_task_labels(self.run_plan, duplicates)
            self._append_log(
                f"{'、'.join(labels)} 在队列里有多份，分不清完成的是哪一份，重试时全部重跑"
            )

    def _load_period_task_records(self) -> dict[str, dict[str, str]]:
        raw_records = _load_json_dict(self.cur_user_config.Data.PeriodTaskRecords)
        records: dict[str, dict[str, str]] = {"daily": {}, "weekly": {}, "monthly": {}}
        for period in records:
            raw_period_records = raw_records.get(period, {})
            if isinstance(raw_period_records, dict):
                records[period] = {
                    str(task_name): str(period_key)
                    for task_name, period_key in raw_period_records.items()
                }
        return records

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        if not completed_tasks:
            return
        daily_tasks = set(_load_json_list(self.script_config.Run.DailyOnceTasks))
        weekly_tasks = set(_load_json_list(self.script_config.Run.WeeklyOnceTasks))
        monthly_tasks = set(_load_json_list(self.script_config.Run.MonthlyOnceTasks))
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        changed = False
        for task_name in set(completed_tasks).intersection(daily_tasks):
            if records["daily"].get(task_name) != daily_key:
                records["daily"][task_name] = daily_key
                changed = True
        for task_name in set(completed_tasks).intersection(weekly_tasks):
            if records["weekly"].get(task_name) != weekly_key:
                records["weekly"][task_name] = weekly_key
                changed = True
        for task_name in set(completed_tasks).intersection(monthly_tasks):
            if records["monthly"].get(task_name) != monthly_key:
                records["monthly"][task_name] = monthly_key
                changed = True
        if changed:
            self.cur_user_config.Data.PeriodTaskRecords = json.dumps(
                records, ensure_ascii=False
            )
            await self.cur_user_config.commit()

    async def _mark_run_started(self) -> None:
        if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d") != self.curdate:
            self.cur_user_config.Data.LastProxyDate = datetime.now(tz=UTC4)
            await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = 0
            await self.cur_user_config.commit()
        self.cur_user_config.Data.LastProxyStatus = "运行中"
        await self.cur_user_config.commit()

    async def _close_emulator(self) -> bool:
        """关闭由 MAS 启动的模拟器，返回是否关成（本来就没开过算关成）。"""

        if not self.opened_emulator:
            return True
        try:
            # 失败原因（含超时）记 warning 进 app.log：#708 设成静默的理由「插件清理属
            # 预期路径」已经不成立（没有插件这一层了）。用户日志不写：重试路径下一轮
            # MAS 会自己重开模拟器，「请手动关闭」会误导。
            return await close_emulator(self)
        finally:
            self.opened_emulator = False
            # 地址是随这次启动缓存的，关掉后下一轮要重新开、重新拿。
            self._cached_adb_address = None
            self._cached_device_info = None
            # 游戏随模拟器一起关了；下一轮重开时按那次拉起重新起算
            self.game_started_at = None
            self.game_start_disk_quiet = False
            # 雷电截图增强的 extras 里带着这次启动的 dnplayer pid；重开后还用旧 pid，
            # MaaFW 建不出截图实例（Failed to create ld inst），这一轮当场 connect 失败。
            self._cached_adb_profile = None

    async def _ensure_desktop_game_started(self) -> None:
        """Win32 场景下由 MAS 负责启动/激活桌面游戏客户端，供后续窗口解析使用。"""
        if self.run_plan is None or self.run_plan.controllerType != "Win32":
            return
        if self.opened_game:
            return
        if not self._mas_manages_game_launch():
            # AttachOnly：游戏由脚本或用户自己起，MAS 只负责找窗口。窗口找不到时
            # _resolve_window_handle 会给出「未找到匹配 MaaFW Win32 controller
            # 的窗口」，比在这里索要一个本模式用不上的 exe 更贴题。
            return

        game_path = self._resolve_game_launch_path()
        if game_path is None or not await asyncio.to_thread(game_path.is_file):
            raise RuntimeError(
                "当前 MaaFW controller 需要由 MAS 启动游戏，请在脚本管理页选择实际游戏 exe"
            )

        if self.interface_model is not None and self.run_plan is not None:
            controller = _find_controller(
                self.interface_model,
                self.run_plan.controllerName,
            )
            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                self._note_resolution_override_skipped()
                self._note_launch_arguments_skipped()
                await self._activate_desktop_game_window(game_path)
                return

        if await asyncio.to_thread(_is_process_path_running, game_path):
            # 走 _append_log（它同样写 app.log）：直接改 script_info.log 会整块替换日志
            # 窗口，这一行也不进用户日志与 history，下一条日志一来就没了。
            self._append_log(
                f"检测到游戏进程已在运行，跳过由 MAS 重复启动游戏: {game_path.name}"
            )
            self._note_resolution_override_skipped()
            self._note_launch_arguments_skipped()
            if await self._wait_for_desktop_game_ready(game_path):
                # 进程在、窗口是等出来的：游戏正在启动，和 MAS 自己拉起的一样要等画面
                self.game_started_at = time.monotonic()
            await self._activate_desktop_game_window(game_path)
            return

        game_arguments = shlex.split(
            str(self.script_config.Game.Arguments or "").strip()
        )
        logger.info(f"启动游戏: {game_path} - {self.script_config.Game.Arguments}")
        # 注册表必须在进程起来之前改好：Unity 播放器只在启动时读一次这些值
        await self._apply_game_resolution_override(game_path)
        try:
            await self.game_process_manager.open_process(
                game_path,
                *game_arguments,
                cwd=game_path.parent,
                breakaway=True,
            )
            # 进程一起来就算 MAS 开的：等窗口时被停止（CancelledError 不是 Exception，
            # 下面接不住），收尾的 _close_game 要看到它才会关游戏。
            self.opened_game = True
            await self._wait_for_desktop_game_ready(game_path)
            self.game_started_at = time.monotonic()
        except Exception:
            self.opened_game = False
            with suppress(Exception):
                await self.game_process_manager.kill()
            await self._restore_game_resolution_override()
            raise

        await self._activate_desktop_game_window(game_path)

    def _unity_resolution_target(self) -> tuple[int, int] | None:
        """``Game.UnityResolution`` 选了尺寸就返回 (宽, 高)，Off 返回 None。"""

        return parse_resolution_option(self.script_config.Game.UnityResolution)

    def _note_resolution_override_skipped(self) -> None:
        """游戏已在运行时不能中途改分辨率，选了尺寸的用户要知道这轮没改。"""

        if self._unity_resolution_target() is not None:
            self._append_log("检测到游戏已在运行，本轮不会中途修改分辨率")

    def _note_launch_arguments_skipped(self) -> None:
        """游戏已在运行时不会重复启动，配了启动参数的用户要知道这轮没生效。"""

        arguments = str(self.script_config.Game.Arguments or "").strip()
        if arguments:
            self._append_log(f"检测到游戏已在运行，本轮不会应用启动参数（{arguments}）")

    async def _apply_game_resolution_override(self, game_path: Path) -> None:
        """按 exe 反查 Unity 注册表并临时写入所选尺寸的窗口模式。

        失败不阻断启动：这只是帮用户过脚本侧的分辨率闸门，改不成就按当前分辨率
        启动，闸门该报什么由脚本自己报，比在这里把整轮打掉更贴题。
        """

        target = self._unity_resolution_target()
        if target is None:
            return
        override = UnityGameResolutionOverride.for_executable(game_path, *target)
        if override is None:
            self._append_log(
                f"未找到 {game_path.name} 的 Unity app.info，无法反查注册表，"
                "跳过临时固定分辨率（只有 Unity 引擎的游戏支持）"
            )
            return
        # 先记下再写：写注册表在工作线程里，等它时被停止（取消）的话，收尾的
        # _close_game 仍要能把它恢复回去
        self.game_resolution_override = override
        try:
            await asyncio.to_thread(override.apply)
        except Exception as exc:
            self.game_resolution_override = None
            logger.warning(f"MaaFW 临时固定游戏分辨率失败: {exc}")
            self._append_log(f"临时固定游戏分辨率失败，按当前分辨率启动: {exc}")
            return
        self._append_log(
            f"已尝试把 HKCU\\{override.registry_path} 的分辨率临时设为 "
            f"{override.label} 窗口模式，游戏关闭后恢复原值"
        )

    async def _restore_game_resolution_override(self) -> None:
        override = self.game_resolution_override
        if override is None:
            return
        self.game_resolution_override = None
        try:
            restored = await asyncio.to_thread(override.restore)
        except Exception as exc:
            logger.warning(f"MaaFW 恢复游戏分辨率注册表失败: {exc}")
            self._append_log(f"恢复游戏分辨率注册表失败: {exc}")
            return
        if restored:
            self._append_log("已恢复启动前的游戏分辨率注册表")

    async def _wait_for_desktop_game_ready(
        self,
        game_path: Path,
        poll_interval: float = 1.0,
    ) -> bool:
        """等到游戏窗口（或配置了句柄时等到进程）就绪。

        返回窗口是不是**等出来的**：第一轮就在的算 False（游戏早就在跑），至少睡过
        一轮才出现的算 True（游戏正在启动）。调用方据此决定要不要再等画面稳定。
        """

        wait_time = max(0, int(self.script_config.Game.WaitTime or 0))
        if wait_time <= 0:
            # 「等待时间」填 0 只表示不等画面稳定；窗口还是要等出来，否则刚拉起的游戏
            # 当场判「窗口未就绪」、被关掉重试，次次如此
            wait_time = _WINDOW_READY_FALLBACK_SECONDS
        if self.run_plan is None or self.interface_model is None:
            raise RuntimeError("MaaFW 运行计划未完成初始化")

        configured_hwnd = self.script_config.Device.HWnd
        explicit_hwnd = _optional_int(configured_hwnd)
        controller = _find_controller(
            self.interface_model, self.run_plan.controllerName
        )

        self._append_log(
            f"正在等待游戏客户端窗口就绪，最大等待时间 {wait_time}s: {game_path.name}"
        )

        waited = 0.0
        process_detected = False
        while waited < wait_time:
            if not explicit_hwnd:
                matches = await asyncio.to_thread(_match_controller_windows, controller)
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited > 0

            if await asyncio.to_thread(_is_process_path_running, game_path):
                if not process_detected:
                    self._append_log(f"检测到游戏进程已启动: {game_path.name}")
                    process_detected = True

                if explicit_hwnd:
                    self._append_log(
                        f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}"
                    )
                    return waited > 0

                matches = await asyncio.to_thread(_match_controller_windows, controller)
                if matches:
                    selected = matches[0]
                    self._append_log(
                        "检测到游戏客户端窗口: "
                        f"hWnd={selected.hWnd}, class={selected.className}, "
                        f"title={selected.windowName}"
                    )
                    return waited > 0

            sleep_seconds = min(poll_interval, wait_time - waited)
            await asyncio.sleep(sleep_seconds)
            waited += sleep_seconds

        if not explicit_hwnd:
            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

        if await asyncio.to_thread(_is_process_path_running, game_path):
            if explicit_hwnd:
                self._append_log(f"已配置窗口句柄，跳过窗口正则等待: {explicit_hwnd}")
                return True

            matches = await asyncio.to_thread(_match_controller_windows, controller)
            if matches:
                selected = matches[0]
                self._append_log(
                    "检测到游戏客户端窗口: "
                    f"hWnd={selected.hWnd}, class={selected.className}, "
                    f"title={selected.windowName}"
                )
                return True

            raise RuntimeError(f"游戏窗口在 {wait_time}s 内未就绪: {game_path.name}")

        raise RuntimeError(f"游戏进程在 {wait_time}s 内未启动: {game_path.name}")

    def _task_start_not_before(self) -> float | None:
        """本轮刚启动的游戏，第一个任务最晚可下发的墙钟时刻；不用等时返回 None。

        沿用 ``Game.WaitTime``，用户只需要理解一个「启动等待时间」：桌面游戏等窗口出现
        用的就是它，等画面稳定再用一次同样的上限；模拟器上从 MAS 随模拟器把游戏拉到
        前台起算。起算时刻（``game_started_at``）之后已经过去的部分（窗口前置、ADB 路径
        解析、运行池租约、准备 job）先扣掉；剩下的交给 worker 在初始化完成后补足，
        这样 MaaFW 加载资源、连 controller、起 agent 的几秒到十几秒也算在等待里。
        worker 看到画面稳定会提前放行，这个时刻只是上限。游戏早就在跑时剩余为负，
        直接不等。

        模拟器冷启动（``game_start_disk_quiet``）时 worker 按「画面有内容、读盘停下来」提前
        放行，到这个时刻还是黑屏就继续等。这时剩余为负也照样给时刻，让 worker 做黑屏检查。
        """

        started_at = self.game_started_at
        if started_at is None:
            return None
        settle = max(0, int(self.script_config.Game.WaitTime or 0))
        if settle <= 0:
            return None
        remaining = settle - (time.monotonic() - started_at)
        if self.game_start_disk_quiet:
            self._append_log(
                f"模拟器冷启动游戏，最多等 {settle}s 再下发任务，画面出来且读盘停下来即提前；"
                f"剩余约 {max(remaining, 0):.0f}s（与 MaaFW 初始化并行）"
            )
            return time.time() + remaining
        if remaining <= 0:
            return None
        self._append_log(
            f"游戏窗口出现后最多等 {settle}s 再下发任务，画面稳定即提前；"
            f"剩余约 {remaining:.0f}s（与 MaaFW 初始化并行）"
        )
        return time.time() + remaining

    async def _activate_desktop_game_window(self, game_path: Path) -> None:
        try:
            # 第二个参数是**秒数**，不是截止时刻。dev 的 #473 把计时改成单调时钟后
            # 内部是 `time.monotonic() + timeout_seconds`，传 datetime 会直接
            # TypeError（真机上表现为「游戏进程已启动，但定位窗口失败」，窗口没被
            # 前置，随后第一个任务识别不到而失败）。
            await self.game_process_manager.search_process(
                ProcessInfo(exe=str(game_path.resolve())),
                WINDOW_SEARCH_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(f"MaaFW 定位游戏进程窗口失败: {exc}")
            self._append_log(f"游戏进程已启动，但定位窗口失败: {exc}")
            return

        activate_end_time = datetime.now() + timedelta(seconds=5)
        while datetime.now() < activate_end_time:
            if await self.game_process_manager.activate_window():
                self._append_log("游戏窗口已置于前台")
                return
            await asyncio.sleep(0.5)

        self._append_log("游戏窗口前置失败，将继续启动 MaaFW 任务")

    def _attempt_limit(self) -> int:
        """本用户这次运行最多跑几次：``Run.RunTimesLimit``，加上清理残留后额外的重跑。"""

        return int(self.script_config.Run.RunTimesLimit or 0) + self._extra_attempts

    async def _recover_resource_failure(self, kind: str) -> tuple[str, str] | None:
        """资源包加载失败之后：视图刚换了载荷（清掉了旧版本残留，或经组同步换上了同组兄弟已
        清理过的那份）就返回下一次的（开头那行, 称呼），该立刻再跑一次；其余情况写一行停止
        原因、返回 None（不重试）。

        只有 MaaFramework 拒收资源包（``load_failed``）才核对：资源目录不在（``missing``）不是
        多了文件。每次运行只核对一次；开发者模式（跟随来源目录）以来源为准、不更新，不核对。
        """

        if kind != "load_failed" or self._release_check_done:
            self._append_log(_RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
            return None
        self._release_check_done = True
        from .embedded_project import follow_source_enabled, shell_hint_from_report

        if follow_source_enabled(self.script_config):
            self._append_log(
                "开发者模式（跟随来源目录）以来源目录为准，不与官方发行包核对；"
                + _RESOURCE_FAILURE_STOP_MESSAGE,
                warning=True,
            )
            return None

        import httpx

        from .update_credentials import resolve_update_credentials
        from .view_release_check import (
            check_view_release,
            describe_outcome,
            release_group_members,
        )

        script_id = str(self.script_info.script_id)
        proxy_url = resolve_update_proxy_url(self.script_config)
        try:
            proxy = httpx.Proxy(proxy_url) if proxy_url else None
        except Exception:  # noqa: BLE001 - 代理填错按直连，地址不进日志
            proxy = None
        stop = threading.Event()
        task = asyncio.create_task(
            check_view_release(
                script_id,
                channel=resolve_update_credentials(self.script_config).channel,
                members=lambda: release_group_members(script_id),
                send_log=self._append_log,
                proxy=proxy,
                shell_hint=shell_hint_from_report(self.script_config),
                script_name=str(self.script_info.name or ""),
                cancel_event=stop,
            )
        )
        # 核对 / 清理 / 切视图都在工作线程里改载荷与视图：用户这时点停止，得等它收尾再放预约
        # （_release_project_path 会等这个任务），否则编辑页的导入、手动更新能同时动同一棵视图。
        self._release_check_task = task
        try:
            outcome = await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            raise
        self._append_log(describe_outcome(outcome), warning=not outcome.switched)
        cleaned = outcome.status in {"cleaned", "repointed"}
        if outcome.switched and outcome.version_changed:
            # 等锁那几秒里组被推到了新版本、视图跟着换了：本次的 interface 与运行计划是按旧
            # 版本建的，不能拿来跑新版本。停下，下次运行前按新版本重做检查。
            self._append_log(
                f"本脚本已换到 {outcome.version or '新版本'}，这一轮不再重新运行，"
                "下次运行会按新版本重新准备",
                warning=True,
            )
            return None
        if outcome.switched:
            # 视图换了载荷就重跑，不看 status：同组兄弟已清理过、本脚本经组同步换过来时，
            # 核对的是换来的那份（status 是 verified / clean），旧视图里的残留照样没了。
            self._append_log(
                "已换上清理后的版本，立即重新运行（不重启游戏/模拟器）"
                if cleaned
                else "立即用换上的版本重新运行（不重启游戏/模拟器）"
            )
            return _RERUN_AFTER_CLEANUP if cleaned else _RERUN_AFTER_SWITCH
        if cleaned:
            self._append_log(
                "清理后的版本已准备好，但本脚本这次没能切换过去，下次运行前自动切换",
                warning=True,
            )
        self._append_log(_RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
        return None

    async def _reset_client_for_retry(self, attempt: int) -> tuple[bool, bool]:
        """重试前关掉 MAS 自己起的客户端，返回（是否全部关成, 是否已不在）。

        前者只决定下一轮日志开头写不写「已重启」；后者给运行前设置判断要不要重跑——
        关的时候报错，opened_* 也已清掉、下一轮会重新拉起，运行前设置同样要重来。
        """

        had_client = self.opened_game or self.opened_emulator
        restarted = await self._restart_client_before_retry(attempt)
        still_open = self.opened_game or self.opened_emulator
        return restarted, bool(had_client and not still_open)

    async def _restart_client_before_retry(self, attempt: int) -> bool:
        """一轮失败后把 MAS 自己拉起的游戏/模拟器关掉，让下一轮从启动重新来。

        和 MAA 专项的重试一个口径：出了问题就整个重来。以前重试只是重启 MaaFW 框架
        再接回同一个窗口——超时那种卡在某一屏的情况（弹窗关不掉、按钮点不动），
        第二、三轮 3 秒内就撞回同一屏，白等两倍时限。
        游戏/模拟器不是 MAS 起的（AttachOnly、发现已在运行）时照旧不碰；
        这是最后一轮时也不在这里关，收尾统一关。返回这次是否全部关成：
        该关的有一个没关成就是 False，下一轮日志开头不写「已重启」。
        """

        if attempt >= self._attempt_limit():
            return False
        if not self.opened_game and not self.opened_emulator:
            return False
        self._append_log("本轮失败，关闭由 MAS 启动的游戏/模拟器，下一轮重新启动")
        emulator_closed = await self._close_emulator()
        game_closed = await self._close_game()
        return emulator_closed and game_closed

    def _start_attempt_log(self) -> None:
        """重试前另起一份日志记录，与 MAA 等专项一样每次尝试单独成段。

        界面日志从这一次重新显示；history 里的 ``.log`` / ``.json``、``.worker.log``、
        ``.maafw.log`` 与失败截图都使用本次尝试自己的临时目录。保留真实开始时刻，
        不再为了文件名冲突顺延时间。
        """

        start_time = datetime.now().astimezone()
        self.cur_user_log_started_at = start_time
        self.cur_user_log = LogRecord()
        self.cur_user_item.add_log_record(start_time, self.cur_user_log)
        # 这份日志从零开始，行号也要回到 1，否则会接着上一个用户的行号往下数
        self.script_info.log_first_line = 1

    def _run_record_call(self, action: Callable[[], Any]) -> Any:
        """运行记录是旁路：记录这一侧出了错只记后端日志、返回 None，不影响运行与收尾。"""

        try:
            return action()
        except Exception as exc:  # noqa: BLE001 - 旁路不能拖垮运行
            logger.opt(exception=True).warning(
                f"MaaFW 运行记录出错（不影响运行）: {exc}"
            )
            return None

    def _begin_run_record_attempt(self, attempt: int) -> None:
        """这次尝试的结构化记录：与本次尝试的日志（history 记录）同一个键。"""

        def begin() -> None:
            plan = self.run_plan
            self._run_record.begin_attempt(
                id(self.cur_user_log),
                attempt=attempt,
                title=self._attempt_title or f"第 {attempt} 次尝试",
                planned=(
                    [(task.name, _task_display_name(task)) for task in plan.tasks]
                    if plan is not None
                    else []
                ),
                retry_skipped=(
                    len(_retry_skipped_tasks(plan)) if plan is not None else 0
                ),
            )

        self._run_record_call(begin)

    def _run_record_statistic(self, key: int) -> HistorySnapshotStatistic | None:
        """某次尝试的运行记录，包成 history 的 snapshot 统计；没有记录返回 None。"""

        value = self._run_record.history_value(key)
        return HistorySnapshotStatistic(value=value) if value is not None else None

    def _on_run_record_event(self, data: Any) -> None:
        """worker 推来的阶段 / 任务起止：归进本次尝试的记录，任务开始时刷新调度台进度。"""

        progress = self._run_record_call(lambda: self._run_record.apply(data))
        if progress is not None:
            self.cur_user_item.progress = progress

    def run_incident_notice(self) -> str:
        """本次运行里被原地打转检测或单任务时限停下的任务：进用户与脚本两份报告。

        只在最后没成功时列出（各次尝试的都列）；后面的重试成功了就不写，免得一份
        「全部完成」的报告里还挂着前面尝试的问题。"""

        if self.run_complete:
            return ""
        return (
            self._run_record_call(
                lambda: format_incident_lines(self._run_record.incidents())
            )
            or ""
        )

    async def _finish_on_signal(self, attempt: int, result: MaaFWRunResult) -> None:
        """worker 回报了信号节点命中：记账、写日志状态。

        不发任务页提示（TASK_NOTICE 会在前端弹通知框并响提示音）：界面上只有 runner
        那行日志，正式通知由管理器收尾时按「信号 + 资源」各发一条（同一资源可能有
        多位用户）。证据图只进那条通知，不当失败截图进统计信息与汇总。
        """

        signal = str(result.signal)
        self.run_signal = signal
        message = SIGNAL_USER_MESSAGES.get(signal, str(result.errorMessage or signal))
        # runner 那行「游戏停服维护中，本轮剩余任务已跳过: <任务>」已进任务日志，
        # 这里只记后端日志，不在界面上再复述一遍。
        logger.warning(
            f"MaaFW 用户 {self.cur_user_item.name} 命中项目信号 {signal}"
            f"（节点 {result.signalNode}）：{message}"
        )
        # 证据图只认命中那个任务、kind 是信号那种的：前面任务普通失败的 failed 图不算。
        evidence = _signal_evidence_shot(result)
        labels = (
            _format_completed_task_labels(self.run_plan, result.completedTasks)
            if self.run_plan is not None
            else list(result.completedTasks)
        )
        # 证据图只随信号通知发一次，不再进统计信息与代理结果汇总；前面任务的普通
        # 失败截图照常进。
        report_shots = [
            (
                _format_completed_task_labels(self.run_plan, [shot.task])[0]
                if self.run_plan is not None
                else shot.task,
                Path(shot.path),
            )
            for shot in result.failureScreenshots
            if shot is not evidence
        ]
        self._record_attempt(
            attempt,
            labels,
            message,
            screenshots=report_shots,
            category=CATEGORY_SIGNAL,
            signal=signal,
        )
        if self.cur_user_log is not None:
            self.cur_user_log.status = message

        project_name = ""
        if self.interface_model is not None:
            with suppress(Exception):
                project_name = await asyncio.to_thread(
                    interface_display_name, self.project_path, self.interface_model
                )
        plan = self.run_plan
        if not project_name and plan is not None:
            project_name = str(plan.projectLabel or plan.projectName or "")
        resource_label = ""
        if plan is not None:
            label = str(plan.resource.label or "").strip()
            resource_label = (
                label if label and not label.startswith("$") else plan.resourceName
            )
        self.signal_tracker.record(
            signal,
            resource_name=plan.resourceName
            if plan is not None
            else result.resourceName,
            resource_label=resource_label,
            project_name=project_name,
            node=result.signalNode,
            user_id=str(self.cur_user_uid),
            user_name=self.cur_user_item.name,
            screenshot=Path(evidence.path) if evidence is not None else None,
        )

    def _is_maintenance_skip(self) -> bool:
        return self.maintenance_skipped or self.run_signal == SERVER_MAINTENANCE

    def _signal_user_message(self) -> str | None:
        """本用户因信号没跑成时给人看的原因；没有信号返回 None。"""

        if self.maintenance_skipped:
            return MAINTENANCE_SKIP_MESSAGE
        if self.run_signal is not None:
            return SIGNAL_USER_MESSAGES.get(self.run_signal, self.run_signal)
        return None

    def _timed_out_user_summary(self, result: MaaFWRunResult) -> str:
        limit = self.script_config.Run.RunTimeLimit
        total = len(self.run_plan.tasks) if self.run_plan is not None else 0
        stopped_at = ""
        if result.failedTask and self.run_plan is not None:
            labels = _format_completed_task_labels(self.run_plan, [result.failedTask])
            stopped_at = f"，最后停在 {labels[0]}"
        return (
            f"MaaFW 任务运行超时（限制 {limit} 分钟，已完成 "
            f"{len(result.completedTasks)}/{total}{stopped_at}）"
        )

    async def _close_game(self) -> bool:
        """关闭由 MAS 启动的游戏，返回是否关成（本来就没开过算关成）。

        只看 opened_game：由 MAS 启动的一律关，其他方式启动（AttachOnly、或
        DirectExe 下发现游戏已在运行而没重复启动）的一律不碰，没有开关。
        """

        if not self.opened_game:
            await self._restore_game_resolution_override()
            return True

        try:
            await self.game_process_manager.kill()
            return True
        except Exception as exc:
            logger.warning(f"MaaFW 清理时关闭游戏失败: {exc}")
            return False
        finally:
            self.opened_game = False
            self.game_started_at = None
            await self._restore_game_resolution_override()

    async def _try_enter_project_path(self) -> bool:
        project_lock_key = await try_reserve_project_path(self.project_path)
        if project_lock_key is None:
            return False
        self.project_lock_key = project_lock_key
        return True

    async def _release_project_path(self) -> None:
        if self.project_lock_key is None:
            return
        pending = self._release_check_task
        if pending is not None and not pending.done():
            # 资源加载失败后的核对 / 清理还在工作线程里改视图（用户停止时）：等它收尾，等不到就
            # 把释放交给它的完成回调，预约不能先放。
            with suppress(BaseException):
                await asyncio.wait_for(
                    asyncio.shield(pending),
                    timeout=_RELEASE_CHECK_CANCEL_GRACE_SECONDS,
                )
            if not pending.done():
                key = self.project_lock_key
                self.project_lock_key = None

                def _release_later(task: asyncio.Task[Any]) -> None:
                    # 顺手取走异常，免得报「never retrieved」（同 manager 的 _release_after_work）
                    if not task.cancelled():
                        task.exception()
                    release_project_path_sync(key)

                pending.add_done_callback(_release_later)
                return
        await release_project_path(self.project_lock_key)
        self.project_lock_key = None

    def _ensure_display_hold(self) -> None:
        """没有生效中的「保持显示开启」请求就再请求一份。

        每次尝试开头都调：电源延时 / 倒计时期间又起了任务时，MAS 执行睡眠 / 休眠前会撤掉
        所有请求、醒来后不会自己补；请求本身失败也会变成已撤销。怕熄屏的启动器那一步就在
        尝试开头的运行前设置里。
        """

        hold = self._display_hold
        if hold is None or not hold.active:
            self._display_hold = power.hold_display(
                f"MFW 运行（{self.cur_user_item.name}）"
            )

    def _release_display_hold(self) -> None:
        hold, self._display_hold = self._display_hold, None
        if hold is not None:
            hold.release()

    async def _freeze_notification_images(self) -> None:
        """归档会移动临时文件，通知及跨用户报告先持有自己的图片内容。"""
        self._notification_screenshots = []
        for label, path in self._collect_failure_screenshots()[
            -NOTIFY_SCREENSHOT_LIMIT:
        ]:
            try:
                self._notification_screenshots.append(
                    (label, await asyncio.to_thread(path.read_bytes))
                )
            except OSError as error:
                self._append_log(f"冻结通知截图失败：{error}", warning=True)
        await self.signal_tracker.freeze_user_screenshots(str(self.cur_user_uid))

    async def _save_user_history(self) -> None:
        if self._history_saved:
            return
        self._history_saved = True
        # 预检未派发的用户只保留当前报告；实际执行后遇到维护仍归档 skipped。
        if self.check_result != "Pass":
            return
        try:
            await self._freeze_notification_images()
        except Exception as error:
            self._append_log(f"冻结通知截图失败：{error}", warning=True)
            logger.opt(exception=True).warning(f"冻结通知截图失败：{error}")
        # 用户停止 / 崩溃时最后一次尝试没走到 _record_attempt：按停止或宿主异常收尾
        self._run_record_call(
            lambda: self._run_record.finish_attempt(
                outcome="stopped" if self.stopped_manually else "failed",
                category=CATEGORY_USER_STOPPED
                if self.stopped_manually
                else CATEGORY_HOST_ERROR,
            )
        )
        records = []
        items = list(self.cur_user_item.iter_history_logs())
        for timestamp, log_item in items:
            status = self._history_statuses.get(id(log_item))
            if status is None:
                status = (
                    "cancelled"
                    if self.stopped_manually
                    else "skipped"
                    if self._is_maintenance_skip()
                    else "error"
                )
            record = HistoryWrite(
                time=timestamp.astimezone(UTC4),
                username=self.cur_user_item.name,
                script_name=self.script_info.name,
                status=status,
                message=log_item.status,
                logs="".join(log_item.content),
            )
            run_record = self._run_record_call(
                lambda: self._run_record_statistic(id(log_item))
            )
            if run_record is not None:
                record.data[RUN_RECORD_HISTORY_KEY] = run_record
            record.attachments.extend(self._history_attachments.get(id(log_item), []))
            records.append(record)
        if records:
            await self.task_info.save_user_history(
                records,
                script=self.script_info,
                user=self.cur_user_item,
                log_warning=partial(self._append_log, warning=True),
            )

    def _record_attempt(
        self,
        attempt: int,
        completed_labels: list[str],
        failure: str | None,
        *,
        screenshots: list[tuple[str, Path]] | None = None,
        category: str | None = None,
        signal: str | None = None,
        user_message: str | None = None,
        failed_task: str | None = None,
    ) -> None:
        """记下本次尝试的结果，供统计通知的「任务详情」与失败截图用。

        ``category`` / ``signal`` 进结构化运行记录；没给类别的失败由记录按任务结局补
        （任务都没开始是初始化失败，否则取第一个计入失败的任务的类别）。
        ``user_message`` / ``failed_task`` 是 worker 回报的人话摘要与失败任务名，推送里的
        失败原因只从它们和失败类别来（``failure`` 是日志里那句，可能带节点链等排障细节）。
        """

        if self.cur_user_log_started_at is not None:
            self._history_statuses[id(self.cur_user_log)] = (
                "success"
                if failure is None
                else "skipped"
                if self.run_signal == SERVER_MAINTENANCE
                else "error"
            )
        self._run_record_call(
            lambda: self._run_record.finish_attempt(
                outcome=(
                    "success"
                    if failure is None
                    else "skipped"
                    if self.run_signal == SERVER_MAINTENANCE
                    else "failed"
                ),
                category=category,
                signal=signal,
            )
        )
        self._attempt_reports.append(
            {
                "attempt": attempt,
                "title": self._attempt_title or f"第 {attempt} 次尝试",
                "time": datetime.now().strftime("%H:%M:%S"),
                "completed": list(completed_labels),
                "failure": failure,
                "screenshots": list(screenshots or []),
                # 对上这次尝试的运行记录（键同 _begin_run_record_attempt）
                "record_key": id(self.cur_user_log),
                "user_message": user_message,
                "failed_task": failed_task,
            }
        )

    def _collect_failure_screenshots(self) -> list[tuple[str, Path]]:
        """本用户要随通知发出去的失败截图（标签, 路径），按时间顺序。

        最终成功的运行不带图：任务详情那边成功时也不提前面尝试的失败，
        早先尝试的失败画面对已经跑通的一轮没有意义。张数上限由消费方裁。
        """

        if self.run_complete:
            return []
        shots: list[tuple[str, Path]] = []
        for report in self._attempt_reports:
            for label, path in report.get("screenshots", ()):
                shots.append((f"{report['title']} · {label}", path))
        return shots

    def report_screenshots(self) -> list[tuple[str, bytes]]:
        """给脚本级「代理结果」报告用的失败截图，标签带上用户名以区分多用户。"""

        return [
            (f"{self.cur_user_item.name} · {label}", path)
            for label, path in self._notification_screenshots
        ]

    def _build_task_details(self) -> str:
        """用户级统计报告的任务详情：最后一次尝试的逐任务时间线（见 ``run_report``）。

        最后没成功时另起一段列各次尝试里的原地打转 / 单任务超时（每类一行），队列里有
        失效任务时末尾再附一行。整次运行一个任务都没开始时没有时间线，原因在运行结果那行。
        """

        details = self._run_record_call(self._task_timeline)
        if details is None:
            details = self._completed_tasks_fallback()
        incidents = self.run_incident_notice()
        missing = self.missing_task_notice()
        return "\n\n".join(part for part in (details, incidents, missing) if part)

    def _attempt_outcomes(self) -> list[MaaFWAttemptReport]:
        """各次尝试的运行记录，配上 worker 回报的人话摘要与失败任务名。"""

        reports = {report.get("record_key"): report for report in self._attempt_reports}
        outcomes = []
        for key, record in self._run_record.attempt_items():
            report = reports.get(key) or {}
            outcomes.append(
                MaaFWAttemptReport(
                    record=record,
                    user_message=report.get("user_message"),
                    failed_task=report.get("failed_task"),
                )
            )
        return outcomes

    def _task_timeline(self) -> str | None:
        """逐任务时间线；没有运行记录返回 None（由调用方退回完成清单）。"""

        outcomes = self._attempt_outcomes()
        if not outcomes:
            return None
        return format_timeline(outcomes)

    def _completed_tasks_fallback(self) -> str:
        """运行记录出错、没有可用记录时的退路：只列完成了哪些任务，不带失败原文。"""

        reports = getattr(self, "_attempt_reports", None) or []
        if not reports:
            return ""
        if getattr(self, "run_complete", False):
            merged: list[str] = []
            for report in reports:
                for label in report["completed"]:
                    if label not in merged:
                        merged.append(label)
        else:
            merged = list(reports[-1]["completed"])
        return "已完成: " + ("、".join(merged) if merged else "无")

    def _report_result(self, *, short: bool = False) -> str:
        """本用户这次的结果，用户级统计报告与脚本级「代理结果」同一口径。

        成功只说完成；失败说失败在哪些任务、为什么（只用人话，见 ``run_report``）；
        信号与运行前检查跳过沿用原来那句话。``short``：脚本级每个用户一行用的简短说法。
        """

        if self.run_complete:
            if self.missing_task_names:
                return MISSING_TASK_USER_RESULT
            return "全部完成" if short else "代理任务全部完成"
        signal_message = self._signal_user_message()
        if signal_message is not None:
            return signal_message
        if self.check_result != "Pass":
            return (
                self.cur_user_log.status
                if self.cur_user_log is not None
                else self.check_result
            )
        summary = self._run_record_call(
            lambda: failure_summary(self._attempt_outcomes())
        )
        if summary:
            return summary
        crash = getattr(self, "_crash_message", None)
        if crash is not None:
            # 还没进第一次尝试就崩了：没有运行记录，按崩溃原因说一句
            reason = human_reason(crash) or CATEGORY_REASONS[CATEGORY_HOST_ERROR]
            return f"MaaFW 运行失败：{reason}"
        return "代理任务未完成"

    def proxy_report_line(self) -> str | None:
        """脚本级「代理结果」里本用户的那一行；运行前检查没过、也没记日志的返回 None，
        由管理器沿用通用的用户结果。"""

        if self.check_result != "Pass" and self.cur_user_log is None:
            return None
        return self._report_result(short=True)

    def missing_task_notice(self) -> str:
        """队列里 interface 已没有的任务（多半是项目更新改了 name）：进用户与脚本两份报告。"""

        if not self.missing_task_names:
            return ""
        return f"{MISSING_TASK_NOTICE_PREFIX}: " + "、".join(self.missing_task_names)

    async def _push_user_statistics(self) -> None:
        """按通知设置推送用户级统计信息。

        与 M9A 专项同形（``M9A/AutoProxy.py`` 的「统计信息」分支）：合并本轮各次
        尝试的统计文件，补上用户名 / 起止时间 / 结果，再发往全局与该用户自己的
        渠道。``MaaFWUserConfig`` 的 Notify 组一直都在、编辑页也能配，但在此之前
        没有任何代码往它发——脚本级「代理结果」是唯一会发出去的报告。

        放在状态落定之后：``user_result`` 要读最终的 ``run_complete``。
        """

        try:
            statistics = {}
            statistics["user_info"] = self.cur_user_item.name
            statistics["start_time"] = (
                self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
                if self.user_start_time is not None
                else ""
            )
            statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            statistics["task_details"] = self._build_task_details()
            images = await prepare_screenshot_images(
                self._notification_screenshots,
                image_id_prefix="maafw",
            )
            statistics["screenshots"] = screenshot_entries(images)
            # 有失效任务时照常算完成（次数、状态不动），但不能说成「全部完成」；
            # 失败时不再用日志状态那句（里面可能有节点链、框架事件）
            statistics["user_result"] = self._report_result()
            if self.run_complete and self.missing_task_names:
                mark = "!"
            elif self.run_complete:
                mark = "√"
            elif self._is_maintenance_skip():
                mark = MAINTENANCE_LAST_STATUS
            else:
                mark = "X"
            await Notify.push_statistics_report(
                payload=_format_maafw.build_statistics_payload(
                    title=f"{datetime.now().strftime('%m-%d')} |{mark}|  {self.cur_user_item.name} 的自动代理统计报告",
                    message=statistics,
                    images=[image for _, image in images],
                ),
                user_config=self.cur_user_config,
                task_info=self.task_info,
            )
        except Exception as exc:
            logger.opt(exception=True).warning(f"推送 MaaFW 统计信息时出现异常: {exc}")
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"推送 MaaFW 统计信息时出现异常: {exc}",
                    ),
                )

    async def _send_success_notify(self) -> None:
        try:
            if self.missing_task_names:
                names = "、".join(self.missing_task_names)
                await Notify.send_notice(
                    LocalNotice(
                        title="MaaFW 自动代理任务完成，但有失效任务",
                        message=f"用户 {self.cur_user_item.name} 的队列里有 interface 内已没有的任务，"
                        f"已跳过：{names}",
                        ticker=f"{self.cur_user_item.name} 有失效任务：{names}",
                        duration_seconds=3,
                    )
                )
                return
            await Notify.send_notice(
                LocalNotice(
                    title="MaaFW 自动代理任务完成",
                    message=f"已完成用户 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    ticker=f"已完成 {self.cur_user_item.name} 的 MaaFW 自动代理任务",
                    duration_seconds=3,
                )
            )
        except Exception as exc:
            logger.warning(f"MaaFW 插件用户通知发送失败: {exc}")

    def _append_log(self, message: str, *, warning: bool = False) -> None:
        # 失败类的用户日志按 WARNING 进 app.log，事后按级别筛得出来
        (logger.warning if warning else logger.info)(message)
        if self.cur_user_log is None:
            self._pending_user_log.append(_format_user_log_line(message))
            return
        content = self.cur_user_log.content
        content.append(_format_user_log_line(message))
        kept = content[-80:]
        self.script_info.log = "".join(kept)
        # 滑出窗口的行仍然占着行号：界面据此从 81 接着往下数，而不是每轮都把
        # 最后 80 条重新编号成 1-80。
        dropped_lines = sum(chunk.count("\n") for chunk in content[:-80])
        self.script_info.log_first_line = dropped_lines + 1


def _sweep_legacy_runner_jobs() -> None:
    """清掉升级前的版本留下的 job 文件（现在 job 经 worker 的 stdin 传，不再落盘）。

    旧版本把 job 写在 ``data/maafw_runner_jobs``（更早是 ``runtime/maafw_runner_jobs``，
    首次访问时整体迁过来再清）。目录本身不再新建。
    """

    jobs_dir = Path.cwd() / "data" / "maafw_runner_jobs"
    _utils_io.migrate_legacy_dir(Path.cwd() / "runtime" / "maafw_runner_jobs", jobs_dir)
    _sweep_stale_runner_jobs(jobs_dir)


def _maafw_agent_constraints_dir() -> Path:
    """agent 运行期 pip 约束文件的目录（一个项目一份 ``maafw_agent_<路径哈希>.txt``，由 worker 写）。"""

    return Path.cwd() / "data" / "maafw_agent_constraints"


# 旧版本的 worker 读完 job 就删，正常情况下 job 文件只在盘上待几秒；超过这么久还在的，
# 是宿主与 worker 一起被硬杀（断电、蓝屏、结束进程树）留下的。
_STALE_RUNNER_JOB_SECONDS = 3600.0


def _sweep_stale_runner_jobs(directory: Path) -> None:
    """删掉上次异常退出残留的 job 文件：里面可能有解密后的密码选项。"""

    try:
        candidates = list(directory.glob("maafw-runner-job-*.json"))
    except OSError:
        return
    now = time.time()
    for path in candidates:
        try:
            if now - path.stat().st_mtime < _STALE_RUNNER_JOB_SECONDS:
                continue
            path.unlink()
        except OSError:
            continue
        logger.info(f"已清理残留的 MaaFW job 文件: {path.name}")


def _find_controller(
    interface_model: MaaFWInterface, controller_name: str
) -> MaaFWController:
    controller = next(
        (item for item in interface_model.controller if item.name == controller_name),
        None,
    )
    if controller is None:
        raise RuntimeError(f"未找到 controller: {controller_name}")
    return controller


def _match_controller_windows(controller: MaaFWController) -> list[Any]:
    # 插件形态下先查 maafw.controller.win32 服务契约再回退到直接实例化；
    # 树内没有服务契约层，直连实现（移植指南 §4 规则 4）
    service = MaaFWWin32ControllerService()
    controller_payload = controller.model_dump(mode="json", by_alias=True)
    return list(service.match_controller_windows(controller_payload))


def _is_process_path_running(executable_path: Path) -> bool:
    target_path = executable_path.resolve()
    for proc in psutil.process_iter(["exe"]):
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            raw_exe = proc.info.get("exe") or proc.exe()
            if raw_exe and Path(raw_exe).resolve() == target_path:
                return True
    return False


def _optional_int(value: Any) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_win32_method(
    configured_value: Any,
    interface_method: str | list[Any] | int | None,
    method_values: dict[str, int],
    default_name: str,
    *,
    label: str = "Win32 控制方式",
    warn: Callable[[str], None] | None = None,
    combinable: bool = False,
) -> int:
    """脚本级配置的数值优先，其次 interface 里写的名字，最后是默认方式。

    名字不认识时退回默认方式并**告警**：以前是静默换成 DXGI_DesktopDup / Seize，
    项目要的后台截图 / 后台输入悄悄变成前台，用户只看到游戏被抢了鼠标。

    名字大小写不敏感（MFAA 用 ``Enum.TryParse(ignoreCase)``）；可以写成数组（MXU）
    或逗号 / ``|`` 分隔（MFAA 的组合名写法），也可以是旧版整数。截图方式
    （``combinable``）按位或合并；输入方式原生层只能选一个，给了多个取第一个并告警。
    认得的值是不是当前原生库支持的，仍由 worker 的 ``_supported_win32_method`` 再判。
    """

    default = method_values[default_name]
    configured = _optional_int(configured_value) or 0
    if configured:
        return configured
    tokens = _win32_method_tokens(interface_method)
    if not tokens:
        return default
    report = warn or logger.warning
    by_name = {name.casefold(): (name, value) for name, value in method_values.items()}
    resolved: list[tuple[str, int]] = []
    unknown: list[str] = []
    for token in tokens:
        if isinstance(token, int):
            if token > 0:
                resolved.append((str(token), token))
            else:
                unknown.append(str(token))
            continue
        if token.isascii() and token.isdigit():
            # 与整数写法同口径：0 不是任何方式（worker 对 <= 0 直接放行，交下去就是
            # 「没有输入方式」），按无法识别处理。
            if int(token) > 0:
                resolved.append((token, int(token)))
            else:
                unknown.append(token)
            continue
        hit = by_name.get(token.casefold())
        if hit is None:
            unknown.append(token)
        else:
            resolved.append(hit)
    if not resolved:
        report(
            f"MaaFW interface 里 {label}「{_describe_win32_method(interface_method)}」"
            f"无法识别，已改用默认的 {default_name}"
        )
        return default
    if unknown:
        report(
            f"MaaFW interface 里 {label}中的「{'、'.join(unknown)}」无法识别，已忽略"
        )
    if combinable:
        value = 0
        for _, item in resolved:
            value |= item
        return value
    if len(resolved) > 1:
        report(
            f"MaaFW interface 里 {label}写了多个（"
            f"{'、'.join(name for name, _ in resolved)}），输入方式只能选一个，"
            f"已取第一个 {resolved[0][0]}"
        )
    return resolved[0][1]


def _win32_method_tokens(value: Any) -> list[str | int]:
    """把 interface 里的 Win32 方法声明拆成一个个名字 / 整数（空的丢掉）。"""

    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    items = value if isinstance(value, list) else [value]
    tokens: list[str | int] = []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            tokens.append(item)
            continue
        for part in re.split(r"[,|]", str(item)):
            part = part.strip()
            if part:
                tokens.append(part)
    return tokens


def _describe_win32_method(value: Any) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return str(value)


def _snapshot_descendants(pid: int) -> list[tuple[int, float]]:
    """记下某进程当前的全部后代（pid 与创建时间）。

    创建时间与 pid 配对使用，防止 pid 复用导致误杀——这段时间里原进程可能
    已经退出、pid 被别人占了。
    """

    snapshot: list[tuple[int, float]] = []
    try:
        for child in psutil.Process(pid).children(recursive=True):
            with suppress(psutil.Error):
                snapshot.append((child.pid, child.create_time()))
    except psutil.Error:
        return []
    return snapshot


def _terminate_snapshot(
    snapshot: list[tuple[int, float]], *, owner: str = "MaaFW worker"
) -> None:
    """结束快照里仍然存活、且身份对得上的进程。

    worker 被强杀后它启动的 agent 会变成孤儿：MaaFW 的 AgentClient 用 IPC 起
    agent，生命周期本该随 worker，但 TerminateProcess 不给收尾机会。实测残留
    过二十多个 agent.exe / python.exe，最老的有二十二小时，它们占内存也占文件
    句柄——曾导致 venv 目录删不掉。
    """

    victims: list[psutil.Process] = []
    for pid, create_time in snapshot:
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - create_time) > 1:
                continue  # pid 被复用了，不是当初那个进程
            process.terminate()
            victims.append(process)
        except psutil.Error:
            continue
    if not victims:
        return
    _gone, alive = psutil.wait_procs(victims, timeout=3)
    for process in alive:
        with suppress(psutil.Error):
            process.kill()
    psutil.wait_procs(alive, timeout=2)
    logger.info(f"已清理 {owner} 残留的 {len(victims)} 个子进程")


def _snapshot_pretask_script_descendants(pid: int) -> list[tuple[int, float, str]]:
    """运行前设置进程下面、要随它一起结束的脚本解释器后代：``(pid, 创建时间, 进程名)``。

    从 pretask 进程往下走，只认 ``_PRETASK_SCRIPT_HOST_NAMES`` 里的脚本解释器（python、cmd、
    powershell……），并且只穿过它们继续往下：pretask 直接或经脚本间接起的游戏、启动器
    不在名单里，它们自己再起的任何进程（哪怕也是 python）都不会走到。宁可少结束，
    不误杀本应继续运行的游戏。
    """

    found: list[tuple[int, float, str]] = []
    try:
        pending = list(psutil.Process(pid).children())
    except psutil.Error:
        return []
    while pending:
        child = pending.pop()
        try:
            name = child.name()
            if name.casefold() not in _PRETASK_SCRIPT_HOST_NAMES:
                continue
            found.append((child.pid, child.create_time(), name))
            pending.extend(child.children())
        except psutil.Error:
            continue
    return found


async def _wait_pretask_exit(
    process: asyncio.subprocess.Process, timeout: float
) -> bool:
    """等运行前设置进程退出，返回是否在 ``timeout`` 秒内退出。

    只看退出码，不用 ``process.wait()``：asyncio 的 wait() 要等输出管道全部关闭才返回，
    pretask 拉起的游戏 / 启动器继承了管道句柄时，它会一直等到游戏退出。
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(timeout, 0.0)
    while process.returncode is None:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return False
        await asyncio.sleep(min(_PRETASK_EXIT_POLL_SECONDS, remaining))
    return True


async def _kill_pretask_process(
    process: asyncio.subprocess.Process, append_log: Callable[[str], None]
) -> None:
    """结束运行前设置进程本身，以及它下面一路都是脚本解释器的后代。"""

    # 先记下要一起结束的脚本解释器后代（pretask 一死，按父子关系就查不到了）。只认
    # 一路都是脚本解释器的那一支：游戏 / 启动器以及它们起的进程都不在其中。
    scripts = await asyncio.to_thread(_snapshot_pretask_script_descendants, process.pid)
    # 不用 process.wait()：它要等输出管道关闭才返回，继承了管道的游戏不退它就不返回。
    try:
        if process.returncode is None:
            process.terminate()
        if not await _wait_pretask_exit(process, 5):
            process.kill()
            if not await _wait_pretask_exit(process, 5):
                logger.warning(
                    f"MaaFW 运行前设置进程（pid {process.pid}）强制结束后 5 秒仍未退出"
                )
    except ProcessLookupError:
        pass
    except Exception as exc:
        logger.warning(f"MaaFW 运行前设置进程清理失败: {exc}")

    if scripts:
        names = "、".join(f"{name}（pid {pid}）" for pid, _created, name in scripts)
        append_log(
            f"一并结束运行前设置启动的脚本进程：{names}；它启动的游戏 / 启动器不受影响"
        )
        await asyncio.to_thread(
            _terminate_snapshot,
            [(pid, created) for pid, created, _name in scripts],
            owner="MaaFW 运行前设置",
        )


class _PretaskOutputPump:
    """把运行前设置的输出按行交给 ``sink``（stdout 与 stderr 已合并）。

    按块读、自己分帧：``readline()`` 遇到超过 64 KB 的一行会抛错。行尾与原来整段
    ``splitlines()`` 同口径：``\\n``、单独的 ``\\r``（进度条原地刷新）、``\\r\\n`` 各算一次
    换行；``\\r`` 一到就把这一段交出去（进度实时可见），紧跟着的 ``\\n``（哪怕在下一块里）
    并进同一个换行。每行单独解码（与原来整段解码同一套编码顺序），先过 ``redact`` 打码
    再交出去。空白行与原来整段 ``strip()`` 后逐行写的口径一致：开头和结尾的空白行不写，
    夹在中间的照写。

    **打码边界**：只有遇到行尾（或 EOF，此时剩下的就是完整的最后一行）的段落才算完整
    片段，打码后交出；还没到行尾的部分一直留在缓冲里，不单独发布——密码可能正好被拆在
    两次读之间，两段各自做整串替换都匹配不上，拼起来就是明文。进程退出后管道还被别的
    程序占着时，``detach`` 只切换 sink：缓冲里的半行留着，和之后的输出拼成完整一行、
    打码后改写后端日志，读到 EOF 为止。
    """

    def __init__(
        self,
        sink: Callable[[str], None],
        *,
        redact: Callable[[str], str] = lambda line: line,
    ) -> None:
        self._sink = sink
        self._redact = redact
        self._pending = b""
        # 上一块以 \r 结尾、那一段已经交出：下一块开头的 \n 是同一个 \r\n，吞掉
        self._after_cr = False
        self._seen_text = False
        self._blank_lines = 0

    async def run(self, stream: asyncio.StreamReader | None) -> None:
        if stream is None:
            return
        while True:
            chunk = await stream.read(65536)
            if not chunk:
                break
            self._feed(chunk)
        # EOF：之后不会再有输出，剩下的就是完整的最后一行
        pending, self._pending = self._pending, b""
        if pending:
            self._emit_line(pending)

    def _feed(self, chunk: bytes) -> None:
        if self._after_cr and chunk.startswith(b"\n"):
            chunk = chunk[1:]
        self._after_cr = False
        # 缓冲里没有行尾（有就已经交出了），只需在新块里找
        start = 0
        for match in _PRETASK_LINE_END_RE.finditer(chunk):
            self._emit_line(self._pending + chunk[start : match.start()])
            self._pending = b""
            start = match.end()
        self._after_cr = start == len(chunk) and chunk.endswith(b"\r")
        self._pending += chunk[start:]

    def detach(self, display_name: str) -> bool:
        """之后的输出改写后端日志；返回缓冲里是否有还没到行尾、留待拼接的半行。"""

        def to_backend_log(line: str) -> None:
            logger.info(f"[运行前设置 {display_name} 退出后的输出] {line}")

        self._sink = to_backend_log
        # 只剩空白或颜色 / 光标控制码的尾巴（很多命令行程序退出前补一个不带换行的复位码）
        # 不算半行：它不含报错正文，失败原因照常从已写出的行里摘
        visible = _PRETASK_TAIL_NOISE_RE.sub(
            "", _decode_subprocess_output(self._pending)
        )
        return bool(visible.strip())

    def _emit_line(self, raw: bytes) -> None:
        text = _decode_subprocess_output(raw)
        if not text.strip():
            # 空白行先记数：后面还有内容才补写（夹在中间），到结尾都没有就不写
            if self._seen_text:
                self._blank_lines += 1
            return
        for _ in range(self._blank_lines):
            self._sink("")
        self._blank_lines = 0
        self._seen_text = True
        # 先对整段打码再去尾空白：密码可以以空白结尾，先去尾空白会把它截短而匹配不上
        self._sink(self._redact(text).rstrip())


def _keep_pretask_drain(reader: asyncio.Task[None]) -> None:
    """让读管道的任务在后台读到 EOF（见 ``_PRETASK_BACKGROUND_DRAINS``）。"""

    if reader.done():
        return
    _PRETASK_BACKGROUND_DRAINS.add(reader)

    def finished(task: asyncio.Task[None]) -> None:
        _PRETASK_BACKGROUND_DRAINS.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning(f"后台读取运行前设置输出失败: {task.exception()}")

    reader.add_done_callback(finished)


def _decode_subprocess_output(data: bytes) -> str:
    if not data:
        return ""
    for encoding in _SUBPROCESS_OUTPUT_ENCODINGS:
        try:
            return data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin1", errors="replace")


def _clean_framework_output(message: str) -> str:
    return strip_ansi(message)


_PRETASK_LOG_HEADER_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\s+"
    r"(?:TRC|DBG|INF|WRN|ERR|FTL|PNC|TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+"
    r"(?:.+?:\d+\s+>\s*)?(?P<body>.+)$"
)
_PRETASK_LOG_FIELD_RE = re.compile(
    r"""(?:^|\s)(?P<key>[A-Za-z_][\w.-]*)=(?P<value>"(?:\\.|[^"\\])*"|'[^']*'|\S+)"""
)


def _pretask_failure_reason(output: str) -> str:
    """只简化认得出的结构化日志；其余输出去色后原样保留。"""

    line = next(
        (
            cleaned
            for raw in reversed(output.splitlines())
            if (cleaned := _clean_framework_output(raw).strip())
        ),
        "",
    )
    if not line:
        return "没有输出错误详情"
    match = _PRETASK_LOG_HEADER_RE.fullmatch(line)
    if match is None:
        return line
    body = match["body"]
    fields = list(_PRETASK_LOG_FIELD_RE.finditer(body))
    if not fields:
        return body
    reason = body[: fields[0].start()].rstrip()
    for field in fields:
        if field["key"] != "error":
            continue
        value = field["value"]
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif value.startswith("'"):
            value = value[1:-1]
        if value:
            # 只有字段没有正文时，error 的值本身就是原因，不再套括号
            reason = f"{reason}（{value}）" if reason else value
    return reason or line


_STREAM_OVERRUN_NOTE = f"（worker 输出有一行超过 {_WORKER_STREAM_LINE_LIMIT // (1024 * 1024)} MB，已丢弃该行）"


async def _iter_stream_lines(
    stream: asyncio.StreamReader, on_overrun: Callable[[], None]
) -> AsyncIterator[bytes]:
    """逐行读子进程输出；单行超过 StreamReader 上限时丢掉这一行、记一句，接着读。

    ``async for line in stream`` 碰到超长行直接抛 ValueError，读取任务随之结束，之后没人
    读管道，worker 写满管道就挂住。StreamReader 抛错前已经把那一行（或缓冲）丢掉，
    接着读是安全的。
    """

    while True:
        try:
            line = await stream.readline()
        except ValueError:
            on_overrun()
            continue
        if not line:
            return
        yield line


def _framework_ui_message(message: str) -> str:
    """Bound worker diagnostics copied to the user-facing task log.

    Complete worker output (runner events, worker stdout/stderr) is already
    retained in ``*.worker.log``. A malformed task/encoding error can otherwise
    contain megabytes of JSON or a parser trace and make the normal task page
    unusable.
    """

    cleaned = _clean_framework_output(message).strip()
    if len(cleaned) <= _FRAMEWORK_UI_LOG_MAX_CHARS:
        return cleaned
    lines = cleaned.splitlines()
    compact = "\n".join(line[:240] for line in lines[:8]).strip()
    omitted = max(0, len(cleaned) - len(compact))
    summary = (
        f"{compact}\n… 上述内容已省略 {omitted} 个字符，"
        "完整内容请查看本次运行的 .worker.log"
    )
    return summary[:_FRAMEWORK_UI_LOG_MAX_CHARS]


def _parse_worker_protocol_line(
    line: str, secrets: list[str] | tuple[str, ...]
) -> dict[str, Any] | None:
    """worker stdout 的一行若是协议事件（JSON 对象）就解析并打码后返回，否则 None。

    **先解析、后打码**：以前对整行 JSON 做字符串替换，密码恰好是 ``true`` / ``result`` /
    ``success`` / ``2026`` 或某个任务名时，替换会打坏 JSON 结构、键名、截图路径、完成任务
    列表——成功的运行被判成「worker exited without result」而重试，或通知丢图、周期任务
    不记完成。现在只替换给人读的文本（log / error 的 ``message``、结果里的
    ``errorMessage`` / ``userMessage``），结构字段（路径、任务名、状态、布尔、数字）一律不动。
    解析不了的行（原生诊断）由调用方照旧整行打码。
    """

    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    return _redact_worker_event(event, secrets)


def _redact_worker_event(
    event: dict[str, Any], secrets: list[str] | tuple[str, ...]
) -> dict[str, Any]:
    """协议事件只打码给人读的文本（见 ``_parse_worker_protocol_line``）；事件通道与 stdout 同一口径。"""

    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact_secret_text(message, secrets)
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("errorMessage", "userMessage"):
            if isinstance(data.get(key), str):
                data[key] = redact_secret_text(data[key], secrets)
    return event


def _should_forward_framework_log(message: str) -> bool:
    """stdout / stderr 上的原生诊断与不带 audience 的旧格式事件进不进界面（规则在 worker_protocol）。"""

    return forwards_to_ui(message)


def _remove_method(methods: int, method: int, fallback: int) -> int:
    """从位掩码中剔除 method 位；若结果为 0（无可用方法）则回退到 fallback。"""
    filtered = methods & ~method
    return filtered or fallback


def _ldplayer_input_text_command(emulator_root: Path, index: int) -> list[str] | None:
    """雷电文本输入改走 ``ldconsole action --key call.input`` 的 adb config 命令。

    MaaFW 的 ``AdbShellInput`` 按 ``config.command.InputText`` 的 argv 起子进程，
    ``{TEXT}`` 由它替换成待输入文本；首元素不必是 adb。ldconsole 成功时无输出、
    返回 0，正好满足 MaaFW「输出为空即成功」的判据；索引错了它会打印错误，
    MaaFW 就把这次 InputText 判失败，让节点失败而不是像 Maatouch 那样静默重打。
    索引必须是雷电原生实例号（与 extras 同口径）。找不到 ldconsole 就返回 None，
    调用方维持原来的 Maatouch 路径。
    """
    console = emulator_root / "ldconsole.exe"
    if not console.is_file():
        return None
    return [
        str(console).replace("\\", "/"),
        "action",
        "--index",
        str(index),
        "--key",
        "call.input",
        "--value",
        "{TEXT}",
    ]


def _has_input_text_command(config: dict[str, Any]) -> bool:
    command = config.get("command")
    return isinstance(command, dict) and bool(command.get("InputText"))


def _load_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_script_hotkeys(value: Any) -> dict[str, dict[str, str]]:
    """``Game.Hotkeys`` → ``{option 名: {字段名: 组合键}}``；不成形的部分丢掉。"""

    result: dict[str, dict[str, str]] = {}
    for option_name, fields in _load_json_dict(value).items():
        if not isinstance(option_name, str) or not isinstance(fields, dict):
            continue
        cleaned = {
            field_name: field_value
            for field_name, field_value in fields.items()
            if isinstance(field_name, str) and isinstance(field_value, str)
        }
        if cleaned:
            result[option_name] = cleaned
    return result


def _minutes_to_seconds(minutes: Any) -> int:
    """配置里的分钟数换算成秒。0 / 负数 / 写坏的值都当「不限」（返回 0）。"""

    try:
        value = int(minutes)
    except (TypeError, ValueError):
        return 0
    return value * 60 if value > 0 else 0


def task_time_limits_from_config(config: Any) -> tuple[int, dict[str, int]]:
    """读 Run.TaskTimeLimit / Run.TaskTimeLimitOverrides 并换算成秒。

    宿主在拉起 worker 之前算一次，随 job 下发：worker 是独立进程，读不到 Config，
    核心包也只收秒数，不认宿主的配置键。

    Returns:
        (默认单任务时限秒数, {任务名: 时限秒数})，0 表示不限。
    """

    default_seconds = _minutes_to_seconds(config.Run.TaskTimeLimit)
    # 配置系统里 JSON 项存的是字符串（JSONValidator），读出来再解析一次。
    overrides = {
        str(name): _minutes_to_seconds(minutes)
        for name, minutes in _load_json_dict(config.Run.TaskTimeLimitOverrides).items()
    }
    return default_seconds, overrides


def loop_guard_from_config(config: Any) -> bool:
    """读 Run.LoopGuard（原地打转检测，实验性，默认关）；读不到或写坏都按关。"""

    try:
        return config.Run.LoopGuard is True
    except Exception:
        return False


def _load_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def _iter_rotated_native_debug_logs(path: Path) -> list[Path]:
    """按轮转时间升序列出 MaaFW 的历史原生日志。

    文件名形如 ``maafw.bak.2026.08.30-22.58.30.451.log``，时间戳是零填充的
    定宽字段，按文件名排序即按时间排序。
    """

    try:
        return sorted(path.parent.glob(path.stem + ".bak.*" + path.suffix))
    except OSError:
        return []


def _snapshot_native_debug_log_state(path: Path) -> tuple[int, frozenset[str]]:
    """记下原生日志的读取起点：当前大小，以及运行前已存在的轮转文件。"""

    try:
        offset = path.stat().st_size
    except OSError:
        offset = 0
    return offset, frozenset(
        rotated.name for rotated in _iter_rotated_native_debug_logs(path)
    )


def _plan_native_debug_log_sources(
    path: Path,
    start_offset: int,
    known_rotations: frozenset[str],
) -> list[tuple[str, Path, int]]:
    """列出本次运行写下的原生日志分片，按时间先后排列。

    MaaFW 会在 ``maafw.log`` 涨到一定大小时把它整体挪成
    ``maafw.bak.<时间戳>.log``，再开一个空文件继续写。只记字节偏移不够用：
    轮转后新文件重新长回超过该偏移，收尾时便会拿运行前的偏移去 seek 一个
    内容毫不相干的文件——运行前半段凭空消失，切口还落在任意字节上。而长到
    足以触发轮转的运行，恰恰是最需要日志的那些。

    所以改为对比运行前后的轮转文件集合：新出现的那些就是本次运行被挪走的
    内容。其中最早的一个才是运行开始时正在写的文件，只有它要跳过运行前已有
    的部分，其余分片都从头读。
    """

    rotated = [
        candidate
        for candidate in _iter_rotated_native_debug_logs(path)
        if candidate.name not in known_rotations
    ]
    sources: list[tuple[str, Path, int]] = [
        ("debug/" + candidate.name, candidate, start_offset if index == 0 else 0)
        for index, candidate in enumerate(rotated)
    ]
    sources.append(("debug/" + path.name, path, 0 if rotated else start_offset))
    return sources


def _copy_native_debug_log_delta(
    path: Path,
    start_offset: int,
    known_rotations: frozenset[str],
    target: Path,
    secrets: list[str] | tuple[str, ...] = (),
) -> int:
    """把本次运行写下的原生日志分片按顺序原样追加到 ``target``，返回复制的字节数。

    按字节复制、不解码不清洗，副本才和项目 ``debug/maafw.log`` 完全一致。每次尝试
    各写各的文件（文件名是这次尝试的开始时刻），追加只是为了不覆盖已有内容。
    逐个分片流式复制，一份可能有几十 MB。

    唯一的改动是 ``secrets``（密码字段的原文及其 JSON 转义写法）：框架在
    ``Tasker::post_task`` 里按 INFO 级别记下整份 ``pipeline_override``（``[pipeline_override={...}]``），
    密码会原样出现；给了就逐行换成占位（按 UTF-8 / GBK / UTF-16LE 的字节替换，其余字节不动）。项目目录里框架
    自己写的 ``debug/maafw.log`` 不归 MAS 管，那份仍是原文。
    """

    # 每个写法按 UTF-8 / GBK / UTF-16LE 的字节都换（与 .project.log 同一套，见 option_secrets）。
    secret_pairs = secret_byte_pairs(list(secrets))

    copied = 0
    target_file: Any | None = None
    try:
        for _label, source_path, source_offset in _plan_native_debug_log_sources(
            path, start_offset, known_rotations
        ):
            try:
                current_size = source_path.stat().st_size
            except OSError:
                continue
            source_offset = source_offset if current_size >= source_offset else 0
            if current_size <= source_offset:
                continue
            if target_file is None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target_file = target.open("ab")
            with source_path.open("rb") as source_file:
                source_file.seek(source_offset)
                if secret_pairs:
                    for raw_line in source_file:
                        for secret, placeholder in secret_pairs:
                            if secret in raw_line:
                                raw_line = raw_line.replace(secret, placeholder)
                        target_file.write(raw_line)
                else:
                    shutil.copyfileobj(source_file, target_file)
                copied += source_file.tell() - source_offset
    finally:
        if target_file is not None:
            target_file.close()
    return copied


# worker 截图文件名是 ``[<前缀>.]<kind>-<HHMMSS>-<任务>.png``，信号证据图的 kind 与 worker
# 共用 worker_protocol.SIGNAL_SCREENSHOT_KINDS。
_SIGNAL_EVIDENCE_NAME_RE = re.compile(
    r"(?:^|\.)(?:"
    + "|".join(re.escape(kind) for kind in SIGNAL_SCREENSHOT_KINDS.values())
    + r")-\d{6}-"
)


def _signal_evidence_shot(result: Any) -> Any | None:
    """信号命中那个任务的证据图；找不到就不带图（宁缺勿错）。"""

    for shot in getattr(result, "failureScreenshots", None) or ():
        if shot.task == result.failedTask and _SIGNAL_EVIDENCE_NAME_RE.search(
            Path(shot.path).name
        ):
            return shot
    return None


def _is_unretryable_failure(message: str) -> bool:
    return any(marker in message for marker in _UNRETRYABLE_ENVIRONMENT_MARKERS)


def _result_failure_category(result: MaaFWRunResult) -> str | None:
    """worker 回报失败时尝试级的类别：只看结果里已有的字段与现有的环境级判定。

    返回 None 时由运行记录按任务结局补（任务都没开始是初始化失败）。
    """

    if result.resourceFailure is not None:
        return CATEGORY_RESOURCE_FAILURE
    if result.timedOut:
        return CATEGORY_RUN_TIMEOUT
    if _is_unretryable_failure(result.errorMessage or ""):
        return CATEGORY_ENVIRONMENT
    return None


_FAILURE_REASON_MAX_CHARS = 300


def _failure_reason_for_user(result: Any) -> str:
    """从运行结果里取一句可读的失败原因。

    runner 会把异常原文放进 ``errorMessage``，但它同时也用
    ``MaaFW 任务执行失败: {exc}`` 发一条日志——那条命中
    ``worker_protocol._RAW_FAILURE_UI_LOG_MARKERS`` 会被当框架噪声过滤掉。若这里再不取，
    Python 侧异常（如缺模块）在任务页上就只剩「任务执行失败」四个字。

    框架自身的失败原文可能是整段原生 backtrace，因此只取首个非空行并截断；
    完整内容仍在本次运行的 ``*.worker.log`` 里。
    """

    raw = str(
        getattr(result, "userMessage", None)
        or getattr(result, "errorMessage", "")
        or ""
    ).strip()
    if not raw:
        return ""
    first_line = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if not first_line:
        return ""
    while len(first_line) > _FAILURE_REASON_MAX_CHARS and "；" in first_line:
        first_line = first_line.rsplit("；", 1)[0]
    if len(first_line) > _FAILURE_REASON_MAX_CHARS:
        first_line = first_line[: _FAILURE_REASON_MAX_CHARS - 1] + "…"
    return first_line


def _failed_task_user_summary(result: Any, plan: Any | None) -> str:
    if getattr(result, "userMessage", None):
        return _failure_reason_for_user(result)
    failed_task = str(getattr(result, "failedTask", "") or "").strip()
    reason = _failure_reason_for_user(result)
    if not failed_task:
        # 还没投递任何任务就失败了（ADB 未就绪、Agent 连接超时、资源加载失败……）：
        # 不把原因挂到第一个任务头上，用户会去查错任务
        return f"MaaFW 运行失败{'：' + reason if reason else ''}"
    suffix = f"：任务执行失败{'：' + reason if reason else ''}"
    tasks = tuple(getattr(plan, "tasks", ()) or ()) if plan is not None else ()
    if tasks:
        for task in tasks:
            task_name = str(getattr(task, "name", "") or "").strip()
            task_entry = str(getattr(task, "entry", "") or "").strip()
            if failed_task and failed_task not in {task_name, task_entry}:
                continue
            return f"{_task_display_name(task)}{suffix}"
    return f"{failed_task or 'MaaFW 任务'}{suffix}"


def _task_display_name(task: Any) -> str:
    label = getattr(task, "label", None)
    # 红灯记录的 label 已在建计划时解析；用户自己起的名字可以以 $ 开头。
    queue_skipped = (
        isinstance(task, MaaFWSkippedTaskPlan)
        and task.reason == QUEUE_SKIPPED_TASK_REASON
    )
    if (
        isinstance(label, str)
        and label.strip()
        and (queue_skipped or not label.lstrip().startswith("$"))
    ):
        return label.strip()
    return str(getattr(task, "name", ""))


def _format_completed_task_labels(
    plan: MaaFWRunPlan | None,
    task_names: list[str],
) -> list[str]:
    labels_by_name = (
        {task.name: _task_display_name(task) for task in plan.tasks}
        if plan is not None
        else {}
    )
    return [labels_by_name.get(task_name, task_name) for task_name in task_names]


def _format_run_overview_log(
    plan: MaaFWRunPlan,
    *,
    selected_preset: str,
) -> str:
    task_names = " -> ".join(_task_display_name(task) for task in plan.tasks) or "-"
    if len(task_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        task_names = task_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    project_name = (
        plan.projectLabel.strip()
        if isinstance(plan.projectLabel, str)
        and plan.projectLabel.strip()
        and not plan.projectLabel.lstrip().startswith("$")
        else plan.projectName
    )
    project_version = str(plan.piEnv.get("PI_VERSION") or "").strip() or "未知"
    overview = (
        "MaaFW 运行总览: "
        f"project={project_name}; version={project_version}; "
        f"controller={plan.controllerName}; resource={plan.resourceName}; "
        f"preset={selected_preset or '自定义'}; "
        f"enabled_tasks({len(plan.tasks)})={task_names}"
    )
    if not plan.skippedTasks:
        return overview

    # 被跳过的任务此前没有任何出口，用户把任务加进队列却看不出它为什么没跑。
    skipped_names = " -> ".join(
        f"{_task_display_name(task)}({task.reason})" for task in plan.skippedTasks
    )
    if len(skipped_names) > _RUN_OVERVIEW_LOG_VALUE_LIMIT:
        skipped_names = skipped_names[:_RUN_OVERVIEW_LOG_VALUE_LIMIT] + "..."
    return f"{overview}; skipped_tasks({len(plan.skippedTasks)})={skipped_names}"


#: 任务报告里「失效任务」一行的前缀：队列里的任务 interface 已没有，本次跳过。
MISSING_TASK_NOTICE_PREFIX = (
    "失效任务（interface 内已无，已跳过，请到用户配置里重新添加）"
)
#: 其余任务都跑完、但队列里有失效任务时统计报告的结果：照常算完成，不说「全部完成」。
MISSING_TASK_USER_RESULT = "代理任务完成，但有失效任务"
#: 特调声明的 skip_on_retry_entries 在重试时被剔掉的原因（进 skippedTasks 与尝试日志）。
_RETRY_SKIP_REASON = "前面的尝试已完成"


def _retry_skipped_tasks(plan: MaaFWRunPlan) -> list[MaaFWSkippedTaskPlan]:
    return [task for task in plan.skippedTasks if task.reason == _RETRY_SKIP_REASON]


_PERIOD_DONE_LABELS = {
    "今日已正常完成": "今日",
    "本周已正常完成": "本周",
    "本月已正常完成": "本月",
}


def _period_all_done_message(plan: MaaFWRunPlan) -> str:
    """队列里的任务都因周期限制被跳过时的提示，按实际跳过原因说今日 / 本周 / 本月。"""

    periods: list[str] = []
    for task in plan.skippedTasks:
        label = _PERIOD_DONE_LABELS.get(task.reason or "")
        if label and label not in periods:
            periods.append(label)
    ordered = [label for label in ("今日", "本周", "本月") if label in periods]
    # 运行日的说法只在跳过原因全是「不在运行日」（或再加周期已完成）时用；混了红灯、失效任务
    # 等别的原因时，照改动前这种情况原本的提示说
    reasons = [task.reason or "" for task in plan.skippedTasks]
    off_day = any(reason.endswith(_OFF_DAY_REASON_SUFFIX) for reason in reasons)
    only_off_day_or_period = all(
        reason.endswith(_OFF_DAY_REASON_SUFFIX) or reason in _PERIOD_DONE_LABELS
        for reason in reasons
    )
    if off_day and only_off_day_or_period and not ordered:
        return "MaaFW 队列里的任务今天都不在运行日，跳过本次运行"
    if off_day and only_off_day_or_period:
        return (
            f"MaaFW 队列里的任务今天不在运行日或已在{' / '.join(ordered)}完成，"
            "跳过本次运行"
        )
    if not periods:
        return "MaaFW 队列里的周期任务都已在本周期内完成，跳过本次运行"
    return f"MaaFW 队列里的周期任务都已在{' / '.join(ordered)}完成，跳过本次运行"


#: ISO 星期（1=周一）对应的叫法，运行日跳过原因用。
_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
#: 运行日跳过原因的后半句：「今天周一，不在运行日」。
_OFF_DAY_REASON_SUFFIX = "，不在运行日"


def _drop_unselectable_tasks(
    interface_model: MaaFWInterface,
    task_ids: list[str],
    task_options: dict[str, Any],
    entries: dict[str, str],
    *,
    send_log: Callable[[str], None],
    dropped_names: list[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """剔掉特调声明不可选的任务（``unselectable_entries``：entry → 原因），连同它们的选项。

    日志按原因合并成一行（同名任务只列一次，名字顺序按队列），没声明时原样返回。
    ``dropped_names`` 非空时把被剔任务的显示名（去重、按队列）追加进去，供空队列报错带上原因。
    """

    if not entries:
        return task_ids, task_options
    task_by_name = {task.name: task for task in interface_model.task}

    def task_of(task_id: str) -> Any:
        return task_by_name.get(resolve_task_instance_name(str(task_id), task_by_name))

    def entry_of(task_id: str) -> str:
        task = task_of(task_id)
        return str(task.entry or "") if task is not None else ""

    kept: list[str] = []
    # 原因 → 被剔任务显示名（dict 保序：原因按首次出现，名字按队列，同名只列一次）
    by_reason: dict[str, dict[str, None]] = {}
    dropped: list[str] = []
    for task_id in task_ids:
        entry = entry_of(task_id)
        if entry not in entries:
            kept.append(task_id)
            continue
        name = _task_display_name(task_of(task_id))
        by_reason.setdefault(entries[entry], {})[name] = None
        dropped.append(name)
    for reason, names in by_reason.items():
        send_log("已跳过" + "".join(f"「{name}」" for name in names) + f"：{reason}")
    if dropped_names is not None:
        dropped_names.extend(dict.fromkeys(dropped))
    if len(kept) == len(task_ids):
        return task_ids, task_options
    options = {
        key: value
        for key, value in task_options.items()
        if entry_of(key) not in entries
    }
    return kept, options


def _mark_abort_round_tasks(plan: MaaFWRunPlan, flavor: Any) -> MaaFWRunPlan:
    """把特调声明的关键任务（``abort_round_entries``：entry → 失败时报的话）标到计划上。

    runner 据此在这些任务失败或超时时直接结束本轮，见 ``MaaFWTaskRunPlan.abortRoundMessage``。
    """

    entries: dict[str, str] = getattr(flavor, "abort_round_entries", None) or {}
    if not entries:
        return plan
    tasks = [
        task.model_copy(update={"abortRoundMessage": entries[task.entry]})
        if task.entry in entries
        else task
        for task in plan.tasks
    ]
    return plan.model_copy(update={"tasks": tasks})


def _mark_nonfatal_tasks(plan: MaaFWRunPlan, flavor: Any) -> MaaFWRunPlan:
    """把特调声明的收尾任务（``nonfatal_entries``：entry → 失败时接在日志后的说明）标到计划上。

    runner 据此在这些任务失败、超时或原地打转时只截图记日志、不计入本轮失败，见
    ``MaaFWTaskRunPlan.nonFatalMessage``。
    """

    entries: dict[str, str] = getattr(flavor, "nonfatal_entries", None) or {}
    if not entries:
        return plan
    tasks = [
        task.model_copy(update={"nonFatalMessage": entries[task.entry]})
        if task.entry in entries
        else task
        for task in plan.tasks
    ]
    return plan.model_copy(update={"tasks": tasks})


def _with_skipped_tasks(
    plan: MaaFWRunPlan, skipped: list[MaaFWSkippedTaskPlan]
) -> MaaFWRunPlan:
    """把建计划之外判出的跳过项排在计划自己的跳过项前面。"""

    if not skipped:
        return plan
    return plan.model_copy(update={"skippedTasks": [*skipped, *plan.skippedTasks]})


def _with_warnings(plan: MaaFWRunPlan, warnings: list[str]) -> MaaFWRunPlan:
    """把建计划之外判出的提示接在计划自己的提示后面（重复的只留一条）。"""

    if not warnings:
        return plan
    return plan.model_copy(
        update={"warnings": list(dict.fromkeys([*plan.warnings, *warnings]))}
    )


def _current_period_keys(now: datetime | None = None) -> tuple[str, str, str]:
    current = now or datetime.now(tz=UTC4)
    iso_year, iso_week, _ = current.isocalendar()
    return (
        current.strftime("%Y-%m-%d"),
        f"{iso_year}-W{iso_week:02d}",
        current.strftime("%Y-%m"),
    )


def _format_user_log_line(message: str) -> str:
    timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
    lines = str(message).splitlines() or [""]
    return "".join(f"[{timestamp}] {line}\n" for line in lines)
