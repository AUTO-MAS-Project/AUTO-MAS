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
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import shutil
import shlex
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import ConfigBase, MultipleConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from ..common.events import (
    OK_SCRIPT_EVENT_PROTOCOL_VERSION,
    OK_SCRIPT_PLUGIN_EVENT,
    OK_SCRIPT_PLUGIN_EVENT_SOURCE,
    OkScriptRunEvent,
    OkScriptRunFailure,
    format_partial_success_status,
    read_ok_script_run_events,
)
from ..common.provider import (
    OkScriptProvider,
    OkScriptRuntimeConfigOverride,
    OkScriptTaskOption,
    ok_script_mas_config_dir,
)
from ..common.report import OkScriptReportHandler
from ..common.runtime_lock import get_ok_script_root_lock
from ..providers import detect_ok_script_provider
from ..shell.manifest import OkProjectInspectError, OkProjectManifest, inspect_ok_project
from ..shell.runtime import (
    PROTOCOL_LEGACY_EXE,
    OkConfigStore,
    OkShellRunner,
    OkShellRuntimeError,
)
from app.task.general.tools import execute_script_task
from app.utils import (
    ProcessInfo,
    ProcessManager,
    decode_bytes,
    get_logger,
    is_process_running,
)
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4

logger = get_logger("ok-script 自动代理")


# 调度台需要足够的近期上下文，但不能因为长时间 OCR 输出无限增长。
DISPATCH_LOG_MAX_CHARS = 100_000
DISPATCH_LOG_MAX_RUNTIME_LINES = 2_000
DISPATCH_LOG_TRUNCATION_NOTICE = "[MAS] 调度台仅保留最近日志，完整历史请查看任务记录。"
SCRIPT_EXIT_CHECK_TIMEOUT = 2
SCRIPT_EXIT_KILL_TIMEOUT = 5
SCRIPT_EXIT_EVENT_GRACE_SECONDS = 1


def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def _replace_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise FileNotFoundError(src)

    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(dst.name + ".tmp")
    shutil.rmtree(tmp_dst, ignore_errors=True)
    shutil.copytree(src, tmp_dst, dirs_exist_ok=True)
    shutil.rmtree(dst, ignore_errors=True)
    tmp_dst.rename(dst)


def _apply_runtime_config_overrides(
    config_dir: Path,
    overrides: tuple[OkScriptRuntimeConfigOverride, ...],
) -> dict[tuple[str, str], tuple[bool, object]]:
    """应用项目运行期覆盖，并返回需要在写回前恢复的原值。"""

    store = OkConfigStore(config_dir)
    available = set(store.list())
    pending: dict[str, dict[str, object]] = {}
    originals: dict[tuple[str, str], tuple[bool, object]] = {}

    for override in overrides:
        if override.file_name not in available:
            logger.warning(
                f"运行期配置覆盖目标不存在，保留兼容兜底: {override.file_name}"
            )
            continue
        if override.file_name not in pending:
            pending[override.file_name] = store.read(override.file_name)

        data = pending[override.file_name]
        state_key = (override.file_name, override.key)
        originals[state_key] = (override.key in data, data.get(override.key))
        data[override.key] = override.value

    for file_name, data in pending.items():
        store.write(file_name, data, merge=False)
    return originals


def _restore_runtime_config_overrides(
    config_dir: Path,
    originals: dict[tuple[str, str], tuple[bool, object]],
) -> None:
    """恢复运行期覆盖前的字段，同时保留脚本对其他配置项的修改。"""

    store = OkConfigStore(config_dir)
    pending: dict[str, dict[str, object]] = {}
    for (file_name, key), (existed, value) in originals.items():
        if file_name not in pending:
            pending[file_name] = store.read(file_name)
        if existed:
            pending[file_name][key] = value
        else:
            pending[file_name].pop(key, None)

    for file_name, data in pending.items():
        store.write(file_name, data, merge=False)


