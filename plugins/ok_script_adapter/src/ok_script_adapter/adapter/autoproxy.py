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
import shlex
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.models.ConfigBase import ConfigBase, MultipleConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.task.general.tools import execute_script_task
from app.utils import get_logger
from app.utils.ProcessManager import ProcessManager, is_process_running
from app.utils.constants import UTC4

from ..common.events import (
    OK_SCRIPT_EVENT_PROTOCOL_VERSION,
    OK_SCRIPT_PLUGIN_EVENT,
    OK_SCRIPT_PLUGIN_EVENT_SOURCE,
    OkScriptRunEvent,
    OkScriptRunFailure,
)
from ..common.provider import (
    OkScriptProvider,
    OkScriptTaskOption,
    ok_script_mas_config_dir,
    resolve_game_executable_path,
)
from ..common.report import OkScriptReportHandler
from ..common.runtime_lock import (
    get_ok_script_config_lock,
    get_ok_script_root_lock,
)
from ..providers import get_ok_script_provider
from ..shell.descriptor import OkProjectDescriptor, OkProjectInspectError
from ..shell.manifest import inspect_ok_project
from ..shell.runtime import (
    OkShellRunner,
    OkShellRuntimeError,
)
from .config_session import OkScriptConfigSession
from .execution import ExecutionPlan, ExecutionPlanner, RunObservation
from .run_controller import (
    AttemptPreparation,
    RunController,
    RunControllerResult,
    RunControllerUpdate,
)

logger = get_logger("ok-script 自动代理")


# 调度台需要足够的近期上下文，但不能因为长时间 OCR 输出无限增长。
DISPATCH_LOG_MAX_CHARS = 100_000
DISPATCH_LOG_MAX_RUNTIME_LINES = 2_000
DISPATCH_LOG_TRUNCATION_NOTICE = "[MAS] 调度台仅保留最近日志，完整历史请查看任务记录。"


def _split_args(raw: object) -> list[str]:
    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def _build_descriptor_provider(descriptor: OkProjectDescriptor) -> OkScriptProvider:
    """为未登记项目提供明确禁止运行的通用 Provider。"""

    def relative_path(path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return path.relative_to(descriptor.root_path).as_posix()
        except ValueError:
            return str(path)

    return OkScriptProvider(
        resource_name=descriptor.resource_name,
        display_name=descriptor.display_name or descriptor.resource_name,
        exe_name=relative_path(descriptor.executable),
        config_dir=relative_path(descriptor.config_dir),
        log_file=relative_path(descriptor.log_path),
        pythonw_path="",
        track_process_name="",
        game_process_name="",
        running_status="运行中",
        fatal_patterns=(),
        success_patterns=(
            "Successfully Executed Task",
            "Successfully Executed Task, Exiting Game and App!",
        ),
        max_task_index=max((task.index for task in descriptor.tasks), default=0),
        task_options=tuple(
            OkScriptTaskOption(task.index, task.label or task.selector)
            for task in descriptor.tasks
        ),
        config_schema_module="",
        config_info_loader="",
        runtime_verified=False,
        runtime_block_reason=(
            "当前项目只完成 descriptor 与配置识别，尚未验证自动运行能力"
        ),
    )


def _resolve_descriptor_provider(
    descriptor: OkProjectDescriptor,
) -> tuple[OkProjectDescriptor, OkScriptProvider, bool]:
    """绑定项目 Provider，并叠加当前目录的运行协议能力。"""

    registered_provider = get_ok_script_provider(descriptor.resource_name)
    provider = registered_provider or _build_descriptor_provider(descriptor)
    verified_descriptor = descriptor.with_runtime_verification(
        verified=provider.runtime_verified,
        reason=provider.runtime_block_reason,
    )
    return verified_descriptor, provider, registered_provider is not None


class OkScriptAutoProxyTask(TaskExecuteBase):
    """ok-script 自动代理：由 descriptor 选择协议并监控运行结果。"""

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
        self.project_descriptor: OkProjectDescriptor | None = None
        self.execution_plan: ExecutionPlan | None = None
        self.config_session: OkScriptConfigSession | None = None
        self.run_controller: RunController | None = None

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: ConfigBase = self.user_config[self.cur_user_uid]

        self.script_root_path: Path = Path()
        self.script_config_path: Path = Path()
        self.mas_config_dir: Path = Path()
        self.script_config_backup_path: Path = Path()
        self.script_root_lock: asyncio.Lock | None = None
        self.script_root_lock_acquired = False
        self.user_config_lock: asyncio.Lock | None = None
        self.user_config_lock_acquired = False
        self.event_failures: list[OkScriptRunFailure] = []
        self.runtime_log_lines: list[str] = []
        self.legacy_log_lines: list[str] = []
        self.log_start_time: datetime = datetime.now()
        self.task_index = 1
        self.game_path: Path = Path()
        self.run_book = False
        self.game_started_by_mas = False
        self.manual_stop = False
        self.attempt_started = False
        self.run_result_persisted = False
        self.cur_user_log: LogRecord | None = None
        self.report_handler: OkScriptReportHandler | None = None
        self.curdate = ""

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 ok-script 项目路径"
        try:
            descriptor = await asyncio.to_thread(inspect_ok_project, root)
        except OkProjectInspectError as exc:
            return f"无法解析 ok-script 项目: {exc}"
        descriptor, self.provider, _ = _resolve_descriptor_provider(descriptor)
        self.project_descriptor = descriptor
        runtime = descriptor.capabilities.runtime
        if not runtime.verified:
            return (
                runtime.reason
                or "当前 ok-script 项目尚未完成运行验证"
            )

        task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        if descriptor.tasks and not any(
            task.index == task_index for task in descriptor.tasks
        ):
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

        configured_game_path_value = str(
            self.script_config.get("Game", "Path") or ""
        ).strip()
        if not configured_game_path_value:
            if self.provider.game_process_name:
                return (
                    f"请设置 {self.provider.display_name} 游戏主程序路径 "
                    f"{self.provider.game_process_name}"
                )
            return "请设置游戏程序路径"

        configured_game_path = Path(configured_game_path_value)
        if self.provider.game_process_name:
            resolved_game_path = await asyncio.to_thread(
                resolve_game_executable_path,
                self.provider,
                configured_game_path,
            )
            if resolved_game_path is None:
                return (
                    f"请设置 {self.provider.display_name} 游戏主程序路径 "
                    f"{self.provider.game_process_name}"
                )
            await self.script_config.set(
                "Game",
                "Path",
                resolved_game_path.as_posix(),
            )
        elif not configured_game_path.is_file():
            return "请设置游戏程序路径"

        return "Pass"

    async def prepare(self) -> None:
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        try:
            descriptor = self.project_descriptor or await asyncio.to_thread(
                inspect_ok_project,
                self.script_root_path,
            )
        except OkProjectInspectError as exc:
            raise RuntimeError(f"无法解析 ok-script 项目: {exc}") from exc
        descriptor, provider, provider_registered = (
            _resolve_descriptor_provider(descriptor)
        )
        self.provider = provider
        self.project_descriptor = descriptor
        runtime = descriptor.capabilities.runtime
        if not runtime.verified:
            raise RuntimeError(
                runtime.reason
                or "当前 ok-script 项目尚未完成运行验证"
            )
        self.script_root_lock = get_ok_script_root_lock(self.script_root_path)
        if not self.script_root_lock_acquired:
            self.script_info.log = "正在等待同一 ok-script 项目完成运行"
            await self.script_root_lock.acquire()
            self.script_root_lock_acquired = True
        self.task_index = int(self.cur_user_config.get("Task", "TaskIndex"))
        command_builder = OkShellRunner(descriptor)
        try:
            available_protocols = await asyncio.to_thread(
                command_builder.available_protocols
            )
            self.execution_plan = ExecutionPlanner(
                descriptor,
                provider,
                provider_registered=provider_registered,
            ).build(
                task_index=self.task_index,
                available_protocols=available_protocols,
                attempt_limit=int(
                    self.script_config.get("Run", "RunTimesLimit")
                ),
                run_timeout_minutes=int(
                    self.script_config.get("Run", "RunTimeLimit")
                ),
            )
        except OkShellRuntimeError as exc:
            raise RuntimeError(f"无法构建 ok-script 运行命令: {exc}") from exc

        self.script_config_path = descriptor.config_dir
        self.mas_config_dir = ok_script_mas_config_dir(
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        await self._acquire_user_config_lock()
        script_uid = str(uuid.UUID(self.script_info.script_id))
        user_uid = str(uuid.UUID(self.cur_user_item.user_id))
        self.script_config_backup_path = (
            Path.cwd()
            / "data"
            / script_uid
            / "Temp"
            / user_uid
            / "ConfigFile"
        )
        self.config_session = OkScriptConfigSession(
            mas_config_dir=self.mas_config_dir,
            project_config_dir=self.script_config_path,
            backup_dir=self.script_config_backup_path,
            runtime_overrides=provider.runtime_config_overrides,
        )
        self.run_controller = RunController(self.execution_plan)
        self.game_path = Path(self.script_config.get("Game", "Path"))
        self.run_book = False
        self.game_started_by_mas = False
        self.report_handler = (
            provider.report_handler_factory()
            if provider.report_handler_factory is not None
            else None
        )

    async def main_task(self) -> None:
        await self.prepare()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.cur_user_item.status = "运行"
        if self.run_controller is None:
            raise RuntimeError("ok-script RunController 未准备完成")
        await self.run_controller.run(self)

    def _reset_attempt_observation(self) -> None:
        """初始化单次运行的日志与结构化事件观测状态。"""

        self.event_failures = []
        self.runtime_log_lines = []
        self.legacy_log_lines = []

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

    async def prepare_attempt(
        self,
        attempt: int,
        total_attempts: int,
    ) -> AttemptPreparation:
        """为 RunController 准备一次完整运行。"""

        provider = self._require_provider()
        self.attempt_started = True
        logger.info(
            f"用户 {self.cur_user_item.name} - 尝试次数: "
            f"{attempt}/{total_attempts}"
        )
        self.cur_user_item.status = "运行"
        self.log_start_time = datetime.now()
        self.cur_user_item.log_record[self.log_start_time] = LogRecord(
            status=provider.running_status
        )
        self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
        self._reset_attempt_observation()
        await self._push_dispatch_log(
            f"开始第 {attempt}/{total_attempts} 次运行，准备接管 "
            f"{provider.display_name}"
        )

        self.report_handler = (
            provider.report_handler_factory()
            if provider.report_handler_factory is not None
            else None
        )
        if self.report_handler is not None:
            await self.report_handler.start(self)

        if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                "脚本前任务",
            )

        config_session = self._require_config_session()
        try:
            await config_session.inject()
            await self._push_dispatch_log("已向脚本注入当前用户配置")
            if config_session.runtime_originals:
                await self._push_dispatch_log(
                    "已应用项目运行期策略，禁止脚本自动打开本地汇报"
                )
            logger.info(
                f"已同步 {provider.display_name} 用户配置到脚本目录: "
                f"{self.script_config_path}"
            )
        except Exception as exc:
            logger.exception(
                f"同步 {provider.display_name} 用户配置到脚本目录失败: {exc}"
            )
            raise

        if self._should_launch_game_before_task():
            game_result = await self._launch_game_before_task()
            if game_result != "Pass":
                return AttemptPreparation(
                    started_at=self.log_start_time,
                    failure_status=game_result,
                )
        else:
            await self._push_dispatch_log(
                "MAS 已跳过游戏启动，游戏启动由 ok-script 负责"
            )
        return AttemptPreparation(started_at=self.log_start_time)

    async def complete_attempt(self, result: RunControllerResult) -> None:
        """处理控制器确认成功且脚本已退出后的项目业务收尾。"""

        self.run_book = True
        self.cur_user_item.status = "完成"
        await self._push_dispatch_log("已确认整轮任务完成，脚本进程已完成收尾")
        config_session = self._require_config_session()
        await config_session.write_back()
        logger.info(
            f"已写回 {self._require_provider().display_name} 用户配置: "
            f"{self.mas_config_dir}"
        )
        await config_session.restore()
        if self.report_handler is not None:
            await self.report_handler.apply(self)
            await self.report_handler.stop(self)
        await self._run_script_after_task()

    async def fail_attempt(
        self,
        result: RunControllerResult,
        *,
        will_retry: bool,
    ) -> None:
        """处理控制器已完成进程清理的一次整轮失败。"""

        provider = self._require_provider()
        status = result.observation.status
        logger.error(
            f"用户 {self.cur_user_item.name} - {provider.display_name} "
            f"代理异常: {status}"
        )
        if self.cur_user_log is not None:
            self.cur_user_log.status = status
            if not self.cur_user_log.content:
                self.cur_user_log.content = [status]
        self.script_info.log = status
        await self._push_dispatch_log(f"本次运行失败：{status}")
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": status},
            )

        config_session = self._require_config_session()
        await config_session.write_back()
        logger.info(
            f"已写回 {provider.display_name} 用户配置: {self.mas_config_dir}"
        )
        await config_session.restore()
        await self._run_script_after_task()
        if self.report_handler is not None:
            await self.report_handler.stop(self)
        with suppress(Exception):
            await Notify.push_plyer(
                f"{provider.display_name} 自动代理出现异常！",
                f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                f"{self.cur_user_item.name}的自动代理出现异常",
                3,
            )
        if not will_retry:
            self.cur_user_item.status = "异常"

    async def cancel_run(self) -> None:
        """标记手动停止并立即恢复项目配置目录。"""

        self.manual_stop = True
        if self.config_session is not None:
            await self.config_session.restore()

    def should_kill_game(self) -> bool:
        return self._should_kill_game()

    async def kill_game(self) -> None:
        await self._kill_game_process()

    async def on_run_update(self, update: RunControllerUpdate) -> None:
        """把控制器统一更新映射到 MAS 日志、报告和插件事件。"""

        if update.kind == "dispatch":
            await self._push_dispatch_log(update.message)
            return
        if update.kind == "stream":
            await self._push_dispatch_log(
                f"[{update.source}] {update.message}"
            )
            if self.report_handler is not None:
                await self.report_handler.capture(self, update.message)
            return
        if update.kind == "legacy":
            self.legacy_log_lines = list(update.lines)
            self._refresh_current_log_content()
            self.script_info.log = self._build_dispatch_log_snapshot()
            if self.report_handler is not None:
                await self.report_handler.capture(
                    self,
                    "".join(update.lines),
                )
            return
        if update.kind == "event" and update.event is not None:
            self.event_failures = list(update.failures)
            await self._emit_ok_script_event(
                update.event,
                status=(
                    update.observation.status
                    if update.observation is not None
                    else None
                ),
            )
            return
        if update.kind == "observation" and update.observation is not None:
            await self._apply_run_observation(update.observation)

    async def _apply_run_observation(
        self,
        observation: RunObservation,
    ) -> None:
        if self.cur_user_log is not None:
            self.cur_user_log.status = observation.status
        self.cur_user_item.status = observation.user_status
        self.script_info.log = observation.status
        if observation.successful:
            self.run_book = True
        await self._push_dispatch_log(
            f"已通过 {observation.source} 确认任务"
            f"{'完成' if observation.successful else '异常'}："
            f"{observation.status}"
        )

    async def _run_script_after_task(self) -> None:
        if not self.cur_user_config.get("Info", "IfScriptAfterTask"):
            return
        await execute_script_task(
            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
            "脚本后任务",
        )

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

    def _should_launch_game_before_task(self) -> bool:
        return bool(self.script_config.get("Game", "Enabled")) and bool(
            self.script_config.get("Game", "LaunchBeforeTask")
        )

    async def _emit_ok_script_event(
        self,
        event: OkScriptRunEvent,
        *,
        status: str | None = None,
    ) -> None:
        """向插件总线广播 ok-script 结构化明细事件。"""

        provider = self._require_provider()

        data = {
            "task_id": self.task_info.task_id,
            "mode": self.task_info.mode,
            "queue_id": self.task_info.queue_id,
            "script_id": self.script_info.script_id,
            "script_name": self.script_info.name,
            "user_id": self.cur_user_item.user_id,
            "user_name": self.cur_user_item.name,
            "resource_name": provider.resource_name,
            "display_name": provider.display_name,
            "task_index": self.task_index,
            "protocol_version": OK_SCRIPT_EVENT_PROTOCOL_VERSION,
            "ok_script_event": event.event,
            "message": event.message,
            "task": event.task,
            "success": event.success,
            "terminal": event.is_terminal,
            "status": status or (
                self.cur_user_log.status
                if self.cur_user_log is not None
                else None
            ),
            "failures": [
                {"task": failure.task, "message": failure.message}
                for failure in self.event_failures
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

    async def final_task(self) -> None:
        try:
            await self._finalize_task()
        finally:
            if self.report_handler is not None:
                with suppress(Exception):
                    await self.report_handler.stop(self)
            self._release_user_config_lock()
            self._release_script_root_lock()

    async def _finalize_task(self) -> None:
        provider = self.provider
        display_name = self._provider_display_name()
        if self.run_controller is not None:
            await self.run_controller.close()
        if self._should_kill_game():
            await self._kill_game_process()
        try:
            if self.config_session is not None:
                await self.config_session.restore()
        except Exception as restore_error:
            logger.exception(
                f"恢复 {display_name} 脚本本地配置失败: {restore_error}"
            )

        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )

            if provider is not None and log_item.status == provider.running_status:
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        if not self.attempt_started or self.run_result_persisted:
            return

        display_name = self._provider_display_name()
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
            self.run_result_persisted = True
            logger.success(
                f"用户 {self.cur_user_uid} 的 {display_name} "
                "自动代理任务已完成"
            )
            return

        await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
        if self.cur_user_item.status not in ("完成", "跳过"):
            self.cur_user_item.status = "异常"
        self.run_result_persisted = True

    async def on_crash(self, e: Exception) -> None:
        display_name = self._provider_display_name()
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"{display_name} 运行异常: {e}"
        if self.report_handler is not None:
            with suppress(Exception):
                await self.report_handler.stop(self)
        logger.exception(f"{display_name} 自动代理任务出现异常: {e}")
        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"{display_name} 自动代理任务出现异常: {e}"},
            )
        except Exception as send_error:
            logger.exception(f"发送 {display_name} 异常通知失败: {send_error}")
        try:
            if self.run_controller is not None:
                await self.run_controller.close()
        except Exception as kill_error:
            logger.exception(f"清理 {display_name} 进程失败: {kill_error}")
        try:
            if self._should_kill_game():
                await self._kill_game_process()
        except Exception as game_error:
            logger.exception(f"清理 {display_name} 游戏进程失败: {game_error}")
        try:
            if self.config_session is not None and self.config_session.injected:
                await self.config_session.write_back()
        except Exception as config_error:
            logger.exception(f"崩溃后写回 {display_name} 配置失败: {config_error}")
        try:
            if self.config_session is not None:
                await self.config_session.restore()
        except Exception as restore_error:
            logger.exception(
                f"崩溃后恢复 {display_name} 脚本本地配置失败: {restore_error}"
            )
        try:
            await self._persist_user_run_result()
        except Exception as persist_error:
            logger.exception(
                f"写回 {display_name} 用户运行结果失败: {persist_error}"
            )

    def _provider_display_name(self) -> str:
        if self.provider is None:
            return "ok-script"
        return self.provider.display_name

    def _require_provider(self) -> OkScriptProvider:
        if self.provider is None:
            raise RuntimeError("ok-script provider 尚未准备完成")
        return self.provider

    def _require_config_session(self) -> OkScriptConfigSession:
        if self.config_session is None:
            raise RuntimeError("ok-script ConfigSession 尚未准备完成")
        return self.config_session

    def _should_kill_game(self) -> bool:
        if self.manual_stop and not self.script_config.get(
            "Game", "KillGameOnManualStop"
        ):
            return False
        return self.game_path.is_file()

    def _release_script_root_lock(self) -> None:
        if (
            self.script_root_lock_acquired
            and self.script_root_lock is not None
            and self.script_root_lock.locked()
        ):
            self.script_root_lock.release()
        self.script_root_lock_acquired = False

    async def _acquire_user_config_lock(self) -> None:
        if self.mas_config_dir == Path():
            raise RuntimeError("ok-script 用户配置目录未初始化")
        self.user_config_lock = get_ok_script_config_lock(self.mas_config_dir)
        if self.user_config_lock_acquired:
            return
        self.script_info.log = "正在等待当前用户配置编辑完成"
        await self.user_config_lock.acquire()
        self.user_config_lock_acquired = True

    def _release_user_config_lock(self) -> None:
        if (
            self.user_config_lock_acquired
            and self.user_config_lock is not None
            and self.user_config_lock.locked()
        ):
            self.user_config_lock.release()
        self.user_config_lock_acquired = False

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