def _build_manifest_provider(manifest: OkProjectManifest) -> OkScriptProvider:
    """为未内置专项的项目提供只含通用运行信息的 Provider。"""

    def relative_path(path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return path.relative_to(manifest.root_path).as_posix()
        except ValueError:
            return str(path)

    return OkScriptProvider(
        resource_name=manifest.resource_name,
        display_name=manifest.display_name or manifest.resource_name,
        exe_name=relative_path(manifest.executable),
        config_dir=relative_path(manifest.config_dir),
        log_file=relative_path(manifest.log_path),
        pythonw_path="",
        track_process_name="",
        game_process_name="",
        running_status="运行中",
        fatal_patterns=(),
        success_patterns=(
            "Successfully Executed Task",
            "Successfully Executed Task, Exiting Game and App!",
        ),
        max_task_index=max((task.index for task in manifest.tasks), default=0),
        task_options=tuple(
            OkScriptTaskOption(task.index, task.label or task.selector)
            for task in manifest.tasks
        ),
        config_schema_module="",
        config_info_loader="",
    )


class OkScriptAutoProxyTask(TaskExecuteBase):
    """ok-script 自动代理：由 Manifest 选择协议并监控运行结果。"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: ConfigBase,
        user_config: MultipleConfig[ConfigBase],
        game_manager: ProcessManager | None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.game_manager = game_manager
        self.provider: OkScriptProvider | None = None
        self.project_manifest: OkProjectManifest | None = None
        self.shell_runner: OkShellRunner | None = None

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: ConfigBase = self.user_config[self.cur_user_uid]

        self.script_process_manager: ProcessManager = ProcessManager()
        self.script_root_path: Path = Path()
        self.script_exe_path: Path = Path()
        self.script_target_process_info: ProcessInfo | None = None
        self.script_config_path: Path = Path()
        self.mas_config_dir: Path = Path()
        self.script_config_backup_path: Path = Path()
        self.had_original_script_config = False
        self.script_config_swap_started = False
        self.script_config_injected = False
        self.runtime_config_originals: dict[
            tuple[str, str], tuple[bool, object]
        ] = {}
        self.script_root_lock: asyncio.Lock | None = None
        self.script_root_lock_acquired = False
        self.script_log_path: Path = Path()
        self.script_event_log_path: Path = Path()
        self.log_monitor: LogMonitor | None = None
        self.event_monitor_task: asyncio.Task[None] | None = None
        self.event_log_offset = 0
        self.event_protocol_active = False
        self.event_terminal_received = False
        self.event_failures: list[OkScriptRunFailure] = []
        self.runtime_log_lines: list[str] = []
        self.legacy_log_lines: list[str] = []
        self.wait_event: asyncio.Event = asyncio.Event()
        self.log_start_time: datetime = datetime.now()
        self.task_index = 1
        self.script_args: list[str] = []
        self.script_cwd: Path = Path()
        self.script_environment: dict[str, str] = {}
        self.execution_protocol = ""
        self.use_provider_process_tracking = False
        self.stream_reader_tasks: list[asyncio.Task[None]] = []
        self.game_path: Path = Path()
        self.run_book = False
        self.game_started_by_mas = False
        self.manual_stop = False
        self.cur_user_log: LogRecord | None = None
        self.report_handler: OkScriptReportHandler | None = None
        self.curdate = ""

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 ok-script 项目路径"
        try:
            manifest = await asyncio.to_thread(inspect_ok_project, root)
        except OkProjectInspectError as exc:
            return f"无法解析 ok-script 项目: {exc}"
        provider = self._resolve_provider(root)
        if provider is not None and not provider.runtime_verified:
            return provider.runtime_block_reason or "当前 ok-script 项目尚未完成运行验证"
        self.project_manifest = manifest
        self.provider = provider or _build_manifest_provider(manifest)

        task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        if manifest.tasks and not any(task.index == task_index for task in manifest.tasks):
            return (
                f"当前任务序号 {task_index} 不属于"
                f"{self.provider.display_name} 已解析的一次性任务"
            )

        mas_config_dir = ok_script_mas_config_dir(
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        if not mas_config_dir.is_dir() or not any(mas_config_dir.glob("*.json")):
            return f"用户 {self.cur_user_item.name} 未完成 ok-script 配置，请先在用户编辑页保存配置"

        today = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != today:
            await self.cur_user_config.set("Data", "LastProxyDate", today)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        if (
            self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"
        if self.cur_user_config.get("Info", "RemainedDay") == 0:
            self.cur_user_item.status = "跳过"
            return "用户剩余天数为 0, 跳过该用户"

        if not Path(self.script_config.get("Game", "Path")).is_file():
            return "请设置游戏程序路径"

        return "Pass"

    async def prepare(self) -> None:
        self.script_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        try:
            manifest = self.project_manifest or await asyncio.to_thread(
                inspect_ok_project,
                self.script_root_path,
            )
        except OkProjectInspectError as exc:
            raise RuntimeError(f"无法解析 ok-script 项目: {exc}") from exc
        detected_provider = self._resolve_provider(self.script_root_path)
        if detected_provider is not None and not detected_provider.runtime_verified:
            raise RuntimeError(
                detected_provider.runtime_block_reason
                or "当前 ok-script 项目尚未完成运行验证"
            )
        self.project_manifest = manifest
        self.provider = detected_provider or _build_manifest_provider(manifest)
        self.script_root_lock = get_ok_script_root_lock(self.script_root_path)
        if not self.script_root_lock_acquired:
            self.script_info.log = "正在等待同一 ok-script 项目完成运行"
            await self.script_root_lock.acquire()
            self.script_root_lock_acquired = True
        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        self.script_event_log_path = manifest.log_path.with_name("mas-events.jsonl")
        self.shell_runner = OkShellRunner(
            manifest,
            event_path=self.script_event_log_path,
        )
        try:
            launch_spec = await asyncio.to_thread(
                self.shell_runner.build_launch_spec,
                str(self.task_index),
            )
        except OkShellRuntimeError as exc:
            raise RuntimeError(f"无法构建 ok-script 运行命令: {exc}") from exc
        self.execution_protocol = launch_spec.protocol
        self.script_exe_path = Path(launch_spec.command[0])
        self.script_args = list(launch_spec.command[1:])
        self.script_cwd = launch_spec.cwd
        self.script_environment = launch_spec.environment
        self.use_provider_process_tracking = (
            detected_provider is not None
            and self.execution_protocol == PROTOCOL_LEGACY_EXE
        )
        self.script_config_path = manifest.config_dir
        self.mas_config_dir = ok_script_mas_config_dir(
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        self.script_config_backup_path = (
            Path.cwd()
            / "data"
            / self.script_info.script_id
            / "Temp"
            / self.cur_user_item.user_id
            / "ConfigFile"
        )
        self.had_original_script_config = False
        self.script_config_swap_started = False
        self.script_config_injected = False
        self.script_target_process_info = (
            ProcessInfo(
                name=self.provider.track_process_name,
                exe=str(self.provider.track_process_path(self.script_root_path)),
                cmdline=None,
            )
            if self.use_provider_process_tracking
            else None
        )
        self.script_log_path = manifest.log_path
        self.log_monitor = LogMonitor(
            self.provider.log_time_range,
            self.provider.log_time_format,
            self.check_log,
        )
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.run_book = False
        self.game_started_by_mas = False
        self.report_handler = (
            self.provider.report_handler_factory()
            if self.provider.report_handler_factory is not None
            else None
        )

    async def main_task(self) -> None:
        try:
            await self._main_task()
        except asyncio.CancelledError:
            self.manual_stop = True
            raise

    async def _main_task(self) -> None:
        await self.prepare()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.cur_user_item.status = "运行"
        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        for i in range(run_limit):
            if self.run_book:
                break

            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
            )
            self.cur_user_item.status = "运行"
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = LogRecord()
            self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
            self._reset_attempt_observation()
            await self._push_dispatch_log(
                f"开始第 {i + 1}/{run_limit} 次运行，准备接管 {self.provider.display_name}"
            )
            self.report_handler = (
                self.provider.report_handler_factory()
                if self.provider.report_handler_factory is not None
                else None
            )
            if self.report_handler is not None:
                await self.report_handler.start(self)

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            await self.sync_script_config()
            await self._push_dispatch_log("已向脚本注入当前用户配置")

            # 标准链路：先启动游戏，再启动 ok-script 执行任务并监察日志。
            game_result = await self._launch_game_before_task()
            if game_result != "Pass":
                await self._handle_attempt_failure(game_result, i, run_limit)
                continue

            status = await self._run_script_process()
            self.cur_user_log.status = status
            if len(self.cur_user_log.content) == 0:
                self.cur_user_log.content = [
                    f"启动 {self.provider.display_name}: {' '.join(self.script_args)}",
                    status,
                ]
            self.script_info.log = status

            if status == "Success!" or self.run_book:
                self.run_book = True
                self.cur_user_item.status = "完成"
                await self._push_dispatch_log("已确认整轮任务完成，等待脚本进程退出")
                try:
                    await self._wait_script_exit(timeout=10)
                finally:
                    # 成功日志出现后继续读取退出阶段输出，避免丢失脚本收尾信息。
                    await self._stop_process_stream_readers()
                await self.update_config()
                await self._restore_script_config()
                if self.report_handler is not None:
                    await self.report_handler.apply(self)
                    await self.report_handler.stop(self)
                await self._run_script_after_task()
                break

            await self._handle_attempt_failure(status, i, run_limit)

    def _reset_attempt_observation(self) -> None:
        """初始化单次运行的日志与结构化事件观测状态。"""

        self.event_protocol_active = False
        self.event_terminal_received = False
        self.event_failures = []
        self.runtime_log_lines = []
        self.legacy_log_lines = []
        self.event_monitor_task = None
        try:
            self.event_log_offset = self.script_event_log_path.stat().st_size
        except FileNotFoundError:
            self.event_log_offset = 0

    def _refresh_current_log_content(self) -> None:
        if self.cur_user_log is None:
            return
        self.cur_user_log.content = [
            *self.runtime_log_lines,
            *self.legacy_log_lines,
        ]

    def _build_dispatch_log_snapshot(self) -> str:
        """构建调度台的滚动日志窗口，优先保留最新运行上下文。"""

        if self.cur_user_log is None or not self.cur_user_log.content:
            return ""

        lines: list[str] = []
        remaining = DISPATCH_LOG_MAX_CHARS
        truncated = False
        for raw_line in reversed(self.cur_user_log.content):
            line = str(raw_line).rstrip("\r\n")
            separator_length = 1 if lines else 0
            required_length = len(line) + separator_length
            if required_length <= remaining:
                lines.append(line)
                remaining -= required_length
                continue

            if remaining > separator_length:
                lines.append(line[-(remaining - separator_length) :])
            truncated = True
            break

        snapshot = "\n".join(reversed(lines))
        if not truncated:
            return snapshot

        snapshot_budget = DISPATCH_LOG_MAX_CHARS - len(DISPATCH_LOG_TRUNCATION_NOTICE) - 1
        return f"{DISPATCH_LOG_TRUNCATION_NOTICE}\n{snapshot[-snapshot_budget:]}"

    async def _push_dispatch_log(self, message: str) -> None:
        """向 MAS 调度台与当前历史记录追加运行阶段日志。"""

        line = f"[MAS] {message}"
        self.runtime_log_lines.append(line)
        # stdout/stderr 可能持续高频输出，调度台仅保留最近窗口避免常驻内存增长。
        if len(self.runtime_log_lines) > DISPATCH_LOG_MAX_RUNTIME_LINES:
            del self.runtime_log_lines[:-DISPATCH_LOG_MAX_RUNTIME_LINES]
        self._refresh_current_log_content()
        self.script_info.log = self._build_dispatch_log_snapshot() or line
        logger.info(f"{self.provider.display_name} | {message}")
        await asyncio.sleep(0)

    async def _handle_attempt_failure(
        self,
        status: str,
        attempt_index: int,
        run_limit: int,
    ) -> None:
        logger.error(
            f"用户 {self.cur_user_item.name} - {self.provider.display_name} 代理异常: {status}"
        )
        if self.cur_user_log is not None:
            self.cur_user_log.status = status
            if len(self.cur_user_log.content) == 0:
                self.cur_user_log.content = [status]
        self.script_info.log = status

        await self._push_dispatch_log(f"本次运行失败：{status}")
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": status},
            )

        await self.kill_managed_process(kill_game=self._should_kill_game())
        await self.update_config()
        await self._restore_script_config()
        await self._run_script_after_task()
        if self.report_handler is not None:
            await self.report_handler.stop(self)
        with suppress(Exception):
            await Notify.push_plyer(
                f"{self.provider.display_name} 自动代理出现异常！",
                f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                f"{self.cur_user_item.name}的自动代理出现异常",
                3,
            )

        if attempt_index + 1 < run_limit:
            await self._push_dispatch_log(
                f"将在 10 秒后开始第 {attempt_index + 2}/{run_limit} 次重试"
            )
            await asyncio.sleep(10)
        else:
            self.cur_user_item.status = "异常"

    async def _run_script_after_task(self) -> None:
        if not self.cur_user_config.get("Info", "IfScriptAfterTask"):
            return
        await execute_script_task(
            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
            "脚本后任务",
        )

    async def sync_script_config(self) -> None:
        try:
            await self._backup_script_config()
            await asyncio.to_thread(
                _replace_tree,
                self.mas_config_dir,
                self.script_config_path,
            )
            self.runtime_config_originals = await asyncio.to_thread(
                _apply_runtime_config_overrides,
                self.script_config_path,
                self.provider.runtime_config_overrides,
            )
            self.script_config_injected = True
            if self.runtime_config_originals:
                await self._push_dispatch_log(
                    "已应用项目运行期策略，禁止脚本自动打开本地汇报"
                )
            logger.info(f"已同步 {self.provider.display_name} 用户配置到脚本目录: {self.script_config_path}")
        except Exception as e:
            logger.exception(f"同步 {self.provider.display_name} 用户配置到脚本目录失败: {e}")
            raise

    async def _backup_script_config(self) -> None:
        """备份脚本本地配置，确保 MAS 注入后可恢复原状。"""

        if self.script_config_injected:
            return

        if self.script_config_backup_path == Path():
            raise RuntimeError("ok-script 配置备份路径未初始化")

        await asyncio.to_thread(
            shutil.rmtree,
            self.script_config_backup_path,
            ignore_errors=True,
        )
        self.had_original_script_config = self.script_config_path.is_dir()
        if self.had_original_script_config:
            await asyncio.to_thread(
                shutil.copytree,
                self.script_config_path,
                self.script_config_backup_path,
            )
        self.script_config_swap_started = True

    async def _restore_script_config(self) -> None:
        """写回 MAS 配置后恢复脚本本地配置。"""

        if not self.script_config_swap_started:
            return

        try:
            if self.had_original_script_config:
                await asyncio.to_thread(
                    _replace_tree,
                    self.script_config_backup_path,
                    self.script_config_path,
                )
            else:
                await asyncio.to_thread(
                    shutil.rmtree,
                    self.script_config_path,
                    ignore_errors=True,
                )
        finally:
            try:
                if self.script_config_backup_path != Path():
                    await asyncio.to_thread(
                        shutil.rmtree,
                        self.script_config_backup_path,
                        ignore_errors=True,
                    )
            finally:
                self.had_original_script_config = False
                self.script_config_swap_started = False
                self.script_config_injected = False
                self.runtime_config_originals = {}

    async def update_config(self) -> None:
        if self.script_config_path == Path() or self.mas_config_dir == Path():
            logger.warning("ok-script 配置路径未初始化，跳过写回")
            return

        try:
            runtime_config_originals = getattr(self, "runtime_config_originals", {})
            await asyncio.to_thread(
                _restore_runtime_config_overrides,
                self.script_config_path,
                runtime_config_originals,
            )
            await asyncio.to_thread(
                _replace_tree,
                self.script_config_path,
                self.mas_config_dir,
            )
            self.runtime_config_originals = {}
            logger.info(f"已写回 {self.provider.display_name} 用户配置: {self.mas_config_dir}")
        except Exception as e:
            logger.exception(f"写回 {self.provider.display_name} 用户配置失败: {e}")
            raise

    async def _launch_game_before_task(self) -> str:
        if not self.game_path.is_file():
            return "请设置游戏程序路径"

        if self.game_manager is None:
            self.game_manager = ProcessManager()

        self.script_info.log = "正在准备由 MAS 启动游戏"
        game_process_name = self.provider.game_process_name or self.game_path.name
        if game_process_name and is_process_running(game_process_name):
            logger.info("检测到游戏进程已在运行，跳过由 MAS 重复启动游戏")
            self.script_info.log = "检测到游戏进程已在运行，跳过启动"
            self.game_started_by_mas = True
            return "Pass"

        try:
            await self.game_manager.open_process(
                self.game_path,
                *_split_args(self.script_config.get("Game", "Arguments")),
            )
        except Exception as e:
            logger.exception(f"启动游戏失败: {e}")
            return f"游戏启动失败: {e}"

        self.game_started_by_mas = True
        wait_time = int(self.script_config.get("Game", "WaitTime"))
        self.script_info.log = f"正在等待游戏完成启动\n请等待{wait_time}s"
        await asyncio.sleep(wait_time)
        self.script_info.log = "游戏启动等待完成"
        return "Pass"

    async def _run_script_process_legacy_text_log(self) -> str:
        await self._kill_script_process()
        logger.info(
            f"启动 {self.provider.display_name} 进程: "
            f"{self.script_exe_path} {' '.join(self.script_args)}"
        )
        self.script_info.log = (
            f"启动 {self.provider.display_name}: -t {self.task_index} -e\n"
            "正在连接游戏窗口并开始运行"
        )
        monitor_started = False
        try:
            await self.script_process_manager.open_process(
                self.script_exe_path,
                *self.script_args,
                cwd=self.script_cwd,
                env=self.script_environment,
                target_process=self.script_target_process_info,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._start_process_stream_readers()
        except Exception as e:
            logger.exception(f"启动 {self.provider.display_name} 失败: {e}")
            with suppress(Exception):
                await self._kill_script_process()
            return f"{self.provider.display_name} 启动失败: {e}"

        try:
            deadline = datetime.now() + timedelta(seconds=60)
            while not self.script_log_path.exists() and datetime.now() < deadline:
                if not await self.script_process_manager.is_running():
                    return f"{self.provider.display_name} 在生成日志前退出"
                await asyncio.sleep(1)

            if not self.script_log_path.exists():
                return f"未找到 {self.provider.display_name} 日志文件"

            if self.log_monitor is None:
                return "ok-script 日志监控未初始化"

            self.wait_event.clear()
            self.script_info.log = "运行中，正在监察 ok-script 日志"
            await self.log_monitor.start_monitor_file(
                self.script_log_path, self.log_start_time
            )
            monitor_started = True
            await self.wait_event.wait()

            if self.cur_user_log is None:
                return f"{self.provider.display_name} 未返回运行结果"
            return self.cur_user_log.status or f"{self.provider.display_name} 未返回运行结果"
        finally:
            if monitor_started and self.log_monitor is not None:
                with suppress(Exception):
                    await self.log_monitor.stop()

    async def check_log_legacy_text_log(
        self,
        log_content: list[str],
        latest_time: datetime,
    ) -> None:
        """ok-script 日志回调：失败/成功均由当前 provider 内置字段判定。"""

        if self.cur_user_log is None:
            return

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.legacy_log_lines = log_content
        self._refresh_current_log_content()
        self.script_info.log = self._build_dispatch_log_snapshot()
        if self.report_handler is not None:
            await self.report_handler.capture(self, log)

        log_status = self.provider.running_status
        user_item_status: str | None = None

        for needle, msg in self.provider.fatal_patterns:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            log_lower = log.lower()
            if any(
                success.lower() in log_lower
                for success in self.provider.success_patterns
            ):
                log_status = "Success!"
                user_item_status = "完成"
            elif not await self.script_process_manager.is_running():
                log_status = f"{self.provider.display_name} 在完成任务前退出"
                user_item_status = "异常"
            elif datetime.now() - latest_time > timedelta(
                minutes=int(self.script_config.get("Run", "RunTimeLimit"))
            ):
                log_status = f"{self.provider.display_name} 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"{self.provider.display_name} 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != self.provider.running_status:
            if self.cur_user_log.status == "Success!":
                self.run_book = True
            logger.info(
                f"{self.provider.display_name} 任务结果: {self.cur_user_log.status}, 日志锁已释放"
            )
            self.wait_event.set()

    async def _run_script_process(self) -> str:
        """运行 ok-script，并同时监听 MAS 结构化事件与旧文本日志。"""

        await self._kill_script_process()
        await self._push_dispatch_log(
            f"启动 {self.provider.display_name}：{' '.join(self.script_args)}"
        )
        logger.info(
            f"启动 {self.provider.display_name} 进程: "
            f"{self.script_exe_path} {' '.join(self.script_args)}"
        )
        monitor_started = False
        try:
            await self.script_process_manager.open_process(
                self.script_exe_path,
                *self.script_args,
                cwd=self.script_cwd,
                env=self.script_environment,
                target_process=self.script_target_process_info,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._start_process_stream_readers()
        except Exception as e:
            logger.exception(f"启动 {self.provider.display_name} 失败: {e}")
            with suppress(Exception):
                await self._kill_script_process()
            return f"{self.provider.display_name} 启动失败: {e}"

        try:
            self.wait_event.clear()
            await self._start_event_monitor()
            if self.shell_runner is not None:
                self.shell_runner.emit_event(
                    "run_started",
                    task=str(self.task_index),
                    message="MAS 已启动项目进程，正在等待日志判态",
                    protocol=self.execution_protocol,
                    command=[str(self.script_exe_path), *self.script_args],
                )

            deadline = datetime.now() + timedelta(seconds=60)
            while (
                not self.script_log_path.exists()
                and not self.wait_event.is_set()
                and datetime.now() < deadline
            ):
                if not await self.script_process_manager.is_running():
                    exit_status = await self._process_exit_status()
                    if exit_status is not None:
                        return exit_status
                    return f"{self.provider.display_name} 在生成日志前退出"
                await asyncio.sleep(1)

            if self.wait_event.is_set():
                return self._current_run_status()

            if self.script_log_path.exists():
                if self.log_monitor is None:
                    return "ok-script 日志监控未初始化"
                await self._push_dispatch_log(
                    f"已开始监察文本日志：{self.script_log_path}"
                )
                await self.log_monitor.start_monitor_file(
                    self.script_log_path, self.log_start_time
                )
                monitor_started = True
            else:
                await self._push_dispatch_log(
                    f"未发现传统文本日志，继续等待结构化事件：{self.script_event_log_path}"
                )

            run_deadline = datetime.now() + timedelta(
                minutes=int(self.script_config.get("Run", "RunTimeLimit"))
            )
            while not self.wait_event.is_set():
                if not await self.script_process_manager.is_running():
                    # 给 stdout 读取器与结构化事件监听器一个短暂窗口处理最终输出。
                    await asyncio.sleep(SCRIPT_EXIT_EVENT_GRACE_SECONDS)
                    if self.wait_event.is_set():
                        return self._current_run_status()

                    exit_status = await self._process_exit_status()
                    if exit_status is not None:
                        return exit_status
                    if not self.script_log_path.exists():
                        return f"{self.provider.display_name} 在返回结果前退出"
                    return f"{self.provider.display_name} 在完成任务前退出"
                if not self.script_log_path.exists() and datetime.now() > run_deadline:
                    return f"{self.provider.display_name} 未输出日志或结构化事件"
                await asyncio.sleep(1)

            return self._current_run_status()
        finally:
            if monitor_started and self.log_monitor is not None:
                with suppress(Exception):
                    await self.log_monitor.stop()
            await self._stop_event_monitor()
            if not self.run_book:
                await self._stop_process_stream_readers()

    def _current_run_status(self) -> str:
        if self.cur_user_log is None:
            return f"{self.provider.display_name} 未返回运行结果"
        return self.cur_user_log.status or f"{self.provider.display_name} 未返回运行结果"

    def _start_process_stream_readers(self) -> None:
        """把被接管进程的控制台输出同步进 MAS 调度日志。"""

        process = self.script_process_manager.process
        if process is None:
            return
        self.stream_reader_tasks = [
            asyncio.create_task(self._read_process_stream(process.stdout, "stdout")),
            asyncio.create_task(self._read_process_stream(process.stderr, "stderr")),
        ]

    async def _read_process_stream(
        self,
        stream: asyncio.StreamReader | None,
        source: str,
    ) -> None:
        if stream is None:
            return
        try:
            while True:
                raw_line = await stream.readline()
                if not raw_line:
                    return
                line = decode_bytes(raw_line).rstrip("\r\n")
                if line:
                    await self._push_dispatch_log(f"[{source}] {line}")
                    if self.report_handler is not None:
                        await self.report_handler.capture(self, line)
                    await self._observe_stream_terminal_log(source, line)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"读取 ok-script {source} 失败: {type(exc).__name__}: {exc}")

    async def _observe_stream_terminal_log(self, source: str, line: str) -> None:
        """在未收到结构化终态时，以受管进程输出补足日志终态。"""

        if (
            self.event_terminal_received
            or self.wait_event.is_set()
            or self.cur_user_log is None
        ):
            return

        status: str | None = None
        user_item_status: str | None = None
        for needle, message in self.provider.fatal_patterns:
            if needle in line:
                status = message
                user_item_status = "异常"
                break
        else:
            line_lower = line.lower()
            if any(
                success.lower() in line_lower
                for success in self.provider.success_patterns
            ):
                status = "Success!"
                user_item_status = "完成"

        if status is None or user_item_status is None:
            return

        self.cur_user_log.status = status
        self.cur_user_item.status = user_item_status
        if status == "Success!":
            self.run_book = True
        await self._push_dispatch_log(
            f"已通过 {source} 日志确认任务{'完成' if status == 'Success!' else '异常'}: {status}"
        )
        logger.info(
            f"{self.provider.display_name} 任务结果: {status}, "
            f"已通过 {source} 日志释放等待"
        )
        self.wait_event.set()

    async def _stop_process_stream_readers(self) -> None:
        stream_tasks = list(getattr(self, "stream_reader_tasks", []))
        for task in stream_tasks:
            if not task.done():
                task.cancel()
        for task in stream_tasks:
            with suppress(asyncio.CancelledError, Exception):
                await task
        self.stream_reader_tasks = []

    async def _process_exit_status(self) -> str | None:
        """进程退出只提供异常证据，成功仍必须等待日志或完成事件。"""

        if self.execution_protocol == PROTOCOL_LEGACY_EXE:
            return None
        process = self.script_process_manager.process
        if process is None or process.returncode is None:
            return None
        if process.returncode == 0:
            await asyncio.sleep(0.5)
            if self.wait_event.is_set():
                return self._current_run_status()
            if self.shell_runner is not None:
                self.shell_runner.emit_event(
                    "process_exited",
                    task=str(self.task_index),
                    message="脚本进程已退出，未收到成功日志或结构化完成事件",
                    protocol=self.execution_protocol,
                    returnCode=0,
                )
            return (
                f"{self.provider.display_name} 进程已退出，"
                "但未收到成功日志或结构化完成事件"
            )
        if self.shell_runner is not None:
            self.shell_runner.emit_event(
                "run_failed",
                task=str(self.task_index),
                message=f"脚本进程异常退出，退出码 {process.returncode}",
                success=False,
                protocol=self.execution_protocol,
                returnCode=process.returncode,
            )
        return f"{self.provider.display_name} 异常退出，退出码 {process.returncode}"

    async def _start_event_monitor(self) -> None:
        if self.event_monitor_task is not None and not self.event_monitor_task.done():
            return
        await self._push_dispatch_log(
            f"已开启 MAS 结构化事件监听：{self.script_event_log_path}"
        )
        self.event_monitor_task = asyncio.create_task(self._monitor_event_log())

    async def _stop_event_monitor(self) -> None:
        if self.event_monitor_task is None:
            self.event_monitor_task = None
            return
        if self.event_monitor_task.done():
            with suppress(asyncio.CancelledError, Exception):
                self.event_monitor_task.result()
            self.event_monitor_task = None
            return
        self.event_monitor_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.event_monitor_task
        self.event_monitor_task = None

    async def _monitor_event_log(self) -> None:
        while not self.wait_event.is_set():
            try:
                events, self.event_log_offset = await asyncio.to_thread(
                    read_ok_script_run_events,
                    self.script_event_log_path,
                    self.event_log_offset,
                )
                for event in events:
                    await self._handle_run_event(event)
                    if self.wait_event.is_set():
                        break
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception(f"监听 ok-script 结构化事件失败: {e}")
                await self._push_dispatch_log(
                    f"结构化事件监听异常，已回退文本日志：{e}"
                )
                return
            await asyncio.sleep(1)

    async def _emit_ok_script_event(
        self,
        event: OkScriptRunEvent,
        *,
        status: str | None = None,
    ) -> None:
        """向插件总线广播 ok-script 结构化明细事件。"""

        provider = getattr(self, "provider", None)
        task_info = getattr(self, "task_info", None)
        script_info = getattr(self, "script_info", None)
        user_item = getattr(self, "cur_user_item", None)
        cur_user_log = getattr(self, "cur_user_log", None)
        failures = getattr(self, "event_failures", [])

        data = {
            "task_id": getattr(task_info, "task_id", None),
            "mode": getattr(task_info, "mode", None),
            "queue_id": getattr(task_info, "queue_id", None),
            "script_id": getattr(script_info, "script_id", None),
            "script_name": getattr(script_info, "name", None),
            "user_id": getattr(user_item, "user_id", None),
            "user_name": getattr(user_item, "name", None),
            "resource_name": getattr(provider, "resource_name", None),
            "display_name": getattr(provider, "display_name", None),
            "task_index": getattr(self, "task_index", None),
            "protocol_version": OK_SCRIPT_EVENT_PROTOCOL_VERSION,
            "ok_script_event": event.event,
            "message": event.message,
            "task": event.task,
            "success": event.success,
            "terminal": event.is_terminal,
            "status": status or getattr(cur_user_log, "status", None),
            "failures": [
                {"task": failure.task, "message": failure.message}
                for failure in failures
            ],
        }

        try:
            from app.plugins import PluginEventFactory

            await PluginEventFactory.emit_event_async(
                event=OK_SCRIPT_PLUGIN_EVENT,
                source=OK_SCRIPT_PLUGIN_EVENT_SOURCE,
                data=data,
            )
        except Exception as e:
            logger.warning(f"广播 ok-script 结构化插件事件失败: {e}")

    async def _handle_run_event(self, event: OkScriptRunEvent) -> None:
        if self.cur_user_log is None:
            return

        if not self.event_protocol_active:
            self.event_protocol_active = True
            await self._push_dispatch_log("检测到 ok-script 结构化事件，切换为 MAS 事件判态")

        if event.failures:
            self.event_failures = list(event.failures)

        subject = event.task or event.event
        message = event.message or subject
        if event.event in {"step", "task_completed", "task_failed", "summary"}:
            await self._push_dispatch_log(f"事件 {event.event}: {message}")

        if event.event == "task_failed":
            if not event.failures:
                self.event_failures.append(
                    OkScriptRunFailure(
                        task=event.task or "未命名任务",
                        message=event.message or "未提供失败原因",
                    )
                )
            await self._emit_ok_script_event(event)
            return

        if event.event == "run_failed" or (
            event.event == "run_completed" and event.success is False
        ):
            self.event_terminal_received = True
            status = event.message or f"{self.provider.display_name} 运行失败"
            self.cur_user_log.status = status
            self.cur_user_item.status = "异常"
            self.script_info.log = status
            await self._emit_ok_script_event(event, status=status)
            self.wait_event.set()
            return

        if event.event != "run_completed":
            await self._emit_ok_script_event(event)
            return

        failures = tuple(self.event_failures)
        self.event_terminal_received = True
        status = format_partial_success_status(failures) if failures else "Success!"
        self.cur_user_log.status = status
        self.cur_user_item.status = "完成"
        self.script_info.log = status
        self.run_book = True
        await self._emit_ok_script_event(event, status=status)
        self.wait_event.set()

    async def check_log(
        self,
        log_content: list[str],
        latest_time: datetime,
    ) -> None:
        """旧文本日志兜底；仅结构化终态可以停止传统日志判态。"""

        if self.cur_user_log is None:
            return

        log = "".join(log_content)
        self.legacy_log_lines = log_content
        self._refresh_current_log_content()
        if self.report_handler is not None:
            await self.report_handler.capture(self, log)

        # 非终态事件只提供进度或专项失败明细，不能屏蔽传统成功/异常字段。
        # 部分上游项目当前只会发送 run_started，最终仍由原始日志或 stdout 收尾。
        if self.event_terminal_received or self.wait_event.is_set():
            return

        self.script_info.log = self._build_dispatch_log_snapshot()

        log_status = self.provider.running_status
        user_item_status: str | None = None

        for needle, msg in self.provider.fatal_patterns:
            if needle in log:
                log_status = msg
                user_item_status = "异常"
                break
        else:
            log_lower = log.lower()
            if any(
                success.lower() in log_lower
                for success in self.provider.success_patterns
            ):
                log_status = "Success!"
                user_item_status = "完成"
            elif not await self.script_process_manager.is_running():
                log_status = f"{self.provider.display_name} 在完成任务前退出"
                user_item_status = "异常"
            elif datetime.now() - latest_time > timedelta(
                minutes=int(self.script_config.get("Run", "RunTimeLimit"))
            ):
                log_status = f"{self.provider.display_name} 运行超时"
                user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"{self.provider.display_name} 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != self.provider.running_status:
            if self.cur_user_log.status == "Success!":
                self.run_book = True
            logger.info(
                f"{self.provider.display_name} 任务结果: {self.cur_user_log.status}, 日志锁已释放"
            )
            self.wait_event.set()

    async def final_task(self) -> None:
        try:
            await self._finalize_task()
        finally:
            report_handler = getattr(self, "report_handler", None)
            if report_handler is not None:
                with suppress(Exception):
                    await report_handler.stop(self)
            self._release_script_root_lock()

    async def _finalize_task(self) -> None:
        await self._stop_process_stream_readers()
        with suppress(Exception):
            if self.log_monitor is not None:
                await self.log_monitor.stop()

        await self.kill_managed_process(
            kill_game=(not self.run_book) and self._should_kill_game()
        )
        try:
            await self._restore_script_config()
        except Exception as restore_error:
            logger.exception(
                f"恢复 {self.provider.display_name} 脚本本地配置失败: {restore_error}"
            )

        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )

            if log_item.status == self.provider.running_status:
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        await self.cur_user_config.set("Data", "LastTaskIndex", self.task_index)
        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            logger.success(
                f"用户 {self.cur_user_uid} 的 {self.provider.display_name} 自动代理任务已完成"
            )
            return

        await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
        if self.cur_user_item.status not in ("完成", "跳过"):
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception) -> None:
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"{self.provider.display_name} 运行异常: {e}"
        self.wait_event.set()
        with suppress(Exception):
            if self.log_monitor is not None:
                await self.log_monitor.stop()
        if self.report_handler is not None:
            with suppress(Exception):
                await self.report_handler.stop(self)
        logger.exception(f"{self.provider.display_name} 自动代理任务出现异常: {e}")
        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"{self.provider.display_name} 自动代理任务出现异常: {e}"},
            )
        except Exception as send_error:
            logger.exception(f"发送 {self.provider.display_name} 异常通知失败: {send_error}")
        try:
            await self.kill_managed_process(kill_game=self._should_kill_game())
        except Exception as kill_error:
            logger.exception(f"清理 {self.provider.display_name} 进程失败: {kill_error}")
        try:
            if self.script_config_injected:
                await self.update_config()
        except Exception as config_error:
            logger.exception(f"崩溃后写回 {self.provider.display_name} 配置失败: {config_error}")
        try:
            await self._restore_script_config()
        except Exception as restore_error:
            logger.exception(
                f"崩溃后恢复 {self.provider.display_name} 脚本本地配置失败: {restore_error}"
            )
        try:
            await self._persist_user_run_result()
        except Exception as persist_error:
            logger.exception(
                f"写回 {self.provider.display_name} 用户运行结果失败: {persist_error}"
            )

    def _should_kill_game(self) -> bool:
        if self.manual_stop and not self.script_config.get(
            "Game", "KillGameOnManualStop"
        ):
            return False
        return self.game_path.is_file()

    def _resolve_provider(self, root: Path) -> OkScriptProvider | None:
        return detect_ok_script_provider(
            root,
            self.script_config.get("Info", "ResourceName"),
        )

    def _release_script_root_lock(self) -> None:
        if (
            self.script_root_lock_acquired
            and self.script_root_lock is not None
            and self.script_root_lock.locked()
        ):
            self.script_root_lock.release()
        self.script_root_lock_acquired = False

    async def _wait_script_exit(self, *, timeout: int = 10) -> None:
        """等待脚本收尾退出，进程查询或清理超时不得阻塞调度终态。"""

        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                is_running = await asyncio.wait_for(
                    self.script_process_manager.is_running(),
                    timeout=min(SCRIPT_EXIT_CHECK_TIMEOUT, remaining),
                )
            except asyncio.TimeoutError:
                await self._push_dispatch_log("确认脚本退出状态超时，开始受控收尾")
                break

            if not is_running:
                logger.info(f"{self.provider.display_name} 已自行退出")
                return
            await asyncio.sleep(min(1, remaining))

        logger.warning(f"{self.provider.display_name} 未在 {timeout}s 内自行退出，兜底强杀")
        await self._push_dispatch_log(
            f"脚本未在 {timeout}s 内退出，正在执行受控收尾"
        )
        try:
            await asyncio.wait_for(
                self._kill_script_process(),
                timeout=SCRIPT_EXIT_KILL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(f"{self.provider.display_name} 受控收尾超时，继续结束调度任务")
            await self._push_dispatch_log("脚本受控收尾超时，继续结束调度任务")

    async def _kill_script_process(self) -> None:
        await self._stop_process_stream_readers()
        try:
            await self.script_process_manager.kill()
        except Exception as e:
            logger.exception(f"通过进程管理器中止 {self.provider.display_name} 进程失败: {e}")
        if (
            self.execution_protocol == PROTOCOL_LEGACY_EXE
            and self.script_exe_path.is_file()
        ):
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as e:
                logger.exception(f"中止 {self.provider.display_name} 主进程失败: {e}")
        if self.use_provider_process_tracking and self.script_root_path != Path():
            track_exe = self.provider.track_process_path(self.script_root_path)
            if track_exe.is_file():
                try:
                    await System.kill_process(track_exe)
                except Exception as e:
                    logger.exception(f"中止 {self.provider.display_name} 追踪进程失败: {e}")

    async def _kill_game_process(self) -> None:
        try:
            if isinstance(self.game_manager, ProcessManager):
                await self.game_manager.kill()
        except Exception as e:
            logger.exception(f"通过进程管理器关闭游戏失败: {e}")
        try:
            if self.game_path.is_file():
                await System.kill_process(self.game_path)
        except Exception as e:
            logger.exception(f"关闭游戏进程失败: {e}")
        finally:
            self.game_started_by_mas = False

    async def kill_managed_process(self, *, kill_game: bool = True) -> None:
        await self._kill_script_process()
        if kill_game:
            await self._kill_game_process()
